from pydantic import BaseModel

from database.models import ItemRarity

class ItemSchema(BaseModel):
    id: int
    name: str
    rarity: ItemRarity
    image: str

    class Config:
        from_attributes = True
