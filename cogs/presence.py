import itertools
import json
import random

import discord
from discord.ext import commands, tasks

ROTATE_EVERY_MINUTES = 10

# Maps the 'type' string from activities.json to the corresponding Discord activity constructor
_ACTIVITY_BUILDERS = {
    "streaming": lambda entry: discord.Streaming(name = entry["name"], url = entry["url"]),
    "listening": lambda entry: discord.Activity(type = discord.ActivityType.listening, name = entry["name"]),
    "watching":  lambda entry: discord.Activity(type = discord.ActivityType.watching, name = entry["name"]),
    "playing":   lambda entry: discord.Game(name = entry["name"]),
    "competing": lambda entry: discord.Activity(type = discord.ActivityType.competing, name = entry["name"]),
}


def _load_activities(path: str = "activities.json") -> list:
    """
    Load and shuffle activities from a JSON file, returning Discord activity objects.

    :param path: Path to the JSON activities file.
    :return: Shuffled list of Discord activity objects.
    """
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    random.shuffle(entries)
    return [_ACTIVITY_BUILDERS[e["type"]](e) for e in entries]


class PresenceCog(commands.Cog):
    """Rotates the bot's rich presence on a fixed interval."""

    def __init__(self, bot: commands.Bot) -> None:
        """
        :param bot: The running Discord bot instance.
        """
        self.bot = bot
        # itertools.cycle loops the shuffled list forever without reloading the file
        self._cycle = itertools.cycle(_load_activities())
        self.rotate.start()

    def cog_unload(self) -> None:
        """Stops the rotation task cleanly when the cog is removed."""
        self.rotate.cancel()

    @tasks.loop(minutes = ROTATE_EVERY_MINUTES)
    async def rotate(self) -> None:
        """Advances to the next activity in the cycle and updates the bot's presence."""
        await self.bot.change_presence(activity = next(self._cycle))

    @rotate.before_loop
    async def before_rotate(self) -> None:
        """Holds the task until the bot is fully connected before setting any presence."""
        await self.bot.wait_until_ready()
