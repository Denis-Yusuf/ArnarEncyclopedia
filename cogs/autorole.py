import os

from discord.ext import commands


class AutoroleCOG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._role = os.getenv("AUTOROLE_ID")

    @commands.Cog.listener(name = "on_member_join")
    async def on_member_join(self, member) -> None:
        """
        I wonder what this does?
        :param member: existance
        :return: nothing fuck you
        """
        role = member.guild.get_role(int(self._role))
        await member.add_roles(role)
