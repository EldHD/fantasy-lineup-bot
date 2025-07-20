import time
import random
import re
from datetime import datetime, timezone, timedelta
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
    TM_CALENDAR_DEBUG,
    LEAGUE_MATCHES_PER_ROUND,
)

# ---------- КЭШ ----------
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


# ---------- HTTP ----------
def _headers(english: bool = True) -> Dict[str, str]:
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


# ---------- ПАРСИНГ ----------
DATE_RE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
MATCHDAY_MARKERS = ["matchday", "spieltag", "тур", "round"]


def _norm_year(y: str) -> int:
    return int("20" + y) if len(y) == 2 else int(y)


def _fix_day_month(d: int, m: int) -> Tuple[int, int]:
    # Если "месяц" > 12, а "день" <= 12 — скорее всего формат mm/dd
    if m > 12 and d <= 12:
        return m, d
    return d, m


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
    team_links = [a for a in tr.css("a") if "/verein/" in (a.attributes.get("href") or "")]
    names = []
    for a in team_links:
        txt = (a.text() or "").strip()
        if txt and txt not in names:
            names.append(txt)
        if len(names) == 2:
            break
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
                    d_int, m_int = int(dd), int(mm)
                    d_int, m_int = _fix_day_month(d_int, m_int)
                    current_date = (d_int, m_int, _norm_year(yy))
                except:
                    pass
        elif tag == "tr":
            row_text = (node.text() or "").strip()
            dm = DATE_RE.search(row_text)
            if dm and "spielbericht" not in row_text:
                dd, mm, yy = dm.groups()
                try:
                    d_int, m_int = int(dd), int(mm)
                    d_int, m_int = _fix_day_month(d_int, m_int)
                    current_date = (d_int, m_int, _norm_year(yy))
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
            d_inline = DATE_RE.search(ttxt)
            if d_inline:
                dd, mm, yy = d_inline.groups()
                try:
                    d_int, m_int = int(dd), int(mm)
                    d_int, m_int = _fix_day_month(d_int, m_int)
                    local_date = (d_int, m_int, _norm_year(yy))
                except:
                    pass
            tm = TIME_RE.search(ttxt)
            if tm:
                hour, minute = int(tm.group(1)), int(tm.group(2))

        date_str = None
        ts = None
        if local_date:
            d_int, m_int, y_int = local_date
            date_str = f"{d_int:02d}/{m_int:02d}/{y_int}"
            if hour is not None and minute is not None:
                try:
                    dt = datetime(y_int, m_int, d_int, hour, minute, tzinfo=timezone.utc)
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
            "matchday_header": matchday_ctx.get(idx),
            "id": match_id,
            "home": home,
            "away": away,
            "date_str": date_str,
            "time_str": f"{hour:02d}:{minute:02d}" if hour is not None and minute is not None else None,
            "timestamp": ts,
        })
    return matches


# ---------- Отбор "Тур 1" ----------
def _select_first_round(matches: List[dict], league_code: str) -> Tuple[List[dict], str]:
    """ Выбор первого тура через окно ранних дат с уникальностью команд. """
    needed = LEAGUE_MATCHES_PER_ROUND.get(league_code, 10)
    # фильтруем матчи где есть timestamp
    with_ts = [m for m in matches if m.get("timestamp")]
    if not with_ts:
        return [], "no_timestamps"

    with_ts.sort(key=lambda x: (x["timestamp"], x["home"], x["away"]))
    earliest_ts = with_ts[0]["timestamp"]
    window_end = earliest_ts + 14 * 24 * 3600  # 14 дней макс расширения
    selected: List[dict] = []
    used_teams: Set[str] = set()

    for m in with_ts:
        ts = m["timestamp"]
        if ts is None or ts > window_end:
            continue
        h, a = m["home"], m["away"]
        # одна команда не может появляться повторно – чтобы получить ровно первый тур
        if h in used_teams or a in used_teams:
            continue
        selected.append(m)
        used_teams.add(h)
        used_teams.add(a)
        if len(selected) >= needed:
            break

    if len(selected) < needed:
        # fallback – если уникально не набрали, просто добиваем по времени (редко)
        for m in with_ts:
            if m in selected:
                continue
            if len(selected) >= needed:
                break
            selected.append(m)

    if not selected:
        return [], "empty_after_window"
    # присвоим matchday = 1
    for m in selected:
        m["matchday"] = 1
    return selected, "window_earliest_unique"


async def fetch_next_matchday_fixtures(league_code: str, limit: int) -> Tuple[List[dict], Optional[dict]]:
    if league_code not in TM_COMP_CODES:
        return [], {"message": f"No TM mapping for '{league_code}'"}

    cached = _cache_get(league_code)
    if cached is not None:
        return cached[:limit], None

    comp = TM_COMP_CODES[league_code]
    season_year = SEASON_START_YEAR

    local_slug = TM_WORLD_LOCAL_SLUG.get(league_code)
    en_slug_world = TM_WORLD_EN_SLUG.get(league_code)
    en_slug_com = TM_COM_EN_SLUG.get(league_code)

    attempts: List[Tuple[str, str, bool]] = []
    if en_slug_com:
        attempts.append((TM_BASE_COM, en_slug_com, True))
    if en_slug_world:
        attempts.append((TM_BASE_WORLD, en_slug_world, True))
    if local_slug and local_slug != en_slug_world:
        attempts.append((TM_BASE_WORLD, local_slug, False))

    attempts_diag: List[dict] = []
    errors: List[str] = []
    selection_strategy = "none"

    for base, slug, english in attempts:
        url = f"{base}/{slug}/gesamtspielplan/wettbewerb/{comp}/saison_id/{season_year}"
        try:
            root = await _fetch_html(url, english=english)
            candidate_rows = sum(1 for tr in root.css("tr") if tr.css_first("a[href*='/spielbericht/']"))
            all_matches = _parse_full_calendar(root, season_year)
            parsed_count = len(all_matches)

            attempts_diag.append({
                "url": url,
                "status": 200,
                "candidate_rows": candidate_rows,
                "parsed_matches": parsed_count
            })

            if parsed_count > 0:
                selected, strategy = _select_first_round(all_matches, league_code)
                if selected:
                    selection_strategy = strategy
                    selected = selected[:limit]
                    _cache_set(league_code, selected)
                    return selected, None
        except TMFixturesError as e:
            attempts_diag.append({
                "url": url,
                "status": e.status or 0,
                "error": str(e)
            })
            errors.append(str(e))
        except Exception as e:
            attempts_diag.append({
                "url": url,
                "status": 0,
                "error": f"Unexpected: {e}"
            })
            errors.append(f"Unexpected: {e}")

    debug_excerpt = None
    if TM_CALENDAR_DEBUG and attempts_diag:
        debug_excerpt = attempts_diag[-1].get("url")

    return [], {
        "message": "No matches parsed",
        "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
        "season_year": season_year,
        "attempts": attempts_diag,
        "errors": errors[:5] if errors else None,
        "selection_strategy": selection_strategy,
        "debug": debug_excerpt,
    }
