from __future__ import annotations

import json
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Tuple

from discord.ext import commands
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import sync
from database.database import SessionLocal
from database.models import Banner, BannerItem, Inventory, Item, ItemRarity, User
from database.schemas import ItemSchema


@asynccontextmanager
async def get_db() -> AsyncSession:
    """
    Returns an Async session context.
    """
    db: AsyncSession = SessionLocal()
    try:
        yield db
        await db.commit()
    except:
        await db.rollback()
        raise
    finally:
        await db.close()


async def get_or_create_user(session: AsyncSession, user_id: int):
    """
    Returns User object given user_id, adds one to database if not exists.

    :param session: Async database session.
    :param user_id: Id of user.
    """
    user = await session.get(User, user_id)

    if not user:
        user = User(id=user_id)
        session.add(user)
        await session.flush()

    return user


async def get_banner_drops(
    session: AsyncSession, banner: Banner
) -> Tuple[str, Tuple[Item, int]]:
    """
    Given a banner, returns the banner items and their drop rates.

    :param session: Async database session.
    :param banner: Banner database model.
    """
    items = await session.execute(
        select(Item, BannerItem.weight)
        .where(BannerItem.banner_id == banner.id)
        .join(Item)
    )
    return banner.name, tuple(list(x) for x in zip(*[
        (ItemSchema.model_validate(item), weight) for item, weight in items
    ]))


async def add_to_inventory(session: AsyncSession, user_id: int, item_id: int, amount: int):
    """
    Inserts item into user's inventory, by inserting into table, or increasing amount.
    Assumes User exists.

    :param session: Asunc database session.
    :param user_id: Id of user.
    :param item_id: Id of item.
    :param amount: Amount of item.
    """
    entry = await session.get(Inventory, (user_id, item_id))

    if entry:
        entry.quantity += amount
    else:
        session.add(Inventory(
            user_id=user_id,
            item_id=item_id,
            quantity=amount
        ))


class GambaCog(commands.Cog):
    """Cog for Gamba services"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_dir = Path("data/gacha")
        self.default_cum_weights = [0.8, 0.94, 0.99, 1]
        self.banners = {}

    async def cog_load(self):
        """Load all active banners"""

        # In future, maybe add support for multiple banner files, hard-coded for now
        with open(self.data_dir / "banners.json", "r", encoding="utf-8") as f:
            banner_data = json.load(f)

        async with get_db() as db:
            # Import default items if table is empty
            stmt = select(exists().select_from(Item))
            if not await db.scalar(stmt):
                print("Importing items...")
                await sync.import_items(self.data_dir / "items.csv")
                print("Done!")

            await sync.sync_banners(db, banner_data)

            banners = await db.scalars(select(Banner).where(Banner.active))
            for banner in banners:
                banner_name, drops = await get_banner_drops(db, banner)
                self.banners[banner_name] = drops

    @commands.hybrid_command(
        name="pull", description="Do a single pull in the gacha banner."
    )
    async def pull(self, ctx: commands.Context, *, banner: str = None) -> None:
        """
        Do a singular pull in given banner or default banner. Item will be added to
        the inventory of the user.

        :param ctx: The invocation context.
        :param banner: The banner to pull from, uses default if none given.
        """
        user_id = ctx.author.id

        if banner is not None and banner not in self.banners:
            await ctx.send(f"Banner \"{banner}\" does not exist.")
            return
        async with get_db() as db:
            await get_or_create_user(db, user_id)
            # no banner support yet
            rarity = random.choices(list(ItemRarity), cum_weights=self.default_cum_weights)[0]

            count = await db.scalar((select(func.count()).where(Item.rarity == rarity).where(Item.active)))
            stmt = select(Item).where(Item.rarity == rarity).where(Item.active).offset(random.randint(0, count - 1)).limit(1)
            drop = await db.scalar(stmt)
            drop = ItemSchema.model_validate(drop)

            add_to_inventory(db, user_id, drop.id, 1)
            await ctx.send(f"You got {drop}!")
