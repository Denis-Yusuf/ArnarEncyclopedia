import discord
import os
import json
import datetime as dt

from pathlib import Path
from discord.ext import commands, tasks
from discord import app_commands

DEFAULT_MESSAGE = "Happy Birthday %n!"
DEFAULT_ROLE = "everyone"
CHECKING_TIME = dt.time(hour=0, minute=0)


class DateTransformer(app_commands.Transformer):
    """Transforms a string in DD-MM format into a datetime object."""

    async def transform(self, interaction: discord.Interaction, value: str) -> dt.datetime:
        return dt.datetime.strptime(value, "%d-%m")


def _load_birthdays(path: str = "birthdays.json") -> dict:
    """
    Load birthdays from a JSON file.
    If the file doesn't exist, it creates an empty one.

    :param path: Path to the JSON file. Defaults to 'birthdays.json'.
    :return: A dictionary of birthdays keyed by user ID.
    """
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
    """
    Save the birthdays dictionary to a JSON file.

    :param data: The birthdays dictionary to save.
    :param path: Path to the JSON file. Defaults to 'birthdays.json'.
    """
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def _replace_placeholders(message: str, uid: str) -> str:
    """
    Replace placeholders in a birthday message with their actual values.

    Supported placeholders:
        %n — Replaced with a mention of the birthday user.
        %r — Replaced with a mention of the default role.

    :param message: The message string containing placeholders.
    :param uid: The Discord user ID of the birthday person.
    :return: The message with all placeholders resolved.
    """
    message = str.replace(message, "%n", f"<@{uid}>")
    message = str.replace(message, "%r", f"<@{DEFAULT_ROLE}>")
    return message


