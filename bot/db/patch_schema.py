"""
Патч-скhema: добавляем отсутствующие столбцы.
Запускать — до старта бота!
"""

import logging
from sqlalchemy import text, inspect

from .database import engine  # async engine

log = logging.getLogger(__name__)

PATCHES: list[tuple[str, str, str]] = [
    ("matches", "status",
     "ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"),
    ("matches", "matchday",
     "ALTER TABLE matches ADD COLUMN matchday INT"),
]


async def _apply_async():
    async with engine.begin() as conn:            # ← async-соединение

        async def _sync_part(sync_conn):
            insp = inspect(sync_conn)             # ← уже sync-conn
            tables = insp.get_table_names()

            for table, column, ddl in PATCHES:
                if table not in tables:
                    log.warning("table %s missing – skip", table)
                    continue

                names = {c["name"] for c in insp.get_columns(table)}
                if column in names:
                    log.info("column %s.%s already exists", table, column)
                    continue

                log.info("ALTER %s", ddl)
                sync_conn.execute(text(ddl))

        await conn.run_sync(_sync_part)           # ← запускаем sync-блок


def run_sync() -> None:
    """
    Блокирующий вызов из main.py.
    Ошибки — только в лог; бот всё-таки должен стартовать.
    """
    import asyncio

    try:
        asyncio.run(_apply_async())
    except Exception:  # noqa
        log.exception("‼️ Ошибка при patch_schema (игнорирую)")
