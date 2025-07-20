import logging
import time
from typing import List, Dict, Optional

from bot.external.sofascore import fetch_league_matches

logger = logging.getLogger(__name__)

# In-memory кэш
_CACHE: Dict[str, dict] = {}
CACHE_TTL_SEC = 60 * 10  # 10 минут


async def get_upcoming_matches_for_league(league_code: str, limit: int = 8) -> List[Dict]:
    """
    Получить кэшированные ближайшие матчи.
    Если кэш свежий – берём из него, иначе тянем заново.
    """
    now = time.time()
    cached = _CACHE.get(league_code)
    if cached and (now - cached["ts"] < CACHE_TTL_SEC):
        logger.debug("Matches cache hit for %s (items=%d)", league_code, len(cached['data']))
        data = cached["data"]
    else:
        logger.debug("Matches cache miss for %s – fetching...", league_code)
        try:
            data = await fetch_league_matches(league_code, limit=limit)
        except Exception as e:
            logger.exception("fetch_league_matches error for %s: %s", league_code, e)
            data = []
        _CACHE[league_code] = {"ts": now, "data": data}

    if len(data) > limit:
        return data[:limit]
    return data


def clear_matches_cache(league_code: Optional[str] = None):
    if league_code:
        _CACHE.pop(league_code, None)
        logger.info("Cleared matches cache for %s", league_code)
    else:
        _CACHE.clear()
        logger.info("Cleared matches cache ALL")
