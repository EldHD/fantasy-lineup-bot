# bot/db/patch_schema.py
import logging
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncEngine
from .database import engine                # ваш общий AsyncEngine

log = logging.getLogger(__name__)

PATCHES = [
    # (table, column, DDL)
    ("matches", "status",
     "ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"),
    ("matches", "matchday",
     "ALTER TABLE matches ADD COLUMN matchday INT")
]


async def apply_async(engine_: AsyncEngine = engine) -> None:
    """Добавляет недостающие колонки без обёртки‐транзакции."""
    async with engine_.connect() as ac:
        def _collect(meta_conn):
            insp = inspect(meta_conn)                   # ← вот ключ
            return {
                t: {c["name"] for c in insp.get_columns(t)}
                for t in insp.get_table_names()
            }

        tables_cols = await ac.run_sync(_collect)

        for table, col, ddl in PATCHES:
            if col in tables_cols.get(table, set()):
                log.debug("✓ %s.%s уже есть", table, col)
                continue
            log.info("➕ %s", ddl)
            await ac.execute(text(ddl).execution_options(autocommit=True))
