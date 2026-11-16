import csv

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert

from database.models import Banner, BannerItem, Item, ItemRarity


async def import_items(session, filename):
    """
    Import items from csv. Items will be appended to the table. Make sure no ids overlap.
    (Leave it out or something)

    :param session: Async database session; the caller commits.
    :param filename: Path to the csv file, with the columns of the items table as header.
    """
    with open(filename, newline="", encoding="utf-8") as f:
        rows = [
            {
                # csv has no NULL: an empty cell means the value is missing.
                **{column: value or None for column, value in row.items()},
                "id": int(row["id"]),
                "mal_id": int(row["mal_id"]) if row["mal_id"] else None,
                "rarity": int(row["rarity"]),
                "active": row["active"] == "1",
            }
            for row in csv.DictReader(f)
        ]
    await session.execute(insert(Item), rows)


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
