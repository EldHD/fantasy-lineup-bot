import re, datetime as dt, httpx
from selectolax.parser import HTMLParser
from bot.config import TM_COMP_CODES, SEASON_YEAR, USER_AGENT

_HEADERS = {"User-Agent": USER_AGENT}

async def fetch_matchday(league_code: str, md: int) -> list[dict]:
    comp = TM_COMP_CODES[league_code]
    url  = (
        f"https://www.transfermarkt.com/{comp}/gesamtspielplan/wettbewerb/{comp}"
        f"?saison_id={SEASON_YEAR}&spieltagVon={md}&spieltagBis={md}"
    )
    async with httpx.AsyncClient(headers=_HEADERS, timeout=30) as cli:
        html = (await cli.get(url)).text
    root = HTMLParser(html)
    rows = root.css("table.items > tbody > tr")

    fixtures: list[dict] = []
    for tr in rows:
        # строки с классом "spacer" – разделительные, пропускаем
        if "spacer" in tr.attributes.get("class",""):
            continue
        txt = tr.text(" ", strip=True)
        # довольно грубое регулярное извлечение
        m = re.search(r"(\d{2}/\d{2}/\d{4}) (\d{2}:\d{2})", txt)
        if not m:
            continue
        date_str, time_str = m.groups()
        kick = dt.datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
        kick = kick.replace(tzinfo=dt.timezone.utc)

        teams = [a.text(strip=True) for a in tr.css("a.spielbericht-link")]
        if len(teams) != 2:
            continue
        fixtures.append({
            "matchday": md,
            "utc_kickoff": kick,
            "home": teams[0],
            "away": teams[1],
        })
    return fixtures
