"""
Патч схемы БД перед стартом бота.
Работает на уже открытом event-loop (см. main.py).
"""
import logging
from sqlalchemy import text, inspect
from .database import engine

log = logging.getLogger(__name__)

# ➊  список «таблица, колонка, DDL» – можете пополнять по мере нужды
PATCHES: list[tuple[str, str, str]] = [
    ("matches", "status",
     "ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"),
    ("matches", "matchday",
     "ALTER TABLE matches ADD COLUMN matchday INT"),
]


async def apply_async() -> None:
    """Добавляет отсутствующие колонки (idempotent)."""
    async with engine.begin() as async_conn:

        async def _sync(sync_conn):
            insp = inspect(sync_conn)
            existing = {
                table: {c["name"] for c in insp.get_columns(table)}
                for table in insp.get_table_names()
            }

            for table, col, ddl in PATCHES:
                if col in existing.get(table, set()):
                    log.debug("✓ %s.%s уже есть", table, col)
                    continue
                log.info("➕ apply patch: %s", ddl)
                sync_conn.execute(text(ddl))

        await async_conn.run_sync(_sync)
