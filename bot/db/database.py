import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Ожидается переменная окружения DATABASE_URL формата:
# postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
