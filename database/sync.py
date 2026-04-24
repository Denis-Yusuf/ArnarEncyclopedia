import os

import polars as pl
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert

from database.models import Banner, BannerItem, Item


async def sync_items(session, data):
    # UPSERT
    stmt = insert(Item).values(data)

    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],  # primary key
        set_={
            c.name: getattr(stmt.excluded, c.name)
            for c in Item.__table__.columns
            if c.name != "id"
        },
    )

    await session.execute(stmt.execution_options(synchronize_session=False))


async def import_items(filename):
    uri = os.getenv("DATABASE_URL")
    df = pl.read_csv(filename)

    df.write_database(table_name="items", connection=uri, engine="adbc", if_table_exists="append")


async def export_items(filename):
    uri = os.getenv("DATABASE_URL")
    df = pl.read_database_uri("SELECT * FROM items", uri, engine="adbc")
    
    df.write_csv(filename)


async def sync_banners(session, data):
    for banner_data in data:
        banner = await session.scalar(
            select(Banner).where(Banner.name == banner_data["name"])
        )

        if not banner:
            banner = Banner(name=banner_data["name"])
            session.add(banner)
            banner.active = banner_data["active"]
            await session.flush()

        else:
            banner.active = banner_data["active"]

        await sync_banner_items(session, banner.id, banner_data["items"])


async def sync_banner_items(session, banner_id, items):
    # UPSERT
    stmt = insert(BannerItem).values(
        [
            {"banner_id": banner_id, "item_id": i["item_id"], "weight": i["weight"]}
            for i in items
        ]
    )

    stmt = stmt.on_conflict_do_update(
        index_elements=["banner_id", "item_id"], set_={"weight": stmt.excluded.weight}
    )

    await session.execute(stmt)

    # DELETE missing
    incoming_ids = {i["item_id"] for i in items}

    await session.execute(
        delete(BannerItem).where(
            BannerItem.banner_id == banner_id, ~BannerItem.item_id.in_(incoming_ids)
        )
    )
