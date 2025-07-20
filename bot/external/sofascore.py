import asyncio
import httpx
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SOFASCORE_BASE = "https://api.sofascore.com/api/v1"

# Базовые заголовки “как браузер”
DEFAULT_HEADERS = {
    "User-Agent": os.getenv("HTTP_USER_AGENT",
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
    "Connection": "keep-alive",
}

class SofaScoreError(Exception):
    """Общая ошибка взаимодействия с SofaScore"""

async def get_json(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    retry_delay: float = 1.2,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    """
    Универсальный запрос к SofaScore.
    Возвращает (json_or_none, error_message_or_none, status_code)
    Не выбрасывает исключение – чтобы хендлеры могли формировать детальные ответы.
    """
    url = f"{SOFASCORE_BASE}/{path.lstrip('/')}"
    last_err = None
    status = 0
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(http2=True, timeout=10.0, headers=DEFAULT_HEADERS) as client:
                resp = await client.get(url, params=params)
                status = resp.status_code
                if status == 200:
                    try:
                        return resp.json(), None, status
                    except Exception as je:
                        last_err = f"JSON decode error: {je}"
                        break
                elif status in (403, 429, 503):
                    # Лимит / блок / временно недоступно
                    last_err = f"HTTP {status} {resp.text.strip()[:180]}"
                    if attempt < max_retries:
                        await asyncio.sleep(retry_delay * attempt)
                        continue
                    break
                else:
                    last_err = f"HTTP {status} {resp.text.strip()[:180]}"
                    break
        except Exception as e:
            last_err = f"Request exception: {e}"
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)
                continue
            break
    return None, last_err, status


async def fetch_seasons(unique_tournament_id: int) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], int]:
    data, err, status = await get_json(f"unique-tournament/{unique_tournament_id}/seasons")
    if data and "seasons" in data:
        return data["seasons"], None, status
    if err is None:
        err = "Unknown seasons format"
    return None, err, status


async def get_or_guess_season_id(
    unique_tournament_id: int,
    fallback_env_name: str = "",
) -> Tuple[Optional[int], Dict[str, Any]]:
    """
    Возвращает (season_id, debug_info).
    debug_info содержит подробности попыток, чтобы вывести пользователю.
    Логика:
      1. Попытка получить список сезонов.
      2. Если 403/ошибка – берем из ENV (fallback_env_name).
      3. Если нет – возвращаем None.
    """
    debug = {
        "tournament_id": unique_tournament_id,
        "steps": [],
        "season_id": None,
    }

    seasons, err, status = await fetch_seasons(unique_tournament_id)
    if seasons:
        # Берём первый (обычно текущий / будущий)
        season_id = seasons[0]["id"]
        debug["steps"].append({"action": "fetch_seasons", "status": status, "result": "ok", "seasons_count": len(seasons)})
        debug["season_id"] = season_id
        return season_id, debug
    else:
        debug["steps"].append({"action": "fetch_seasons", "status": status, "error": err})
        # Fallback ENV
        if fallback_env_name:
            env_val = os.getenv(fallback_env_name)
            if env_val and env_val.isdigit():
                season_id = int(env_val)
                debug["steps"].append({"action": "env_fallback", "name": fallback_env_name, "value": season_id})
                debug["season_id"] = season_id
                return season_id, debug
            else:
                debug["steps"].append({"action": "env_fallback", "name": fallback_env_name, "error": "not set or not digit"})

    return None, debug


async def fetch_upcoming_matches(
    unique_tournament_id: int,
    season_id: int,
    limit: int = 30,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    """
    Забираем список ближайших матчей турнира (вариант endpoints).
    Пробуем несколько путей:
      1. unique-tournament/<id>/season/<season_id>/events/next/0
      2. unique-tournament/<id>/events/last/<n>?  (как запасной – но нам нужны будущие)
      3. популярный endpoint: unique-tournament/<id>/season/<season_id>/fixtures/round/<x> (сложнее – нужен round)
    Для MVP ограничимся 'events/next/0'.
    Возвращает (matches, debug, error)
    """
    debug = {"attempts": [], "used_endpoint": None}
    matches: List[Dict[str, Any]] = []

    path = f"unique-tournament/{unique_tournament_id}/season/{season_id}/events/next/0"
    data, err, status = await get_json(path)
    debug["attempts"].append({"endpoint": path, "status": status, "error": err})
    if data and "events" in data:
        events = data["events"][:limit]
        for ev in events:
            matches.append({
                "id": ev.get("id"),
                "home": ev.get("homeTeam", {}).get("name"),
                "away": ev.get("awayTeam", {}).get("name"),
                "startTimestamp": ev.get("startTimestamp"),
                "roundInfo": ev.get("roundInfo"),
            })
        debug["used_endpoint"] = path
        return matches, debug, None

    # Если не получилось – сообщаем ошибку
    return [], debug, err or f"Не удалось получить events (status={status})"
