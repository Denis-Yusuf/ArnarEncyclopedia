import calendar
import discord
import os
import datetime as dt

from zoneinfo import ZoneInfo
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import SessionLocal
from database.models import Birthday, Setting

# Built-in defaults; an admin's own choice is stored in the settings table so it survives a restart.
DEFAULT_MESSAGE = "Happy Birthday %n!"
# Kept as ready-to-send mention text: "@everyone", or "<@&role_id>" for a role.
DEFAULT_ROLE = "@everyone"
DEFAULT_MESSAGE_KEY = "birthday_default_message"
DEFAULT_ROLE_KEY = "birthday_default_role"
# Date (YYYY-MM-DD) of the last day whose birthdays were announced.
LAST_CHECK_KEY = "birthday_last_check"
# Without a zone the loop runs at 00:00 UTC, which is 01:00 or 02:00 for the server's members.
TIMEZONE = ZoneInfo("Europe/Brussels")
CHECKING_TIME = dt.time(hour=0, minute=0, tzinfo=TIMEZONE)
# Discord's limit for an embed description.
EMBED_DESCRIPTION_LIMIT = 4096


class DateTransformer(app_commands.Transformer):
    """Transforms a string in DD-MM format into a datetime object."""

    async def transform(self, interaction: discord.Interaction, value: str) -> dt.datetime:
        # Without a year strptime assumes 1900, which has no 29 February; 2000 is a leap year.
        return dt.datetime.strptime(f"{value}-2000", "%d-%m-%Y")


async def _get_setting(db: AsyncSession, key: str, default: str | None) -> str | None:
    """
    Read a stored setting.

    :param db: Async database session.
    :param key: Name of the setting.
    :param default: Returned when the setting was never stored.
    :return: The stored value, or the default.
    """
    setting = await db.get(Setting, key)
    return setting.value if setting else default


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    """
    Store a setting, replacing any earlier value. The caller commits.

    :param db: Async database session.
    :param key: Name of the setting.
    :param value: The value to store.
    """
    await db.merge(Setting(key=key, value=value))


def _replace_placeholders(message: str, uid: int, role: str) -> str:
    """
    Replace placeholders in a birthday message with their actual values.

    Supported placeholders:
        %n — Replaced with a mention of the birthday user.
        %r — Replaced with a mention of the default role.

    :param message: The message string containing placeholders.
    :param uid: The Discord user ID of the birthday person.
    :param role: Mention text of the default role.
    :return: The message with all placeholders resolved.
    """
    message = str.replace(message, "%n", f"<@{uid}>")
    message = str.replace(message, "%r", role)
    return message


def _require_admin_for_others(ctx: commands.Context, user: discord.abc.User) -> None:
    """
    Members may change their own birthday; changing someone else's needs Administrator.

    :param ctx: The invocation context.
    :param user: The member whose birthday is being changed.
    :raises commands.MissingPermissions: When a non-admin targets another member.
    """
    if user != ctx.author and not ctx.author.guild_permissions.administrator:
        raise commands.MissingPermissions(["administrator"])


