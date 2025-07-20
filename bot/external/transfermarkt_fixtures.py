import time
import random
import re
from datetime import datetime, timezone
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
    MAX_MATCHDAY_SCAN,
)

# ------------------ КЭШ ------------------
_cache: Dict[str, Dict[str, Any]] = {}  # key -> {ts, data}

def _cache_key(league: str, season: int, md: int) -> str:
    return f"tm_md:{league}:{season}:{md}"

def _cache_get(league: str, season: int, md: int):
    key = _cache_key(league, season, md)
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > TM_CACHE_TTL:
        _cache.pop(key, None)
        return None
    return entry["data"]

def _cache_set(league: str, season: int, md: int, data):
    key = _cache_key(league, season, md)
    _cache[key] = {"ts": time.time(), "data": data}

# ------------------ HTTP ------------------
def _headers(english: bool) -> Dict[str, str]:
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
            resp = await client.get(url, headers=_headers(english))
        except Exception as e:
            raise TMFixturesError(f"Request exception: {e}", url=url)
    if resp.status_code != 200:
        raise TMFixturesError(f"HTTP {resp.status_code}", url=url, status=resp.status_code)
    return HTMLParser(resp.text)

# ------------------ ПАРСИНГ ------------------
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
SCORE_RE = re.compile(r"\b(\d{1,2}):(\d{1,2})\b")

def _extract_match_id(href: str) -> Optional[str]:
    # /spielbericht/.../<id>
    parts = [p for p in href.split("/") if p.isdigit()]
    if parts:
        return parts[-1]
    return None

def _parse_matchday_table(root: HTMLParser, season_year: int) -> List[dict]:
    matches: List[dict] = []
    for tr in root.css("tr"):
        rep = tr.css_first("a[href*='/spielbericht/']")
        if not rep:
            continue

        # Команды
        team_links = [a for a in tr.css("a") if "/verein/" in (a.attributes.get("href") or "")]
        team_names = []
        for a in team_links:
            nm = (a.text() or "").strip()
            if nm and nm not in team_names:
                team_names.append(nm)
            if len(team_names) == 2:
                break
        if len(team_names) < 2:
            continue
        home, away = team_names[0], team_names[1]

        tds = tr.css("td")
        date_str = None
        time_str = None
        score_present = False

        for td in tds:
            txt = (td.text() or "").strip()
            cls = td.attributes.get("class", "")
            if not date_str:
                dmatch = DATE_RE.search(txt)
                if dmatch:
                    d, m, y = dmatch.groups()
                    date_str = f"{int(d):02d}/{int(m):02d}/{y}"
            if not time_str:
                tmatch = TIME_RE.search(txt)
                if tmatch:
                    hh, mm = tmatch.groups()
                    time_str = f"{int(hh):02d}:{int(mm):02d}"
            # Результат
            if "ergebnis" in cls.lower() or "result" in cls.lower():
                if SCORE_RE.search(txt):
                    score_present = True

        if not date_str:
            continue

        timestamp = None
        try:
            day, month, year = map(int, date_str.split("/"))
            hour = minute = 0
            if time_str:
                hour, minute = map(int, time_str.split(":"))
            dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            timestamp = int(dt.timestamp())
        except Exception:
            pass

        match_id = _extract_match_id(rep.attributes.get("href", "")) or ""

        matches.append({
            "id": match_id,
            "home": home,
            "away": away,
            "date_str": date_str,
            "time_str": time_str,
            "timestamp": timestamp,
            "played": score_present,
        })
    return matches

async def _fetch_matchday_page(league_code: str, season_year: int, md: int) -> Tuple[List[dict], List[dict]]:
    if league_code not in TM_COMP_CODES:
        return [], [{"url": None, "status": 0, "error": f"No comp for {league_code}"}]

    comp = TM_COMP_CODES[league_code]
    en_slug_com = TM_COM_EN_SLUG.get(league_code)
    en_slug_world = TM_WORLD_EN_SLUG.get(league_code)
    local_slug = TM_WORLD_LOCAL_SLUG.get(league_code)

    attempts: List[Tuple[str, str, bool]] = []
    if en_slug_com:
        attempts.append((TM_BASE_COM, en_slug_com, True))
    if en_slug_world:
        attempts.append((TM_BASE_WORLD, en_slug_world, True))
    if local_slug and local_slug != en_slug_world:
        attempts.append((TM_BASE_WORLD, local_slug, False))

    diag: List[dict] = []
    all_matches: List[dict] = []

    for base, slug, english in attempts:
        url = f"{base}/{slug}/gesamtspielplan/wettbewerb/{comp}?saison_id={season_year}&spieltagVon={md}&spieltagBis={md}"
        try:
            root = await _fetch_html(url, english)
            parsed = _parse_matchday_table(root, season_year)
            diag.append({"url": url, "status": 200, "parsed": len(parsed)})
            if parsed:
                all_matches = parsed
                break
        except TMFixturesError as e:
            diag.append({"url": e.url, "status": e.status or 0, "error": str(e)})
        except Exception as e:
            diag.append({"url": url, "status": 0, "error": f"Unexpected: {e}"})

    return all_matches, diag

async def fetch_current_matchday_upcoming(league_code: str, limit: int) -> Tuple[List[dict], Optional[dict]]:
    """Сканирует с 1-го тура. Берёт первый тур, где есть хотя бы один НЕ начавшийся матч.
       Возвращает список этих матчей (ограничено limit).
    """
    season_year = SEASON_START_YEAR
    overall_attempts: List[dict] = []

    for md in range(1, MAX_MATCHDAY_SCAN + 1):
        cached = _cache_get(league_code, season_year, md)
        if cached is not None:
            matches = cached
            diag = []
        else:
            matches, diag = await _fetch_matchday_page(league_code, season_year, md)
            _cache_set(league_code, season_year, md, matches)
        overall_attempts.extend([{"md": md, **d} for d in diag])

        if not matches:
            # пустой тур – пропускаем, идём дальше
            continue

        upcoming = [m for m in matches if not m["played"]]
        if upcoming:
            for m in upcoming:
                m["matchday"] = md
            return upcoming[:limit], None
        # если все сыграны – проверяем следующий

    # ничего не нашли
    return [], {
        "message": "No upcoming matches in scanned matchdays",
        "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
        "season_year": season_year,
        "attempts": overall_attempts[:10],
        "scan_limit": MAX_MATCHDAY_SCAN,
    }
