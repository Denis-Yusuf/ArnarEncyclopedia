import random

import discord
from discord.ext import commands


class Eggcog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.quotes: list[str] = [
            line.strip()
            for line in open("././Arnar_Encyclopedia.txt", 'r', encoding = "utf-8").readlines()
            if line.strip()
        ]

    MA_CHANNEL_ID = 1463216947910021385

    @commands.hybrid_command(name = 'egg', description = 'Mimic Arnar.')
    async def egg(self, ctx: commands.Context) -> None:
        """
        The classic, good ol' reliable
        """
        pick = random.choice(self.quotes)
        is_url = pick.startswith("http://") or pick.startswith("https://")
        if pick == "$ma":
            channel = self.bot.get_channel(self.MA_CHANNEL_ID)
            target = channel if channel is not None else ctx
        else:
            target = ctx
        await target.send(
            pick,
            allowed_mentions = discord.AllowedMentions(users = True),
            suppress_embeds = not is_url
        )