class BirthdaySchedulerCog(commands.Cog):
    """Cog for managing and announcing birthdays."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.birthdays: dict = _load_birthdays()
        self.birthday_channel = int(os.getenv("BIRTHDAY_CHANNEL_ID"))

    def cog_load(self) -> None:
        """Start the birthday check loop when the cog is loaded."""
        self.check_birthdays.start()

    def cog_unload(self) -> None:
        """Stop the birthday check loop when the cog is unloaded."""
        self.check_birthdays.stop()

    #@commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-default-message", description="Set the default birthday message")
    async def birthday_set_default_message(self, ctx: commands.Context, *, message: str = None) -> None:
        """
        Set the default birthday message used when no custom message is specified.
        Resets to 'Happy Birthday %n!' if no message is provided.

        :param ctx: The invocation context.
        :param message: The new default message. Supports %n (user mention) and %r (role mention).
        """
        global DEFAULT_MESSAGE
        DEFAULT_MESSAGE = message or "Happy Birthday %n!"

        embed = discord.Embed(
            title="Default Birthday Message Updated",
            description=f"The default birthday message has been set to:\n\n**{DEFAULT_MESSAGE}**",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Use %n as a placeholder for the user's name.\nUse %r to mention the default role.")
        await ctx.send(embed=embed)

    #@commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-default-role", description="Set the default mention role")
    async def birthday_set_default_role(self, ctx: commands.Context, *, role: str = None) -> None:
        """
        Set the default role to be mentioned in birthday messages via %r.
        Resets to 'everyone' if no role is provided.

        :param ctx: The invocation context.
        :param role: The role name or ID to use as the default mention.
        """
        global DEFAULT_ROLE
        DEFAULT_ROLE = role or "everyone"

        embed = discord.Embed(
            title="Default Role Updated",
            description=f"The default birthday mention role has been set to:\n\n**{DEFAULT_ROLE}**",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    #@commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-set", description="Add or update a birthday")
    async def birthday_set(self, ctx: commands.Context, date: app_commands.Transform[dt.datetime, DateTransformer], user: discord.Member = None, *, message: str = None) -> None:
        """
        Add or update a user's birthday. Defaults to the command author if no user is given.
        If a custom message is not provided on update, the existing message is preserved.

        :param ctx: The invocation context.
        :param date: The birthday date in DD-MM format.
        :param user: The member whose birthday to set. Defaults to the author.
        :param message: Optional custom birthday message. Use DEFAULT to fall back to the global message.
        """
        user = user or ctx.author
        uid = str(user.id)

        if self.birthdays.get(uid) is None:
            self.birthdays[uid] = {
                "date": date.strftime("%d-%m"),
                "message": message or "DEFAULT",
            }
            _save_birthdays(self.birthdays)

            embed = discord.Embed(
                title=f"🎂 {user.display_name}'s birthday saved",
                color=discord.Color.greyple()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Date", value=date.strftime("%d-%m"), inline=True)
            embed.add_field(name="Message", value=f"_{DEFAULT_MESSAGE if 'DEFAULT' else message}_", inline=False)
            embed.set_footer(text="Use %n as a placeholder for the user's name.\nUse %r to mention the default role.\nDEFAULT will use the default set message.")
            await ctx.send(embed=embed)
        else:
            existing_message = self.birthdays.get(uid, {}).get("message")
            self.birthdays[uid] = {
                "date": date.strftime("%d-%m"),
                "message": message or existing_message,
            }
            _save_birthdays(self.birthdays)

            embed = discord.Embed(
                title=f"🎂 {user.display_name}'s birthday updated",
                color=discord.Color.blurple()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Date", value=date.strftime("%d-%m"), inline=True)
            embed.add_field(name="Message", value=f"_{message or existing_message}_", inline=False)
            embed.set_footer(text="Use %n as a placeholder for the user's name.\nUse %r to mention the default role.\nDEFAULT will use the default set message.")
            await ctx.send(embed=embed)

    #@commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-remove", description="Remove a birthday")
    async def birthday_remove(self, ctx: commands.Context, user: discord.Member) -> None:
        """
        Remove a user's birthday from the saved list.

        :param ctx: The invocation context.
        :param user: The member whose birthday to remove.
        """
        user = user or ctx.author
        uid = str(user.id)

        if uid in self.birthdays:
            del self.birthdays[uid]
            _save_birthdays(self.birthdays)

            embed = discord.Embed(
                title=f"🗑️ {user.display_name}'s birthday removed",
                color=discord.Color.greyple()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title=f"❌ Not found",
                description=f"No birthday found for **{user.display_name}**.",
                color=discord.Color.orange()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="birthday-list", description="Show a list of all saved birthdays")
    async def birthday_list(self, ctx: commands.Context) -> None:
        """
        Display all saved birthdays in an embed, sorted with their custom or default message.
        Shows a notice if no birthdays have been saved yet.

        :param ctx: The invocation context.
        """
        if not self.birthdays:
            embed = discord.Embed(
                description="No birthdays saved.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="🎂 Birthday calendar",
            color=discord.Color.blurple()
        )
        for uid, data in self.birthdays.items():
            user = await ctx.guild.fetch_member(int(uid))
            name = user.display_name if user else f"Unknown ({uid})"
            date = data["date"]
            message = data["message"] if data["message"] != "DEFAULT" else DEFAULT_MESSAGE
            embed.add_field(
                name=f"{name} — {date}",
                value=f"_{message}_",
                inline=False
            )

        embed.set_footer(text=f"{len(self.birthdays)} birthday(s) saved")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="birthday-get", description="Show the birthday of a specific user")
    async def birthday_get(self, ctx: commands.Context, user: discord.Member = None) -> None:
        """
        Look up and display the birthday details for a specific user.
        Defaults to the command author if no user is specified.

        :param ctx: The invocation context.
        :param user: The member whose birthday to look up. Defaults to the author.
        """
        user = user or ctx.author
        uid = str(user.id)

        if uid not in self.birthdays:
            embed = discord.Embed(
                description=f"No birthday found for {user.display_name}.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        birthday = self.birthdays[uid]
        date = birthday["date"]
        message = birthday["message"] if birthday["message"] != "DEFAULT" else DEFAULT_MESSAGE

        embed = discord.Embed(
            title=f"🎂 {user.display_name}'s birthday",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Date", value=date, inline=True)
        embed.add_field(name="Message", value=f"_{message}_", inline=False)
        await ctx.send(embed=embed)

    @tasks.loop(time = CHECKING_TIME)
    async def check_birthdays(self):
        """
        Periodic task that checks for birthdays matching today's date.
        Sends a birthday message in the configured channel for each match.
        Runs at the time of day specified in CHECKING_TIME. Errors per user are caught and logged individually
        to prevent one failure from stopping the rest.
        """
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
        """Wait until the bot is fully ready before starting the birthday check loop."""
        await self.bot.wait_until_ready()