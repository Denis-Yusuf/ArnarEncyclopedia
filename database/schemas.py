from pydantic import BaseModel, ConfigDict, field_validator

from database.models import ItemRarity

class ItemSchema(BaseModel):
    id: int
    name: str
    mal_id: int | None
    source: str | None
    image: str
    image_fallback: str | None
    image_small: str | None
    rarity: ItemRarity

    model_config = ConfigDict(from_attributes=True)

    @field_validator("rarity", mode="before")
    @classmethod
    def convert_rarity(cls, v):
        if isinstance(v, str):
            return ItemRarity[v]
        return v
