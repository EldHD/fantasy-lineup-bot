# bot/db/patch_schema.py
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from .database import engine           # ваш общий AsyncEngine

log = logging.getLogger(__name__)

PATCHES = [
    # (таблица, колонка, DDL)
    ("matches", "status",
     "ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"),
    ("matches", "matchday",
     "ALTER TABLE matches ADD COLUMN matchday INT"),
]


async def apply_async(engine_: AsyncEngine = engine) -> None:
    """Добавляет отсутствующие колонки без транзакции."""
    async with engine_.connect() as ac:
        insp = await ac.run_sync(lambda c: {
            t: {col["name"] for col in c.get_columns(t)}
            for t in c.get_table_names()
        })
        for table, col, ddl in PATCHES:
            if col in insp.get(table, set()):
                log.debug("✓ %s.%s уже есть", table, col)
                continue
            log.info("➕ %s", ddl)
            # DDL выполняем AUTOCOMMIT-ом, чтобы сразу было видно
            await ac.execute(text(ddl).execution_options(autocommit=True))