class BirthdaySchedulerCog(commands.Cog):
    """Cog for managing and announcing birthdays."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.birthday_channel = int(os.getenv("BIRTHDAY_CHANNEL_ID") or 0) or None

    def cog_load(self) -> None:
        """Start the birthday check loop when the cog is loaded."""
        # Without a channel there is nowhere to announce; the commands keep working.
        if self.birthday_channel is None:
            print("BIRTHDAY_CHANNEL_ID is not set, birthdays will not be announced.")
            return
        self.check_birthdays.start()

    def cog_unload(self) -> None:
        """Stop the birthday check loop when the cog is unloaded."""
        self.check_birthdays.stop()

    @commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-default-message", description="Set the default birthday message")
    async def birthday_set_default_message(self, ctx: commands.Context, *, message: str = None) -> None:
        """
        Set the default birthday message used when no custom message is specified.
        Resets to 'Happy Birthday %n!' if no message is provided.

        :param ctx: The invocation context.
        :param message: The new default message. Supports %n (user mention) and %r (role mention).
        """
        message = message or DEFAULT_MESSAGE
        async with SessionLocal.begin() as db:
            await _set_setting(db, DEFAULT_MESSAGE_KEY, message)

        embed = discord.Embed(
            title="Default Birthday Message Updated",
            description=f"The default birthday message has been set to:\n\n**{message}**",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Use %n as a placeholder for the user's name.\nUse %r to mention the default role.")
        await ctx.send(embed=embed)

    @commands.has_guild_permissions(administrator=True)
    @commands.hybrid_command(name="birthday-default-role", description="Set the default mention role")
    async def birthday_set_default_role(self, ctx: commands.Context, *, role: discord.Role = None) -> None:
        """
        Set the default role to be mentioned in birthday messages via %r.
        Resets to 'everyone' if no role is provided.

        :param ctx: The invocation context.
        :param role: The role to use as the default mention.
        """
        mention = role.mention if role else DEFAULT_ROLE
        async with SessionLocal.begin() as db:
            await _set_setting(db, DEFAULT_ROLE_KEY, mention)

        embed = discord.Embed(
            title="Default Role Updated",
            description=f"The default birthday mention role has been set to:\n\n**{mention}**",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

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
        _require_admin_for_others(ctx, user)
        date_text = date.strftime("%d-%m")

        async with SessionLocal.begin() as db:
            default_message = await _get_setting(db, DEFAULT_MESSAGE_KEY, DEFAULT_MESSAGE)
            birthday = await db.get(Birthday, user.id)
            is_new = birthday is None
            if is_new:
                db.add(Birthday(user_id=user.id, date=date_text, message=message or "DEFAULT"))
            else:
                # Read here: ORM objects expire once the session commits.
                existing_message = birthday.message
                birthday.date = date_text
                birthday.message = message or existing_message

        if is_new:
            embed = discord.Embed(
                title=f"🎂 {user.display_name}'s birthday saved",
                color=discord.Color.greyple()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Date", value=date.strftime("%d-%m"), inline=True)
            embed.add_field(name="Message", value=f"_{message if message and message != 'DEFAULT' else default_message}_", inline=False)
            embed.set_footer(text="Use %n as a placeholder for the user's name.\nUse %r to mention the default role.\nDEFAULT will use the default set message.")
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title=f"🎂 {user.display_name}'s birthday updated",
                color=discord.Color.blurple()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Date", value=date.strftime("%d-%m"), inline=True)
            embed.add_field(name="Message", value=f"_{message or existing_message}_", inline=False)
            embed.set_footer(text="Use %n as a placeholder for the user's name.\nUse %r to mention the default role.\nDEFAULT will use the default set message.")
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="birthday-remove", description="Remove a birthday")
    async def birthday_remove(self, ctx: commands.Context, user: discord.Member = None) -> None:
        """
        Remove a user's birthday from the saved list. Defaults to the command author if no user is given.

        :param ctx: The invocation context.
        :param user: The member whose birthday to remove. Defaults to the author.
        """
        user = user or ctx.author
        _require_admin_for_others(ctx, user)

        async with SessionLocal.begin() as db:
            birthday = await db.get(Birthday, user.id)
            if birthday is not None:
                await db.delete(birthday)

        if birthday is not None:
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
        async with SessionLocal() as db:
            birthdays = (await db.scalars(select(Birthday))).all()
            default_message = await _get_setting(db, DEFAULT_MESSAGE_KEY, DEFAULT_MESSAGE)

        if not birthdays:
            embed = discord.Embed(
                description="No birthdays saved.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return

        lines = []
        for birthday in birthdays:
            # get_member returns None for someone who left; fetch_member would raise and break the whole list.
            user = ctx.guild.get_member(birthday.user_id)
            name = user.display_name if user else f"Unknown ({birthday.user_id})"
            date = birthday.date
            message = birthday.message if birthday.message != "DEFAULT" else default_message
            # Cut one oversized entry so it still fits in an embed by itself.
            lines.append(f"**{name} — {date}**\n_{message}_"[:EMBED_DESCRIPTION_LIMIT])

        # One text block, not a field per birthday: an embed holds at most 25 fields.
        # Whole entries are packed into pages, so no entry is split across two embeds.
        pages = []
        for line in lines:
            if pages and len(pages[-1]) + 1 + len(line) <= EMBED_DESCRIPTION_LIMIT:
                pages[-1] += "\n" + line
            else:
                pages.append(line)

        # One message per page: the embeds of a single message share a 6000-character limit.
        for number, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title="🎂 Birthday calendar" if number == 1 else None,
                description=page,
                color=discord.Color.blurple()
            )
            if number == len(pages):
                embed.set_footer(text=f"{len(birthdays)} birthday(s) saved")
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

        async with SessionLocal() as db:
            birthday = await db.get(Birthday, user.id)
            default_message = await _get_setting(db, DEFAULT_MESSAGE_KEY, DEFAULT_MESSAGE)

        if birthday is None:
            embed = discord.Embed(
                description=f"No birthday found for {user.display_name}.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        date = birthday.date
        message = birthday.message if birthday.message != "DEFAULT" else default_message

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
        Also runs once at startup (see before_check); a day that was already announced is skipped.
        """
        now = dt.datetime.now(TIMEZONE)
        today = now.date().isoformat()
        dates = [now.strftime("%d-%m")]
        # Leap-day birthdays are announced on 28-02 in years that have no 29-02.
        if dates[0] == "28-02" and not calendar.isleap(now.year):
            dates.append("29-02")
        channel = self.bot.get_channel(self.birthday_channel)

        # An error that escapes a tasks.loop stops it for good, so report and skip today instead of raising.
        if channel is None:
            await self.bot.report_error(
                "birthday check", f"Birthday channel {self.birthday_channel} not found, skipping today's check."
            )
            return

        try:
            async with SessionLocal() as db:
                last_check = await _get_setting(db, LAST_CHECK_KEY, None)
                default_message = await _get_setting(db, DEFAULT_MESSAGE_KEY, DEFAULT_MESSAGE)
                default_role = await _get_setting(db, DEFAULT_ROLE_KEY, DEFAULT_ROLE)
                birthdays = (await db.scalars(select(Birthday).where(Birthday.date.in_(dates)))).all()
        except Exception as e:
            await self.bot.report_error("birthday check", e)
            return

        # A restart on a day that was already announced must not announce it again.
        if last_check == today:
            return

        for birthday in birthdays:
            uid = birthday.user_id
            message = birthday.message
            try:
                member = await channel.guild.fetch_member(uid)
                if member is None:
                    raise commands.UserNotFound("User not found.")

                if message == "DEFAULT":
                    message = default_message
                message = _replace_placeholders(message, uid, default_role)
                await channel.send(message)
            except Exception as e:
                await self.bot.report_error(f"birthday of user {uid}", e)

        # Stored only here, after the announcements: a run that gave up earlier is retried at the next start.
        try:
            async with SessionLocal.begin() as db:
                await _set_setting(db, LAST_CHECK_KEY, today)
        except Exception as e:
            await self.bot.report_error("birthday check", e)

    @check_birthdays.before_loop
    async def before_check(self):
        """
        Wait until the bot is fully ready, then announce today's birthdays if the bot was down at midnight.
        Days that were missed completely are not announced.
        """
        await self.bot.wait_until_ready()

        # An error that escapes before_loop stops the loop before it starts, so report instead of raising.
        try:
            async with SessionLocal.begin() as db:
                if await _get_setting(db, LAST_CHECK_KEY, None) is None:
                    # First start with this feature: the old version may have announced today already,
                    # so mark today as done instead of risking a second announcement.
                    await _set_setting(db, LAST_CHECK_KEY, dt.datetime.now(TIMEZONE).date().isoformat())
                    return
        except Exception as e:
            await self.bot.report_error("birthday check", e)
            return

        await self.check_birthdays()