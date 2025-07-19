import os
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DATABASE URL
# ---------------------------------------------------------------------------
# Ожидается переменная окружения DATABASE_URL или (Railway-style) POSTGRES_xxx
# Если у тебя в Railway автоматически проставлены:
#   PGHOST / PGUSER / PGPASSWORD / PGDATABASE / PGPORT
# можешь собрать строку ниже. Иначе просто задай DATABASE_URL в Variables.
# Формат: postgresql+asyncpg://user:password@host:port/dbname
# ---------------------------------------------------------------------------

def _build_database_url() -> str:
    direct = os.getenv("DATABASE_URL") or os.getenv("DB_URL")
    if direct:
        return direct

    host = os.getenv("PGHOST") or os.getenv("DB_HOST")
    user = os.getenv("PGUSER") or os.getenv("DB_USER")
    password = os.getenv("PGPASSWORD") or os.getenv("DB_PASSWORD")
    dbname = os.getenv("PGDATABASE") or os.getenv("DB_NAME")
    port = os.getenv("PGPORT") or os.getenv("DB_PORT") or "5432"

    if host and user and password and dbname:
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"

    raise RuntimeError("DATABASE_URL (или PG* переменные) не заданы.")

DATABASE_URL = _build_database_url()

# ---------------------------------------------------------------------------
# ASYNC ENGINE + SESSION FACTORY
# ---------------------------------------------------------------------------

engine = create_async_engine(
    DATABASE_URL,
    echo=False,         # можно True для детализированных SQL логов
    future=True,
    pool_pre_ping=True, # проверка соединений
)

# sessionmaker (SQLAlchemy 2.x: async_sessionmaker)
async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Для совместимости с прежним кодом, который мог использовать SessionLocal()
SessionLocal = async_session  # просто псевдоним

# ---------------------------------------------------------------------------
# УТИЛИТА ДЛЯ ПРОВЕРКИ СОЕДИНЕНИЯ (опционально)
# ---------------------------------------------------------------------------

async def test_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.exception("DB connection test failed: %s", e)
        return False

# ---------------------------------------------------------------------------
# Контекстный менеджер (если понадобится в других местах)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_session():
    """
    Пример использования:
        async with get_session() as session:
            await session.execute(...)
    """
    session = async_session()
    try:
        yield session
        # коммит автоматически НЕ вызываем — ответственность вызывающего
    finally:
        await session.close()
