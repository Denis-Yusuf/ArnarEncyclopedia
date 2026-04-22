from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert

from database.models import Banner, BannerItem


async def sync_banner(session, data):
    banner = await session.scalar(select(Banner).where(Banner.name == data["name"]))

    if not banner:
        banner = Banner(name=data["name"])
        session.add(banner)

    banner.active = data["active"]

    await sync_banner_items(session, banner.id, data["items"])


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
