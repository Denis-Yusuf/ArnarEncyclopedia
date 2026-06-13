from discord.ext import commands
from discord import Embed
import regex as re


class  BlacklistCog(commands.Cog):
    def __init__(self, bot, modlog_channel_id: int):
        self.bot = bot
        self._modlog_channel_id = modlog_channel_id

    @commands.Cog.listener(name = "on_message")
    async def on_message(self, message) -> None:
        """
        Remove certain filth from messages
        :param message: a message dipshit
        :return: Nothing
        """
        if message.author == self.bot.user:
            return
        if bool(re.match("[Ll]\\s*[uU]\\s*[Cc]\\s*[yY]", message.content)):
            channel = self.bot.get_channel(self._modlog_channel_id)
            await message.delete()
            embed = Embed(
                title="Message Deleted",
                description=f"**Offender**: <@{message.author.id}>\n**Reason**: Think about it for a bit, dawg.\n **Responsible Moderator**: The Goat Himself, Me",
            )
            await channel.send(embed = embed)

