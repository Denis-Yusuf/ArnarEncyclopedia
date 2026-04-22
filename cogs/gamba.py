from __future__ import annotations

import json
import random
from contextlib import asynccontextmanager
from typing import Tuple

from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import models, sync
from database.database import SessionLocal, engine
from database.models import Banner, BannerItem, Item, User


models.Base.metadata.create_all(bind=engine)


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
    return banner.name, tuple(list(x) for x in zip(*items))


class GambaCog(commands.Cog):
    """Cog for Gamba services"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.banners = {}
        self.default_banner = None

    async def cog_load(self):
        """Load all active banners"""
        # In future, maybe add support for multiple banner files, hard-coded for now
        with open("banners.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        async with get_db() as db:
            await sync.sync_banner(db, data)

            banners = await db.scalars(select(Banner).where(Banner.active)).all()
            self.banners = {await get_banner_drops(db, banner) for banner in banners}
            self.default_banner = self.default_banner or next(iter(self.banners))

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
        banner = banner or self.default_banner
        async with get_db() as db:
            user = await get_or_create_user(db, user_id)
            items, weights = self.banners[banner]

            drop = random.choices(items, weights=weights, k=1)[0]
            await ctx.send(f"You got {drop['name']}!")
