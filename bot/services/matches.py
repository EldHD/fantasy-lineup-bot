import logging
import time
from typing import List, Dict, Tuple, Optional

from bot.external.sofascore import fetch_league_matches_with_meta

logger = logging.getLogger(__name__)

_CACHE: Dict[str, dict] = {}
CACHE_TTL_SEC = 60 * 10  # 10 минут

async def get_upcoming_matches_for_league(league_code: str, limit: int = 8) -> Tuple[List[Dict], dict]:
    """
    Возвращает (matches, meta).
    Кэшируем и матчи, и мета-информацию.
    """
    now = time.time()
    cached = _CACHE.get(league_code)
    if cached and (now - cached["ts"] < CACHE_TTL_SEC):
        logger.debug("Matches cache hit for %s (items=%d)", league_code, len(cached["matches"]))
        matches = cached["matches"]
        meta = cached["meta"]
    else:
        logger.debug("Matches cache miss for %s – fetching...", league_code)
        try:
            matches, meta = await fetch_league_matches_with_meta(league_code, limit=limit)
        except Exception as e:
            logger.exception("fetch_league_matches_with_meta error for %s", league_code)
            matches, meta = [], {
                "league_code": league_code,
                "reason": f"Внутренняя ошибка: {e}",
                "requests": [],
                "link": None
            }
        _CACHE[league_code] = {
            "ts": now,
            "matches": matches,
            "meta": meta
        }

    if limit and len(matches) > limit:
        matches = matches[:limit]
    return matches, meta


def clear_matches_cache(league_code: Optional[str] = None):
    if league_code:
        _CACHE.pop(league_code, None)
        logger.info("Cleared matches cache for %s", league_code)
    else:
        _CACHE.clear()
        logger.info("Cleared matches cache ALL")
