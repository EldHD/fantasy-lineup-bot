import time
import random
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import httpx
from selectolax.parser import HTMLParser

from bot.config import (
    TM_COMP_CODES,
    TM_WORLD_EN_SLUG,
    TM_COM_EN_SLUG,
    TM_WORLD_LOCAL_SLUG,
    TM_BASE_WORLD,
    TM_BASE_COM,
    TM_TIMEOUT,
    TM_USER_AGENTS,
    TM_CACHE_TTL,
    LEAGUE_DISPLAY,
    SEASON_START_YEAR,
    TM_CALENDAR_DEBUG,
    LEAGUE_MATCHES_PER_ROUND,
    PREFER_MATCHDAY_PAGE,
    DEFAULT_MATCHDAY,
    MIN_VALID_MONTH,
)

# --------- КЭШ ----------
_cache: Dict[str, Dict[str, Any]] = {}


def _cache_key(league_code: str, matchday: int) -> str:
    return f"tm_md:{league_code}:{matchday}"


def _cache_get(league_code: str, matchday: int):
    entry = _cache.get(_cache_key(league_code, matchday))
    if not entry:
        return None
    if time.time() - entry["ts"] > TM_CACHE_TTL:
        _cache.pop(_cache_key(league_code, matchday), None)
        return None
    return entry["data"]


def _cache_set(league_code: str, matchday: int, data):
    _cache[_cache_key(league_code, matchday)] = {"ts": time.time(), "data": data}


