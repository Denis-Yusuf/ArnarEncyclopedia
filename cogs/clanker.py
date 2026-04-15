import json
import os
import random
import time
from collections import deque

from discord.ext import commands


def _load_encyclopedia(path:str = "Clanker_Encyclopedia.json") -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)

class ClankerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        data = _load_encyclopedia()
        self.default_quotes: list[str] = data["Default"]
        self.ma_channel_id = int(os.getenv("MUDAI_CHANNEL_ID"))

        self.window_seconds = 10      # interval to track
        self.max_messages = 5         # messages before chance hits 0
        self.recent_messages = deque() # timestamps of recent triggers

    def _response_chance(self) -> float:
        now = time.monotonic()
        # drop timestamps outside the window
        while self.recent_messages and self.recent_messages[0] < now - self.window_seconds:
            self.recent_messages.popleft()

        count = len(self.recent_messages)
        # linear drop: 0 messages = 100%, max_messages = 0%
        return max(0.0, 1.0 - (count / self.max_messages))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        if message.channel.id == self.ma_channel_id:
            return
        if message.author.bot:
            chance = self._response_chance()
            if random.random() < chance:
                self.recent_messages.append(time.monotonic())
                quote = random.choice(self.default_quotes)
                await message.channel.send(quote)