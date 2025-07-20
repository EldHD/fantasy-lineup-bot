import re
import time
import random
import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

import httpx
from bs4 import BeautifulSoup

from bot.config import (
    TM_COMP_CODES,
    TM_SEASON_YEAR,
    TM_MAX_MATCHDAY_SCAN,
    TM_BASE_COM,
    TM_TIMEOUT,
    TM_HEADERS,
)

logger = logging.getLogger(__name__)


@dataclass
class ParsedMatch:
    match_id: Optional[int]
    home: str
    away: str
    dt_str: str
    matchday: Optional[int]


# ---------- Utility parsing helpers ----------

TEAM_SPLIT_RE = re.compile(r"\s+-\s+|\s+vs\s+", re.IGNORECASE)
ID_RE = re.compile(r"/spielbericht/spielbericht/spielbericht/(\d+)|/spielbericht/(\d+)|/index/spielbericht/(\d+)")

DATE_TIME_CANDIDATE_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})|(\d{2}:\d{2})")

WHITESPACE_RE = re.compile(r"\s+")


def _clean(s: str) -> str:
    return WHITESPACE_RE.sub(" ", s).strip()


def _row_text(tr) -> str:
    """Собрать полный текст строки fixtures как одна строка."""
    return _clean(" ".join(tr.stripped_strings))


def _extract_match_id(tr) -> Optional[int]:
    # Попробуем найти ссылку на матч (spielbericht или match report)
    for a in tr.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/spielbericht/spielbericht/spielbericht/(\d+)", href)
        if not m:
            m = re.search(r"/spielbericht/(\d+)", href)
        if not m:
            m = re.search(r"/index/spielbericht/(\d+)", href)
        if m:
            try:
                return int(m.group(1))
            except:
                pass
    return None


