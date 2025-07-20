import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# ---------- Общий HTTP клиент ----------
_DEFAULT_TIMEOUT = 20.0


async def _fetch_json(url: str, *, referer: Optional[str] = None) -> Optional[dict]:
    """
    Универсальная обёртка GET -> JSON.
    Возвращает dict или None при ошибке.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.8",
        "Origin": "https://www.sofascore.com",
        "Referer": referer or "https://www.sofascore.com/",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 200:
                return r.json()
            else:
                snippet = r.text[:200]
                logger.warning("SofaScore GET %s -> %s (%s)", url, r.status_code, snippet)
    except httpx.HTTPError as e:
        logger.error("HTTP error %s fetching %s", e, url)
    except Exception as e:
        logger.exception("Unexpected error fetching %s: %s", url, e)
    return None


# ---------- Матчи турниров ----------
# Маппинг кодов лиг -> (unique tournament id, season id)
# season_id нужно обновлять в начале нового сезона.
SOFASCORE_TOURNAMENTS = {
    "epl":       {"utid": 17,  "season": 52186},  # Premier League 2024/25
    "laliga":    {"utid": 8,   "season": 52177},  # La Liga
    "seriea":    {"utid": 23,  "season": 52192},  # Serie A
    "bundesliga":{"utid": 35,  "season": 52157},  # Bundesliga
    "ligue1":    {"utid": 34,  "season": 52187},  # Ligue 1
    "rpl":       {"utid": 203, "season": 52170},  # Russian Premier League
}


async def fetch_league_matches(league_code: str, limit: int = 10) -> List[Dict]:
    """
    Получить ближайшие (не начавшиеся) матчи для лиги из SofaScore.
    Возвращает список словарей:
    {
        'matchday': int | None,
        'home_team': str,
        'away_team': str,
        'kickoff_utc': datetime,
        'start_ts': int,
    }
    """
    info = SOFASCORE_TOURNAMENTS.get(league_code)
    if not info:
        logger.warning("Unknown league_code=%s for SofaScore", league_code)
        return []

    utid = info["utid"]
    season = info["season"]

    url = f"https://api.sofascore.com/api/v1/unique-tournament/{utid}/season/{season}/events"
    data = await _fetch_json(url)
    if not data or "events" not in data:
        return []

    events = data["events"]
    upcoming = []
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())

    for ev in events:
        # Статус матча
        status = ev.get("status", {}).get("type")
        start_ts = ev.get("startTimestamp")
        if status not in ("notstarted", "postponed") or not start_ts:
            continue
        if start_ts < now_ts:  # на всякий случай
            continue

        home = ev.get("homeTeam", {}).get("name") or "?"
        away = ev.get("awayTeam", {}).get("name") or "?"
        round_info = ev.get("roundInfo", {})
        matchday = round_info.get("round") or ev.get("round")

        kickoff_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        upcoming.append(
            {
                "matchday": matchday,
                "home_team": home,
                "away_team": away,
                "kickoff_utc": kickoff_dt,
                "start_ts": start_ts,
            }
        )

    # сортировка и ограничение
    upcoming.sort(key=lambda x: x["start_ts"])
    if limit:
        upcoming = upcoming[:limit]
    return upcoming


# Простой тест локально:
if __name__ == "__main__":
    async def _t():
        res = await fetch_league_matches("epl", limit=5)
        for r in res:
            print(r)
    asyncio.run(_t())
