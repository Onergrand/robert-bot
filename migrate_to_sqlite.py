#!/usr/bin/env python3
"""
Скрипт миграции данных из PostgreSQL в SQLite
Использование: python migrate_to_sqlite.py
"""
import os
import asyncio
import json
from datetime import datetime
from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import asyncpg
import aiosqlite

# Загрузка переменных окружения
from dotenv import load_dotenv
load_dotenv()

# URL подключений
POSTGRES_URL = os.getenv("DATABASE_URL")  # postgresql+asyncpg://...
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "./bot.db")
SQLITE_URL = f"sqlite+aiosqlite:///{SQLITE_DB_PATH}"

async def migrate_table_pg_to_sqlite(table_name: str, pg_conn, sqlite_conn):
    """Мигрировать данные из одной таблицы PostgreSQL в SQLite"""
    print(f"  Миграция таблицы {table_name}...")
    
    # Получаем данные из PostgreSQL
    rows = await pg_conn.fetch(f"SELECT * FROM {table_name}")
    
    if not rows:
        print(f"    Таблица {table_name} пуста, пропускаем")
        return 0
    
    # Получаем названия колонок
    columns = list(rows[0].keys())
    
    # Вставляем данные в SQLite
    count = 0
    for row in rows:
        values = [row[col] for col in columns]
        placeholders = ", ".join(["?" for _ in columns])
        col_names = ", ".join(columns)
        
        # Для SQLite нужно обработать специальные типы
        processed_values = []
        for val in values:
            if isinstance(val, dict):
                processed_values.append(json.dumps(val))
            elif isinstance(val, (list, tuple)):
                processed_values.append(json.dumps(list(val)))
            elif val is None:
                processed_values.append(None)
            else:
                processed_values.append(val)
        
        try:
            await sqlite_conn.execute(
                f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})",
                processed_values
            )
            count += 1
        except Exception as e:
            print(f"    Ошибка при вставке строки: {e}")
            print(f"    Данные: {dict(row)}")
    
    await sqlite_conn.commit()
    print(f"    Перенесено {count} записей")
    return count

async def migrate_data():
    """Основная функция миграции"""
    print("=" * 60)
    print("МИГРАЦИЯ ДАННЫХ ИЗ POSTGRESQL В SQLITE")
    print("=" * 60)
    
    if not POSTGRES_URL or "postgresql" not in POSTGRES_URL:
        print("❌ Ошибка: DATABASE_URL не указывает на PostgreSQL")
        print("   Установите DATABASE_URL в .env файле")
        return False
    
    # Парсим URL PostgreSQL для asyncpg
    # Формат: postgresql+asyncpg://user:pass@host:port/db
    pg_url_clean = POSTGRES_URL.replace("postgresql+asyncpg://", "postgresql://")
    
    print(f"\n📊 Источник: PostgreSQL ({POSTGRES_URL.split('@')[-1] if '@' in POSTGRES_URL else 'unknown'})")
    print(f"📊 Назначение: SQLite ({SQLITE_DB_PATH})")
    
    # Подключение к PostgreSQL
    print("\n1. Подключение к PostgreSQL...")
    try:
        # Парсим URL для asyncpg
        from urllib.parse import urlparse
        parsed = urlparse(pg_url_clean)
        pg_conn = await asyncpg.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip('/')
        )
        print("   ✅ Подключено к PostgreSQL")
    except Exception as e:
        print(f"   ❌ Ошибка подключения к PostgreSQL: {e}")
        return False
    
    # Подключение к SQLite
    print("\n2. Подключение к SQLite...")
    try:
        sqlite_conn = await aiosqlite.connect(SQLITE_DB_PATH)
        await sqlite_conn.execute("PRAGMA foreign_keys = ON")
        print("   ✅ Подключено к SQLite")
    except Exception as e:
        print(f"   ❌ Ошибка подключения к SQLite: {e}")
        await pg_conn.close()
        return False
    
    # Создание таблиц в SQLite (если их нет)
    print("\n3. Создание таблиц в SQLite...")
    try:
        with open("schema.sql", "r", encoding="utf-8") as f:
            schema_sql = f.read()
        
        # Удаляем PRAGMA для выполнения через aiosqlite
        schema_sql = schema_sql.replace("PRAGMA foreign_keys = ON;", "")
        
        # Выполняем CREATE TABLE команды
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement and statement.upper().startswith("CREATE"):
                try:
                    await sqlite_conn.execute(statement)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"   ⚠️  Предупреждение при создании таблицы: {e}")
        
        await sqlite_conn.commit()
        print("   ✅ Таблицы созданы")
    except Exception as e:
        print(f"   ❌ Ошибка создания таблиц: {e}")
        await pg_conn.close()
        await sqlite_conn.close()
        return False
    
    # Миграция данных
    print("\n4. Миграция данных...")
    tables = ["chats", "chat_messages", "holiday_log", "chat_metrics", "users"]
    total_migrated = 0
    
    for table in tables:
        try:
            # Проверяем, существует ли таблица в PostgreSQL
            exists = await pg_conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = $1
                )
            """, table)
            
            if not exists:
                print(f"  ⚠️  Таблица {table} не существует в PostgreSQL, пропускаем")
                continue
            
            count = await migrate_table_pg_to_sqlite(table, pg_conn, sqlite_conn)
            total_migrated += count
        except Exception as e:
            print(f"  ❌ Ошибка при миграции таблицы {table}: {e}")
    
    # Закрываем соединения
    await pg_conn.close()
    await sqlite_conn.close()
    
    print(f"\n✅ Миграция завершена! Всего перенесено записей: {total_migrated}")
    print(f"\n📝 Следующие шаги:")
    print(f"   1. Обновите DATABASE_URL в .env на: sqlite+aiosqlite:///{SQLITE_DB_PATH}")
    print(f"   2. Перезапустите бота")
    print(f"   3. Проверьте работу бота")
    
    return True

if __name__ == "__main__":
    asyncio.run(migrate_data())

