# bot/db/patch_schema.py
"""
Добавляет недостающие столбцы в таблицу matches.
Работает асинхронно, поэтому вызывать нужно через `await apply_async()`.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from bot.config import DATABASE_URL

log = logging.getLogger(__name__)

async_engine = create_async_engine(DATABASE_URL, echo=False, future=True)


async def apply_async() -> None:
    """Проверяем/патчим схему (idempotent)."""
    async with async_engine.begin() as conn:
        # PostgreSQL понимает `IF NOT EXISTS`, так что инспекция не нужна
        log.info("🛠  ALTER TABLE matches ADD COLUMN IF NOT EXISTS status …")
        await conn.execute(text(
            "ALTER TABLE IF EXISTS matches "
            "ADD COLUMN IF NOT EXISTS status VARCHAR(20) "
            "DEFAULT 'scheduled'"
        ))

        log.info("🛠  ALTER TABLE matches ADD COLUMN IF NOT EXISTS matchday …")
        await conn.execute(text(
            "ALTER TABLE IF EXISTS matches "
            "ADD COLUMN IF NOT EXISTS matchday INT"
        ))
