import asyncio
import httpx
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional

from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

# Mapping кодов лиг вашего бота -> коды соревнований Transfermarkt
TM_COMP_CODES = {
    "epl": "GB1",
    "laliga": "ES1",
    "seriea": "IT1",
    "bundesliga": "L1",
    "ligue1": "FR1",
    "rpl": "RU1",
}

CURRENT_SEASON = 2024  # при необходимости менять

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]
SESSION_UA = random.choice(UA_POOL)

_CLIENT: Optional[httpx.AsyncClient] = None
_SEMAPHORE = asyncio.Semaphore(3)


class TMFixturesError(Exception):
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


async def _fetch(url: str, max_retries: int = 4) -> str:
    last_exc = None
    for attempt in range(1, max_retries + 1):
        async with _SEMAPHORE:
            try:
                r = await _get_client().get(url)
            except httpx.RequestError as e:
                last_exc = TMFixturesError(f"Network error attempt {attempt}: {e}")
                sleep_t = 1.5 * attempt + random.uniform(0, 0.7)
            else:
                if r.status_code == 200 and "<html" in r.text.lower():
                    await asyncio.sleep(0.4 + random.uniform(0, 0.4))
                    return r.text
                if r.status_code in (429, 403, 503):
                    last_exc = TMFixturesError(f"HTTP {r.status_code} anti-bot attempt {attempt}")
                    sleep_t = (2 ** (attempt - 1)) + random.uniform(0, 1.2)
                else:
                    raise TMFixturesError(f"Unexpected status {r.status_code}: {r.text[:150]!r}")
        if attempt < max_retries:
            await asyncio.sleep(sleep_t)
    if last_exc:
        raise last_exc
    raise TMFixturesError("Fetch failed (unknown)")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


DATE_PAT = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
TIME_PAT = re.compile(r"\b(\d{2}):(\d{2})\b")


