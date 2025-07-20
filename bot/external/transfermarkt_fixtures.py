import time
import random
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import httpx
from selectolax.parser import HTMLParser

from bot.config import (
    TM_COMP_CODES,
    TM_WORLD_LOCAL_SLUG,
    TM_WORLD_EN_SLUG,
    TM_COM_EN_SLUG,
    TM_BASE_WORLD,
    TM_BASE_COM,
    TM_TIMEOUT,
    TM_USER_AGENTS,
    TM_CACHE_TTL,
    LEAGUE_DISPLAY,
    SEASON_START_YEAR,
    SHOW_ONLY_NEXT_MATCHDAY,
    TM_CALENDAR_DEBUG,
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
MATCHDAY_MARKERS = ["matchday", "spieltag", "тур", "round"]


def _norm_year(y: str) -> int:
    return int("20" + y) if len(y) == 2 else int(y)


def _detect_matchday_from_text(txt: str) -> Optional[int]:
    lower = txt.lower()
    for marker in MATCHDAY_MARKERS:
        if marker in lower:
            nums = re.findall(r"\d{1,3}", lower)
            if nums:
                try:
                    return int(nums[0])
                except:
                    return None
    # fallback — строка только число
    if re.fullmatch(r"\d{1,3}", lower.strip()):
        try:
            return int(lower.strip())
        except:
            return None
    return None


def _parse_full_calendar(root: HTMLParser, season_year: int) -> List[dict]:
    """
    Универсальный проход: h1..h4, div, table, tr – последовательно.
    Любой <tr> с ссылкой '/spielbericht/' и >=2 ссылками 'vereinprofil_tooltip' -> матч.
    """
    matches: List[dict] = []
    current_matchday: Optional[int] = None
    current_date_context = None

    nodes = root.css("h1,h2,h3,h4,div,table,tr")

    for node in nodes:
        tag = node.tag.lower()

        # Заголовок туров
        if tag in ("h1", "h2", "h3", "h4", "div"):
            txt = (node.text() or "").strip()
            md = _detect_matchday_from_text(txt)
            if md:
                current_matchday = md
                current_date_context = None
            else:
                # Возможный перенос даты в заголовке
                dm = DATE_RE.search(txt)
                if dm:
                    dd, mm, yy = dm.groups()
                    try:
                        current_date_context = (int(dd), int(mm), _norm_year(yy))
                    except:
                        pass

        if tag == "tr":
            row_text = (node.text() or "").strip()
            # Строка даты
            dm = DATE_RE.search(row_text)
            if dm and "spielbericht" not in row_text:
                dd, mm, yy = dm.groups()
                try:
                    current_date_context = (int(dd), int(mm), _norm_year(yy))
                except:
                    pass

            link_rep = node.css_first("a[href*='/spielbericht/']")
            if not link_rep:
                continue

            team_links = node.css("a.vereinprofil_tooltip")
            if len(team_links) < 2:
                continue

            home = (team_links[0].text() or "").strip()
            away = (team_links[-1].text() or "").strip()
            if not home or not away:
                continue

            # Время
            hour = minute = None
            for td in node.css("td"):
                ttxt = (td.text() or "").strip()
                tmatch = TIME_RE.search(ttxt)
                if tmatch:
                    hour, minute = int(tmatch.group(1)), int(tmatch.group(2))
                # если прямо в ячейке есть дата (перезапишем)
                dmatch_inline = DATE_RE.search(ttxt)
                if dmatch_inline:
                    dd, mm, yy = dmatch_inline.groups()
                    try:
                        current_date_context = (int(dd), int(mm), _norm_year(yy))
                    except:
                        pass

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

            # ID матча
            match_id = None
            href = link_rep.attributes.get("href", "")
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
    if not all_matches:
        return []
    groups: Dict[int, List[dict]] = {}
    for m in all_matches:
        md = m.get("matchday")
        if md is None:
            md = 10_000
        groups.setdefault(md, []).append(m)

    now_ts = time.time()
    GRACE = 6 * 3600
    candidates: List[Tuple[int, float]] = []
    for md, group in groups.items():
        fut = [g["timestamp"] for g in group if g.get("timestamp") and g["timestamp"] >= now_ts - GRACE]
        if fut:
            candidates.append((md, min(fut)))
    if candidates:
        candidates.sort(key=lambda x: (x[1], x[0]))
        chosen = candidates[0][0]
    else:
        chosen = min(groups.keys())
    result = groups[chosen]
    result.sort(key=lambda x: (x["timestamp"] is None, x["timestamp"] or 0, x["home"]))
    return result


async def fetch_next_matchday_fixtures(league_code: str, limit: int) -> Tuple[List[dict], Optional[dict]]:
    if league_code not in TM_COMP_CODES:
        return [], {"message": f"No TM mapping for '{league_code}'"}

    cached = _cache_get(league_code)
    if cached is not None:
        return cached[:limit], None

    comp = TM_COMP_CODES[league_code]
    season_year = SEASON_START_YEAR

    attempts: List[dict] = []
    errors: List[str] = []
    first_error: Optional[TMFixturesError] = None
    parsed_matches_total: List[dict] = []

    # Список попыток (domain, slug_map)
    url_attempts: List[Tuple[str, str]] = []

    local_slug = TM_WORLD_LOCAL_SLUG.get(league_code)
    en_slug_world = TM_WORLD_EN_SLUG.get(league_code)
    en_slug_com = TM_COM_EN_SLUG.get(league_code)

    if local_slug:
        url_attempts.append((TM_BASE_WORLD, local_slug))
    if en_slug_world and en_slug_world != local_slug:
        url_attempts.append((TM_BASE_WORLD, en_slug_world))
    if en_slug_com:
        url_attempts.append((TM_BASE_COM, en_slug_com))

    for base, slug in url_attempts:
        url = f"{base}/{slug}/gesamtspielplan/wettbewerb/{comp}/saison_id/{season_year}"
        try:
            root = await _fetch_html(url)
            text_raw = root.text() or ""
            # Диагностические счётчики
            spielbericht_links = len(root.css("a[href*='/spielbericht/']"))
            team_rows = 0
            # Быстрый подсчёт потенциальных строк
            for tr in root.css("tr"):
                if tr.css_first("a[href*='/spielbericht/']") and len(tr.css("a.vereinprofil_tooltip")) >= 2:
                    team_rows += 1

            all_matches = _parse_full_calendar(root, season_year)
            parsed_count = len(all_matches)
            attempts.append({
                "url": url,
                "status": 200,
                "spielbericht_links": spielbericht_links,
                "team_rows": team_rows,
                "parsed_matches": parsed_count
            })

            if parsed_count > 0 and not parsed_matches_total:
                # Первый успешный набор
                if SHOW_ONLY_NEXT_MATCHDAY:
                    selected = _select_next_matchday(all_matches)
                else:
                    selected = all_matches
                if selected:
                    _cache_set(league_code, selected)
                    return selected[:limit], None
                else:
                    # Нет подходящего матча в будущем — фиксируем, но продолжаем попытки? (Можно сразу завершить)
                    parsed_matches_total = all_matches  # сохраним
            # Если parsed_count == 0 — пробуем следующий вариант
        except TMFixturesError as e:
            attempts.append({
                "url": url,
                "status": e.status or 0,
                "error": str(e)
            })
            if first_error is None:
                first_error = e
            errors.append(str(e))
        except Exception as e:  # непредвиденное
            attempts.append({
                "url": url,
                "status": 0,
                "error": f"Unexpected: {e}"
            })
            if first_error is None:
                first_error = TMFixturesError(str(e), url=url)
            errors.append(f"Unexpected: {e}")

    # Если дошли сюда — не нашли матчей
    debug_excerpt = None
    if TM_CALENDAR_DEBUG and attempts:
        # Показываем небольшой срез данных последней удачной/неудачной попытки — аккуратно (без HTML, только текст).
        # В реальном проде лучше убрать.
        debug_excerpt = (attempts[-1].get("url") or "")[:120]

    return [], {
        "message": "No matches parsed",
        "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
        "season_year": season_year,
        "attempts": attempts,
        "errors": errors[:5],
        "debug": debug_excerpt,
    }
    
