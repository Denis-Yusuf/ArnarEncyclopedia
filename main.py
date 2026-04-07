import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.music import MusicCog
from cogs.egg import Eggcog
from cogs.presence import PresenceCog
from services.spotify import SpotifyService
from services.youtube import YouTubeService

load_dotenv()


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
finally:
    os._exit(0)
