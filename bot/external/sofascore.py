import httpx
import asyncio
import random
import time

BASE_URL = "https://api.sofascore.com/api/v1"

SOFASCORE_TEAM_IDS = {
    "Arsenal": 42,
    "Chelsea": 38,
    "Zenit": 2699,
    "CSKA Moscow": 211,
}

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

DEFAULT_HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Connection": "keep-alive",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
}

class SofascoreError(Exception):
    pass


async def _get_json(url: str, max_retries: int = 3, backoff: float = 1.2):
    """
    Универсальный GET с ретраями и случайным User-Agent.
    """
    # Корректный timeout: либо один total, либо все 4 параметра.
    timeout = httpx.Timeout(connect=8.0, read=12.0, write=12.0, pool=8.0)

    for attempt in range(1, max_retries + 1):
        headers = dict(DEFAULT_HEADERS_BASE)
        headers["User-Agent"] = random.choice(USER_AGENTS)
        async with httpx.AsyncClient(timeout=timeout, headers=headers, http2=True) as client:
            try:
                r = await client.get(url)
            except httpx.RequestError as e:
                if attempt == max_retries:
                    raise SofascoreError(f"Network error after {attempt} attempts: {e}") from e
                await asyncio.sleep(backoff * attempt)
                continue

        if r.status_code == 200:
            try:
                return r.json()
            except ValueError as e:
                raise SofascoreError("Invalid JSON from Sofascore") from e

        if r.status_code in (403, 429, 503):
            # антибот или много запросов — попробуем подождать и сменить UA
            if attempt == max_retries:
                snippet = r.text[:120].replace("\n", " ")
                raise SofascoreError(f"HTTP {r.status_code} (anti-bot?) {snippet}")
            await asyncio.sleep(backoff * attempt + random.uniform(0, 0.5))
            continue

        # другие коды — нет смысла ретраить (чаще 404)
        snippet = r.text[:120].replace("\n", " ")
        raise SofascoreError(f"HTTP {r.status_code} {snippet}")

    # Теоретически сюда не дойдём
    raise SofascoreError("Unreachable state in _get_json")


async def fetch_team_players(sofa_team_id: int):
    """
    Возвращает список игроков команды с Sofascore.
    """
    url = f"{BASE_URL}/team/{sofa_team_id}/players"
    data = await _get_json(url)
    players = data.get("players")
    if players is None:
        raise SofascoreError("Field 'players' missing in Sofascore response")
    return players


if __name__ == "__main__":
    async def _t():
        try:
            st = time.time()
            ps = await fetch_team_players(42)
            print("Count:", len(ps), "elapsed", round(time.time() - st, 2), "s")
            if ps:
                print(ps[0])
        except Exception as e:
            print("ERR:", e)
    asyncio.run(_t())
