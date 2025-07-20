# bot/db/patch_schema.py
"""
Патч-скрипт для схемы БД.
Добавляет недостающие колонки, если их ещё нет.
Запускается синхронно при старте бота.
"""

import logging
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine
from bot.config import DATABASE_URL

log = logging.getLogger(__name__)

# асинхронный движок в проекте
async_engine = create_async_engine(DATABASE_URL, echo=False, future=True)
# sync-обёртка для работы в текущем потоке
sync_engine = async_engine.sync_engine


def apply_sync() -> None:
    """Одноразовая проверка/патч схемы."""
    with sync_engine.begin() as conn:
        insp = inspect(conn)

        # -- matches.status ---------------------------------------------------
        if "status" not in insp.get_columns("matches"):
            log.info("➕ ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'")
            conn.execute(text(
                "ALTER TABLE matches "
                "ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"
            ))

        # -- matches.matchday -------------------------------------------------
        if "matchday" not in insp.get_columns("matches"):
            log.info("➕ ALTER TABLE matches ADD COLUMN matchday INT")
            conn.execute(text(
                "ALTER TABLE matches "
                "ADD COLUMN matchday INT"
            ))

        conn.commit()
