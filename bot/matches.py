import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from bot.external.sofascore import (
    get_or_guess_season_id,
    get_upcoming_matches,
)

logger = logging.getLogger(__name__)

# ID турниров SofaScore (проверь актуальность)
TOURNAMENT_ID_BY_CODE = {
    "epl": 17,
    "laliga": 8,
    "seriea": 23,
    "bundesliga": 35,
    "ligue1": 34,
    "rpl": 203,
}

# Кэш матчей
_MATCH_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 15 * 60  # 15 минут


def _cache_valid(entry: Dict[str, Any]) -> bool:
    ts: datetime = entry.get("fetched_at")
    if not ts:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age < CACHE_TTL_SECONDS


async def load_matches_for_league(
    league_code: str,
    force_refresh: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Возвращает словарь:
    {
      ok: bool,
      league_code: str,
      events: list,
      season_id: int|None,
      error: str|None,
      attempts: list,
      debug: dict
    }

    :param league_code: 'epl', 'laliga', ...
    :param force_refresh: игнорировать кэш
    :param limit: если задан – обрезать список событий до limit
    """
    raw_input = league_code
    league_code = (league_code or "").strip().lower()

    if not league_code:
        return {
            "ok": False,
            "league_code": raw_input,
            "events": [],
            "season_id": None,
            "error": "Empty league code",
            "attempts": [],
            "debug": {},
        }

    if league_code not in TOURNAMENT_ID_BY_CODE:
        return {
            "ok": False,
            "league_code": league_code,
            "events": [],
            "season_id": None,
            "error": f"Unknown league code '{league_code}'",
            "attempts": [],
            "debug": {"input": raw_input},
        }

    # Кэш
    if not force_refresh:
        cache_entry = _MATCH_CACHE.get(league_code)
        if cache_entry and _cache_valid(cache_entry):
            events = cache_entry["events"]
            if limit is not None:
                events = events[:limit]
            return {
                "ok": True,
                "league_code": league_code,
                "events": events,
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

    matches_resp = await get_upcoming_matches(
        season_id=season_id,
        tournament_id=tournament_id,
        limit=200  # вытягиваем «с запасом», потом режем
    )
    events = matches_resp.get("events", [])
    attempts = matches_resp.get("attempts", [])
    errors = matches_resp.get("errors", [])

    if not events:
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

    # Кладём в кэш полную выборку
    _MATCH_CACHE[league_code] = {
        "season_id": season_id,
        "events": events,
        "attempts": attempts,
        "fetched_at": datetime.now(timezone.utc),
    }

    if limit is not None:
        events = events[:limit]

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
