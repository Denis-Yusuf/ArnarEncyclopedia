import json
import os
import random

import discord
from discord.ext import commands


def _load_encyclopedia(path: str = "Arnar_Encyclopedia.json") -> dict:
    """
    Loads the encyclopedia JSON and returns the parsed data.

    :param path: Path to the encyclopedia JSON file.
    :return: Dict with a 'default' quote list and a 'users' map of user ID strings to quote lists.
    """
    with open(path, encoding = "utf-8") as f:
        return json.load(f)


class Eggcog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        """
        :param bot: The running Discord bot instance.
        """
        self.bot = bot
        self.ma_channel_id = int(os.getenv("MUDAI_CHANNEL_ID"))
        data = _load_encyclopedia()
        self.default_quotes: list[str] = data["default"]
        # Keyed by user ID string to match Discord's snowflake format
        self.user_quotes: dict[str, list[str]] = data["users"]

    @commands.hybrid_command(name = 'egg', description = 'Mimic Arnar.')
    async def egg(self, ctx: commands.Context) -> None:
        """
        Picks a random quote from the encyclopedia and sends it.
        Users with a dedicated quote set in 'users' get their own pool;
        everyone else draws from 'default'.
        The special value '$ma' redirects the message to the configured channel instead of the invoking one.

        :param ctx: The invocation context.
        """
        # Use the invoking user's dedicated pool if one exists, otherwise fall back to default
        pool = self.user_quotes.get(str(ctx.author.id), self.default_quotes)
        pick = random.choice(pool)

        is_url = pick.startswith("http://") or pick.startswith("https://")
        if pick == "$ma":
            channel = self.bot.get_channel(self.ma_channel_id)
            # Fall back to the invoking context if the channel isn't cached
            target = channel if channel is not None else ctx
        else:
            target = ctx
        await target.send(
            pick,
            allowed_mentions = discord.AllowedMentions(users = True),
            suppress_embeds = not is_url
        )
