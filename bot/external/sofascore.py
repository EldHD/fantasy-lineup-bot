import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 25.0

# code -> unique tournament id (utid) + человеко-читабельный slug для ссылки
SOFASCORE_TOURNAMENTS = {
    "epl":        {"utid": 17,  "country": "england",  "slug": "premier-league"},
    "laliga":     {"utid": 8,   "country": "spain",    "slug": "laliga"},
    "seriea":     {"utid": 23,  "country": "italy",    "slug": "serie-a"},
    "bundesliga": {"utid": 35,  "country": "germany",  "slug": "bundesliga"},
    "ligue1":     {"utid": 34,  "country": "france",   "slug": "ligue-1"},
    "rpl":        {"utid": 203, "country": "russia",   "slug": "premier-league"},
}

# ---------- ВСПОМОГАТЕЛЬНОЕ HTTP ----------

async def _fetch_json(url: str, *, referer: Optional[str] = None) -> Tuple[Optional[dict], int, Optional[str]]:
    """
    Возвращает (json|None, status_code, error_text_snippet)
    error_text_snippet = обрезок тела при неудачном статусе.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
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
            status = r.status_code
            if status == 200:
                try:
                    return r.json(), status, None
                except Exception as e:
                    logger.error("JSON parse error %s: %s", url, e)
                    return None, status, f"json-parse-error: {e}"
            else:
                snippet = (r.text or "")[:200]
                logger.warning("SofaScore GET %s -> %s; snippet=%r", url, status, snippet)
                return None, status, snippet
    except httpx.HTTPError as e:
        logger.error("HTTP error %s fetching %s", e, url)
        return None, 0, f"http-error: {e}"
    except Exception as e:
        logger.exception("Unexpected error fetching %s", url)
        return None, 0, f"unexpected: {e}"

# ---------- СЕЗОН ----------

async def _resolve_current_season(utid: int, meta: dict) -> Optional[int]:
    seasons_url = f"https://api.sofascore.com/api/v1/unique-tournament/{utid}/seasons"
    data, status, err = await _fetch_json(seasons_url)
    meta["requests"].append({"url": seasons_url, "status": status, "err": err})
    if status != 200 or not data or "seasons" not in data:
        meta["reason"] = f"Не удалось получить список сезонов (status={status})"
        return None
    seasons = data["seasons"]
    if not seasons:
        meta["reason"] = "Пустой список сезонов"
        return None

    current = [s for s in seasons if s.get("isCurrent")]
    if current:
        sid = current[0].get("id")
        meta["season_id"] = sid
        return sid

    seasons_sorted = sorted(seasons, key=lambda s: s.get("startTimestamp") or 0, reverse=True)
    sid = seasons_sorted[0].get("id")
    meta["season_id"] = sid
    meta["season_fallback"] = True
    return sid

# ---------- НОРМАЛИЗАЦИЯ СОБЫТИЯ ----------

def _event_to_record(ev: dict) -> Optional[Dict]:
    start_ts = ev.get("startTimestamp")
    if not start_ts:
        return None
    status_type = ev.get("status", {}).get("type")
    if status_type not in ("notstarted", "postponed"):
        return None
    home = ev.get("homeTeam", {}).get("name")
    away = ev.get("awayTeam", {}).get("name")
    if not home or not away:
        return None
    round_info = ev.get("roundInfo", {})
    matchday = (
        round_info.get("round")
        or ev.get("round")
        or round_info.get("name")
    )
    kickoff_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    return {
        "matchday": matchday,
        "home_team": home,
        "away_team": away,
        "kickoff_utc": kickoff_dt,
        "start_ts": start_ts,
        "raw_id": ev.get("id"),
    }

# ---------- ОСНОВНАЯ ФУНКЦИЯ ----------

async def fetch_league_matches_with_meta(league_code: str, limit: int = 10) -> Tuple[List[Dict], dict]:
    """
    Возвращает (matches, meta)
    meta содержит:
      - league_code
      - season_id
      - season_fallback (bool)
      - requests: список {url,status,err}
      - raw_events_count
      - raw_next_added
      - reason (почему пусто)
      - link (страница турнира на SofaScore)
    """
    meta = {
        "league_code": league_code,
        "season_id": None,
        "season_fallback": False,
        "requests": [],
        "raw_events_count": 0,
        "raw_next_added": 0,
        "reason": None,
        "link": None,
    }
    info = SOFASCORE_TOURNAMENTS.get(league_code)
    if not info:
        meta["reason"] = "Неизвестный код лиги"
        return [], meta

    utid = info["utid"]
    slug = info["slug"]
    country = info["country"]

    matches: List[Dict] = []

    season_id = await _resolve_current_season(utid, meta)
    if not season_id:
        if meta["reason"] is None:
            meta["reason"] = "Сезон не найден"
        return [], meta

    # Ссылка для пользователя
    meta["link"] = f"https://www.sofascore.com/tournament/football/{country}/{slug}/{season_id}"

    # Основные события
    events_url = f"https://api.sofascore.com/api/v1/unique-tournament/{utid}/season/{season_id}/events"
    data, status, err = await _fetch_json(events_url)
    meta["requests"].append({"url": events_url, "status": status, "err": err})
    if status == 200 and data and "events" in data:
        meta["raw_events_count"] = len(data["events"])
        for ev in data["events"]:
            rec = _event_to_record(ev)
            if rec:
                matches.append(rec)
    else:
        if status != 200:
            meta["reason"] = f"Основной список событий не получен (status={status})"

    # Догрузка через next
    page = 0
    while len(matches) < limit and page < 6:
        next_url = (
            f"https://api.sofascore.com/api/v1/unique-tournament/"
            f"{utid}/season/{season_id}/events/next/{page}"
        )
        next_data, nstatus, nerr = await _fetch_json(next_url)
        meta["requests"].append({"url": next_url, "status": nstatus, "err": nerr})
        page += 1
        if nstatus != 200 or not next_data or "events" not in next_data:
            break
        added_here = 0
        for ev in next_data["events"]:
            rec = _event_to_record(ev)
            if rec:
                if not any(
                    r["start_ts"] == rec["start_ts"] and
                    r["home_team"] == rec["home_team"] and
                    r["away_team"] == rec["away_team"]
                    for r in matches
                ):
                    matches.append(rec)
                    added_here += 1
        meta["raw_next_added"] += added_here
        if added_here == 0:
            break

    matches.sort(key=lambda r: r["start_ts"])
    if limit:
        matches = matches[:limit]

    if not matches and meta["reason"] is None:
        # Определим, это «действительно пусто» или какая-то проблема
        if meta["raw_events_count"] == 0 and meta["raw_next_added"] == 0:
            meta["reason"] = "API вернуло 0 будущих матчей (вероятно календарь ещё не опубликован)"
        else:
            meta["reason"] = "Не удалось собрать подходящие матчи (фильтрация/статусы)"

    logger.info(
        "fetch_league_matches_with_meta(%s) -> %d matches (season=%s) reason=%s",
        league_code, len(matches), season_id, meta["reason"]
    )
    return matches, meta


# Тест локально
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    async def _t():
        m, meta = await fetch_league_matches_with_meta("epl", 12)
        print("Matches:", len(m))
        print("Meta:", meta)
    asyncio.run(_t())
