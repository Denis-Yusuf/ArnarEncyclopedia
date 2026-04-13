import discord
import os
import json
import datetime as dt

from pathlib import Path
from discord.ext import commands, tasks
from discord import app_commands

DEFAULT_MESSAGE = "Happy Birthday %n!"
CHECKING_TIME = dt.time(hour = 0, minute = 0)

class DateTransformer(app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction, value: str) -> dt.datetime:
        return dt.datetime.strptime(value, "%d-%m")

def _load_birthdays(path: str = "birthdays.json"):
    file = Path(path)
    if file.exists():
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass

    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)
    return {}

def _save_birthdays(data: dict, path: str = "birthdays.json") -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def _replace_placeholders(message: str, uid: str) -> str:
    message = str.replace(message, "%n", f"<@{uid}>")
    message = str.replace(message, "%e", f"@everyone")
    return message

class BirthdaySchedulerCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.birthdays: dict = _load_birthdays()
        self.birthday_channel = int(os.getenv("BIRTHDAY_CHANNEL_ID"))

    def cog_load(self) -> None:
        self.check_birthdays.start()

    def cog_unload(self) -> None:
        self.check_birthdays.stop()

    @commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-default-message", description="set the default message")
    async def birthday_set_default_message(self, ctx: commands.Context, *, message: str = None) -> None:
        global DEFAULT_MESSAGE
        if message is None:
            DEFAULT_MESSAGE = "Happy Birthday %n!"
        else:
            DEFAULT_MESSAGE = message
        await ctx.send(f"Default message set to: {DEFAULT_MESSAGE}")

    @commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-set", description="Add or update a birthday")
    async def birthday_set(self, ctx: commands.Context,date: app_commands.Transform[dt.datetime, DateTransformer], user: discord.Member = None, *, message: str = None ) -> None:
        user = user or ctx.author
        uid = str(user.id)

        if self.birthdays.get(uid) is None:
            self.birthdays[uid] = {
                "date": date.strftime("%d-%m"),
                "message":  message or "DEFAULT",
            }
            _save_birthdays(self.birthdays)
            await ctx.send(f"saved <@{uid}>'s birthday", ephemeral=True)
        else:
            existing_message = self.birthdays.get(uid, {}).get("message")
            self.birthdays[uid] = {
                "date": date.strftime("%d-%m"),
                "message": message or existing_message,
            }
            _save_birthdays(self.birthdays)
            await ctx.send(f"updated <@{uid}>'s birthday", ephemeral=True)

    @commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-remove", description="remove a birthday")
    async def birthday_remove( self, ctx: commands.Context, user: discord.Member)-> None:
        user = user or ctx.author
        uid = str(user.id)

        if uid in self.birthdays:
            del self.birthdays[uid]
            await ctx.send(f"removed <@{uid}>'s birthday", ephemeral=True)
        else:
            await ctx.send(f"**uid:{uid}** not found.")

    @commands.hybrid_command(name="birthday-list", description="shows a list of all birthdays" )
    async def birthday_list(self, ctx: commands.Context) -> None:
        if not self.birthdays:
            await ctx.send(f"**no birthdays saved**")
            return

        cells = []
        for uid, data in self.birthdays.items():
            user = await ctx.guild.fetch_member(int(uid))
            name = user.name if user else uid
            date = data["date"]
            message = data["message"]
            cells.append(f"**{name}**: {date} - {message}")

        await ctx.send("**Birthdays:**\n" + "\n".join(cells))

    @commands.hybrid_command(name="birthday-get", description="shows birthday of a specific user")
    async def birthday_get(self, ctx: commands.Context, user: discord.Member = None) -> None:
        user = user or ctx.author
        uid = str(user.id)

        if uid in self.birthdays:
            birthday = self.birthdays[uid]
            date = birthday["date"]
            message = birthday["message"]
            await ctx.send(f"**{user.name}**: {date} - {message}")
        else:
            await ctx.send("**No birthday found**")


    @tasks.loop(time=CHECKING_TIME)
    async def check_birthdays(self):
        today = dt.datetime.now().strftime("%d-%m")
        channel = self.bot.get_channel(self.birthday_channel)

        if channel is None:
            raise commands.ChannelNotFound("Channel not found.")

        for uid, data in self.birthdays.items():
            message = data["message"]

            if data["date"] != today:
                continue
            try:
                member = await channel.guild.fetch_member(int(uid))
                if member is None:
                    raise commands.UserNotFound("User not found.")

                if message == "DEFAULT":
                    message = DEFAULT_MESSAGE
                message = _replace_placeholders(message, uid)
                await channel.send(message)
            except Exception as e:
                print(f"Error thrown at birthday of uid:{uid}:\n {e}")

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
