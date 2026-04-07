import itertools
import json
import random
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

ROTATE_EVERY_MINUTES = 10


# Maps the 'type' string from activities.json to the corresponding Discord activity constructor.
# Each lambda is called fresh per rotation so start= reflects the actual time the activity is set.
_ACTIVITY_BUILDERS = {
    "streaming": lambda entry: discord.Streaming(name = entry["name"], url = entry["url"]),
    "listening": lambda entry: discord.Activity(type = discord.ActivityType.listening, name = entry["name"]),
    "watching":  lambda entry: discord.Activity(type = discord.ActivityType.watching,  name = entry["name"]),
    "playing":   lambda entry: discord.Game(name = entry["name"], start = datetime.now(tz = timezone.utc)),
    "competing": lambda entry: discord.Activity(type = discord.ActivityType.competing, name = entry["name"], start = datetime.now(tz = timezone.utc)),
}


def _load_entries(path: str = "activities.json") -> list:
    """
    Load and shuffle raw activity entries from a JSON file.

    :param path: Path to the JSON activities file.
    :return: Shuffled list of raw entry dicts.
    """
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    random.shuffle(entries)
    return entries


class PresenceCog(commands.Cog):
    """Rotates the bot's rich presence on a fixed interval."""

    def __init__(self, bot: commands.Bot) -> None:
        """
        :param bot: The running Discord bot instance.
        """
        self.bot = bot
        self._cycle = itertools.cycle(_load_entries())
        self.rotate.start()

    def cog_unload(self) -> None:
        """Stops the rotation task cleanly when the cog is removed."""
        self.rotate.cancel()

    @tasks.loop(minutes=ROTATE_EVERY_MINUTES)
    async def rotate(self) -> None:
        """Advances to the next activity in the cycle and updates the bot's presence."""
        entry = next(self._cycle)
        activity = _ACTIVITY_BUILDERS[entry["type"]](entry)
        await self.bot.change_presence(activity=activity)

    @rotate.before_loop
    async def before_rotate(self) -> None:
        """Holds the task until the bot is fully connected before setting any presence."""
        await self.bot.wait_until_ready()
