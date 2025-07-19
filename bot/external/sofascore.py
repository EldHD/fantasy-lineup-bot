import httpx

BASE_URL = "https://api.sofascore.com/api/v1"

# Пример Sofascore IDs (актуально на момент разработки)
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
    return data.get("players", [])
