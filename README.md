# ArnarEncyclopedia

Garbage ass bot for discord.

## Instructions

1.  .env.example > .env \(Ask somebody for tokens, or the whole .env file\)
2.  - either venv requirements and python main.py
    - or docker compose up
3.  Before running main.py, first apply migrations
    ```sh
    alembic upgrade head
    ```
    inside venv, then run main.py

## Documention

### Alembic

This bot makes use of alembic migrations. To add a new table, you need to make a new migration file. The easiest way to add a new table is by inheriting from `database.database.base`. For reference, see `database.models`. For complicated shit, ask for help from your preferred chatbot. After creating the models, generate a migration using the following inside your virtual environment:

```sh
alembic revision --autogenerate -m "<migration message>"
```

### SQLite

We make use of aiosqlite, meaning it is asynchronous. You will have to await all table modifications and reads. See `cogs.gamba` for examples.

## Gacha

Right now, only the basic functionality is implemented. That includes single pull, 10 pull, inventory, and character query. What is not implemented is currency system, dailies, other stuff, etc. Each character also has a source, and most of them are null. That is because my anime list api has a rate limit of 3 per second and 10 per minute. With 10,000 characters, which is a little difficult (not really). So most (all) of them don't have a source. Also, a lot of images just don't exist, and should be manually fixed. That is all for now.

## Datasets

This repository contains processed data of the following dataset: https://www.kaggle.com/datasets/sazzadsiddiquelikhon/anime-character-database-july-2025 Licensed under [ODbL](https://opendatacommons.org/licenses/odbl/1-0/)
