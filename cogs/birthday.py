import discord
import os
import json
import datetime
from discord.ext import commands, tasks
from datetime import datetime, time

DEFAULT_MESSAGE = "{mention} kys"
CHECKING_TIME = time(hour=0, minute=0)

class DateConverter(commands.Converter[datetime.datetime]):
    async def convert(self, ctx: commands.Context, value: str) -> datetime.datetime:
            try:
                return datetime.datetime.strptime(value, "%d-%m")
            except ValueError:
                raise commands.BadArgument("Ongeldig formaat nigga. Gebruik `DD-MM`.")

def _load_birthdays(path: str = "birthdays.json"):
    try:
        with open(path, "r", encoding="utf-8") as birthdays:
            return json.load(birthdays)
    except FileNotFoundError:
        with open(path, "w", encoding="utf-8") as birthdays:
            json.dump({}, birthdays, indent=4)
            return {}


def _save_birthdays(data: dict, path: str = "birthdays.json") -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


class BirthdaySchedulerCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.birthdays: dict = _load_birthdays()
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.stop()


@commands.hybrid_command(name="birthday", description="Add or update a birthday")
async def birthday_add(self, ctx: commands.Context, date: DateConverter, user: discord.Member = None, *, message: str = None ) -> None:
    user = user or ctx.author
    uid = user.id

    if self.birthdays.get(uid) is None:
        self.birthdays[uid] = {
            "date": date,
            "message": message or DEFAULT_MESSAGE,
        }
        _save_birthdays(self.birthdays)
        await ctx.send(f"saved {user.name}'s birthday", ephemeral=True)
    else:
        existing_message = self.birthdays(uid, {}).get("message")
        self.birthdays[uid] = {
            "date": date,
            "message": message or existing_message,
        }
        _save_birthdays(self.birthdays)
        await ctx.send(f"updated {user.name}'s birthday", ephemeral=True)

@commands.hybrid_command(name="birthday remove", description="remove a birthday")
async def birthday_remove( self, ctx: commands.Context, user: discord.Member = None)-> None:
    user = user or ctx.author
    uid = user.id

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
    for uid, data in self.birthdays:
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
    uid = user.id

    if uid in self.birthdays:
        birthday = self.birthdays[uid]
        date = birthday["date"]
        message = birthday["message"]
        await ctx.send(f"{user.name} - {date} - {message}")
    else:
        await ctx.send("No birthday found")


@tasks.loop(time=CHECKING_TIME)
async def check_birthdays(self):
    today = datetime.datetime.now().strftime("%d-%m")

    channel = self.bot.get_channel(os.getenv("BIRTHDAY_CHANNEL_ID"))
    if channel is None:
        raise ValueError("channel not found nigga")

    for user_id, data in self.birthdays.items():
        date: data["date"]

        if date == today:
            member = channel.guild.get_member(int(user_id))
            if member is None:
                continue

            message = data["message"]
            if message is None:
                message = DEFAULT_MESSAGE
            await channel.send(f"{message}")

@check_birthdays.before_loop
async def before_check(self):
    await self.bot.wait_until_ready()
