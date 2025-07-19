import httpx
import asyncio

BASE_URL = "https://api.sofascore.com/api/v1"

# Пример ID команд (убедись позже или поправим):
# Arsenal = 42, Chelsea = 38, Zenit = 2699, CSKA Moscow = 211
SOFASCORE_TEAM_IDS = {
    "Arsenal": 42,
    "Chelsea": 38,
    "Zenit": 2699,
    "CSKA Moscow": 211,
}

async def fetch_team_players(sofa_team_id: int):
    url = f"{BASE_URL}/team/{sofa_team_id}/players"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    players = data.get("players", [])
    return players

if __name__ == "__main__":
    # Небольшой тест локально (не выполняется на Railway)
    async def _t():
        print(await fetch_team_players(42))
    asyncio.run(_t())
