import asyncio
import os
import sys
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
from cogs.blacklist import BlacklistCog
from cogs.autorole import AutoroleCOG
from services.spotify import SpotifyService
from services.youtube import YouTubeService


class SaltBot(commands.Bot):
    """The bot. Wires up services and cogs on startup."""

    modlog_channel_id: int | None = None

    async def report_error(self, where: str, error: BaseException | str) -> None:
        """
        Prints an error to the log and also posts it in the modlog channel,
        so problems are visible from Discord without reading the container log.
        Never raises: a failure to report must not cause a second error.

        :param where: Short description of what was running, e.g. 'birthday check'.
        :param error: The exception that was raised, or a plain message.
        """
        if isinstance(error, BaseException):
            traceback.print_exception(type(error), error, error.__traceback__)
        else:
            print(f"[{where}] {error}")

        channel = self.get_channel(self.modlog_channel_id) if self.modlog_channel_id else None
        if channel is None:
            return
        try:
            # 4096 is Discord's limit for an embed description; leave room for the code fence.
            embed = discord.Embed(
                title = f"❌ Error in {where}", description = f"```{str(error)[:4000]}```", color = discord.Color.red()
            )
            await channel.send(embed = embed)
        except Exception as send_error:  # pylint: disable=broad-exception-caught
            # Broad on purpose: a network failure or a channel that can't take messages must not escape.
            print(f"Could not post the error to the modlog channel: {send_error}")

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        """
        Handles errors raised inside event listeners (on_message, on_member_join, ...).

        :param event_method: Name of the event whose listener failed.
        """
        await self.report_error(f"event {event_method}", sys.exception() or "unknown error")

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
        music_channel_id = int(os.getenv("MUSIC_CHANNEL_ID") or 0) or None
        modlog_channel_id = int(os.getenv("MODLOG_CHANNEL_ID") or 0) or None
        self.modlog_channel_id = modlog_channel_id
        await self.add_cog(MusicCog(self, youtube, spotify, music_channel_id))
        await self.add_cog(Eggcog(self))
        await self.add_cog(PresenceCog(self))
        await self.add_cog(BirthdaySchedulerCog(self))
        await self.add_cog(ClankerCog(self))
        await self.add_cog(GambaCog(self))
        await self.add_cog(BlacklistCog(self, modlog_channel_id))
        await self.add_cog(AutoroleCOG(self))
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
        elif isinstance(error, commands.BadArgument):
            # Input the user got wrong (a bad date, an unknown member): the message says what to change.
            description = str(error)
        else:
            await self.report_error(f"command {ctx.command}", error)
            description = f"An unexpected error ocurred.\n```{error}```"

        embed = discord.Embed(title = "❌ Error", description = description, color = discord.Color.red())
        await ctx.send(embed = embed, ephemeral = True)

async def main() -> None:
    discord.utils.setup_logging()
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    async with SaltBot(command_prefix = '/', intents = intents) as bot:
        await bot.start(os.getenv("TOKEN"))


exit_code = 0
try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
except Exception:  # pylint: disable=broad-exception-caught
    # os._exit skips Python's own crash report, so print it here or the error is lost.
    traceback.print_exc()
    exit_code = 1
finally:
    os._exit(exit_code)
