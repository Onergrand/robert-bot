# migrations.py
"""
Функции для миграций и автоматического создания таблиц
"""
import logging
from sqlalchemy import text, inspect
from db.db import engine, DATABASE_URL

async def table_exists(table_name: str) -> bool:
    """Проверить, существует ли таблица в БД"""
    async with engine.begin() as conn:
        if "sqlite" in DATABASE_URL:
            # Для SQLite - используем параметризованный запрос
            result = await conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=:table_name
            """), {"table_name": table_name})
            return result.first() is not None
        else:
            # Для PostgreSQL
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = :table_name
                )
            """), {"table_name": table_name})
            return result.scalar()


async def create_users_table():
    """Создать таблицу users если её нет"""
    if await table_exists("users"):
        logging.info("Table 'users' already exists")
        return
    
    logging.info("Creating table 'users'...")
    async with engine.begin() as conn:
        if "sqlite" in DATABASE_URL:
            # SQLite версия
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    role TEXT DEFAULT 'user' CHECK(role IN ('owner', 'admin', 'user')),
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)
            """))
        else:
            # PostgreSQL версия
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    role VARCHAR(20) DEFAULT 'user' CHECK(role IN ('owner', 'admin', 'user')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)
            """))
    
    logging.info("Table 'users' created successfully")


async def run_migrations():
    """Выполнить все миграции"""
    await create_users_table()

