# db.py
import os
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql+asyncpg://user:pass@localhost:5432/db

engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=10)
Session = async_sessionmaker(engine, expire_on_commit=False)

@asynccontextmanager
async def get_session() -> AsyncSession:
    async with Session() as s:
        yield s

async def healthcheck():
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
