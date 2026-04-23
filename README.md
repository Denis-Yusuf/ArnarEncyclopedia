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