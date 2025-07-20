import asyncio
import random
import time
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

import httpx
from selectolax.parser import HTMLParser

from bot.config import (
    TM_BASE,
    TM_COMP_CODES,
    TM_TIMEOUT,
    TM_USER_AGENTS,
    TM_MAX_MATCHDAYS_LOOKAHEAD,
    TM_REQUEST_DELAY_BASE,
    TM_RANDOM_JITTER,
    TM_CACHE_TTL,
    LEAGUE_DISPLAY,
    SEASON_START_YEAR,
)

# In-memory cache: key -> {ts, data}
_cache: Dict[str, Dict[str, Any]] = {}


class TMFixturesError(Exception):
    def __init__(self, message: str, *, url: str | None = None, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status


def _cache_key(league_code: str) -> str:
    return f"tm_fixtures:{league_code}"


def _get_cache(league_code: str):
    entry = _cache.get(_cache_key(league_code))
    if not entry:
        return None
    if time.time() - entry["ts"] > TM_CACHE_TTL:
        _cache.pop(_cache_key(league_code), None)
        return None
    return entry["data"]


def _set_cache(league_code: str, data):
    _cache[_cache_key(league_code)] = {"ts": time.time(), "data": data}


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(TM_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": TM_BASE + "/",
    }


async def _fetch_html(client: httpx.AsyncClient, url: str) -> HTMLParser:
    try:
        resp = await client.get(url, headers=_headers())
    except Exception as e:
        raise TMFixturesError(f"Request exception: {e}", url=url) from e
    if resp.status_code != 200:
        raise TMFixturesError(f"HTTP {resp.status_code}", url=url, status=resp.status_code)
    try:
        return HTMLParser(resp.text)
    except Exception as e:
        raise TMFixturesError(f"HTML parse error: {e}", url=url) from e


def _parse_match_table(root: HTMLParser, season_year: int) -> List[dict]:
    """
    Парсит одну страницу matchday.
    Структура на TM может меняться; опираемся на присущие классы:
    - Таблицы с классами 'livescore' или div c class 'box'
    - Строки матчей имеют data-matchid (или id можно вытащить из ссылок)
    Команды: td.verein-heim / td.verein-gast -> a/text
    Время: td.zeit -> текст (например '15:00')
    Дата не всегда в строке – обычно заголовок h2 / div с классом 'table-header' перед группой.
    Упростим: соберём текущую дату блока, обновляем при встрече заголовка.
    """
    matches: List[dict] = []
    current_date_str = None

    # Соберём блоки с датами: заголовки, содержащие день и месяц.
    # На TM это часто <div class="table-header">Matchday 1  –  17/08/24</div> или похож.
    # Будем ловить DD/MM.
    # fallback: если дату не нашли – вставим None.
    for node in root.css("div.table-header, h2, h3"):
        txt = (node.text() or "").strip()
        # ищем паттерн вида 17/08/24 или 17/08/2024
        if "/" in txt:
            parts = txt.split()
            for p in parts:
                if p.count("/") == 2:
                    current_date_str = p

    # Реальные строки матчей
    for row in root.css("tr"):
        # Попробуем найти команды
        home_td = row.css_first("td.verein-heim")
        away_td = row.css_first("td.verein-gast")
        if not home_td or not away_td:
            continue

        home = (home_td.text() or "").strip()
        away = (away_td.text() or "").strip()
        if not home or not away:
            continue

        # Время
        time_td = row.css_first("td.zeit")
        time_txt = (time_td.text() or "").strip() if time_td else ""

        # ID матча (если есть)
        match_id = None
        # Иногда data-matchid:
        if row.attributes.get("data-matchid"):
            match_id = row.attributes.get("data-matchid")
        else:
            # Попробуем из ссылки
            link = row.css_first("a[href*='/spielbericht/']")
            if link:
                # пример: /spielbericht/index/spielbericht/1234567
                href = link.attributes.get("href", "")
                # вытаскиваем числа
                for token in href.split("/"):
                    if token.isdigit():
                        match_id = token
                        break

        # Парсим дату+время в timestamp (UTC мы не знаем – возьмём naive)
        # current_date_str может быть формата DD/MM/YY или DD/MM/YYYY
        ts = None
        if current_date_str and time_txt:
            try:
                dd, mm, yy = current_date_str.split("/")
                if len(yy) == 2:
                    # преобразуем к 20yy
                    yy_full = int("20" + yy)
                else:
                    yy_full = int(yy)
                # иногда сезон: если год не совпадает, но сезон_year = старт, можно доверять yy_full
                dt = datetime(yy_full, int(mm), int(dd), int(time_txt[0:2]), int(time_txt[3:5]))
                ts = int(dt.timestamp())
            except Exception:
                pass

        matches.append({
            "id": match_id,
            "home": home,
            "away": away,
            "time_str": time_txt,
            "date_str": current_date_str,
            "timestamp": ts,
        })

    return matches


async def fetch_transfermarkt_fixtures(league_code: str, limit: int) -> Tuple[List[dict], Optional[dict]]:
    """
    Возвращает (список матчей, err_dict)
    err_dict = { message, attempts: [...], league_display, season_year }
    """
    if league_code not in TM_COMP_CODES:
        return [], {"message": f"No TM competition code for league '{league_code}'"}

    cached = _get_cache(league_code)
    if cached is not None:
        # Ограничим по limit
        data = cached[:limit] if limit and len(cached) > limit else cached
        return data, None

    comp_code = TM_COMP_CODES[league_code]
    season_year = SEASON_START_YEAR
    attempts = []
    collected: List[dict] = []
    first_error: TMFixturesError | None = None

    async with httpx.AsyncClient(timeout=TM_TIMEOUT) as client:
        # Идём по будущим "matchday" (spieltag) начиная с 1 – пока не наберём или не исчерпали лимит lookahead
        # (Можно улучшить, сначало найти текущий тур – упрощаем.)
        for matchday in range(1, TM_MAX_MATCHDAYS_LOOKAHEAD + 1):
            url = f"{TM_BASE}/{LEAGUE_DISPLAY.get(league_code,'')}/spieltag/wettbewerb/{comp_code}/spieltag/{matchday}/saison_id/{season_year}"
            # В URL в реальности имя лиги в slug (с дефисами), но TM терпим к /<что угодно>/spieltag/wettbewerb/...
            try:
                html = await _fetch_html(client, url)
                partial = _parse_match_table(html, season_year)
                attempts.append({"matchday": matchday, "url": url, "status": 200, "found": len(partial)})
                if partial:
                    # Фильтруем уже прошедшие (по timestamp > сейчас - 6ч) – грубо
                    now_ts = int(time.time()) - 6 * 3600
                    future_only = [m for m in partial if (m["timestamp"] or (now_ts + 1)) > now_ts]
                    if future_only:
                        collected.extend(future_only)
                if len(collected) >= limit:
                    break
            except TMFixturesError as e:
                attempts.append({"matchday": matchday, "url": e.url, "status": e.status or 0, "error": str(e)})
                if first_error is None:
                    first_error = e
            # Пауза между турами
            await asyncio.sleep(TM_REQUEST_DELAY_BASE + random.uniform(0, TM_RANDOM_JITTER))

    if not collected:
        err = {
            "message": first_error and str(first_error) or "No fixtures parsed",
            "attempts": attempts,
            "league_display": LEAGUE_DISPLAY.get(league_code, league_code),
            "season_year": season_year,
        }
        return [], err

    # Отсортируем по времени, уберём None в конец
    collected.sort(key=lambda x: (x["timestamp"] is None, x["timestamp"] or 0))
    sliced = collected[:limit]

    _set_cache(league_code, collected)
    return sliced, None
