import itertools
import json
import logging
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
    Entries that cannot be turned into an activity (unknown type, missing field) are left out.

    :param path: Path to the JSON activities file.
    :return: Shuffled list of raw entry dicts.
    """
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    usable = []
    for entry in entries:
        try:
            # The cycle repeats forever, so a broken entry would fail again on every round: drop it now.
            _ACTIVITY_BUILDERS[entry["type"]](entry)
        except (KeyError, TypeError):
            logging.warning("Skipping unusable entry in %s: %r", path, entry)
            continue
        usable.append(entry)
    random.shuffle(usable)
    return usable


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
        entry = next(self._cycle, None)
        if entry is None:
            return
        # An error that escapes a tasks.loop stops it for good, so report and try again next round.
        try:
            activity = _ACTIVITY_BUILDERS[entry["type"]](entry)
            await self.bot.change_presence(activity=activity)
        except Exception as e:  # pylint: disable=broad-exception-caught
            await self.bot.report_error("presence rotation", e)

    @rotate.before_loop
    async def before_rotate(self) -> None:
        """Holds the task until the bot is fully connected before setting any presence."""
        await self.bot.wait_until_ready()
