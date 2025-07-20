import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from bot.external.sofascore import (
    get_or_guess_season_id,
    get_upcoming_matches,
)

logger = logging.getLogger(__name__)

# Коды турниров SofaScore (пример: EPL = 17)
TOURNAMENT_ID_BY_CODE = {
    "epl": 17,
    "laliga": 8,
    "seriea": 23,
    "bundesliga": 35,
    "ligue1": 34,
    "rpl": 203,   # пример, проверь реальный ID, если нужно
}

# Кэш: { league_code: { "season_id": int, "events": [...], "fetched_at": datetime } }
_MATCH_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 15 * 60  # 15 минут

def _cache_valid(entry: Dict[str, Any]) -> bool:
    ts: datetime = entry.get("fetched_at")
    if not ts:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age < CACHE_TTL_SECONDS

async def load_matches_for_league(league_code: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Возвращает структуру:
    {
      "ok": bool,
      "league_code": str,
      "events": [...],
      "season_id": ..,
      "error": str|None,
      "attempts": [...],
      "debug": {...},
    }
    """
    league_code = league_code.lower()
    if league_code not in TOURNAMENT_ID_BY_CODE:
        return {
            "ok": False,
            "league_code": league_code,
            "events": [],
            "season_id": None,
            "error": f"Unknown league code '{league_code}'",
            "attempts": [],
            "debug": {},
        }

    # Кэш
    if not force_refresh:
        cache_entry = _MATCH_CACHE.get(league_code)
        if cache_entry and _cache_valid(cache_entry):
            return {
                "ok": True,
                "league_code": league_code,
                "events": cache_entry["events"],
                "season_id": cache_entry["season_id"],
                "error": None,
                "attempts": cache_entry.get("attempts", []),
                "debug": {"cached": True},
            }

    tournament_id = TOURNAMENT_ID_BY_CODE[league_code]
    season_id, debug_season = await get_or_guess_season_id(tournament_id)
    if not season_id:
        return {
            "ok": False,
            "league_code": league_code,
            "events": [],
            "season_id": None,
            "error": f"Cannot determine season for tournament {tournament_id}",
            "attempts": [],
            "debug": {"season_debug": debug_season},
        }

    matches_resp = await get_upcoming_matches(season_id=season_id, tournament_id=tournament_id, limit=40)
    events = matches_resp.get("events", [])
    attempts = matches_resp.get("attempts", [])
    errors = matches_resp.get("errors", [])

    if not events:
        # формируем читабельное описание
        err_msg = "Нет матчей"
        if errors:
            err_msg += f"; errors: {errors[:2]}"
        return {
            "ok": False,
            "league_code": league_code,
            "events": [],
            "season_id": season_id,
            "error": err_msg,
            "attempts": attempts,
            "debug": {"season_debug": debug_season},
        }

    # Сохраняем в кэш
    _MATCH_CACHE[league_code] = {
        "season_id": season_id,
        "events": events,
        "attempts": attempts,
        "fetched_at": datetime.now(timezone.utc),
    }

    return {
        "ok": True,
        "league_code": league_code,
        "events": events,
        "season_id": season_id,
        "error": None,
        "attempts": attempts,
        "debug": {"season_debug": debug_season},
    }

def format_events_short(events: List[Dict[str, Any]], limit: int = 8) -> str:
    """
    Форматируем список матчей в короткий текст.
    """
    lines: List[str] = []
    for ev in events[:limit]:
        h = (ev.get("homeTeam") or {}).get("name", "Home")
        a = (ev.get("awayTeam") or {}).get("name", "Away")
        ts = ev.get("startTimestamp")
        if ts:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            kick = dt.strftime("%Y-%m-%d %H:%M UTC")
        else:
            kick = "TBD"
        lines.append(f"{h} vs {a} — {kick}")
    return "\n".join(lines)
