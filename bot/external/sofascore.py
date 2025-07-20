import asyncio
import httpx
from typing import Any, Dict, Optional, Tuple
from bot.config import SOFASCORE_BASE, SOFASCORE_TOURNAMENT_IDS

DEFAULT_TIMEOUT = 15.0

class SofascoreError(Exception):
    """Общее исключение для ошибок при работе с Sofascore."""
    def __init__(self, message: str, *, endpoint: str | None = None, status: int | None = None,
                 payload: dict | None = None):
        super().__init__(message)
        self.endpoint = endpoint
        self.status = status
        self.payload = payload or {}


async def _request_json(client: httpx.AsyncClient, endpoint: str) -> dict:
    url = f"{SOFASCORE_BASE}/{endpoint}"
    try:
        resp = await client.get(url)
    except Exception as e:
        raise SofascoreError(f"Request exception: {e}", endpoint=endpoint) from e
    if resp.status_code != 200:
        snippet = ""
        try:
            snippet = resp.text[:200]
        except Exception:
            pass
        raise SofascoreError(
            f"HTTP {resp.status_code}",
            endpoint=endpoint,
            status=resp.status_code,
            payload={"snippet": snippet}
        )
    try:
        return resp.json()
    except Exception as e:
        raise SofascoreError(f"Invalid JSON: {e}", endpoint=endpoint) from e


async def get_or_guess_season_id(league_code: str) -> Tuple[Optional[int], Optional[dict]]:
    """
    Для некоторых турниров можно получить «текущий» сезон из endpoints,
    но чтобы не усложнять пока – возвращаем None (пусть наружная логика fallback’ит),
    либо можно захардкодить (пример: EPL сезон 2024/2025 => 76986).
    """
    # Можно сделать простую мапу (временный костыль – до динамического определения).
    HARDCODE = {
        "epl": 76986,
        # Добавляй по необходимости другие лиги.
    }
    season_id = HARDCODE.get(league_code)
    if season_id:
        return season_id, None
    return None, {"message": "Season ID not resolved"}


async def fetch_upcoming_events(
    league_code: str,
    limit: int | None = None
) -> Tuple[list[dict], Optional[dict]]:
    """
    Возвращает список (не более limit) «следующих» событий турнира (если эндпоинт поддерживает).
    Формат ответа: (events, error_dict)
    error_dict = { message, endpoint, status, season_id, attempts: [...] }
    """
    unique_tournament_id = SOFASCORE_TOURNAMENT_IDS.get(league_code)
    if not unique_tournament_id:
        return [], {
            "message": f"No Sofascore tournament id for league '{league_code}'"
        }

    season_id, season_err = await get_or_guess_season_id(league_code)

    attempts: list[dict[str, Any]] = []
    events: list[dict] = []
    client_timeout = httpx.Timeout(DEFAULT_TIMEOUT)

    async with httpx.AsyncClient(timeout=client_timeout, http2=False) as client:
        # Пытаемся сначала «upcoming» (next)
        endpoints = []
        if season_id:
            # эндпоинт “season events next” – структура может меняться, уточняем
            endpoints.append(f"unique-tournament/{unique_tournament_id}/season/{season_id}/events/next/0")
        # fallback – общий upcoming для турнира (некоторые турниры работают без season)
        endpoints.append(f"unique-tournament/{unique_tournament_id}/events/next/0")

        first_error: SofascoreError | None = None

        for ep in endpoints:
            try:
                data = await _request_json(client, ep)
                # Примерная структура: { "events":[ ... ] }
                raw_events = data.get("events") or []
                events = raw_events
                break
            except SofascoreError as e:
                attempts.append({
                    "endpoint": e.endpoint,
                    "status": e.status or 0,
                    "error": str(e),
                    "snippet": e.payload.get("snippet", "")
                })
                if first_error is None:
                    first_error = e
                # Подождём немного между попытками
                await asyncio.sleep(0.4)

    if not events:
        # Если совсем нет событий
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

    # Упрощённый набор полей, которые могут пригодиться
    normalized = []
    for ev in events:
        norm = {
            "id": ev.get("id"),
            "homeTeam": ev.get("homeTeam", {}).get("name"),
            "awayTeam": ev.get("awayTeam", {}).get("name"),
            "startTimestamp": ev.get("startTimestamp"),
            "status": ev.get("status", {}).get("type"),
            "roundInfo": ev.get("roundInfo"),
        }
        normalized.append(norm)

    return normalized, None
