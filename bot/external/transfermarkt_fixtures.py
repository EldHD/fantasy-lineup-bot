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

RE_MATCH_ID = re.compile(r"/spielbericht/.*/(\d+)")
RE_DATE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})")
RE_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")

def _pick_ua() -> str:
    return random.choice(TM_USER_AGENTS)

def _http_get(url: str) -> Tuple[Optional[str], int, str]:
    last_err = ""
    for _ in range(TM_RETRIES + 1):
        try:
            headers = {"User-Agent": _pick_ua()}
            with httpx.Client(timeout=TM_TIMEOUT, headers=headers) as client:
                r = client.get(url)
                if r.status_code == 200:
                    return r.text, r.status_code, ""
                last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = f"EXC {type(e).__name__}: {e}"
        time.sleep(0.4 + random.random() * 0.6)
    return None, 0, last_err

def _build_matchday_url(comp_code: str, season_year: int, md: int) -> str:
    return f"{TM_BASE_COM}/premier-league/gesamtspielplan/wettbewerb/{comp_code}?saison_id={season_year}&spieltagVon={md}&spieltagBis={md}"

def _extract_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def _parse_matchday_page(html: str, matchday: int) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    seen_ids = set()
    last_date: Optional[datetime] = None

    # Селектор: ссылки на отчёт о матче
    for a in soup.select("a[href*='/spielbericht/']"):
        href = a.get("href", "")
        mid_m = RE_MATCH_ID.search(href)
        if not mid_m:
            continue
        match_id = mid_m.group(1)
        if match_id in seen_ids:
            continue
        tr = a.find_parent("tr")
        if not tr:
            continue
        row_txt = _extract_text(tr)

        home = ""
        away = ""
        if " - " in row_txt:
            parts = row_txt.split(" - ", 1)
            home = parts[0].strip()
            away_part = parts[1]
            away = re.split(r"\s+\d+:\d+|\s+\(\d+:\d+\)", away_part)[0].strip()
        elif " vs " in row_txt.lower():
            parts = re.split(r"(?i)\s+vs\s+", row_txt, 1)
            home = parts[0].strip()
            away = parts[1].strip()

        date_match = RE_DATE.search(row_txt)
        time_match = RE_TIME.search(row_txt)

        if date_match:
            d, mo, y = date_match.groups()
            try:
                base_dt = datetime(int(y), int(mo), int(d))
                last_date = base_dt
            except ValueError:
                base_dt = last_date
        else:
            base_dt = last_date

        if base_dt and time_match:
            hh, mm = time_match.groups()
            try:
                dt = base_dt.replace(hour=int(hh), minute=int(mm))
            except ValueError:
                dt = base_dt
        else:
            dt = base_dt

        matches.append({
            "id": match_id,
            "matchday": matchday,
            "home": home,
            "away": away,
            "datetime": dt,
        })
        seen_ids.add(match_id)
    return matches

def fetch_current_matchday_upcoming(
    league_code: str,
    limit: int = 15,
    season_year: int = TM_SEASON_YEAR,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    comp_code = TM_COMP_CODES.get(league_code)
    if not comp_code:
        return [], {"error": f"Unknown league code '{league_code}'"}

    now = datetime.utcnow()
    attempts = []
    chosen_matches: List[Dict[str, Any]] = []
    chosen_md = None

    for md in range(1, TM_MAX_MATCHDAY_SCAN + 1):
        url = _build_matchday_url(comp_code, season_year, md)
        text, status, err = _http_get(url)
        attempts.append({"md": md, "url": url, "status": status, "err": err})
        if not text or status != 200:
            continue
        parsed = _parse_matchday_page(text, md)
        if TM_CALENDAR_DEBUG:
            print(f"[DEBUG] md={md} parsed={len(parsed)}")
        future = []
        for m in parsed:
            dt = m.get("datetime")
            if dt and dt >= now:
                future.append(m)
        if future:
            future.sort(key=lambda x: x["datetime"] or datetime(2100,1,1))
            chosen_matches = future[:limit]
            chosen_md = md
            break

    if not chosen_matches:
        return [], {
            "error": "No upcoming matches found",
            "attempts": attempts,
            "season_year": season_year,
            "scanned_up_to": attempts[-1]["md"] if attempts else 0,
        }

    meta = {
        "matchday": chosen_md,
        "attempts": attempts,
        "season_year": season_year,
        "count": len(chosen_matches),
    }
    return chosen_matches, meta
