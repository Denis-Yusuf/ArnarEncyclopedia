import json
import os
import random


from discord.ext import commands


def _load_encyclopedia(path:str = "Clanker_Encyclopedia.json") -> dict:
    """
    Loads the encyclopedia JSON and returns the parsed data?

    :param path: path to the encyclopedia JSON file
    :return: Dict with quote list
    """
    with open(path, encoding= "utf-8") as file:
        return json.load(file)

class Clankercogg(commands.Cog):
    def __init__(self, bot : commands.Bot):
        """
        :param bot: Running Discord bot instance
        """
        self.bot = bot
        data = _load_encyclopedia()
        self.default_quotes : list[str] = data["Default"]
        self.ma_channel_id = int(os.getenv("MUDAI_CHANNEL_ID"))


    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listens for messages sent by bots and sends a message to them

        :param message: discord.Message
        """
        if message.author == self.bot.user:
            return
        if message.channel.id == self.ma_channel_id:
            return
        if message.author.bot:
            quote = random.choice(self.default_quotes)
            await message.channel.send(quote)
