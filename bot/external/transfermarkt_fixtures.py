"""
Парсинг ближайшего тура (или конкретных туров) с Transfermarkt.
Упрощённый, без сложных edge-cases. При необходимости усилим.
"""

import random
import re
import time
from datetime import datetime
from typing import List, Dict, Tuple, Any, Optional

import httpx
from bs4 import BeautifulSoup

from bot.config import (
    TM_COMP_CODES,
    TM_SEASON_YEAR,
    TM_MAX_MATCHDAY_SCAN,
    TM_BASE_COM,
    TM_USER_AGENTS,
    TM_TIMEOUT,
    TM_RETRIES,
    TM_CALENDAR_DEBUG,
)

# --- Паттерны ---
RE_MATCH_ID = re.compile(r"/spielbericht/.*/(\d+)")
# Иногда даты на странице формата 15/08/2025 или 15.08.2025
RE_DATE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})")
# Время часто '22:00' или '9:00' (бывает без ведущего нуля)
RE_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _pick_ua() -> str:
    return random.choice(TM_USER_AGENTS)


def _http_get(url: str) -> Tuple[Optional[str], int, str]:
    """
    Возвращает text, status_code, err
    """
    for attempt in range(TM_RETRIES + 1):
        try:
            headers = {"User-Agent": _pick_ua()}
            with httpx.Client(timeout=TM_TIMEOUT, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    return resp.text, resp.status_code, ""
                else:
                    err = f"HTTP {resp.status_code}"
        except Exception as e:
            err = f"EXC {type(e).__name__}: {e}"
        # задержка между попытками
        time.sleep(0.4 + random.random() * 0.6)
    return None, 0, err


def _build_matchday_url(comp_code: str, season_year: int, md: int) -> str:
    # пример:
    # https://www.transfermarkt.com/premier-league/gesamtspielplan/wettbewerb/GB1?saison_id=2025&spieltagVon=1&spieltagBis=1
    return f"{TM_BASE_COM}/premier-league/gesamtspielplan/wettbewerb/{comp_code}?saison_id={season_year}&spieltagVon={md}&spieltagBis={md}"


def _extract_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _parse_matchday_page(html: str, matchday: int) -> List[Dict[str, Any]]:
    """
    Ищем ссылки вида /spielbericht/.../<id> — считаем, что каждая ссылка соответствует матчу.
    Получаем строку с командами, датой и временем по соседним ячейкам/контексту.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Иногда есть хэдэр с названием тура / датой
    matches = []
    seen_ids = set()

    # Чтобы подтягивать "последнюю встреченную дату" (иногда дата общая для группы матчей)
    last_date: Optional[datetime] = None

    # Соберём все <a> с /spielbericht/
    for a in soup.select("a[href*='/spielbericht/']"):
        href = a.get("href", "")
        m = RE_MATCH_ID.search(href)
        if not m:
            continue
        match_id = m.group(1)
        if match_id in seen_ids:
            continue

        # Найдём строку (tr) повыше
        tr = a.find_parent("tr")
        if tr is None:
            continue

        # Извлечём весь текст строки
        row_txt = _extract_text(tr)

        # Попытаемся из строки или соседей достать команды
        # Часто команды в отдельных <td> с классами, но упростим:
        # Разделитель " - " или " vs "
        home = away = ""
        if " - " in row_txt:
            parts = row_txt.split(" - ", 1)
            home = parts[0].strip()
            rest = parts[1].strip()
            # Удалим возможный итоговый счёт в конце (в скобках) для away
            away = re.split(r"\s+\d+:\d+|\s+\(\d+:\d+\)", rest)[0].strip()
        elif " vs " in row_txt.lower():
            parts = re.split(r"(?i)\s+vs\s+", row_txt, 1)
            home = parts[0].strip()
            away = parts[1].strip()

        # Дата/время: пробуем сначала в текущем tr
        dt = None
        date_match = RE_DATE.search(row_txt)
        time_match = RE_TIME.search(row_txt)

        if date_match:
            d, mo, y = date_match.groups()
            try:
                dt_base = datetime(int(y), int(mo), int(d))
                last_date = dt_base
            except ValueError:
                dt_base = None
        else:
            dt_base = last_date  # Если в этой строке нет даты, берём последнюю найденную

        if dt_base and time_match:
            hh, mm = time_match.groups()
            try:
                dt = dt_base.replace(hour=int(hh), minute=int(mm))
            except ValueError:
                dt = dt_base
        else:
            # Если время не найдено — оставляем только дату
            dt = dt_base

        matches.append({
            "id": match_id,
            "matchday": matchday,
            "home": home,
            "away": away,
            "datetime": dt,   # может быть None
        })
        seen_ids.add(match_id)

    return matches


def fetch_current_matchday_upcoming(
    league_code: str,
    limit: int = 15,
    season_year: int = TM_SEASON_YEAR,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Ищет ближайший тур с будущими матчами (matchday от 1 до TM_MAX_MATCHDAY_SCAN).
    Возвращает (matches, meta).
    meta включает 'error' если пусто, и 'attempts'.
    """
    comp_code = TM_COMP_CODES.get(league_code)
    if not comp_code:
        return [], {"error": f"Unknown league code '{league_code}'"}

    now = datetime.utcnow()
    attempts = []
    chosen_md = None
    chosen_matches: List[Dict[str, Any]] = []

    for md in range(1, TM_MAX_MATCHDAY_SCAN + 1):
        url = _build_matchday_url(comp_code, season_year, md)
        text, status, err = _http_get(url)
        attempts.append({
            "md": md,
            "url": url,
            "status": status,
            "err": err,
        })
        if not text or status != 200:
            continue

        parsed = _parse_matchday_page(text, md)
        if TM_CALENDAR_DEBUG:
            print(f"[DEBUG] MD {md} parsed={len(parsed)}")

        # Фильтруем только будущие матчи
        future_matches = []
        for m in parsed:
            dt = m.get("datetime")
            if dt is None:
                # Если не удалось распарсить дату/время — пропускаем
                continue
            if dt >= now:
                future_matches.append(m)

        if future_matches:
            chosen_md = md
            # отсортировать по времени
            future_matches.sort(key=lambda x: x["datetime"] or datetime(2100, 1, 1))
            chosen_matches = future_matches[:limit]
            break

    if not chosen_matches:
        return [], {
            "error": "No upcoming matches found",
            "attempts": attempts,
            "season_year": season_year,
            "scanned_up_to": attempts[-1]["md"] if attempts else 0
        }

    meta = {
        "matchday": chosen_md,
        "attempts": attempts,
        "season_year": season_year,
        "count": len(chosen_matches),
    }
    return chosen_matches, meta
