# Gacha data

1.  banners.json should have the following structure:
    ```yaml
    [
        {
            "name": <string>,
            "items": [
                {
                    "item_id": <existing id in items.json>,
                    "weight": <int>
                },
                ...
            ],
            "active": <bool>
        },
        ...
    ]
    ```
    Multiple banner files might be supported in the future.

2.  items.json should have the following structure:
    ```yaml
    [
        {
            "id": <unique int>,
            "name": <string>,
            "rarity": <one of the following: ("THRASH", "MEH", "GOOD", "HOLY")>,
            "image": <string>
        },
        ...
    ]
    ```