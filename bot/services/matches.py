import logging
import time
from typing import List, Dict

from bot.external.sofascore import fetch_league_matches

logger = logging.getLogger(__name__)

# Простой in-memory кэш (процессный). На прод с несколькими инстансами нужна БД/redis.
_CACHE: Dict[str, dict] = {}
CACHE_TTL_SEC = 60 * 10  # 10 минут


async def get_upcoming_matches_for_league(league_code: str, limit: int = 8) -> List[Dict]:
    """
    Возвращает (с кэшем) список ближайших матчей.
    """
    now = time.time()
    cached = _CACHE.get(league_code)
    if cached and (now - cached["ts"] < CACHE_TTL_SEC):
        return cached["data"]

    try:
        data = await fetch_league_matches(league_code, limit=limit)
    except Exception as e:
        logger.exception("Failed to fetch matches for %s: %s", league_code, e)
        data = []

    _CACHE[league_code] = {"ts": now, "data": data}
    return data


def clear_matches_cache(league_code: str | None = None):
    """
    Опционально: очистка кэша (можно вызвать из команды админа).
    """
    if league_code:
        _CACHE.pop(league_code, None)
    else:
        _CACHE.clear()
