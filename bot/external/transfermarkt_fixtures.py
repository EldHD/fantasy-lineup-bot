import time
import random
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set

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
    if re.fullmatch(r"\d{1,3}", lower.strip()):
        try:
            return int(lower.strip())
        except:
            return None
    return None


def _extract_teams_from_tr(tr: HTMLParser) -> Optional[Tuple[str, str]]:
    """
    Универсально достаём две команды:
      1) Ищем ссылки с /verein/ (чаще всего)
      2) Fallback: ссылки внутри узлов с классом, где есть 'hauptlink'
    Возвращаем (home, away) или None.
    """
    # Основной способ
    team_links = [a for a in tr.css("a") if "/verein/" in (a.attributes.get("href") or "")]
    names = []
    for a in team_links:
        txt = (a.text() or "").strip()
        if txt and txt not in names:
            names.append(txt)
        if len(names) == 2:
            break

    if len(names) < 2:
        # fallback: попробовать hauptlink
        alt_links = []
        for td in tr.css("td"):
            cls = td.attributes.get("class", "")
            if "hauptlink" in cls:
                for a in td.css("a"):
                    txt = (a.text() or "").strip()
                    if txt and txt not in alt_links:
                        alt_links.append(txt)
        if len(alt_links) >= 2:
            names = alt_links[:2]

    if len(names) >= 2:
        return names[0], names[1]
    return None


def _parse_full_calendar(root: HTMLParser, season_year: int) -> List[dict]:
    """
    Подход:
      - Собираем ВСЕ <tr>, где есть ссылка /spielbericht/
      - Для каждой строки вытягиваем matchday из ближайших предыдущих заголовков
      - Дата/время: из текущего tr или последнего date-context
    """
    # Сначала соберём линейный список узлов для определения контекста туров и дат
    linear_nodes = root.css("h1,h2,h3,h4,div,table,tr")
    matchday_context_for_tr: Dict[int, Optional[int]] = {}
    date_context_for_tr: Dict[int, Optional[Tuple[int, int, int]]] = {}

    current_matchday: Optional[int] = None
    current_date: Optional[Tuple[int, int, int]] = None

    # Присвоим каждому узлу индекс
    for idx, node in enumerate(linear_nodes):
        tag = node.tag.lower()
        if tag in ("h1", "h2", "h3", "h4", "div"):
            txt = (node.text() or "").strip()
            md = _detect_matchday_from_text(txt)
            if md:
                current_matchday = md
            # возможная дата в заголовке
            dm = DATE_RE.search(txt)
            if dm:
                dd, mm, yy = dm.groups()
                try:
                    current_date = (int(dd), int(mm), _norm_year(yy))
                except:
                    pass
        elif tag == "tr":
            # строка-дата?
            row_text = (node.text() or "").strip()
            dm = DATE_RE.search(row_text)
            if dm and "spielbericht" not in row_text:
                dd, mm, yy = dm.groups()
                try:
                    current_date = (int(dd), int(mm), _norm_year(yy))
                except:
                    pass

        # Записываем контекст для этого узла
        matchday_context_for_tr[idx] = current_matchday
        date_context_for_tr[idx] = current_date

    # Теперь обрабатываем только те tr, где есть /spielbericht/
    matches: List[dict] = []
    seen_keys: Set[str] = set()

    for idx, node in enumerate(linear_nodes):
        if node.tag.lower() != "tr":
            continue
        rep_link = node.css_first("a[href*='/spielbericht/']")
        if not rep_link:
            continue

        # команды
        teams = _extract_teams_from_tr(node)
        if not teams:
            continue
        home, away = teams

        # время
        hour = minute = None
        local_date = date_context_for_tr.get(idx)
        for td in node.css("td"):
            ttxt = (td.text() or "").strip()
            # Inline дата
            d_inline = DATE_RE.search(ttxt)
            if d_inline:
                dd, mm, yy = d_inline.groups()
                try:
                    local_date = (int(dd), int(mm), _norm_year(yy))
                except:
                    pass
            # время
            tm = TIME_RE.search(ttxt)
            if tm:
                hour, minute = int(tm.group(1)), int(tm.group(2))

        timestamp = None
        date_str = None
        if local_date:
            dd, mm, yy = local_date
            date_str = f"{dd:02d}/{mm:02d}/{yy}"
            if hour is not None and minute is not None:
                try:
                    dt = datetime(yy, mm, dd, hour, minute)
                    timestamp = int(dt.timestamp())
                except:
                    pass

        # ID
        href = rep_link.attributes.get("href", "")
        match_id = None
        parts = [p for p in href.split("/") if p.isdigit()]
        if parts:
            match_id = parts[-1]

        key = f"{home}|{away}|{date_str}|{hour}:{minute}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        matches.append({
            "matchday": matchday_context_for_tr.get(idx),
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

    local_slug = TM_WORLD_LOCAL_SLUG.get(league_code)
    en_slug_world = TM_WORLD_EN_SLUG.get(league_code)
    en_slug_com = TM_COM_EN_SLUG.get(league_code)

    url_attempts: List[Tuple[str, str]] = []
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
            # Подсчёт "кандидатных" строк (строки с /spielbericht/)
            candidate_rows = 0
            for tr in root.css("tr"):
                if tr.css_first("a[href*='/spielbericht/']"):
                    candidate_rows += 1

            all_matches = _parse_full_calendar(root, season_year)
            parsed_count = len(all_matches)

            attempts.append({
                "url": url,
                "status": 200,
                "candidate_rows": candidate_rows,
                "parsed_matches": parsed_count
            })

            if parsed_count > 0:
                if SHOW_ONLY_NEXT_MATCHDAY:
                    selected = _select_next_matchday(all_matches)
                else:
                    selected = all_matches
                if selected:
                    _cache_set(league_code, selected)
                    return selected[:limit], None
                else:
                    # нашлись матчи, но не удалось выбрать тур
                    errors.append("Parsed matches but no selectable matchday")
        except TMFixturesError as e:
            attempts.append({
                "url": url,
                "status": e.status or 0,
                "error": str(e)
            })
            if first_error is None:
                first_error = e
            errors.append(str(e))
        except Exception as e:
            attempts.append({
                "url": url,
                "status": 0,
                "error": f"Unexpected: {e}"
            })
            if first_error is None:
                first_error = TMFixturesError(str(e), url=url)
            errors.append(f"Unexpected: {e}")

    debug_excerpt = None
    if TM_CALENDAR_DEBUG and attempts:
        debug_excerpt = attempts[-1].get("url")

    return [], {
        "message": "No matches parsed",
        "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
        "season_year": season_year,
        "attempts": attempts,
        "errors": errors[:5],
        "debug": debug_excerpt,
    }
