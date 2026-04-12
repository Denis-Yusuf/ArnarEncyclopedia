import discord
import os
import json
import datetime

from pathlib import Path
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time

DEFAULT_MESSAGE = "Happy Birthday %n!"
CHECKING_TIME = time(hour=0, minute=0)

class DateTransformer(app_commands.Transformer):
    async def transform(self, interaction: discord.Interaction, value: str) -> datetime:
            try:
                return datetime.strptime(value, "%d-%m")
            except ValueError:
                raise commands.BadArgument("Ongeldig formaat nigga. Gebruik `DD-MM`.")

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

def replace_placeholders(message: str, uid: str) -> str:
    str.replace(message, "%n", f"<@{uid}>")
    str.replace(message, "%e", f"<@everyone>")
    return message

class BirthdaySchedulerCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.birthdays: dict = _load_birthdays()
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.stop()

    @commands.hybrid_command(name="birthday set message", description="change the default message")
    async def birthday_set_default_message(self, ctx: commands.Context, message: str = None) -> None:
        if message is not None:
            DEFAULT_MESSAGE = message
        else:
            DEFAULT_MESSAGE= "Happy Birthday %n!"


    @commands.hybrid_command(name="birthday", description="Add or update a birthday")
    async def birthday(self, ctx: commands.Context,date: app_commands.Transform[datetime, DateTransformer], user: discord.Member = None, message: str = None ) -> None:
        user = user or ctx.author
        uid = str(user.id)

        if self.birthdays.get(uid) is None:
            self.birthdays[uid] = {
                "date": date.strftime("%d-%m"),
                "message":  message or DEFAULT_MESSAGE,
            }
            _save_birthdays(self.birthdays)
            await ctx.send(f"saved {user.name}'s birthday", ephemeral=True)
        else:
            existing_message = self.birthdays.get(uid, {}).get("message")
            self.birthdays[uid] = {
                "date": date.strftime("%d-%m"),
                "message": message or existing_message,
            }
            _save_birthdays(self.birthdays)
            await ctx.send(f"updated {user.name}'s birthday", ephemeral=True)

    @commands.hybrid_command(name="birthday remove", description="remove a birthday")
    async def birthday_remove( self, ctx: commands.Context, user: discord.Member = None)-> None:
        user = user or ctx.author
        uid = str(user.id)

        if uid in self.birthdays:
            del self.birthdays[uid]
            await ctx.send(f"removed {user}'s birthday", ephemeral=True)
        else:
            raise commands.BadArgument(f"User {uid} not found.")

    @commands.hybrid_command(name="birthday list", description="shows a list of all birthdays" )
    async def birthday_list(self, ctx: commands.Context) -> None:
        if not self.birthdays:
            await ctx.send(f"no birthdays saved")

        cells = []
        for uid, data in self.birthdays.items():
            user = ctx.guild.get_member(int(uid))
            if user is None:
                user = uid

            date = data["date"]
            message = data["message"]
            cells.append(f"{user.name}: {date} - {message}")

        await ctx.send("**Birthdays:**\n" + "\n".join(cells))

    @commands.hybrid_command(name="birthday get", description="shows birthday of a specific user")
    async def birthday_get(self, ctx: commands.Context, user: discord.Member = None) -> None:
        user = user or ctx.author
        uid = str(user.id)

        if uid in self.birthdays:
            birthday = self.birthdays[uid]
            date = birthday["date"]
            message = birthday["message"]
            await ctx.send(f"{user.name} - {date} - {message}")
        else:
            await ctx.send("No birthday found")


    @tasks.loop(time=CHECKING_TIME)
    async def check_birthdays(self):
        today = datetime.now().strftime("%d-%m")

        channel = self.bot.get_channel(int(os.getenv("BIRTHDAY_CHANNEL_ID")))
        if channel is None:
            raise ValueError("channel not found nigga")

        for uid, data in self.birthdays.items():
            date = data["date"]

            if date == today:
                member = channel.guild.get_member(int(uid))
                if member is None:
                    continue

                message = data["message"]
                message = replace_placeholders(message, uid)
                await channel.send(f"{message}")

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
