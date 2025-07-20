"""
Непривязанный к loop модуль: даёт корутину apply_async(),
которую вызываем из main.py на уже выбранном event-loop.
"""
import logging
from sqlalchemy import text, inspect

from .database import engine

log = logging.getLogger(__name__)

_PATCHES: list[tuple[str, str, str]] = [
    ("matches", "status",
     "ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"),
    ("matches", "matchday",
     "ALTER TABLE matches ADD COLUMN matchday INT"),
]


async def apply_async() -> None:
    """Добавляем отсутствующие столбцы."""
    async with engine.begin() as conn:

        async def _sync(sync_conn):
            insp = inspect(sync_conn)
            tables = insp.get_table_names()

            for table, col, ddl in _PATCHES:
                if table not in tables:
                    log.warning("table %s missing – skip", table)
                    continue
                if col in {c["name"] for c in insp.get_columns(table)}:
                    log.info("column %s.%s already exists", table, col)
                    continue

                log.info("apply patch → %s", ddl)
                sync_conn.execute(text(ddl))

        await conn.run_sync(_sync)