# --------- HTTP ----------
def _headers(english: bool = True) -> Dict[str, str]:
    lang = "en-US,en;q=0.9" if english else "ru-RU,ru;q=0.9,en;q=0.8"
    return {
        "User-Agent": random.choice(TM_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": lang,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
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


DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")  # на TM обычно dd.mm.yyyy
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def _norm_year(y: str) -> int:
    return int("20" + y) if len(y) == 2 else int(y)


def _parse_matchday_table(root: HTMLParser) -> List[dict]:
    """
    Из таблицы тура вытаскиваем строки с матчами.
    Ищем ссылки /spielbericht/ID
    """
    matches = []
    for tr in root.css("tr"):
        rep = tr.css_first("a[href*='/spielbericht/']")
        if not rep:
            continue

        # Получаем клубы
        # На страницах тура обычно есть по два 'td' с классами 'text-right' и 'no-border-links hauptlink'
        tds = tr.css("td")
        home = away = None
        # Пробуем извлечь из ссылок с '/verein/'
        club_links = [a for a in tr.css("a") if "/verein/" in (a.attributes.get("href") or "")]
        club_names = []
        for a in club_links:
            txt = (a.text() or "").strip()
            if txt and txt not in club_names:
                club_names.append(txt)
            if len(club_names) == 2:
                break
        if len(club_names) == 2:
            home, away = club_names
        else:
            # fallback — пробежаться по tds
            texts = [ (td.text() or "").strip() for td in tds ]
            # Иногда home в первом/втором "hauptlink"
            # Оставим как есть если не нашли
            pass

        if not home or not away:
            continue

        # Дата/время
        date_str = None
        time_str = None
        for td in tds:
            txt = (td.text() or "").strip()
            m_date = DATE_RE.search(txt.replace("/", ".").replace("-", "."))
            if m_date:
                dd, mm, yy = m_date.groups()
                d_i, m_i = int(dd), int(mm)
                y_i = _norm_year(yy)
                # фильтр по сезону: отбрасываем даты до июля
                if m_i < MIN_VALID_MONTH:
                    continue
                if y_i < SEASON_START_YEAR:
                    continue
                date_str = f"{d_i:02d}/{m_i:02d}/{y_i}"
            m_time = TIME_RE.search(txt)
            if m_time:
                hh, mn = m_time.groups()
                time_str = f"{int(hh):02d}:{int(mn):02d}"

        href = rep.attributes.get("href", "")
        match_id = None
        parts = [p for p in href.split("/") if p.isdigit()]
        if parts:
            match_id = parts[-1]

        # timestamp если возможно
        ts = None
        if date_str and time_str:
            d, m, y = date_str.split("/")
            try:
                dt = datetime(int(y), int(m), int(d), int(time_str[:2]), int(time_str[3:]), tzinfo=timezone.utc)
                ts = int(dt.timestamp())
            except:
                pass

        matches.append({
            "id": match_id,
            "home": home,
            "away": away,
            "date_str": date_str,
            "time_str": time_str,
            "timestamp": ts,
            "matchday": None,  # добавим позже
        })
    return matches


async def _fetch_matchday_page(league_code: str, matchday: int) -> Tuple[List[dict], List[dict]]:
    """
    Страница: /<slug>/gesamtspielplan/wettbewerb/<code>?saison_id=YYYY&spieltagVon=X&spieltagBis=X
    Пробуем несколько баз / языков.
    """
    if league_code not in TM_COMP_CODES:
        raise TMFixturesError(f"No comp mapping for {league_code}")
    comp = TM_COMP_CODES[league_code]
    season = SEASON_START_YEAR

    attempts_cfg = []

    en_slug_com = TM_COM_EN_SLUG.get(league_code)
    en_slug_world = TM_WORLD_EN_SLUG.get(league_code)
    local_slug = TM_WORLD_LOCAL_SLUG.get(league_code)

    # Порядок: .com EN, world EN, world local
    if en_slug_com:
        attempts_cfg.append((TM_BASE_COM, en_slug_com, True))
    if en_slug_world:
        attempts_cfg.append((TM_BASE_WORLD, en_slug_world, True))
    if local_slug and local_slug != en_slug_world:
        attempts_cfg.append((TM_BASE_WORLD, local_slug, False))

    attempts_diag: List[dict] = []
    all_matches: List[dict] = []

    for base, slug, english in attempts_cfg:
        url = f"{base}/{slug}/gesamtspielplan/wettbewerb/{comp}?saison_id={season}&spieltagVon={matchday}&spieltagBis={matchday}"
        try:
            root = await _fetch_html(url, english=english)
            parsed = _parse_matchday_table(root)
            attempts_diag.append({
                "url": url, "status": 200, "parsed": len(parsed)
            })
            if parsed:
                all_matches = parsed
                break
        except TMFixturesError as e:
            attempts_diag.append({
                "url": e.url or url,
                "status": e.status or 0,
                "error": str(e)
            })
        except Exception as e:
            attempts_diag.append({
                "url": url,
                "status": 0,
                "error": f"Unexpected: {e}"
            })

    return all_matches, attempts_diag


async def fetch_next_matchday_fixtures(league_code: str, limit: int) -> Tuple[List[dict], Optional[dict]]:
    """
    Сейчас: берём фиксированный DEFAULT_MATCHDAY (обычно 1).
    В будущем: можно динамически искать ближайший незавершённый.
    """
    matchday = DEFAULT_MATCHDAY

    cached = _cache_get(league_code, matchday)
    if cached is not None:
        return cached[:limit], None

    matches, attempts = await _fetch_matchday_page(league_code, matchday)

    if not matches:
        err = {
            "message": "No matches parsed",
            "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
            "season_year": SEASON_START_YEAR,
            "attempts": attempts,
            "matchday": matchday
        }
        return [], err

    # Фильтр по лимиту и добавление matchday
    cleaned = []
    for m in matches:
        # Отбрасываем без даты
        if not m.get("date_str"):
            continue
        m["matchday"] = matchday
        cleaned.append(m)
        if len(cleaned) >= LEAGUE_MATCHES_PER_ROUND.get(league_code, 10):
            break

    if not cleaned:
        return [], {
            "message": "All matches dropped after filtering",
            "attempts": attempts,
            "matchday": matchday
        }

    _cache_set(league_code, matchday, cleaned)
    return cleaned[:limit], None
