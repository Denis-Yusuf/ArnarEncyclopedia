import asyncio
import os
import traceback

import discord
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv() # pylint: disable=wrong-import-position

from cogs.birthday import BirthdaySchedulerCog
from cogs.music import MusicCog
from cogs.egg import Eggcog
from cogs.clanker import ClankerCog
from cogs.presence import PresenceCog
from cogs.gamba import GambaCog
from services.spotify import SpotifyService
from services.youtube import YouTubeService


class SaltBot(commands.Bot):
    """The bot. Wires up services and cogs on startup."""

    async def setup_hook(self) -> None:
        """
        Instantiates shared services and registers all cogs.
        Runs once after login before the bot starts processing events.
        Command syncing happens in on_ready once guild list is available.
        """
        youtube = YouTubeService()
        spotify = SpotifyService(
            client_id = os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        await self.add_cog(MusicCog(self, youtube, spotify))
        await self.add_cog(Eggcog(self))
        await self.add_cog(PresenceCog(self))
        await self.add_cog(BirthdaySchedulerCog(self))
        await self.add_cog(ClankerCog(self))
        await self.add_cog(GambaCog(self))
        # Remove any previously registered global commands from Discord's API.
        # We save and restore the in-memory commands so copy_global_to still works in on_ready.
        global_commands = self.tree.get_commands()
        self.tree.clear_commands(guild = None)
        await self.tree.sync()
        for command in global_commands:
            self.tree.add_command(command)

    async def on_ready(self) -> None:
        """Copies global commands to each guild and syncs, so they appear instantly."""
        for guild in self.guilds:
            self.tree.copy_global_to(guild = guild)
            await self.tree.sync(guild = guild)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Syncs slash commands when the bot is added to a new server."""
        self.tree.copy_global_to(guild = guild)
        await self.tree.sync(guild = guild)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """
        Handles errors raised by prefix and hybrid commands.
        Unknown commands are silently ignored; all other errors are sent as an ephemeral embed.

        :param ctx: The invocation context of the failed command.
        :param error: The error that was raised.
        """
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            description = f"Missing argument: `{error.param.name}`"
        elif isinstance(error, commands.MissingPermissions):
            description = "You don't have permissions to use that command."
        else:
            traceback.print_exception(type(error), error, error.__traceback__)
            description = f"An unexpected error ocurred.\n```{error}```"

        embed = discord.Embed(title="❌ Error", description=description, color=discord.Color.red())
        await ctx.send(embed=embed, ephemeral=True)

    async def on_app_command_error(
            self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ) -> None:
        """
        Handles errors raised by slash commands.
        Uses followup if the interaction was already acknowledged, otherwise responds directly.

        :param interaction: The interaction that triggered the failed command.
        :param error: The error that was raised.
        """
        if isinstance(error, discord.app_commands.MissingPermissions):
            description = "You don't have permissions to use that command."
        else:
            traceback.print_exception(type(error), error, error.__traceback__)
            description = f"An unexpected error ocurred.\n```{error}```"

        embed = discord.Embed(title="❌ Error", description=description, color=discord.Color.red())

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
async def main() -> None:
    discord.utils.setup_logging()
    intents = discord.Intents.default()
    intents.message_content = True

    async with SaltBot(command_prefix = '/', intents = intents) as bot:
        await bot.start(os.getenv("TOKEN"))


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
# except Exception:
#     traceback.print_exc()
finally:
    os._exit(0)