def _extract_teams_from_row(tr) -> Tuple[Optional[str], Optional[str]]:
    # На Transfermarkt названия команд обычно в <td class=""> с <a title="Club name">
    tds = tr.find_all("td")
    candidates = []
    for td in tds:
        a = td.find("a", title=True)
        if a and not a.find("img"):
            title = _clean(a.get("title") or a.text)
            if title and len(title) > 1:
                candidates.append(title)

    # Иногда в строке может быть больше элементов (резерв, повтор). Возьмем первые две уникальные.
    unique = []
    for c in candidates:
        if c not in unique:
            unique.append(c)
        if len(unique) == 2:
            break

    if len(unique) == 2:
        return unique[0], unique[1]

    # fallback: попробуем разрезать общий текст
    txt = _row_text(tr)
    parts = TEAM_SPLIT_RE.split(txt)
    parts = [p for p in (p.strip() for p in parts) if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def _extract_datetime_string(tr) -> str:
    """
    На страницах полного календаря дата и время часто в отдельных <td> или в заголовке блока тура.
    Мы здесь просто собираем все паттерны dd.mm.yyyy и hh:mm и склеиваем.
    """
    txt = _row_text(tr)
    dates = DATE_TIME_CANDIDATE_RE.findall(txt)
    # dates = list of tuples; flatten
    flat = []
    for tpl in dates:
        for seg in tpl:
            if seg:
                flat.append(seg)
    # Уберем повторы, оставим максимум 2-3 сегмента
    out = []
    for f in flat:
        if f not in out:
            out.append(f)
    return " ".join(out)


def _parse_fixture_rows(soup: BeautifulSoup, season_start_year: int) -> List[ParsedMatch]:
    """
    Ищет основные строки матчей в таблице расписания.
    Часто нужные <tr> имеют data-matchid или класс 'begegnungZeile'.
    """
    matches: List[ParsedMatch] = []
    table = soup.find("table", class_="items")
    if not table:
        # Иногда другой класс
        table = soup.find("table", {"class": re.compile(r".*matchplan.*")})
    if not table:
        return matches

    rows = table.find_all("tr")
    for tr in rows:
        classes = tr.get("class") or []
        cls_join = " ".join(classes)
        if "begegnungZeile" not in cls_join and "match" not in cls_join and not tr.find("a", href=re.compile("spielbericht")):
            continue

        home, away = _extract_teams_from_row(tr)
        if not home or not away:
            continue

        mid = _extract_match_id(tr)
        dt_str = _extract_datetime_string(tr)

        matches.append(
            ParsedMatch(
                match_id=mid,
                home=home,
                away=away,
                dt_str=dt_str,
                matchday=None,  # можем дополнить позже
            )
        )
    return matches


# ----------- HTTP Fetch -----------

def _fetch(url: str, headers=None, timeout=TM_TIMEOUT) -> Tuple[int, str]:
    hdrs = dict(TM_HEADERS)
    if headers:
        hdrs.update(headers)
    # Небольшая рандомная пауза (чтобы не спамить)
    time.sleep(0.3 + random.random() * 0.4)
    try:
        r = httpx.get(url, headers=hdrs, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        logger.warning("Request error %s: %s", url, e)
        return 0, ""


def _compose_matchday_url(comp_code: str, season_year: int, md: int) -> str:
    # Пример:
    # https://www.transfermarkt.com/premier-league/gesamtspielplan/wettbewerb/GB1?saison_id=2025&spieltagVon=1&spieltagBis=1
    return (
        f"{TM_BASE_COM}/premier-league/gesamtspielplan/wettbewerb/{comp_code}"
        f"?saison_id={season_year}&spieltagVon={md}&spieltagBis={md}"
    )


def _compose_full_season_url(comp_code: str, season_year: int) -> str:
    return f"{TM_BASE_COM}/premier-league/gesamtspielplan/wettbewerb/{comp_code}/saison_id/{season_year}"


# ----------- Main high-level fetch -----------

def fetch_current_matchday_upcoming(league_code: str, limit: int = 10) -> Tuple[List[Dict], Dict]:
    """
    Пытаемся найти ближайший (текущий/предстоящий) тур и вернуть его матчи.
    Стратегия:
      1. Сканируем матч-дей от 1 до TM_MAX_MATCHDAY_SCAN.
      2. Берём первый матч-дей, в котором есть строки (парсятся матчи).
      3. (Упрощённо) Возвращаем все матчи этого тура (в реальном сезоне можно
         дописать логику "тур считается текущим пока не сыграны все").
    На случай проблем возвращаем meta с попытками.

    Возвращает:
      matches: список словарей
      meta: { source, season_start_year, attempts, error?(при неудаче) }
    """
    meta = {
        "source": "Transfermarkt (matchday filtered)",
        "season_start_year": TM_SEASON_YEAR,
        "attempts": [],
        "match_count": 0,
    }

    comp_code = TM_COMP_CODES.get(league_code, TM_COMP_CODES.get("epl"))
    if not comp_code:
        meta["error"] = f"Unknown league code {league_code}"
        return [], meta

    selected_matches: List[ParsedMatch] = []
    selected_md = None

    for md in range(1, TM_MAX_MATCHDAY_SCAN + 1):
        url = _compose_matchday_url(comp_code, TM_SEASON_YEAR, md)
        status, text = _fetch(url)
        attempt_info = {"url": url, "status": status, "md": md, "parsed": 0}
        meta["attempts"].append(attempt_info)

        if status != 200 or not text:
            continue

        soup = BeautifulSoup(text, "lxml")
        parsed = _parse_fixture_rows(soup, TM_SEASON_YEAR)
        attempt_info["parsed"] = len(parsed)

        if parsed:
            selected_matches = parsed
            selected_md = md
            break

    if not selected_matches:
        meta["error"] = "No upcoming matches in scanned matchdays"
        return [], meta

    # Обновим matchday у всех
    for pm in selected_matches:
        pm.matchday = selected_md

    # Ограничим лимитом
    sel = selected_matches[:limit]
    meta["match_count"] = len(sel)

    return [pm.__dict__ for pm in sel], meta


def fetch_full_season_first_upcoming(league_code: str, limit: int = 15) -> Tuple[List[Dict], Dict]:
    """
    Альтернатива: парсим всю страницу сезона и просто берём первые 'limit' матчей.
    Используй, если нужна не логика туров, а «просто N ближайших».
    """
    meta = {
        "source": "Transfermarkt (full season)",
        "season_start_year": TM_SEASON_YEAR,
        "attempts": [],
        "match_count": 0,
    }
    comp_code = TM_COMP_CODES.get(league_code, TM_COMP_CODES.get("epl"))
    if not comp_code:
        meta["error"] = f"Unknown league code {league_code}"
        return [], meta

    url = _compose_full_season_url(comp_code, TM_SEASON_YEAR)
    status, text = _fetch(url)
    meta["attempts"].append({"url": url, "status": status})

    if status != 200 or not text:
        meta["error"] = f"HTTP {status}"
        return [], meta

    soup = BeautifulSoup(text, "lxml")
    parsed = _parse_fixture_rows(soup, TM_SEASON_YEAR)
    if not parsed:
        meta["error"] = "No matches parsed"
        return [], meta

    meta["match_count"] = min(len(parsed), limit)
    return [pm.__dict__ for pm in parsed[:limit]], meta
