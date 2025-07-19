import httpx
import asyncio
import random
import re
from selectolax.parser import HTMLParser
from typing import Optional, List, Dict

# Transfermarkt IDs EPL 24/25 (проверка актуальности может понадобиться позже)
TRANSFERMARKT_TEAM_IDS = {
    "Arsenal": 11,
    "Aston Villa": 405,
    "Bournemouth": 989,
    "Brentford": 1148,
    "Brighton & Hove Albion": 1237,
    "Chelsea": 631,
    "Crystal Palace": 873,
    "Everton": 29,
    "Fulham": 931,
    "Ipswich Town": 677,
    "Leicester City": 1003,
    "Liverpool": 31,
    "Manchester City": 281,
    "Manchester United": 985,
    "Newcastle United": 762,
    "Nottingham Forest": 703,
    "Southampton": 180,
    "Tottenham Hotspur": 148,
    "West Ham United": 379,
    "Wolverhampton Wanderers": 543,
    # Уже существовавшие вне EPL:
    "Zenit": 964,
    "CSKA Moscow": 2410,
}

CURRENT_SEASON = 2024

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


class TMError(Exception):
    pass


async def _fetch(url: str, max_retries: int = 3):
    timeout = httpx.Timeout(15.0)
    last_exc = None
    for attempt in range(1, max_retries + 1):
        headers = {
            "User-Agent": random.choice(UA_LIST),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Referer": "https://www.transfermarkt.com/",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, headers=headers)
        except httpx.RequestError as e:
            last_exc = TMError(f"Network error attempt {attempt}: {e}")
        else:
            if r.status_code == 200 and "<html" in r.text.lower():
                return r.text
            if r.status_code in (403, 429):
                last_exc = TMError(f"HTTP {r.status_code} anti-bot attempt {attempt}")
            else:
                raise TMError(f"HTTP {r.status_code} unexpected: {r.text[:120]!r}")
        if attempt < max_retries:
            await asyncio.sleep(1.2 * attempt + random.uniform(0, 0.5))
    if last_exc:
        raise last_exc
    raise TMError("Unknown fetch fail")


def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _parse_shirt_number_cell(raw: str):
    raw = _clean(raw)
    if not raw or raw in {"-", "—"}:
        return None
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else None


def _map_main(pos: str):
    p = pos.lower()
    if "goalkeeper" in p:
        return "goalkeeper"
    if any(k in p for k in ("defender", "back", "centre-back", "center-back")):
        return "defender"
    if "midfield" in p:
        return "midfielder"
    if any(k in p for k in ("attack", "forward", "winger", "striker")):
        return "forward"
    return "midfielder"


def _map_detail(raw: str):
    raw_norm = raw.strip()
    mapping = {
        "Right Winger": "RW",
        "Left Winger": "LW",
        "Centre-Back": "CB",
        "Center-Back": "CB",
        "Central Midfield": "CM",
        "Central Midfielder": "CM",
        "Defensive Midfield": "DM",
        "Attacking Midfield": "AM",
        "Left-Back": "LB",
        "Right-Back": "RB",
        "Second Striker": "SS",
        "Goalkeeper": "GK",
        "Centre-Forward": "CF",
        "Center-Forward": "CF",
    }
    if raw_norm in mapping:
        return mapping[raw_norm]
    if len(raw_norm) <= 12:
        return raw_norm
    return None


def _extract_position_from_row(row):
    inline_tbl = row.css_first("table.inline-table")
    if inline_tbl:
        text_chunks = []
        for td in inline_tbl.css("td"):
            t = _clean(td.text())
            if t and not re.search(r'^\d+$', t):
                text_chunks.append(t)
        if text_chunks:
            return text_chunks[-1]
    tds = row.css("td")
    for idx_guess in (4, 5, 6):
        if idx_guess < len(tds):
            guess_text = _clean(tds[idx_guess].text())
            if any(k in guess_text.lower() for k in
                   ["midfield", "back", "wing", "forward", "striker", "keeper"]):
                return guess_text
    return ""


async def fetch_team_squad(team_name: str):
    team_id = TRANSFERMARKT_TEAM_IDS.get(team_name)
    if not team_id:
        raise TMError(f"No Transfermarkt ID for {team_name}")
    url = f"https://www.transfermarkt.com/-/kader/verein/{team_id}/saison_id/{CURRENT_SEASON}/plus/1"
    html = await _fetch(url)
    parser = HTMLParser(html)
    table = parser.css_first("table.items")
    if not table:
        raise TMError("Squad table not found")

    players = []
    for row in table.css("tbody tr"):
        tds = row.css("td")
        if len(tds) < 2:
            continue
        number = _parse_shirt_number_cell(tds[0].text())
        link = row.css_first("td a")
        full_name = _clean(link.text()) if link else _clean(row.text())
        if not full_name or len(full_name) < 2:
            continue
        pos_detail_raw = _extract_position_from_row(row)
        position_main = _map_main(pos_detail_raw or "")
        position_detail = _map_detail(pos_detail_raw) if pos_detail_raw else None
        players.append({
            "full_name": full_name,
            "shirt_number": number,
            "position_main": position_main,
            "position_detail": position_detail
        })
    if not players:
        raise TMError("No players parsed")
    return players


def _normalize_reason(player_name: str, raw_reason: str) -> str:
    reason = _clean(raw_reason)
    if reason.lower() == player_name.lower():
        reason = ""
    if not reason or len(reason) < 3:
        reason = "Injury (unspecified)"
    low = reason.lower()
    if any(k in low for k in ["suspens", "yellow", "red", "disciplin", "ban"]):
        if "yellow" in low:
            reason = "Suspension (yellow cards)"
        elif "red" in low:
            reason = "Suspension (red card)"
        else:
            reason = "Suspension"
    return reason


async def fetch_injury_list(team_name: str):
    team_id = TRANSFERMARKT_TEAM_IDS.get(team_name)
    if not team_id:
        return []
    url = f"https://www.transfermarkt.com/-/sperrenundverletzungen/verein/{team_id}/saison_id/{CURRENT_SEASON}"
    try:
        html = await _fetch(url, max_retries=2)
    except TMError:
        return []
    parser = HTMLParser(html)
    table = parser.css_first("table.items")
    if not table:
        return []
    out_list = []
    for row in table.css("tbody tr"):
        tds = row.css("td")
        if len(tds) < 4:
            continue
        name_link = row.css_first("td a")
        full_name = _clean(name_link.text()) if name_link else _clean(row.text())
        raw_reason = tds[1].text() if len(tds) > 1 else ""
        reason = _normalize_reason(full_name, raw_reason)
        if full_name:
            out_list.append({
                "full_name": full_name,
                "availability": "OUT",
                "reason": reason,
            })
    return out_list
