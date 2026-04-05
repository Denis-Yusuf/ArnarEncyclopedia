import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.music import MusicCog
from services.spotify import SpotifyService
from services.youtube import YouTubeService

load_dotenv()


class SaltBot(commands.Bot):
    """Main bot class. Handles cog and service initialization on startup."""

    async def setup_hook(self) -> None:
        """
        Called once after login, before connecting to the gateway.
        Instantiates services and loads cogs.
        """
        youtube = YouTubeService()
        spotify = SpotifyService(
            client_id = os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
        await self.add_cog(MusicCog(self, youtube, spotify))


intents = discord.Intents.default()
intents.message_content = True

bot = SaltBot(command_prefix = '/', intents = intents)
bot.run(os.getenv("TOKEN"))
