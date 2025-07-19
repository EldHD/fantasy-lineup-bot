import httpx
import asyncio

BASE_URL = "https://api.sofascore.com/api/v1"

# Пример Sofascore IDs (минимум для test):
SOFASCORE_TEAM_IDS = {
    "Arsenal": 42,
    "Chelsea": 38,
    "Zenit": 2699,
    "CSKA Moscow": 211,
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Connection": "keep-alive",
    "Accept-Language": "en-US,en;q=0.9",
}

class SofascoreError(Exception):
    pass


async def fetch_team_players(sofa_team_id: int):
    """
    Возвращает список игроков Sofascore.
    Поднимает SofascoreError при проблемах.
    """
    url = f"{BASE_URL}/team/{sofa_team_id}/players"
    timeout = httpx.Timeout(connect=8, read=12)
    async with httpx.AsyncClient(timeout=timeout, headers=DEFAULT_HEADERS) as client:
        try:
            r = await client.get(url)
        except httpx.RequestError as e:
            raise SofascoreError(f"Network error: {e}") from e

    if r.status_code != 200:
        # иногда они отдают HTML → попытаемся взять json но без падения
        snippet = r.text[:150].replace("\n", " ")
        raise SofascoreError(f"HTTP {r.status_code} for {url} | snippet: {snippet}")

    try:
        data = r.json()
    except ValueError as e:
        raise SofascoreError("Invalid JSON from Sofascore") from e

    players = data.get("players")
    if players is None:
        raise SofascoreError("Field 'players' missing in Sofascore response")

    return players


# Локальный тест (не будет запускаться на Railway при обычном старте)
if __name__ == "__main__":
    async def _t():
        try:
            ps = await fetch_team_players(42)
            print("Count:", len(ps))
            print(ps[0] if ps else "No players")
        except Exception as e:
            print("ERR:", e)
    asyncio.run(_t())
