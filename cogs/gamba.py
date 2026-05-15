from __future__ import annotations

import json
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import defaultdict, Tuple

import discord
from discord.ext import commands
from discord.utils import logging
from sqlalchemy import column, exists, func, select, table, text
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


async def create_fts():
    """
    Create virtual items table for indexing.
    """
    async with get_db() as db:
        await db.execute(
            text(
                """
            CREATE VIRTUAL TABLE IF NOT EXISTS items_fts
            USING fts5(
                name,
                content='items',
                content_rowid='id',
                prefix='2 3 4'
            );
        """
            )
        )

        await db.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
            INSERT INTO items_fts(rowid, name)
            VALUES (new.id, new.name);
            END;
        """
            )
        )

        await db.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
            DELETE FROM items_fts WHERE rowid = old.id;
            END;
        """
            )
        )

        await db.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
            UPDATE items_fts
            SET name = new.name
            WHERE rowid = new.id;
            END;
        """
            )
        )


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
    return banner.name, tuple(
        list(x)
        for x in zip(
            *[(ItemSchema.model_validate(item), weight) for item, weight in items]
        )
    )


async def add_to_inventory(
    session: AsyncSession, user_id: int, item_id: int, amount: int
):
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
        session.add(Inventory(user_id=user_id, item_id=item_id, quantity=amount))


class GambaCog(commands.Cog):
    """Cog for Gamba services"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_dir = Path("data/gacha")
        self.default_cum_weights = [0.8, 0.95, 0.99, 1]
        self.rarity_colors = [
            discord.Color.light_gray(),
            discord.Color.blue(),
            discord.Color.purple(),
            discord.Color.gold(),
        ]
        self.rarity_counts = []
        self.banners = {}

    async def cog_load(self):
        """Load all active banners"""
        # Create virtual items table
        await create_fts()

        async with get_db() as db:
            # Import default items if table is empty
            stmt = select(exists().select_from(Item))
            if not await db.scalar(stmt):
                logging.info("Importing items...")
                await sync.import_items(self.data_dir / "items.csv")
                await db.execute(
                    text(
                        """
                    INSERT INTO items_fts(items_fts)
                    VALUES ('optimize');
                """
                    )
                )
                logging.info("Done!")

            # Total count of each rarity
            stmt = (
                select(func.count())
                .select_from(Item)
                .group_by(Item.rarity)
                .order_by(Item.rarity.asc())
            )
            self.rarity_counts = (await db.scalars(stmt)).all()

            # In future, maybe add support for multiple banner files, hard-coded for now
            with open(self.data_dir / "banners.json", "r", encoding="utf-8") as f:
                banner_data = json.load(f)
            await sync.sync_banners(db, banner_data)

            banners = await db.scalars(select(Banner).where(Banner.active))
            for banner in banners:
                banner_name, drops = await get_banner_drops(db, banner)
                self.banners[banner_name] = drops

    async def single_pull(self, user_id: int, banner: str = None) -> None:
        """
        Does a single pull and returns an embed.
        """
        async with get_db() as db:
            await get_or_create_user(db, user_id)
            # no banner support yet
            rarity = random.choices(
                list(ItemRarity), cum_weights=self.default_cum_weights
            )[0]

            count = await db.scalar(
                (select(func.count()).where(Item.rarity == rarity).where(Item.active))
            )
            stmt = (
                select(Item)
                .where(Item.rarity == rarity)
                .where(Item.active)
                .offset(random.randint(0, count - 1))
                .limit(1)
            )
            drop = await db.scalar(stmt)
            drop: ItemSchema = ItemSchema.model_validate(drop)

            await add_to_inventory(db, user_id, drop.id, 1)
        embed = discord.Embed(
            color=self.rarity_colors[drop.rarity],
            title=drop.name,
            description=drop.rarity.name,
        )
        embed.set_image(url=drop.image)
        return embed

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
            await ctx.send(f'Banner "{banner}" does not exist.', ephemeral=True)
            return

        embed = await self.single_pull(user_id, banner)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="pullten", description="Do a 10 pull in the gacha banner."
    )
    async def pull_ten(self, ctx: commands.Context, *, banner: str = None) -> None:
        user_id = ctx.author.id

        if banner is not None and banner not in self.banners:
            await ctx.send(f'Banner "{banner}" does not exist.', ephemeral=True)
            return

        await ctx.send(
            embeds=[await self.single_pull(user_id, banner) for _ in range(10)],
        )

    @commands.hybrid_command(name="inventory", description="Check your inventory.")
    async def inventory(
        self, ctx: commands.Context, *, member: discord.Member = None
    ) -> None:
        """
        Display the inventory of user.

        :param member: An optional Discord user to see its inventory instead.
        """
        user_id = ctx.author.id if member is None else member.id
        async with get_db() as db:
            user = await get_or_create_user(db, user_id)
            stmt = (
                select(Item.rarity, func.count())
                .join_from(Inventory, Item)
                .where(Inventory.user_id == user_id)
                .group_by(Item.rarity)
                .order_by(Item.rarity.desc())
            )
            counts = (await db.execute(stmt)).all()

            stmt = (
                select(Item)
                .join_from(Inventory, Item)
                .where(Inventory.user_id == user_id)
                .order_by(Item.rarity.desc(), Item.id)
                .limit(10)
            )
            items = (await db.scalars(stmt)).all()
            msg = "Collection:\n"

            counts = defaultdict(int, counts)

            for rarity in reversed(list(ItemRarity)):
                msg += (
                    f"{rarity.name}: {counts[rarity]} / {self.rarity_counts[rarity]}\n"
                )

            msg += "\nTop 10:\n"
            for item in items:
                msg += f"-\t{item.name}, {item.rarity.name}\n"

            await ctx.send(msg)

    @commands.hybrid_command(
        name="query", description="Search for an item in the Database."
    )
    async def query(self, ctx: commands.Context, *, query: str) -> None:
        """
        Search for an item given a query, using fts5.
        """
        q = " AND ".join(f"{t}*" for t in query.strip().split())
        async with get_db() as db:
            # Declare the FTS table as a lightweight construct
            items_fts = table(
                "items_fts",
                column("rowid"),
                column("name"),
                column("rank"),
            )
            stmt = (
                select(Item)
                .join(items_fts, Item.id == items_fts.c.rowid)
                .where(items_fts.c.name.match(q))
                .order_by(items_fts.c.rank)
                .limit(1)
            )
            result = ItemSchema.model_validate(await db.scalar(stmt, {"q": q}))

        embed = discord.Embed(
            color=self.rarity_colors[result.rarity],
            title=result.name,
            description=result.rarity.name,
        )
        embed.set_image(url=result.image)
        await ctx.send(embed=embed)
