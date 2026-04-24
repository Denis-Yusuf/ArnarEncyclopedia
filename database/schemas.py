from pydantic import BaseModel, ConfigDict

from database.models import ItemRarity

class ItemSchema(BaseModel):
    id: int
    mal_id: int
    name: str
    source: str | None
    image: str
    image_fallback: str
    image_small: str
    rarity: ItemRarity

    model_config = ConfigDict(from_attributes=True)
