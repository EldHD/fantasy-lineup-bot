import httpx
import asyncio
import random
import re
from selectolax.parser import HTMLParser
from typing import List, Dict, Optional

# Mapping team -> Transfermarkt club ID
TRANSFERMARKT_TEAM_IDS = {
    "Arsenal": 11,
    "Chelsea": 631,
    "Zenit": 964,
    "CSKA Moscow": 2410,
    # Добавим позже остальные команды / лиги
}

# Пример сезона (можно сделать динамическим)
CURRENT_SEASON = 2024  # сезон 2024/2025

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
                raise TMError(f"HTTP {r.status_code} unexpected body snippet={r.text[:120]!r}")
        if attempt < max_retries:
            await asyncio.sleep(1.2 * attempt + random.uniform(0, 0.5))
    if last_exc:
        raise last_exc
    raise TMError("Unknown fetch fail")


def _clean_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _parse_shirt_number(raw: str) -> Optional[int]:
    m = re.search(r"\d+", raw or "")
    return int(m.group()) if m else None


def _map_position(pos: str):
    pos = pos.lower()
    # Transfermarkt часто: "Goalkeeper", "Defender", "Midfield", "Attack"
    if "goalkeeper" in pos:
        return "goalkeeper"
    if "defender" in pos or "back" in pos or "centre-back" in pos:
        return "defender"
    if "midfield" in pos:
        return "midfielder"
    if "attack" in pos or "forward" in pos or "winger" in pos or "striker" in pos:
        return "forward"
    return "midfielder"


def _extract_position_detail(raw: str):
    # Возможные детали: "Right Winger", "Central Midfield", "Left-Back", "Second Striker"
    raw = raw.strip()
    # Сократим
    mapping = {
        "Right Winger": "RW",
        "Left Winger": "LW",
        "Centre-Back": "CB",
        "Central Midfield": "CM",
        "Defensive Midfield": "DM",
        "Attacking Midfield": "AM",
        "Left-Back": "LB",
        "Right-Back": "RB",
        "Second Striker": "SS",
        "Goalkeeper": "GK",
        "Centre-Forward": "CF",
    }
    if raw in mapping:
        return mapping[raw]
    # fallback
    if len(raw) <= 12:
        return raw
    return None


async def fetch_team_squad(team_name: str):
    """
    Возвращает список игроков (dict):
    {
      'full_name', 'shirt_number', 'position_main', 'position_detail'
    }
    """
    team_id = TRANSFERMARKT_TEAM_IDS.get(team_name)
    if not team_id:
        raise TMError(f"No Transfermarkt ID for {team_name}")

    # Пример URL состава:
    # https://www.transfermarkt.com/arsenal-fc/startseite/verein/11/saison_id/2024
    # Для более детального списка можно использовать /kader/...
    url = f"https://www.transfermarkt.com/-/kader/verein/{team_id}/saison_id/{CURRENT_SEASON}/plus/1"

    html = await _fetch(url)
    parser = HTMLParser(html)

    # Таблица с классом "items" (обычно)
    table = parser.css_first("table.items")
    if not table:
        raise TMError("Squad table not found (selector 'table.items')")

    players = []
    # Каждая строка игрока чаще всего "tr" с классом "odd" или "even"
    for row in table.css("tbody tr"):
        # Пропускаем заголовочные/пустые
        tds = row.css("td")
        if len(tds) < 5:
            continue

        # Структура может меняться, но обычно:
        # td[0] = shirt number
        # td[1] = player (link)
        # далее позиции и прочее

        number = _parse_shirt_number(tds[0].text())
        # Имя
        name_link = tds[1].css_first("a")
        full_name = _clean_text(name_link.text()) if name_link else _clean_text(tds[1].text())
        if not full_name:
            continue

        # Позиция – часто в отдельном столбце / span
        pos_td = row.css_first("td:nth-child(5)")  # иногда структура может смещаться
        pos_detail_raw = None
        if pos_td:
            pos_detail_raw = _clean_text(pos_td.text())

        position_main = _map_position(pos_detail_raw or "")
        position_detail = _extract_position_detail(pos_detail_raw) if pos_detail_raw else None

        players.append({
            "full_name": full_name,
            "shirt_number": number,
            "position_main": position_main,
            "position_detail": position_detail,
        })

    if not players:
        raise TMError("No players parsed (maybe markup changed)")

    return players


async def fetch_injury_list(team_name: str):
    """
    VERY SIMPLE MVP:
    Найти на странице текста 'Injury' или 'Suspension' – это ненадёжно.
    Реально лучше парсить отдельный раздел клубных новостей или конкретные
    подстраницы Transfermarkt (есть отдельная /sperrenundverletzungen/).
    """
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
        full_name = _clean_text(name_link.text()) if name_link else _clean_text(row.text())
        reason_cell = tds[2].text() if len(tds) > 2 else ""
        reason = _clean_text(reason_cell)
        # Статусы: injury / suspension (упростим)
        availability = "OUT"
        out_list.append({
            "full_name": full_name,
            "availability": availability,
            "reason": reason,
        })
    return out_list


# Локальный тест
if __name__ == "__main__":
    async def _t():
        sq = await fetch_team_squad("Arsenal")
        print("Players parsed:", len(sq))
        print(sq[:3])
        inj = await fetch_injury_list("Arsenal")
        print("Injuries parsed:", inj)
    asyncio.run(_t())
