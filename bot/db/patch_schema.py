"""
Автоматически добавляет недостающие столбцы в существующие таблицы.
Запускается один раз при старте контейнера. Если столбец уже есть — пропускает.
"""

import asyncio
import logging

from sqlalchemy import text, inspect

from .database import engine  # тот же engine, который ты уже используешь

logger = logging.getLogger(__name__)

# ------------ что именно патчить -----------------
PATCHES: list[tuple[str, str, str]] = [
    # (table, column, DDL)
    (
        "matches",
        "status",
        "ALTER TABLE matches ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled'"
    ),
    (
        "matches",
        "matchday",
        "ALTER TABLE matches ADD COLUMN matchday INT"
    ),
]
# --------------------------------------------------


async def _apply_patches() -> None:
    """Проверяем каждую пару (table, column); если столбца нет — выполняем ALTER."""
    async with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        for table, column, ddl in PATCHES:
            if table not in tables:
                logger.warning("Таблица %s не найдена — пропуск", table)
                continue

            columns = {col["name"] for col in inspector.get_columns(table)}
            if column in columns:
                logger.info("Столбец %s.%s уже есть", table, column)
                continue

            logger.info("Добавляем столбец %s.%s", table, column)
            await conn.execute(text(ddl))
            logger.info("✅ ALTER выполнен: %s", ddl)


def run_sync() -> None:
    """Вспомогательная синхронная обёртка (удобно вызывать из main.py)."""
    try:
        asyncio.run(_apply_patches())
    except Exception:
        logger.exception("‼️ Ошибка при применении патчей (бот всё-таки стартует)")
