"""
patch_schema.py
Проверяет наличие колонок `status` и `matchday` в таблице matches и при
необходимости добавляет их.
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from bot.config import DATABASE_URL

log = logging.getLogger(__name__)

ASYNC_ENGINE: AsyncEngine = create_async_engine(DATABASE_URL, echo=False)


async def apply_async() -> None:
    """Асинхронно применяет патчи к схеме."""
    async with ASYNC_ENGINE.begin() as conn:
        # Проверяем, есть ли нужные колонки
        columns = (
            await conn.run_sync(lambda c: {col["name"] for col in c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='matches'"
            )).mappings()})
        )
        # Добавляем недостающие
        if "status" not in columns:
            log.info("➕ ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'")
            await conn.execute(text("ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"))
        if "matchday" not in columns:
            log.info("➕ ALTER TABLE matches ADD COLUMN matchday INT")
            await conn.execute(text("ALTER TABLE matches ADD COLUMN matchday INT"))
    log.info("✅ База данных готова")


# ────────────────────────────────────────────────────────────────────────────────
# ↓↓↓ ДОБАВЛЯЕМ ↓↓↓
def apply_sync() -> None:
    """
    Синхронная обёртка, которую импортирует main.py.
    Запускает `apply_async()` через `asyncio.run()`.
    """
    asyncio.run(apply_async())
# ────────────────────────────────────────────────────────────────────────────────
