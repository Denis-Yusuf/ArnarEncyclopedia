import enum
from typing import List

from sqlalchemy import ForeignKey, Integer, text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class ItemRarity(enum.IntEnum):
    """Rarities of items"""
    TRASH = 0
    MEH = 1
    GOOD = 2
    HOLY = 3


class IntEnumType(TypeDecorator):
    """Store enum as integer in database"""
    impl = Integer
    cache_ok = True

    def __init__(self, enum_class):
        self.enum_class = enum_class
        super().__init__()

    def __repr__(self):
        return f"IntEnumType({self.enum_class.__name__})"

    @property
    def python_type(self):
        return self.enum_class

    def process_bind_param(self, value, dialect):
        if isinstance(value, self.enum_class):
            return value.value
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return self.enum_class[value].value
        raise TypeError(f"Invalid type for enum: {type(value)}")

    def process_result_value(self, value, dialect):
        return self.enum_class(value)

    def process_literal_param(self, value, dialect):
        if value is None:
            return "NULL"
        return str(int(value))

    def coerce_compared_value(self, op, value):
        return self


class User(Base):
    """Table of discord users"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[int] = mapped_column(default=0)

    inventory: Mapped[List["Inventory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Item(Base):
    """All items in gacha"""
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    mal_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(nullable=True)
    image: Mapped[str] = mapped_column()
    image_fallback: Mapped[str] = mapped_column()
    image_small: Mapped[str] = mapped_column()
    rarity: Mapped[ItemRarity] = mapped_column(IntEnumType(ItemRarity))
    active: Mapped[bool] = mapped_column(default=True)

    owners: Mapped[List["Inventory"]] = relationship(back_populates="item")
    banners: Mapped[List["BannerItem"]] = relationship(back_populates="item")


class Inventory(Base):
    """Inventory of users"""
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
    """Specific banner in gacha"""
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    active: Mapped[bool] = mapped_column()

    items: Mapped[List["BannerItem"]] = relationship(
        back_populates="banner", cascade="all, delete-orphan"
    )


class BannerItem(Base):
    """Item pool of banners"""
    __tablename__ = "banner_items"
    __table_args__ = (UniqueConstraint("banner_id", "item_id"),)

    banner_id: Mapped[int] = mapped_column(
        ForeignKey("banners.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    weight: Mapped[int] = mapped_column()

    banner: Mapped["Banner"] = relationship(back_populates="items")
    item: Mapped["Item"] = relationship(back_populates="banners")
