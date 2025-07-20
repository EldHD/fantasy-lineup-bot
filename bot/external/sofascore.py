import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Базовый таймаут
_DEFAULT_TIMEOUT = 25.0

# Маппинг кодов турниров -> unique tournament id (utid)
SOFASCORE_TOURNAMENTS = {
    "epl":       17,    # Premier League
    "laliga":     8,
    "seriea":    23,
    "bundesliga":35,
    "ligue1":    34,
    "rpl":      203,
}


# ---------- ВСПОМОГАТЕЛЬНОЕ HTTP ----------

async def _fetch_json(url: str, *, referer: Optional[str] = None) -> Optional[dict]:
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
                try:
                    return r.json()
                except Exception as e:
                    logger.error("JSON parse error for %s: %s", url, e)
            else:
                snippet = (r.text or "")[:240]
                logger.warning(
                    "SofaScore GET %s -> %s; snippet=%r",
                    url, r.status_code, snippet
                )
    except httpx.HTTPError as e:
        logger.error("HTTP error %s fetching %s", e, url)
    except Exception as e:
        logger.exception("Unexpected error fetching %s: %s", url, e)
    return None


# ---------- ВЫБОР ТЕКУЩЕГО СЕЗОНА ----------

async def _resolve_current_season(utid: int) -> Optional[int]:
    """
    Получить актуальный season_id для unique tournament.
    Берём тот, у которого isCurrent = True, иначе – последний по startDate.
    """
    seasons_url = f"https://api.sofascore.com/api/v1/unique-tournament/{utid}/seasons"
    data = await _fetch_json(seasons_url)
    if not data or "seasons" not in data:
        logger.warning("No seasons data for utid=%s", utid)
        return None
    seasons = data["seasons"]
    if not seasons:
        logger.warning("Empty seasons list for utid=%s", utid)
        return None

    current = [s for s in seasons if s.get("isCurrent")]
    if current:
        season_id = current[0].get("id")
        logger.debug("Resolved current season (isCurrent) utid=%s -> %s", utid, season_id)
        return season_id

    # fallback: последний по startTimestamp
    seasons_sorted = sorted(
        seasons,
        key=lambda s: s.get("startTimestamp") or 0,
        reverse=True
    )
    season_id = seasons_sorted[0].get("id")
    logger.debug("Resolved current season (fallback last) utid=%s -> %s", utid, season_id)
    return season_id


# ---------- ЗАГРУЗКА МАТЧЕЙ ----------

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
        or ev.get("roundInfo", {}).get("name")
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


async def fetch_league_matches(league_code: str, limit: int = 10) -> List[Dict]:
    """
    Универсальная функция получения ближайших матчей:
      1) Находим utid
      2) Подтягиваем актуальный season_id
      3) Пробуем массив /events
      4) Если итог < limit — догружаем через /events/next/{page}
    """
    utid = SOFASCORE_TOURNAMENTS.get(league_code)
    if not utid:
        logger.warning("Unknown league_code=%s (no utid)", league_code)
        return []

    season_id = await _resolve_current_season(utid)
    if not season_id:
        logger.warning("Could not resolve season for league_code=%s utid=%s", league_code, utid)
        return []

    # 1) Основной список событий сезона
    events_url = f"https://api.sofascore.com/api/v1/unique-tournament/{utid}/season/{season_id}/events"
    data = await _fetch_json(events_url)
    collected: List[Dict] = []
    if data and "events" in data:
        raw_events = data["events"]
        logger.debug("Fetched %d events for %s (season=%s)", len(raw_events), league_code, season_id)
        for ev in raw_events:
            rec = _event_to_record(ev)
            if rec:
                collected.append(rec)

    # 2) Если мало — пробуем “next” пагинацию (часто лежат будущие туры)
    page = 0
    # Чтобы не уйти в бесконечную прокрутку: ограничим страниц 6
    while len(collected) < limit and page < 6:
        next_url = (
            f"https://api.sofascore.com/api/v1/unique-tournament/"
            f"{utid}/season/{season_id}/events/next/{page}"
        )
        next_data = await _fetch_json(next_url)
        page += 1
        if not next_data or "events" not in next_data:
            break
        new_added = 0
        for ev in next_data["events"]:
            rec = _event_to_record(ev)
            if rec:
                # Исключим дубликаты (по start_ts + пара команд)
                if not any(
                    r["start_ts"] == rec["start_ts"]
                    and r["home_team"] == rec["home_team"]
                    and r["away_team"] == rec["away_team"]
                    for r in collected
                ):
                    collected.append(rec)
                    new_added += 1
        logger.debug(
            "Page %s added %s new upcoming events (total=%s) for %s",
            page, new_added, len(collected), league_code
        )
        if new_added == 0:
            # Ничего нового — останавливаемся
            break

    # Сортировка и ограничение
    collected.sort(key=lambda r: r["start_ts"])
    if limit:
        collected = collected[:limit]

    logger.info(
        "fetch_league_matches(%s) -> %d upcoming matches (season=%s)",
        league_code, len(collected), season_id
    )
    return collected


# ---------- Отладочная функция ----------

async def debug_fetch_league_matches(league_code: str):
    res = await fetch_league_matches(league_code, limit=12)
    logger.info("DEBUG %s matches:", league_code)
    for r in res:
        logger.info(
            "%s: %s vs %s (%s UTC) md=%s",
            league_code, r["home_team"], r["away_team"], r["kickoff_utc"], r["matchday"]
        )
    return res


# Локальный тест
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    async def _t():
        await debug_fetch_league_matches("epl")
    asyncio.run(_t())
