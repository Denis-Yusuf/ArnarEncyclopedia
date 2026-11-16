import os

from discord.ext import commands


class AutoroleCOG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._role = int(os.getenv("AUTOROLE_ID") or 0) or None

    @commands.Cog.listener(name = "on_member_join")
    async def on_member_join(self, member) -> None:
        """
        I wonder what this does?
        :param member: existance
        :return: nothing fuck you
        """
        # Nothing to hand out when AUTOROLE_ID is unset or the role no longer exists.
        role = member.guild.get_role(self._role) if self._role else None
        if role is not None:
            await member.add_roles(role)