def _parse_kickoff(date_text: str, time_text: Optional[str]) -> Optional[datetime]:
    """
    На Transfermarkt даты формата DD/MM/YYYY.
    Время — локальное (обычно CET/CEST или GMT в Англии). Мы упрощённо считаем UTC.
    (Для точности позже можно прикрутить timezone по лиге.)
    """
    date_text = _clean(date_text)
    m = DATE_PAT.search(date_text)
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    hh, minute = 12, 0
    if time_text:
        tm = TIME_PAT.search(time_text)
        if tm:
            hh, minute = int(tm.group(1)), int(tm.group(2))
    try:
        dt = datetime(int(yyyy), int(mm), int(dd), hh, minute, tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _extract_matches_from_page(html: str, matchday: int) -> List[Dict]:
    """
    Пытаемся выделить матчи.
    Структура у TM может меняться, поэтому делаем несколько эвристик.
    """
    parser = HTMLParser(html)
    matches: List[Dict] = []

    # Попробуем найти контейнеры матчей: div.box или table с классом 'livescore'/'items'
    # Внутри ищем строки, где есть 2 команды и, возможно, время.
    tables = parser.css("table.livescore, table.items")
    seen = set()

    for table in tables:
        for row in table.css("tr"):
            txt = _clean(row.text())
            if not txt:
                continue

            # Упрощённое выделение: команда1 – команда2 (может быть "Team A - Team B")
            # На страницах расписания часто нет счёта, а просто "Team A - Team B".
            # Ограничим длину чтобы не ловить длинные служебные строки.
            if " - " not in txt or len(txt) > 120:
                continue

            # Извлекаем даты выше (часто дата отдельной строкой над блоком)
            # Попробуем "пройти вверх" (parent) и поискать в предыдущих соседях date pattern
            date_text = ""
            time_text = ""
            # Простой подход: ищем первое совпадение даты в родительском блоке
            parent_html = row.parent.html if row.parent else ""
            # Иногда дата в отдельной <th> или <h2>/<h3>
            date_match = DATE_PAT.search(parent_html)
            if date_match:
                date_text = date_match.group(0)

            # Попробуем найти время прямо в самой строке (или соседях)
            time_match = TIME_PAT.search(txt)
            if time_match:
                time_text = time_match.group(0)

            # Если не нашли дату – попробуем в самом тексте (иногда она дублируется)
            if not date_text:
                d2 = DATE_PAT.search(txt)
                if d2:
                    date_text = d2.group(0)

            # Выделяем команды:
            # Разобьём по " - " и возьмём левую/правую первую “фразу” до (возможных) времени / счёта.
            parts = txt.split(" - ")
            if len(parts) != 2:
                continue
            left = parts[0]
            right = parts[1]

            # Уберём возможный хвост с временем/датой у правой части
            # (например "Chelsea 17:30" -> команда + время)
            # Если нашли time_text отдельно – можно вырезать.
            if time_text and time_text in right:
                right_clean = right.replace(time_text, "")
            else:
                right_clean = right

            # Уберём лишние цифры счёта если вдруг есть (на этапе расписания их быть не должно)
            def clean_team_name(raw: str) -> str:
                raw = re.sub(r"\b\d+:\d+\b", "", raw)
                raw = re.sub(r"\(\d+\)", "", raw)
                return _clean(raw)

            home_team = clean_team_name(left)
            away_team = clean_team_name(right_clean)

            # Эвристический фильтр – названия не должны быть слишком короткими
            if len(home_team) < 2 or len(away_team) < 2:
                continue
            key = (home_team.lower(), away_team.lower(), matchday)
            if key in seen:
                continue

            kickoff_dt = _parse_kickoff(date_text, time_text) if date_text else None

            matches.append(
                {
                    "matchday": matchday,
                    "home_team": home_team,
                    "away_team": away_team,
                    "kickoff_utc": kickoff_dt,
                    "date_raw": date_text or None,
                    "time_raw": time_text or None,
                }
            )
            seen.add(key)

    return matches


async def fetch_league_fixtures(
    league_code: str,
    start_matchday: int = 1,
    max_matchdays: int = 5,
) -> List[Dict]:
    """
    Парсим несколько туров подряд (от start_matchday до start_matchday+max_matchdays-1).
    Возвращаем список матчей.
    """
    comp_code = TM_COMP_CODES.get(league_code.lower())
    if not comp_code:
        raise TMFixturesError(f"Unsupported league code: {league_code}")

    all_matches: List[Dict] = []
    for md in range(start_matchday, start_matchday + max_matchdays):
        url = (
            f"https://www.transfermarkt.com/spieltag/tabelle/wettbewerb/"
            f"{comp_code}/saison_id/{CURRENT_SEASON}/spieltag/{md}"
        )
        # У некоторых лиг альтернативный путь (spieltagtabelle). Подстрахуемся:
        alt_url = (
            f"https://www.transfermarkt.com/premier-league/spieltagtabelle/"
            f"wettbewerb/{comp_code}/saison_id/{CURRENT_SEASON}/spieltag/{md}"
        )
        try:
            try:
                html = await _fetch(url)
            except TMFixturesError:
                html = await _fetch(alt_url)
        except TMFixturesError as e:
            logger.warning("Matchday %s fetch fail (%s): %s", md, league_code, e)
            continue

        matches = _extract_matches_from_page(html, md)
        # Если совсем пусто – прерываем (скорее всего дальше туров нет / не развернуты)
        if not matches and md > start_matchday:
            break
        all_matches.extend(matches)

        # Пауза, чтобы не лупить подряд
        await asyncio.sleep(0.8 + random.uniform(0, 0.7))

    return all_matches


# Локальный тест
if __name__ == "__main__":
    async def _t():
        data = await fetch_league_fixtures("epl", start_matchday=1, max_matchdays=2)
        print("Parsed:", len(data))
        for m in data[:8]:
            print(m)
    asyncio.run(_t())
