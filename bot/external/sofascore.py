import httpx
import asyncio
import random
import time

BASE_URL = "https://api.sofascore.com/api/v1"

# Карта Sofascore ID команд, с которых начинаем
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

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Connection": "keep-alive",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
}

class SofascoreError(Exception):
    """Кастомная ошибка для единой обработки."""
    pass


async def _fetch_json(url: str, max_retries: int = 3, backoff: float = 1.2):
    """
    Универсальный GET c ретраями и случайным User-Agent.
    Без http2 — чтобы не требовалась установка h2.
    """
    # Простой общий таймаут
    timeout = 15.0

    last_exc = None
    for attempt in range(1, max_retries + 1):
        headers = dict(BASE_HEADERS)
        headers["User-Agent"] = random.choice(USER_AGENTS)

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            try:
                resp = await client.get(url)
            except httpx.RequestError as e:
                last_exc = SofascoreError(f"Network error attempt {attempt}: {e}")
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as ve:
                        raise SofascoreError("Invalid JSON in Sofascore response") from ve

                # Антибот / лимиты — можно попробовать повторить
                if resp.status_code in (403, 429, 503):
                    last_exc = SofascoreError(
                        f"HTTP {resp.status_code} (anti-bot/limit) attempt {attempt}; snippet={resp.text[:100].replace(chr(10),' ')}"
                    )
                else:
                    # Прочие коды — не ретраим
                    raise SofascoreError(
                        f"HTTP {resp.status_code} {resp.text[:120].replace(chr(10),' ')}"
                    )

        if attempt < max_retries:
            await asyncio.sleep(backoff * attempt + random.uniform(0, 0.4))

    # Все попытки исчерпаны
    if last_exc:
        raise last_exc
    raise SofascoreError("Unknown fetch error (no response, no exception?)")


async def fetch_team_players(sofa_team_id: int):
    """
    Возвращает список игроков для команды Sofascore.
    Поднимает SofascoreError при проблеме.
    """
    url = f"{BASE_URL}/team/{sofa_team_id}/players"
    data = await _fetch_json(url)
    players = data.get("players")
    if players is None:
        raise SofascoreError("Field 'players' missing in Sofascore JSON")
    return players


# Локальный быстрый тест
if __name__ == "__main__":
    async def _t():
        try:
            st = time.time()
            players = await fetch_team_players(42)
            print("Count:", len(players), "Time:", round(time.time() - st, 2), "s")
            if players:
                print(players[0])
        except Exception as e:
            print("TEST ERROR:", e)
    asyncio.run(_t())
