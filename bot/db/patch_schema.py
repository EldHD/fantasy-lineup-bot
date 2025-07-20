# bot/db/patch_schema.py
"""
Патчи схемы БД, выполняющиеся при старте бота.

Добавляет недостающие колонки в таблицу matches:
    • matchday  INT
    • status    VARCHAR(20) DEFAULT 'scheduled'

▪ apply_sync()  – вызывается из main.py до запуска event-loop
▪ apply_async() – можно вызвать из любой async-функции
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from bot.config import DATABASE_URL

log = logging.getLogger(__name__)

# ---------- подключаемся к БД ------------------------------------------------
ASYNC_ENGINE: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

# ---------- internal helpers -------------------------------------------------
async def _columns_present() -> set[str]:
    """Возвращает множество колонок, которые уже есть в matches."""
    async with ASYNC_ENGINE.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {
                row["column_name"]                      # <-- исправлено!
                for row in c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'matches'"
                    )
                ).mappings()
            }
        )
    return cols


async def _apply_patches() -> None:
    desired_ddl: dict[str, str] = {
        "matchday": "ALTER TABLE matches ADD COLUMN matchday INT",
        "status": (
            "ALTER TABLE matches "
            "ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"
        ),
    }

    present = await _columns_present()
    missing = desired_ddl.keys() - present

    if not missing:
        log.info("✅ База данных готова – патчи не требуются")
        return

    async with ASYNC_ENGINE.begin() as conn:
        for col in missing:
            ddl = desired_ddl[col]
            log.info("➕ %s", ddl)
            await conn.execute(text(ddl))

    log.info("✅ Патчи применены: %s", ", ".join(sorted(missing)))


# ---------- публичные функции ----------------------------------------------
async def apply_async() -> None:
    """Асинхронная версия – используйте внутри async-кода."""
    try:
        await _apply_patches()
    finally:
        await ASYNC_ENGINE.dispose()


def apply_sync() -> None:
    """
    Синхронная обёртка – удобно вызывать из main.py
    до запуска event-loop (asyncio.run).
    """
    asyncio.run(apply_async())
