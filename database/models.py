import enum
from typing import List

from sqlalchemy import Enum, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class ItemRarity(enum.Enum):
    THRASH = "THRASH"
    MEH = "MEH"
    GOOD = "GOOD"
    HOLY = "HOLY"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[int] = mapped_column(default=0)

    inventory: Mapped[List["Inventory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    mal_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(index=True)
    name_source: Mapped[str] = mapped_column()
    source: Mapped[str] = mapped_column()
    image: Mapped[str] = mapped_column()
    image_fallback: Mapped[str] = mapped_column()
    image_small: Mapped[str] = mapped_column()
    rarity: Mapped[ItemRarity] = mapped_column(Enum(ItemRarity))
    active: Mapped[bool] = mapped_column(default=True)

    owners: Mapped[List["Inventory"]] = relationship(back_populates="item")
    banners: Mapped[List["BannerItem"]] = relationship(back_populates="item")


class Inventory(Base):
    __tablename__ = "inventory"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(default=1, server_default=text("1"))

    user: Mapped["User"] = relationship(back_populates="inventory")
    item: Mapped["Item"] = relationship(back_populates="owners")


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    active: Mapped[bool] = mapped_column()

    items: Mapped[List["BannerItem"]] = relationship(
        back_populates="banner", cascade="all, delete-orphan"
    )


class BannerItem(Base):
    __tablename__ = "banner_items"
    __table_args__ = (UniqueConstraint("banner_id", "item_id"),)

    banner_id: Mapped[int] = mapped_column(
        ForeignKey("banners.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    weight: Mapped[int] = mapped_column()

    banner: Mapped["Banner"] = relationship(back_populates="items")
    item: Mapped["Item"] = relationship(back_populates="banners")
