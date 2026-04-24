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

2.  items.json should have the following structure:
    ```yaml
    [
        {
            "id": <unique int>,
            "name": <string>,
            "rarity": <string (see ItemRarity in database/models)>,
            "image": <string>
        },
        ...
    ]
    ```