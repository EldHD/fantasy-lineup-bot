import logging
from sqlalchemy import text
from bot.db.database import engine
from bot.db.models import Base

log = logging.getLogger(__name__)

async def apply_async() -> None:
    """Создаём таблицы при первом запуске."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        log.info("✅ База данных готова")
