import asyncio
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from selectolax.parser import HTMLParser

from bot.config import (
    TM_COMP_CODES, TM_SEASON_YEAR, TM_TIMEOUT, TM_USER_AGENTS,
    TM_REQUEST_DELAY_SEC, MAX_MATCHDAY_SCAN, TM_BASE_DOMAIN
)

# Рег. выражения
_DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})")
_TIME_RE = re.compile(r"(\d{2}:\d{2})")
_MATCH_ID_RE = re.compile(r"/spielbericht/(\d+)")
_MATCH_ID_ALT_RE = re.compile(r"/matchbericht/(\d+)")

def _headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(TM_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    }

async def _fetch(url: str) -> Tuple[int, Optional[str]]:
    try:
        async with httpx.AsyncClient(headers=_headers(), http2=False) as client:
            r = await client.get(url, timeout=TM_TIMEOUT)
            return r.status_code, r.text
    except Exception:
        return 0, None

def _parse_table_rows(parser: HTMLParser) -> List[Dict]:
    """
    Универсальный разбор таблиц матчей на странице тура или полной страницы.
    """
    fixtures: List[Dict] = []
    rows = parser.css("tr")
    for tr in rows:
        link = tr.css_first("a[href*='spielbericht'], a[href*='matchbericht']")
        if not link:
            continue
        href = link.attributes.get("href", "")
        m = _MATCH_ID_RE.search(href) or _MATCH_ID_ALT_RE.search(href)
        if not m:
            continue
        match_id = int(m.group(1))

        tds = tr.css("td")
        if len(tds) < 5:
            # иногда структура другая – пробуем собрать текст
            continue

        row_text = " ".join(td.text(strip=True) for td in tds)
        date_match = _DATE_RE.search(row_text)
        time_match = _TIME_RE.search(row_text)
        dt_obj = None
        if date_match and time_match:
            date_str = date_match.group(1)
            time_str = time_match.group(1)
            try:
                dt_obj = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            except ValueError:
                pass

        # На большинстве страниц:
        # tds[2] – домашняя команда, tds[4] – гостевая (между ними счёт/прочее)
        home_raw = tds[2].text(strip=True) if len(tds) > 2 else ""
        away_raw = tds[4].text(strip=True) if len(tds) > 4 else ""
        home = home_raw.replace("\xa0", " ").strip()
        away = away_raw.replace("\xa0", " ").strip()

        if not home or not away:
            continue

        fixtures.append({
            "id": match_id,
            "home": home,
            "away": away,
            "datetime": dt_obj
        })
    return fixtures

def _split_by_matchday(all_fixtures: List[Dict]) -> Dict[int, List[Dict]]:
    """
    Если парсим полную сезонную страницу (все туры подряд), нужно попытаться группировать по порядку появления.
    У Transfermarkt каждый тур обычно идёт блоком и содержит 8–10 матчей (в PL – 10).
    Алгоритм: идём по списку; каждый раз, когда набираем 10 матчей (или 9/8 для других лиг), увеличиваем номер тура.
    Т.к. точное число матчей в туре зависит от лиги, примем эвристику:
      - Англия / Испания / Италия / Германия / Франция: 10 матчей
      - RPL: 8 матчей
    """
    result: Dict[int, List[Dict]] = {}
    if not all_fixtures:
        return result
    # Эвристика по количеству
    league_size = 10  # по умолчанию
    # (Можно передать параметром, но здесь оставим 10; RPL ниже скорректируем при необходимости внутри вызывающего кода)
    md = 1
    bucket: List[Dict] = []
    for fx in all_fixtures:
        bucket.append(fx)
        if len(bucket) == league_size:
            result[md] = bucket
            md += 1
            bucket = []
    if bucket:
        result[md] = bucket
    return result

async def fetch_matchday_page(league_code: str, matchday: int, season_year: int) -> Tuple[List[Dict], Dict]:
    comp = TM_COMP_CODES[league_code]
    url = (
        f"https://{TM_BASE_DOMAIN}/{comp}/gesamtspielplan/wettbewerb/{comp}"
        f"?saison_id={season_year}&spieltagVon={matchday}&spieltagBis={matchday}"
    )
    status, html = await _fetch(url)
    if status != 200 or not html:
        return [], {"ok": False, "url": url, "matchday": matchday, "reason": f"HTTP {status}"}
    parser = HTMLParser(html)
    fixtures = _parse_table_rows(parser)
    for f in fixtures:
        f["matchday"] = matchday
    return fixtures, {
        "ok": True,
        "url": url,
        "count": len(fixtures),
        "matchday": matchday
    }

async def fetch_full_season_page(league_code: str, season_year: int) -> Tuple[Dict[int, List[Dict]], Dict]:
    comp = TM_COMP_CODES[league_code]
    # есть и форма /.../saison_id/2025 и query-вариант
    url = f"https://{TM_BASE_DOMAIN}/{comp}/gesamtspielplan/wettbewerb/{comp}/saison_id/{season_year}"
    status, html = await _fetch(url)
    if status != 200 or not html:
        # пробуем query-вариант
        url2 = f"https://{TM_BASE_DOMAIN}/{comp}/gesamtspielplan/wettbewerb/{comp}?saison_id={season_year}"
        status2, html2 = await _fetch(url2)
        if status2 != 200 or not html2:
            return {}, {
                "ok": False,
                "reason": f"HTTP {status}/{status2}",
                "urls": [url, url2]
            }
        parser = HTMLParser(html2)
        fixtures = _parse_table_rows(parser)
        grouped = _split_by_matchday(fixtures)
        return grouped, {"ok": True, "url": url2, "total": sum(len(v) for v in grouped.values())}
    parser = HTMLParser(html)
    fixtures = _parse_table_rows(parser)
    grouped = _split_by_matchday(fixtures)
    return grouped, {"ok": True, "url": url, "total": sum(len(v) for v in grouped.values())}

async def fetch_current_matchday_upcoming(
    league_code: str,
    season_year: int = TM_SEASON_YEAR,
    max_scan: int = MAX_MATCHDAY_SCAN
) -> Tuple[List[Dict], Dict]:
    """
    1. Сканируем туровые страницы от 1 до max_scan – возвращаем первый тур, где >0 матчей.
    2. Если ни один не дал матчей, fallback к полной сезонной странице.
    """
    attempts = []
    for md in range(1, max_scan + 1):
        fixtures, meta = await fetch_matchday_page(league_code, md, season_year)
        attempts.append(meta)
        if fixtures:
            return fixtures, {
                "ok": True,
                "mode": "matchday_page",
                "matchday": md,
                "count": len(fixtures),
                "attempts": attempts
            }
        await asyncio.sleep(TM_REQUEST_DELAY_SEC)

    # Fallback
    grouped, meta_full = await fetch_full_season_page(league_code, season_year)
    if not grouped:
        return [], {
            "ok": False,
            "mode": "full_season",
            "reason": "No matches parsed",
            "attempts": attempts,
            "full_meta": meta_full
        }

    # Возьмём минимальный номер тура с матчами
    md_sorted = sorted(grouped.keys())
    if not md_sorted:
        return [], {
            "ok": False,
            "mode": "full_season",
            "reason": "Grouped empty",
            "attempts": attempts,
            "full_meta": meta_full
        }

    first_md = md_sorted[0]
    fixtures = grouped[first_md]
    for f in fixtures:
        f["matchday"] = first_md
    return fixtures, {
        "ok": True,
        "mode": "full_season",
        "matchday": first_md,
        "count": len(fixtures),
        "attempts": attempts,
        "full_meta": meta_full
    }
