import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

SOFASCORE_BASE = "https://api.sofascore.com/api/v1"

# ------------ Исключения ------------
class SofaScoreError(Exception):
    pass


# ------------ HTTP клиент с fallback ------------
class SofaScoreClient:
    """
    Async клиент SofaScore.
    Пытается http2 (если включено), при проблеме (нет h2/ошибка) откатывается на http1.
    """

    def __init__(
        self,
        timeout: float = 12.0,
        try_http2: bool = True,
        headers: Optional[Dict[str, str]] = None,
    ):
        base_headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.sofascore.com/",
            "Origin": "https://www.sofascore.com",
        }
        if headers:
            base_headers.update(headers)

        self._try_http2 = try_http2
        self._timeout = timeout
        self._headers = base_headers
        self._client: Optional[httpx.AsyncClient] = None
        self._http2_in_use = False

    async def __aenter__(self):
        await self._init_client()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def _init_client(self):
        if self._client is not None:
            return
        if self._try_http2:
            try:
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    http2=True,
                    headers=self._headers,
                )
                self._http2_in_use = True
            except Exception as e:
                logger.warning("HTTP/2 init failed (%s). Fallback to HTTP/1.1", e)
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._headers,
                )
        else:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=self._headers,
            )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_json(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
        """
        Возвращает (json|None, error|None, status_code|0).
        """
        if self._client is None:
            await self._init_client()

        url = f"{SOFASCORE_BASE}/{endpoint.lstrip('/')}"
        try:
            resp = await self._client.get(url, params=params)
            status = resp.status_code
            if status >= 400:
                snippet = resp.text[:250]
                msg = f"HTTP {status} {snippet}"
                return None, msg, status
            try:
                data = resp.json()
            except Exception as je:
                return None, f"JSON decode error: {je}", status
            return data, None, status
        except Exception as e:
            msg = str(e)
            # Fallback при http2 ошибке
            if self._http2_in_use and ("http2" in msg.lower() or "h2" in msg.lower()):
                logger.warning(
                    "HTTP/2 runtime error (%s). Recreating client as HTTP/1.1", msg
                )
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._headers,
                )
                self._http2_in_use = False
                try:
                    resp = await self._client.get(url, params=params)
                    status = resp.status_code
                    if status >= 400:
                        snippet = resp.text[:250]
                        return None, f"HTTP {status} {snippet}", status
                    return resp.json(), None, status
                except Exception as e2:
                    return None, f"Request exception after fallback: {e2}", 0
            return None, f"Request exception: {e}", 0


# ------------ Функции получения сезонов ------------

async def get_seasons_list(
    tournament_id: int, client: Optional[SofaScoreClient] = None
) -> Dict[str, Any]:
    """
    Возвращает список сезонов турнира (если есть).
    Endpoint: unique-tournament/{tournament_id}/seasons
    """
    own = client is None
    if client is None:
        client = SofaScoreClient()
    data, err, status = await client.get_json(f"unique-tournament/{tournament_id}/seasons")
    if own:
        await client.close()
    return {
        "data": data if not err else None,
        "error": err,
        "status": status,
    }


async def get_current_season_id(
    tournament_id: int, client: Optional[SofaScoreClient] = None
) -> Dict[str, Any]:
    """
    Endpoint: unique-tournament/{tournament_id}
    Ожидаем поле uniqueTournament -> currentSeason -> id
    """
    own = client is None
    if client is None:
        client = SofaScoreClient()
    data, err, status = await client.get_json(f"unique-tournament/{tournament_id}")
    season_id = None
    if not err and isinstance(data, dict):
        ut = data.get("uniqueTournament") or {}
        cs = ut.get("currentSeason") or {}
        season_id = cs.get("id")
    if own:
        await client.close()
    return {
        "season_id": season_id,
        "raw": data,
        "error": err,
        "status": status,
    }


async def get_or_guess_season_id(
    tournament_id: int, prefer_current: bool = True
) -> Tuple[Optional[int], Dict[str, Any]]:
    """
    Возвращает (season_id | None, debug_info).
    1) Пытаемся взять currentSeason.
    2) Если не получилось – берём первый из списка seasons (обычно упорядочен по убыванию).
    """
    debug: Dict[str, Any] = {"steps": []}
    async with SofaScoreClient() as cl:
        season_id = None

        if prefer_current:
            cur = await get_current_season_id(tournament_id, client=cl)
            debug["steps"].append({"current": cur})
            if cur.get("season_id"):
                season_id = cur["season_id"]

        if season_id is None:
            seasons_resp = await get_seasons_list(tournament_id, client=cl)
            debug["steps"].append({"seasons": seasons_resp})
            data = seasons_resp.get("data") or {}
            seasons = data.get("seasons") if isinstance(data, dict) else None
            if seasons and isinstance(seasons, list):
                # Берём первый (обычно самый свежий)
                season_id = seasons[0].get("id")

        debug["result_season_id"] = season_id
        return season_id, debug


# ------------ Получение ближайших матчей (events) ------------

async def fetch_upcoming_events_for_season(
    season_id: int,
    tournament_id: int,
    limit: int = 30,
    batch_pages: int = 3,
    client: Optional[SofaScoreClient] = None,
) -> Dict[str, Any]:
    """
    Возвращает:
    {
      "events": [...],
      "attempts": [ {endpoint, status, error} ],
      "errors": [...],
      "season_id": season_id
    }
    """
    own_client = client is None
    if client is None:
        client = SofaScoreClient()

    attempts: List[Dict[str, Any]] = []
    collected: List[Dict[str, Any]] = []
    errors: List[str] = []

    page = 0
    while page < batch_pages and len(collected) < limit:
        endpoint = f"unique-tournament/{tournament_id}/season/{season_id}/events/next/{page}"
        data, err, status = await client.get_json(endpoint)
        attempts.append({"endpoint": endpoint, "status": status, "error": err})
        if err:
            errors.append(f"page {page}: {err}")
            if status == 404:
                break
            page += 1
            continue
        events = data.get("events") if isinstance(data, dict) else None
        if not events:
            page += 1
            continue
        collected.extend(events)
        page += 1
        await asyncio.sleep(0.35)

    if own_client:
        await client.close()

    return {
        "events": collected[:limit],
        "attempts": attempts,
        "errors": errors,
        "season_id": season_id,
    }


async def get_upcoming_matches(
    season_id: int,
    tournament_id: int,
    limit: int = 30,
) -> Dict[str, Any]:
    async with SofaScoreClient(try_http2=True) as cl:
        return await fetch_upcoming_events_for_season(
            season_id=season_id,
            tournament_id=tournament_id,
            limit=limit,
            client=cl,
        )
    
