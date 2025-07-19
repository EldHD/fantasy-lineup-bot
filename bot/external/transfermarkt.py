import asyncio
import httpx
import logging
import random
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

# -------------------------------
# Константы / настройки
# -------------------------------
CURRENT_SEASON = 2024

TRANSFERMARKT_TEAM_IDS = {
    # EPL
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
    # RPL (пример)
    "Zenit": 964,
    "CSKA Moscow": 2410,
}

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]
SESSION_UA = random.choice(UA_POOL)

# Ограничим одновременные сетевые запросы (если вызовешь параллельно)
_MAX_CONCURRENT = 4
_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

# Один клиент на модуль
_CLIENT: Optional[httpx.AsyncClient] = None


class TMError(Exception):
    pass


def _get_client() -> httpx.AsyncClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            headers={
                "User-Agent": SESSION_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://www.transfermarkt.com/",
                "Connection": "keep-alive",
            },
        )
    return _CLIENT


async def aclose_client():
    """Закрыть клиент (если нужно при остановке)."""
    global _CLIENT
    if _CLIENT:
        await _CLIENT.aclose()
        _CLIENT = None


async def _fetch(
    url: str,
    max_retries: int = 4,
    base_delay: float = 2.0,
) -> str:
    """
    Улучшенный fetch:
    - Один httpx клиент
    - Backoff для 503/403/429
    - Подмена UA при повторных 503
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        async with _semaphore:
            try:
                client = _get_client()
                r = await client.get(url)
            except httpx.RequestError as e:
                last_exc = TMError(f"Network error attempt {attempt}: {e}")
                # fallback sleep
                sleep_time = base_delay * (attempt) + random.uniform(0, 0.7)
            else:
                txt_low = r.text.lower() if r.text else ""
                if r.status_code == 200 and "<html" in txt_low:
                    # Лёгкая пауза
                    await asyncio.sleep(0.6 + random.uniform(0, 0.5))
                    return r.text
                if r.status_code == 503:
                    # Перегенерируем UA после 2 попытки
                    if attempt >= 2:
                        new_ua = random.choice(UA_POOL)
                        if new_ua != SESSION_UA:
                            # обновим заголовок клиента
                            client.headers["User-Agent"] = new_ua
                    sleep_time = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1.2)
                    last_exc = TMError(f"HTTP 503 (attempt {attempt}) backoff {sleep_time:.1f}s")
                elif r.status_code in (403, 429):
                    sleep_time = base_delay * (1.5 ** (attempt - 1)) + random.uniform(0, 1.0)
                    last_exc = TMError(
                        f"HTTP {r.status_code} anti-bot (attempt {attempt}) sleep {sleep_time:.1f}s"
                    )
                else:
                    raise TMError(f"HTTP {r.status_code} unexpected: {r.text[:160]!r}")
        if attempt < max_retries:
            await asyncio.sleep(sleep_time)
    if last_exc:
        raise last_exc
    raise TMError("Unknown fetch fail")


# -------------------------------
# Утилиты парсинга
# -------------------------------
def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _parse_number_cell(text: str) -> Optional[int]:
    t = _clean(text)
    if not t or t in {"-", "—"}:
        return None
    m = re.match(r"^\d{1,3}$", t)
    if m:
        return int(m.group())
    # иногда "7." или "#7"
    m2 = re.search(r"\d{1,3}", t)
    return int(m2.group()) if m2 else None


POSITION_KEYWORDS = (
    "midfield",
    "back",
    "wing",
    "forward",
    "striker",
    "keeper",
    "goalkeeper",
    "defence",
    "defender",
    "attack",
)


def _extract_pos_cell_text(row) -> str:
    """
    Более прицельный поиск позиции:
    - Проверяем td с классами, содержащими 'pos' или 'hauptposition'
    - Fallback: любой td, где ключевые слова.
    """
    tds = row.css("td")
    # 1) Классы с pos
    for td in tds:
        cls = td.attributes.get("class", "")
        if "pos" in cls or "hauptposition" in cls:
            txt = _clean(td.text())
            if any(k in txt.lower() for k in POSITION_KEYWORDS):
                return txt
    # 2) Fallback
    for td in tds:
        txt = _clean(td.text())
        low = txt.lower()
        if any(k in low for k in POSITION_KEYWORDS):
            return txt
    return ""


def _map_main(pos: str) -> str:
    p = pos.lower()
    if "keeper" in p:
        return "goalkeeper"
    if any(k in p for k in ("defender", "back", "centre-back", "center-back", "full-back", "wing-back")):
        return "defender"
    if "midfield" in p:
        return "midfielder"
    if any(k in p for k in ("attack", "forward", "striker", "winger")):
        return "forward"
    # default
    return "midfielder"


POSITION_DETAIL_MAP = {
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
    "Left Midfield": "LM",
    "Right Midfield": "RM",
    "Right Wing": "RW",
    "Left Wing": "LW",
}


def _map_detail(pos: str) -> Optional[str]:
    p = pos.strip()
    if p in POSITION_DETAIL_MAP:
        return POSITION_DETAIL_MAP[p]
    # иногда формат "Attacking Midfield" -> AM уже покрыт
    # fallback: если короткая (<=10), вернуть как есть
    return p if len(p) <= 10 else None


def _is_player_row(row) -> bool:
    a = row.css_first("a")
    if not a:
        return False
    href = a.attributes.get("href", "")
    if "/profil/spieler/" in href:
        return True
    cls = a.attributes.get("class", "")
    if "spielprofil_tooltip" in cls:
        return True
    return False


def _extract_player_number(tds) -> Optional[int]:
    """
    Иногда номер в 1-й, иногда во 2-й ячейке (перед именем бывают флаги).
    Пробуем первые 3.
    """
    for i in range(min(3, len(tds))):
        num = _parse_number_cell(tds[i].text())
        if num is not None:
            return num
    return None


# -------------------------------
# Парсинг состава
# -------------------------------
async def fetch_team_squad(team_name: str) -> List[Dict[str, Any]]:
    team_id = TRANSFERMARKT_TEAM_IDS.get(team_name)
    if not team_id:
        raise TMError(f"No TM ID for {team_name}")
    url = f"https://www.transfermarkt.com/-/kader/verein/{team_id}/saison_id/{CURRENT_SEASON}/plus/1"
    html = await _fetch(url)
    parser = HTMLParser(html)
    table = parser.css_first("table.items")
    if not table:
        raise TMError("Squad table not found")

    players: List[Dict[str, Any]] = []
    for row in table.css("tbody tr"):
        if not _is_player_row(row):
            continue
        tds = row.css("td")
        if len(tds) < 2:
            continue
        number = _extract_player_number(tds)
        link = row.css_first("a")
        full_name = _clean(link.text()) if link else _clean(row.text())
        if not full_name or len(full_name) < 2:
            continue

        pos_raw = _extract_pos_cell_text(row)
        pos_main = _map_main(pos_raw) if pos_raw else "midfielder"
        pos_detail = _map_detail(pos_raw) if pos_raw else None

        # Отбрасываем вероятные дубли по Youth (опционально можно улучшить)
        if full_name.lower().endswith((" u21", " u20", " u19")):
            continue

        players.append(
            {
                "full_name": full_name,
                "shirt_number": number,
                "position_main": pos_main,
                "position_detail": pos_detail,
                "raw_position": pos_raw or None,
            }
        )
        if len(players) >= 60:  # safety cap (иногда youth+аренды)
            break

    if not players:
        raise TMError("No players parsed")
    return players


# -------------------------------
# Парсинг травм / дисквалификаций
# -------------------------------
def _normalize_reason(player_name: str, raw_reason: str) -> str:
    reason = _clean(raw_reason)
    if not reason or reason.lower() == player_name.lower():
        reason = "Unavailable (unspecified)"
    low = reason.lower()
    if "susp" in low or "yellow" in low or "red" in low or "ban" in low:
        if "yellow" in low:
            return "Suspension (yellow cards)"
        if "red" in low:
            return "Suspension (red card)"
        return "Suspension"
    return reason


def _maybe_parse_date(txt: str) -> Optional[str]:
    """
    Попробуем распознать дату вида 12/08/2024 или 12.08.2024 или 2024-08-12.
    Возвращаем ISO 'YYYY-MM-DD' или None.
    """
    txt = txt.strip()
    if not txt or len(txt) < 6:
        return None
    patterns = [
        r"(\d{2})[./](\d{2})[./](\d{4})",
        r"(\d{4})-(\d{2})-(\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, txt)
        if m:
            try:
                if len(m.groups()) == 3:
                    g1, g2, g3 = m.groups()
                    if len(g1) == 4:  # YYYY-MM-DD
                        return f"{g1}-{g2}-{g3}"
                    else:  # DD MM YYYY
                        return f"{g3}-{g2}-{g1}"
            except Exception:
                return None
    return None


async def fetch_injury_list(team_name: str) -> List[Dict[str, Any]]:
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

    out_list: List[Dict[str, Any]] = []
    for row in table.css("tbody tr"):
        tds = row.css("td")
        if len(tds) < 2:
            continue
        link = row.css_first("a")
        full_name = _clean(link.text()) if link else _clean(row.text())
        # На некоторых страницах структура: [Player | Reason | Since | Estimated return]
        raw_reason = tds[1].text() if len(tds) > 1 else ""
        reason = _normalize_reason(full_name, raw_reason)
        since = _maybe_parse_date(tds[2].text()) if len(tds) > 2 else None
        est_return = _maybe_parse_date(tds[3].text()) if len(tds) > 3 else None

        if full_name:
            out_list.append(
                {
                    "full_name": full_name,
                    "availability": "OUT",
                    "reason": reason,
                    "injury_since": since,
                    "return_date": est_return,
                }
            )
        if len(out_list) >= 30:
            break
    return out_list


# -------------------------------
# Быстрый тест (локально)
# -------------------------------
if __name__ == "__main__":
    async def _test():
        team = "Arsenal"
        squad = await fetch_team_squad(team)
        print(team, "players:", len(squad))
        for p in squad[:5]:
            print(p)
        inj = await fetch_injury_list(team)
        print("Injuries:", inj)

    asyncio.run(_test())
