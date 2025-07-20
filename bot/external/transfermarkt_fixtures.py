# bot/external/transfermarkt_fixtures.py
"""
⚠️ Сильно упрощённый парсер: берём только один тур,
меняем при необходимости URL / CSS-selectors.
"""
import datetime as dt
import httpx
from bs4 import BeautifulSoup

TM_BASE = "https://www.transfermarkt.com"
UA      = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA}

def _parse_row(tr: BeautifulSoup, matchday: int):
    tds = tr.select("td")
    if len(tds) < 5:
        return None      # строка-заголовок и т.д.

    time_txt = tds[1].get_text(" ", strip=True)
    if ":" not in time_txt:
        return None

    date_txt = tds[0]["data-date"].split(" ")[0]       # «2025-08-15»
    kck      = dt.datetime.fromisoformat(f"{date_txt}T{time_txt}:00+00:00")

    home_a = tds[2].select_one("a")
    away_a = tds[4].select_one("a")
    mid_a  = tds[3].select_one("a")

    return {
        "round":      f"MD {matchday}",
        "matchday":   matchday,
        "utc":        kck,
        "home_code":  home_a["href"].split("/")[-1],
        "home_name":  home_a.get_text(strip=True),
        "away_code":  away_a["href"].split("/")[-1],
        "away_name":  away_a.get_text(strip=True),
        "tm_id":      int(mid_a["id"].split("_")[1]),   # <a id="match_4625774" …>
    }

async def fetch_first_matchday_premier_league(season_year: int = 2025):
    url = (
        f"{TM_BASE}/premier-league/gesamtspielplan/"
        f"wettbewerb/GB1?saison_id={season_year}&spieltagVon=1&spieltagBis=1"
    )
    async with httpx.AsyncClient(headers=HEADERS, timeout=20) as cli:
        r = await cli.get(url)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    table = soup.select_one("table.items")
    out   = []
    for tr in table.select("tbody > tr"):
        parsed = _parse_row(tr, 1)
        if parsed:
            out.append(parsed)
    return out      # список словарей
