import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

SOFASCORE_BASE = "https://api.sofascore.com/api/v1"

# --------- ВСПОМОГАТЕЛЬНЫЕ ИСКЛЮЧЕНИЯ ---------
class SofaScoreError(Exception):
    pass


# --------- HTTP КЛИЕНТ С FALLBACK ПО HTTP/2 ---------
class SofaScoreClient:
    """
    Клиент SofaScore с возможностью пробовать http2 и откатываться на http1,
    если библиотека h2 не установлена или соединение не поддерживает.
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
        # Пытаемся http2 если разрешено
        if self._try_http2:
            try:
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    http2=True,
                    headers=self._headers,
                )
                # сделаем легкий запрос, чтобы убедиться что всё хорошо
                self._http2_in_use = True
            except Exception as e:
                logger.warning(
                    "HTTP/2 client init failed (%s). Falling back to HTTP/1.1", e
                )
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
        Возвращает (json_or_none, error_message_or_none, status_code_or_0)
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
            # Если ошибка связана с http2 и мы ещё не откатывались – откат
            msg = str(e)
            if self._http2_in_use and ("http2" in msg.lower() or "h2" in msg.lower()):
                logger.warning(
                    "HTTP/2 runtime error (%s). Recreating client as HTTP/1.1", msg
                )
                # Пересоздаём клиент без http2
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    headers=self._headers,
                )
                self._http2_in_use = False
                # Повтор только один раз
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


# --------- ФУНКЦИИ ВЫСОКОГО УРОВНЯ ---------
async def fetch_upcoming_events_for_season(
    season_id: int,
    tournament_id: int,
    limit: int = 30,
    batch_pages: int = 3,
    client: Optional[SofaScoreClient] = None,
) -> Dict[str, Any]:
    """
    Получить ближайшие события турнира по сезону.
    Возвращает структуру:
    {
      "events": [...],
      "attempts": [ {endpoint, status, error?} ],
      "errors": [... (строки общих ошибок)],
      "season_id": season_id
    }
    """
    own_client = client is None
    if client is None:
        client = SofaScoreClient()

    attempts: List[Dict[str, Any]] = []
    collected: List[Dict[str, Any]] = []
    errors: List[str] = []

    # SofaScore пагинирует: /events/next/0 , /events/next/1 , ...
    page = 0
    while page < batch_pages and len(collected) < limit:
        endpoint = f"unique-tournament/{tournament_id}/season/{season_id}/events/next/{page}"
        data, err, status = await client.get_json(endpoint)
        attempts.append(
            {
                "endpoint": endpoint,
                "status": status,
                "error": err,
            }
        )
        if err:
            errors.append(f"page {page}: {err}")
            # При 404 или пустом JSON — считаем что дальше нечего
            if status == 404:
                break
            page += 1
            continue
        # Ожидаем поле "events"
        events = data.get("events") if isinstance(data, dict) else None
        if not events:
            # если пусто — дальше смысла идти может не быть
            page += 1
            continue
        collected.extend(events)
        if len(events) == 0:
            break
        page += 1
        # Небольшая задержка
        await asyncio.sleep(0.4)

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
    """
    Упрощённая обёртка. Возвращает ту же структуру, что fetch_upcoming_events_for_season.
    """
    async with SofaScoreClient(try_http2=True) as cl:
        return await fetch_upcoming_events_for_season(
            season_id=season_id,
            tournament_id=tournament_id,
            limit=limit,
            client=cl,
        )
