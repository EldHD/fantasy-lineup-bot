import asyncio
import random
import time
from typing import Any, Dict, Optional, Tuple, List

import httpx
from bot.config import SOFASCORE_BASE, SOFASCORE_TOURNAMENT_IDS

DEFAULT_TIMEOUT = 15.0
MAX_ATTEMPTS_PER_ENDPOINT = 2
BACKOFF_BASE = 0.5
CACHE_TTL = 180  # секунд – кэшируем успешный результат чтобы не спамить
USE_HTTP2 = False  # если поставишь True – нужно установить зависимость h2

# Простейший in-memory кэш (процесс живёт – кэш живёт)
_cache: dict[str, dict] = {}


class SofascoreError(Exception):
    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        status: int | None = None,
        payload: dict | None = None
    ):
        super().__init__(message)
        self.endpoint = endpoint
        self.status = status
        self.payload = payload or {}


# --- Сезон (временный костыль) ---
HARDCODE_SEASONS = {
    "epl": 76986,
    # добавь другие если выяснишь ID
}


async def get_or_guess_season_id(league_code: str) -> Tuple[Optional[int], Optional[dict]]:
    season_id = HARDCODE_SEASONS.get(league_code)
    if season_id:
        return season_id, None
    return None, {"message": "Season ID not resolved"}


def _browser_headers() -> Dict[str, str]:
    # Несколько вариантов UA можно ротировать
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko)"
        " Version/16.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/123.0.0.0 Safari/537.36",
    ]
    return {
        "User-Agent": random.choice(ua_pool),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.sofascore.com",
        "Referer": "https://www.sofascore.com/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


async def _request_json(client: httpx.AsyncClient, endpoint: str) -> dict:
    url = f"{SOFASCORE_BASE}/{endpoint}"
    try:
        resp = await client.get(url, headers=_browser_headers())
    except Exception as e:
        raise SofascoreError(f"Request exception: {e}", endpoint=endpoint) from e
    if resp.status_code != 200:
        snippet = ""
        try:
            snippet = resp.text[:250]
        except Exception:
            pass
        raise SofascoreError(
            f"HTTP {resp.status_code}",
            endpoint=endpoint,
            status=resp.status_code,
            payload={"snippet": snippet},
        )
    try:
        return resp.json()
    except Exception as e:
        raise SofascoreError(f"Invalid JSON: {e}", endpoint=endpoint) from e


def _cache_key(league_code: str, limit: int | None) -> str:
    return f"events:{league_code}:{limit or 0}"


def _get_cached(league_code: str, limit: int | None):
    key = _cache_key(league_code, limit)
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > CACHE_TTL:
        _cache.pop(key, None)
        return None
    return entry["data"]


def _set_cached(league_code: str, limit: int | None, data):
    key = _cache_key(league_code, limit)
    _cache[key] = {"ts": time.time(), "data": data}


async def fetch_upcoming_events(
    league_code: str,
    limit: int | None = None
) -> Tuple[list[dict], Optional[dict]]:
    """
    Возвращает (events, err_dict)
    err_dict: { message, attempts: [...], season_id, tournament_id, season_resolve_error }
    """
    # Кэш
    cached = _get_cached(league_code, limit)
    if cached is not None:
        return cached, None

    unique_tournament_id = SOFASCORE_TOURNAMENT_IDS.get(league_code)
    if not unique_tournament_id:
        return [], {"message": f"No Sofascore tournament id for league '{league_code}'"}

    season_id, season_err = await get_or_guess_season_id(league_code)
    # Список эндпоинтов (в порядке приоритетов)
    endpoints: List[str] = []
    if season_id:
        endpoints.append(f"unique-tournament/{unique_tournament_id}/season/{season_id}/events/next/0")
    endpoints.append(f"unique-tournament/{unique_tournament_id}/events/next/0")
    if season_id:
        endpoints.append(f"unique-tournament/{unique_tournament_id}/season/{season_id}/events")
    endpoints.append(f"unique-tournament/{unique_tournament_id}/events")

    attempts: list[dict[str, Any]] = []
    events: list[dict] = []
    first_error: SofascoreError | None = None

    timeout = httpx.Timeout(DEFAULT_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, http2=USE_HTTP2) as client:
        for ep in endpoints:
            success = False
            for attempt in range(1, MAX_ATTEMPTS_PER_ENDPOINT + 1):
                try:
                    data = await _request_json(client, ep)
                    raw_events = data.get("events") or []
                    events = raw_events
                    success = True
                    break
                except SofascoreError as e:
                    attempts.append({
                        "endpoint": e.endpoint,
                        "status": e.status or 0,
                        "error": str(e),
                        "snippet": e.payload.get("snippet", "")[:120],
                        "attempt": attempt,
                    })
                    if first_error is None:
                        first_error = e
                    # 403 часто означает блокировку – не делаем слишком много лишних
                    if e.status == 403:
                        # Немного паузы перед след. эндпоинтом
                        await asyncio.sleep(0.8 + random.uniform(0, 0.4))
                        break
                    else:
                        # backoff
                        await asyncio.sleep(BACKOFF_BASE * attempt + random.uniform(0, 0.3))
            if success and events:
                break

    if not events:
        err_msg = first_error and str(first_error) or "No events returned"
        err_dict = {
            "message": err_msg,
            "season_id": season_id,
            "season_resolve_error": season_err,
            "attempts": attempts,
            "tournament_id": unique_tournament_id,
        }
        return [], err_dict

    if limit and len(events) > limit:
        events = events[:limit]

    normalized = []
    for ev in events:
        normalized.append({
            "id": ev.get("id"),
            "homeTeam": ev.get("homeTeam", {}).get("name"),
            "awayTeam": ev.get("awayTeam", {}).get("name"),
            "startTimestamp": ev.get("startTimestamp"),
            "status": (ev.get("status") or {}).get("type"),
            "slug": ev.get("slug"),
        })

    # Кэшируем
    _set_cached(league_code, limit, normalized)

    return normalized, None
