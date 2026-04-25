# Gacha data

1.  banners.json should have the following structure:
    ```yaml
    [
        {
            "name": <string>,
            "items": [
                {
                    "item_id": <existing id in items.csv>,
                    "weight": <int>
                },
                ...
            ],
            "active": <bool>
        },
        ...
    ]
    ```
    Multiple banner files might be supported in the future. Right now, all items need to be manually added. Maybe in the future, only rare items need to be added.

2.  items.csv should have the following columns:
    -   id: Item id
    -   mal_id: Character Id in myanimelist
    -   name: Name of the character
    -   image: Image url
    -   image_fallback: fallback image url
    -   image_small: Small image url
    -   rarity: Item rarity, see database.models. It is important that this column is of type int.
    -   active: Active in pool or not
    -   source: Original media appearance of character. (Default null, need to query mal.)
