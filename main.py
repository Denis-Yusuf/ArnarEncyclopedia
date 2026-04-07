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
        Instantiates shared services, registers all cogs, and syncs slash commands.
        Runs once after login before the bot starts processing events.
        """
        youtube = YouTubeService()
        spotify = SpotifyService(
            client_id = os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        await self.add_cog(MusicCog(self, youtube, spotify))
        await self.add_cog(Eggcog(self))
        await self.add_cog(PresenceCog(self))
        await self.tree.sync()  # registers slash commands globally


intents = discord.Intents.default()
intents.message_content = True

bot = SaltBot(command_prefix = '/', intents = intents)
bot.run(os.getenv("TOKEN"))
