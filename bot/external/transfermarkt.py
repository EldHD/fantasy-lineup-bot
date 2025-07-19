import httpx
import asyncio
import random
import re
from selectolax.parser import HTMLParser
from typing import Optional, List, Dict, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Transfermarkt IDs EPL + RPL (нужное сейчас)
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
    "Zenit": 964,
    "CSKA Moscow": 2410,
}

CURRENT_SEASON = 2024

# Один UA на «сессию»
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]
SESSION_UA = random.choice(UA_POOL)


class TMError(Exception):
    pass


async def _fetch(url: str,
                 max_retries: int = 4,
                 base_delay: float = 2.0) -> str:
    """
    Усовершенствованный fetch с отдельной обработкой 503.
    """
    last_exc = None
    timeout = httpx.Timeout(20.0)
    for attempt in range(1, max_retries + 1):
        headers = {
            "User-Agent": SESSION_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Referer": "https://www.transfermarkt.com/",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                r = await client.get(url, headers=headers)
        except httpx.RequestError as e:
            last_exc = TMError(f"Network error attempt {attempt}: {e}")
        else:
            if r.status_code == 200 and "<html" in r.text.lower():
                # Лёгкая случайная пауза между успешными запросами (throttle)
                await asyncio.sleep(0.8 + random.uniform(0, 0.6))
                return r.text
            if r.status_code == 503:
                # Антибот – exponential backoff + небольшой шум
                sleep_time = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1.2)
                last_exc = TMError(f"HTTP 503 (attempt {attempt}) – backoff {sleep_time:.1f}s")
            elif r.status_code in (403, 429):
                sleep_time = base_delay * (1.5 ** (attempt - 1)) + random.uniform(0, 1.0)
                last_exc = TMError(f"HTTP {r.status_code} anti-bot (attempt {attempt}) sleep {sleep_time:.1f}s")
            else:
                raise TMError(f"HTTP {r.status_code} unexpected: {r.text[:160]!r}")
        if attempt < max_retries:
            await asyncio.sleep(sleep_time)
    if last_exc:
        raise last_exc
    raise TMError("Unknown fetch fail")


def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _parse_number_cell(txt: str):
    txt = _clean(txt)
    if not txt or txt in {"-", "—"}:
        return None
    m = re.search(r"\d+", txt)
    return int(m.group()) if m else None


POSITION_KEYWORDS = (
    "midfield", "back", "wing", "forward", "striker", "keeper", "goalkeeper",
    "defence", "defender"
)


def _extract_position_from_row(row) -> str:
    # Ищем inline-table с позицией
    link_cells = row.css("td")
    # Быстро ищем текст с ключевыми словами
    for td in link_cells:
        t = _clean(td.text())
        low = t.lower()
        if any(k in low for k in POSITION_KEYWORDS):
            return t
    return ""


def _map_main(pos: str):
    p = pos.lower()
    if "keeper" in p:
        return "goalkeeper"
    if any(k in p for k in ("defender", "back", "centre-back", "center-back")):
        return "defender"
    if "midfield" in p:
        return "midfielder"
    if any(k in p for k in ("attack", "forward", "wing", "striker")):
        return "forward"
    return "midfielder"


def _map_detail(pos: str):
    pos = pos.strip()
    mapping = {
        "Goalkeeper": "GK",
        "Left Winger": "LW",
        "Right Winger": "RW",
        "Left-Back": "LB",
        "Right-Back": "RB",
        "Centre-Back": "CB",
        "Center-Back": "CB",
        "Central Midfield": "CM",
        "Central Midfielder": "CM",
        "Defensive Midfield": "DM",
        "Attacking Midfield": "AM",
        "Second Striker": "SS",
        "Centre-Forward": "CF",
        "Center-Forward": "CF",
    }
    return mapping.get(pos, pos if len(pos) <= 10 else None)


def _is_player_row(row) -> bool:
    # Линк на профиль игрока обычно содержит "/profil/spieler/"
    a = row.css_first("a")
    if not a:
        return False
    href = a.attributes.get("href", "")
    if "/profil/spieler/" in href:
        return True
    # fallback – класс с tooltip
    cls = a.attributes.get("class", "")
    if "spielprofil_tooltip" in cls:
        return True
    return False


async def fetch_team_squad(team_name: str):
    team_id = TRANSFERMARKT_TEAM_IDS.get(team_name)
    if not team_id:
        raise TMError(f"No TM ID for {team_name}")

    url = f"https://www.transfermarkt.com/-/kader/verein/{team_id}/saison_id/{CURRENT_SEASON}/plus/1"
    html = await _fetch(url)
    parser = HTMLParser(html)
    table = parser.css_first("table.items")
    if not table:
        raise TMError("Squad table not found")

    players = []
    for row in table.css("tbody tr"):
        if not _is_player_row(row):
            continue
        tds = row.css("td")
        if len(tds) < 2:
            continue
        number = _parse_number_cell(tds[0].text())
        link = row.css_first("a")
        full_name = _clean(link.text()) if link else _clean(row.text())
        if not full_name or len(full_name) < 2:
            continue
        pos_raw = _extract_position_from_row(row)
        pos_main = _map_main(pos_raw)
        pos_detail = _map_detail(pos_raw) if pos_raw else None
        players.append({
            "full_name": full_name,
            "shirt_number": number,
            "position_main": pos_main,
            "position_detail": pos_detail
        })
        if len(players) >= 45:  # upper safety cap
            break

    if not players:
        raise TMError("No players parsed")
    return players


def _normalize_reason(player_name: str, raw_reason: str) -> str:
    reason = _clean(raw_reason)
    if reason.lower() == player_name.lower() or len(reason) < 3:
        reason = "Injury (unspecified)"
    low = reason.lower()
    if "susp" in low or "yellow" in low or "red" in low or "ban" in low:
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
        html = await _fetch(url, max_retries=3, base_delay=2.0)
    except TMError as e:
        logger.warning("Injury fetch fail %s: %s", team_name, e)
        return []
    parser = HTMLParser(html)
    table = parser.css_first("table.items")
    if not table:
        return []
    out_list = []
    for row in table.css("tbody tr"):
        tds = row.css("td")
        if len(tds) < 2:
            continue
        link = row.css_first("a")
        full_name = _clean(link.text()) if link else _clean(row.text())
        raw_reason = tds[1].text() if len(tds) > 1 else ""
        reason = _normalize_reason(full_name, raw_reason)
        if full_name:
            out_list.append({
                "full_name": full_name,
                "availability": "OUT",
                "reason": reason,
            })
        if len(out_list) >= 25:
            break
    return out_list
