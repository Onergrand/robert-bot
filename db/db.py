# db.py
import os
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

load_dotenv()
# По умолчанию используем SQLite, можно переопределить через переменную окружения
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")

# Для SQLite нужно включить поддержку внешних ключей
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Включает поддержку внешних ключей для SQLite"""
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Для SQLite настраиваем connect_args
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args["check_same_thread"] = False
    # Используем NullPool для SQLite (не нужен connection pooling)
    engine = create_async_engine(
        DATABASE_URL,
        connect_args=connect_args,
        poolclass=NullPool,
        echo=False
    )
    # Регистрируем обработчик для включения foreign keys
    event.listens_for(engine.sync_engine, "connect")(set_sqlite_pragma)
else:
    # Для других БД используем стандартный pool
    engine = create_async_engine(
        DATABASE_URL,
        connect_args=connect_args,
        echo=False
    )

Session = async_sessionmaker(engine, expire_on_commit=False)

@asynccontextmanager
async def get_session() -> AsyncSession:
    async with Session() as s:
        yield s

async def healthcheck():
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
