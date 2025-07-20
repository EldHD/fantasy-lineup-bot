import time
import random
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import httpx
from selectolax.parser import HTMLParser

from bot.config import (
    TM_BASE_WORLD,
    TM_TIMEOUT,
    TM_USER_AGENTS,
    TM_CACHE_TTL,
    TM_COMP_CODES,
    TM_WORLD_SLUG,
    LEAGUE_DISPLAY,
    SEASON_START_YEAR,
    SHOW_ONLY_NEXT_MATCHDAY,
)

# ----------------- Кэш -----------------
_cache: Dict[str, Dict[str, Any]] = {}

def _cache_key(league_code: str) -> str:
    return f"tm_world_next:{league_code}"

def _cache_get(league_code: str):
    entry = _cache.get(_cache_key(league_code))
    if not entry:
        return None
    if time.time() - entry["ts"] > TM_CACHE_TTL:
        _cache.pop(_cache_key(league_code), None)
        return None
    return entry["data"]

def _cache_set(league_code: str, data):
    _cache[_cache_key(league_code)] = {"ts": time.time(), "data": data}

# ----------------- HTTP -----------------
def _headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(TM_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": TM_BASE_WORLD + "/",
    }

class TMFixturesError(Exception):
    def __init__(self, message: str, *, url: str | None = None, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status

async def _fetch_html(url: str) -> HTMLParser:
    async with httpx.AsyncClient(timeout=TM_TIMEOUT, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=_headers())
        except Exception as e:
            raise TMFixturesError(f"Request exception: {e}", url=url)
    if resp.status_code != 200:
        raise TMFixturesError(f"HTTP {resp.status_code}", url=url, status=resp.status_code)
    return HTMLParser(resp.text)

# ----------------- Парсинг -----------------
DATE_RE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
MATCHDAY_MARKERS = ["matchday", "spieltag", "тур", "round"]  # разные языки

def _norm_year(y: str) -> int:
    return int("20" + y) if len(y) == 2 else int(y)

def _detect_matchday_from_text(txt: str) -> Optional[int]:
    lower = txt.lower()
    # ищем явные слова + число
    for marker in MATCHDAY_MARKERS:
        if marker in lower:
            # извлекаем первое число
            nums = re.findall(r"\d{1,3}", lower)
            if nums:
                try:
                    return int(nums[0])
                except:
                    pass
    # fallback: если строка просто число (1,2,3…)
    if re.fullmatch(r"\d{1,3}", lower.strip()):
        try:
            return int(lower.strip())
        except:
            return None
    return None

def _parse_full_calendar(root: HTMLParser, season_year: int) -> List[dict]:
    """
    Парсит полную страницу 'gesamtspielplan'.
    Структура (может меняться): несколько таблиц или одна таблица 'items'.
    Каждая группа матчей (тур) отделена заголовком <h2>, <h3>, <div class=...> содержащим 'Matchday'/'Spieltag'/...
    """
    matches: List[dict] = []
    current_matchday: Optional[int] = None
    current_date_context = None  # иногда рядом общая дата строки

    # Собираем ВСЕ узлы в порядке появления
    body_nodes = root.css("h1,h2,h3,div,table,tr")

    for node in body_nodes:
        tag = node.tag.lower()

        # Определение туров
        if tag in ("h2", "h3", "div"):
            text = (node.text() or "").strip()
            md = _detect_matchday_from_text(text)
            if md:
                current_matchday = md
                # сбрасываем дату группы
                current_date_context = None

        # Матчи внутри таблиц
        if tag == "tr":
            cls = node.attributes.get("class", "")
            # Пропускаем заголовки и рекламные/пустые
            if "begegnungZeile" not in cls:
                # Но некоторые строки даты тура могут быть внутри таблицы
                maybe_date_txt = (node.text() or "").strip()
                # Если строка содержит дату формата dd/mm/yy — обновим контекст
                dmatch = DATE_RE.search(maybe_date_txt)
                if dmatch:
                    dd, mm, yy = dmatch.groups()
                    try:
                        current_date_context = (int(dd), int(mm), _norm_year(yy))
                    except:
                        pass
                continue

            # Команды: ссылки с class=vereinprofil_tooltip
            team_links = node.css("a.vereinprofil_tooltip")
            if len(team_links) < 2:
                continue
            home = (team_links[0].text() or "").strip()
            away = (team_links[-1].text() or "").strip()
            if not home or not away:
                continue

            # Время / дополнительная дата
            time_text = None
            date_override = None
            for td in node.css("td"):
                ttxt = (td.text() or "").strip()
                if TIME_RE.search(ttxt):
                    time_text = ttxt
                # иногда и дата и время в одной ячейке
                if DATE_RE.search(ttxt):
                    dm = DATE_RE.search(ttxt)
                    if dm:
                        dd, mm, yy = dm.groups()
                        try:
                            date_override = (int(dd), int(mm), _norm_year(yy))
                        except:
                            pass

            if date_override:
                current_date_context = date_override

            hour = minute = None
            if time_text:
                tm = TIME_RE.search(time_text)
                if tm:
                    hour, minute = int(tm.group(1)), int(tm.group(2))

            timestamp = None
            date_str = None
            if current_date_context:
                dd, mm, yy = current_date_context
                date_str = f"{dd:02d}/{mm:02d}/{yy}"
                if hour is not None and minute is not None:
                    try:
                        dt = datetime(yy, mm, dd, hour, minute)
                        timestamp = int(dt.timestamp())
                    except:
                        pass

            # ID
            match_id = None
            rep_link = node.css_first("a[href*='/spielbericht/']")
            if rep_link:
                href = rep_link.attributes.get("href", "")
                parts = [p for p in href.split("/") if p.isdigit()]
                if parts:
                    match_id = parts[-1]

            matches.append({
                "matchday": current_matchday,
                "id": match_id,
                "home": home,
                "away": away,
                "date_str": date_str,
                "time_str": f"{hour:02d}:{minute:02d}" if hour is not None and minute is not None else None,
                "timestamp": timestamp,
            })

    return matches

def _select_next_matchday(all_matches: List[dict]) -> List[dict]:
    """
    Возвращает матчи ближайшего тура.
    """
    if not all_matches:
        return []

    # Группировка по matchday (None -> в конец)
    groups: Dict[int, List[dict]] = {}
    for m in all_matches:
        md = m.get("matchday")
        if md is None:
            # пометим заведомо большим числом, чтобы не ломать сорт
            md = 10_000
        groups.setdefault(md, []).append(m)

    # Определяем ближайший по минимальному будущему timestamp
    now_ts = time.time()
    GRACE = 6 * 3600  # небольшое окно
    candidates: List[Tuple[int, float]] = []
    for md, group in groups.items():
        future_times = [g["timestamp"] for g in group if g.get("timestamp") and g["timestamp"] >= now_ts - GRACE]
        if future_times:
            candidates.append((md, min(future_times)))

    chosen_md = None
    if candidates:
        candidates.sort(key=lambda x: (x[1], x[0]))
        chosen_md = candidates[0][0]
    else:
        # все матчи в прошлом/без времени -> берем минимальный matchday
        chosen_md = min(groups.keys())

    result = groups[chosen_md]
    # Отсортируем в рамках тура по timestamp (None в конец)
    result.sort(key=lambda x: (x["timestamp"] is None, x["timestamp"] or 0, x["home"]))
    return result

async def fetch_next_matchday_fixtures(league_code: str, limit: int) -> Tuple[List[dict], Optional[dict]]:
    """
    Возвращает только ближайший тур (или пусто + err).
    """
    if league_code not in TM_COMP_CODES or league_code not in TM_WORLD_SLUG:
        return [], {"message": f"No TM mapping for '{league_code}'"}

    cached = _cache_get(league_code)
    if cached is not None:
        # ограничим limit просто для единообразия (обычно тур < limit)
        return cached[:limit], None

    comp = TM_COMP_CODES[league_code]
    slug = TM_WORLD_SLUG[league_code]
    season_year = SEASON_START_YEAR

    url = f"{TM_BASE_WORLD}/{slug}/gesamtspielplan/wettbewerb/{comp}/saison_id/{season_year}"

    try:
        root = await _fetch_html(url)
    except TMFixturesError as e:
        return [], {
            "message": str(e),
            "status": e.status,
            "url": e.url,
            "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
            "season_year": season_year,
        }

    all_matches = _parse_full_calendar(root, season_year)

    if not all_matches:
        return [], {
            "message": "No matches parsed",
            "url": url,
            "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
            "season_year": season_year,
        }

    if SHOW_ONLY_NEXT_MATCHDAY:
        selected = _select_next_matchday(all_matches)
    else:
        selected = all_matches

    if not selected:
        return [], {
            "message": "No upcoming matchday found",
            "url": url,
            "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
            "season_year": season_year,
            "parsed_total": len(all_matches),
        }

    _cache_set(league_code, selected)
    return selected[:limit], None
