import os

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base


@event.listens_for(Engine, "connect")
def enable_foreign_keys(dbapi_connection, connection_record):
    "Enables sqlite foreign keys on connect"
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}  # needed for SQLite
)

SessionLocal = async_sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
