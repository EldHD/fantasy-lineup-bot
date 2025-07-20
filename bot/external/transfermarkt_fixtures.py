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
    LEAGUE_MATCHES_PER_ROUND,
)

# --------- КЭШ ----------
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


# --------- HTTP ----------
def _headers(english: bool = True) -> Dict[str, str]:
    # Если english=True – просим английский
    lang = "en-US,en;q=0.9" if english else "ru-RU,ru;q=0.9,en;q=0.8"
    return {
        "User-Agent": random.choice(TM_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": lang,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": TM_BASE_COM + "/" if english else TM_BASE_WORLD + "/",
    }


class TMFixturesError(Exception):
    def __init__(self, message: str, *, url: str | None = None, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status


async def _fetch_html(url: str, english: bool) -> HTMLParser:
    async with httpx.AsyncClient(timeout=TM_TIMEOUT, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=_headers(english=english))
        except Exception as e:
            raise TMFixturesError(f"Request exception: {e}", url=url)
    if resp.status_code != 200:
        raise TMFixturesError(f"HTTP {resp.status_code}", url=url, status=resp.status_code)
    return HTMLParser(resp.text)


# --------- ПАРСИНГ ----------
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
    # чистое число
    if re.fullmatch(r"\d{1,3}", lower.strip()):
        try:
            return int(lower.strip())
        except:
            return None
    return None


def _extract_teams_from_tr(tr: HTMLParser) -> Optional[Tuple[str, str]]:
    # 1) ссылки /verein/
    team_links = [a for a in tr.css("a") if "/verein/" in (a.attributes.get("href") or "")]
    names = []
    for a in team_links:
        txt = (a.text() or "").strip()
        if txt and txt not in names:
            names.append(txt)
        if len(names) == 2:
            break
    # fallback
    if len(names) < 2:
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


def _linear_context(root: HTMLParser):
    linear_nodes = root.css("h1,h2,h3,h4,div,table,tr")
    matchday_ctx: Dict[int, Optional[int]] = {}
    date_ctx: Dict[int, Optional[Tuple[int, int, int]]] = {}
    current_md = None
    current_date = None
    for idx, node in enumerate(linear_nodes):
        tag = node.tag.lower()
        if tag in ("h1", "h2", "h3", "h4", "div"):
            txt = (node.text() or "").strip()
            md = _detect_matchday_from_text(txt)
            if md:
                current_md = md
            dm = DATE_RE.search(txt)
            if dm:
                dd, mm, yy = dm.groups()
                try:
                    current_date = (int(dd), int(mm), _norm_year(yy))
                except:
                    pass
        elif tag == "tr":
            row_text = (node.text() or "").strip()
            dm = DATE_RE.search(row_text)
            if dm and "spielbericht" not in row_text:
                dd, mm, yy = dm.groups()
                try:
                    current_date = (int(dd), int(mm), _norm_year(yy))
                except:
                    pass
        matchday_ctx[idx] = current_md
        date_ctx[idx] = current_date
    return linear_nodes, matchday_ctx, date_ctx


def _parse_full_calendar(root: HTMLParser, season_year: int) -> List[dict]:
    linear_nodes, matchday_ctx, date_ctx = _linear_context(root)
    matches: List[dict] = []
    seen: Set[str] = set()

    for idx, node in enumerate(linear_nodes):
        if node.tag.lower() != "tr":
            continue
        rep = node.css_first("a[href*='/spielbericht/']")
        if not rep:
            continue
        teams = _extract_teams_from_tr(node)
        if not teams:
            continue
        home, away = teams

        hour = minute = None
        local_date = date_ctx.get(idx)
        for td in node.css("td"):
            ttxt = (td.text() or "").strip()
            # inline date
            d_inline = DATE_RE.search(ttxt)
            if d_inline:
                dd, mm, yy = d_inline.groups()
                try:
                    local_date = (int(dd), int(mm), _norm_year(yy))
                except:
                    pass
            tm = TIME_RE.search(ttxt)
            if tm:
                hour, minute = int(tm.group(1)), int(tm.group(2))

        date_str = None
        ts = None
        if local_date:
            dd, mm, yy = local_date
            date_str = f"{dd:02d}/{mm:02d}/{yy}"
            if hour is not None and minute is not None:
                try:
                    dt = datetime(yy, mm, dd, hour, minute)
                    ts = int(dt.timestamp())
                except:
                    pass

        href = rep.attributes.get("href", "")
        match_id = None
        parts = [p for p in href.split("/") if p.isdigit()]
        if parts:
            match_id = parts[-1]

        key = f"{home}|{away}|{date_str}|{hour}:{minute}"
        if key in seen:
            continue
        seen.add(key)

        matches.append({
            "matchday": matchday_ctx.get(idx),
            "id": match_id,
            "home": home,
            "away": away,
            "date_str": date_str,
            "time_str": f"{hour:02d}:{minute:02d}" if hour is not None and minute is not None else None,
            "timestamp": ts,
        })
    return matches


def _group_by_matchday(matches: List[dict]) -> Dict[int, List[dict]]:
    groups: Dict[int, List[dict]] = {}
    for m in matches:
        md = m.get("matchday")
        if md is None:
            md = -1  # нераспознанные
        groups.setdefault(md, []).append(m)
    return groups


def _select_next_round_with_headings(matches: List[dict]) -> Tuple[List[dict], str]:
    """
    Если распознаны matchday (кроме -1), берём ближайший (минимальный).
    Возвращаем (список, 'headings') либо ([], 'headings') если не вышло.
    """
    groups = _group_by_matchday(matches)
    valid = {md: lst for md, lst in groups.items() if md != -1}
    if not valid:
        return [], "headings"
    chosen = min(valid.keys())
    out = valid[chosen]
    out.sort(key=lambda x: (x["timestamp"] is None, x["timestamp"] or 0, x["home"]))
    return out, "headings"


def _select_earliest_n(matches: List[dict], league_code: str) -> Tuple[List[dict], str]:
    """
    Эвристика: берем N ранних матчей (по timestamp, потом по id/home).
    Всем присваиваем matchday='guessed'.
    """
    n = LEAGUE_MATCHES_PER_ROUND.get(league_code, 10)
    sorted_all = sorted(
        matches,
        key=lambda x: (x["timestamp"] is None, x["timestamp"] or 0, x.get("id") or "", x["home"])
    )
    slice_n = sorted_all[:n]
    for m in slice_n:
        m["matchday"] = "guessed"
    return slice_n, "earliest_N"


def _final_select(matches: List[dict], league_code: str) -> Tuple[List[dict], str]:
    if not matches:
        return [], "none"
    # Пытаемся по заголовкам
    first_try, strat = _select_next_round_with_headings(matches)
    if first_try:
        return first_try, strat
    # fallback: ранние N
    fallback, strat2 = _select_earliest_n(matches, league_code)
    return fallback, strat2


async def fetch_next_matchday_fixtures(league_code: str, limit: int) -> Tuple[List[dict], Optional[dict]]:
    if league_code not in TM_COMP_CODES:
        return [], {"message": f"No TM mapping for '{league_code}'"}

    cached = _cache_get(league_code)
    if cached is not None:
        return cached[:limit], None

    comp = TM_COMP_CODES[league_code]
    season_year = SEASON_START_YEAR

    # Порядок попыток: приоритет .COM английский slug -> world англ -> world локальный
    local_slug = TM_WORLD_LOCAL_SLUG.get(league_code)
    en_slug_world = TM_WORLD_EN_SLUG.get(league_code)
    en_slug_com = TM_COM_EN_SLUG.get(league_code)

    url_attempts: List[Tuple[str, str, bool]] = []
    if en_slug_com:
        url_attempts.append((TM_BASE_COM, en_slug_com, True))
    if en_slug_world:
        url_attempts.append((TM_BASE_WORLD, en_slug_world, True))
    if local_slug and local_slug != en_slug_world:
        url_attempts.append((TM_BASE_WORLD, local_slug, False))

    attempts_diag: List[dict] = []
    errors: List[str] = []
    first_error: Optional[TMFixturesError] = None

    collected_all: List[dict] = []
    selection_strategy = "none"

    for base, slug, english in url_attempts:
        url = f"{base}/{slug}/gesamtspielplan/wettbewerb/{comp}/saison_id/{season_year}"
        try:
            root = await _fetch_html(url, english=english)
            # Кандидатные строки (tr с ссылкой spielbericht)
            candidate_rows = sum(1 for tr in root.css("tr") if tr.css_first("a[href*='/spielbericht/']"))
            all_matches = _parse_full_calendar(root, season_year)
            parsed_count = len(all_matches)

            attempts_diag.append({
                "url": url,
                "status": 200,
                "candidate_rows": candidate_rows,
                "parsed_matches": parsed_count
            })

            if parsed_count > 0 and not collected_all:
                # Делаем выбор тура / ранних матчей
                selected, strategy = _final_select(all_matches, league_code)
                if selected:
                    selection_strategy = strategy
                    # ограничим (но limit обычно >= числу в туре)
                    selected = selected[:limit]
                    _cache_set(league_code, selected)
                    return selected, None
                else:
                    collected_all = all_matches  # сохраним на случай показа диагностики
        except TMFixturesError as e:
            attempts_diag.append({
                "url": url,
                "status": e.status or 0,
                "error": str(e)
            })
            errors.append(str(e))
            if first_error is None:
                first_error = e
        except Exception as e:
            attempts_diag.append({
                "url": url,
                "status": 0,
                "error": f"Unexpected: {e}"
            })
            errors.append(f"Unexpected: {e}")
            if first_error is None:
                first_error = TMFixturesError(str(e), url=url)

    debug_excerpt = None
    if TM_CALENDAR_DEBUG and attempts_diag:
        debug_excerpt = attempts_diag[-1].get("url")

    return [], {
        "message": "No matches parsed",
        "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
        "season_year": season_year,
        "attempts": attempts_diag,
        "errors": errors[:5],
        "selection_strategy": selection_strategy,
        "debug": debug_excerpt,
    }
