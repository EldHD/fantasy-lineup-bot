import random
import httpx
from selectolax.parser import HTMLParser
from typing import List, Dict, Tuple, Optional

from bot.config import (
    TM_COMP_CODES,
    TM_BASE_COM,
    TM_BASE_WORLD,
    TM_USER_AGENTS,
    TM_TIMEOUT,
    TM_MAX_RETRIES,
    SEASON_START_YEAR,
    MAX_MATCHDAY_SCAN,
    TM_CALENDAR_DEBUG,
)

Fixture = Dict[str, object]
FixtureList = List[Fixture]

# ---------- Вспомогательные ----------

def _choose_base_urls() -> List[str]:
    # Можем пытаться обе локализации
    return [TM_BASE_WORLD, TM_BASE_COM]

def _headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(TM_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
        "Connection": "keep-alive",
    }

def _fetch(url: str) -> Tuple[int, str]:
    try:
        with httpx.Client(timeout=TM_TIMEOUT, follow_redirects=True) as client:
            r = client.get(url, headers=_headers())
            return r.status_code, r.text
    except Exception as e:
        return 0, f"__ERR__:{e}"

def _log_debug(*args):
    if TM_CALENDAR_DEBUG:
        print("[TM_DEBUG]", *args)

# ---------- Парсинг страниц тура ----------

def _parse_matchday_page(html: str, season: int) -> FixtureList:
    """
    Универсальный парсер строк матчей (matchday страница или фильтр по туру).
    Ищем tr с >=2 ссылками на /startseite/verein.
    """
    tree = HTMLParser(html)
    fixtures: FixtureList = []
    current_date_text = ""

    def extract_match_id(tr_node) -> Optional[int]:
        a = tr_node.css_first("a[href*='spielbericht']")
        if not a:
            a = tr_node.css_first("a.ergebnis-link")
        if not a:
            return None
        href = a.attributes.get("href", "")
        parts = href.strip("/").split("/")
        for part in reversed(parts):
            if part.isdigit():
                return int(part)
        return None

    all_tr = tree.css("tr")
    for tr in all_tr:
        txt = tr.text(" ", strip=True)

        # попытка выделить "строку даты" (часто отдельная строка с одной ячейкой)
        tds = tr.css("td")
        if len(tds) == 1:
            t = txt.lower()
            if any(x in t for x in [
                "2025", str(season),
                "jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec",
                "янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"
            ]):
                # грубая эвристика
                if any(ch.isdigit() for ch in t):
                    current_date_text = txt

        links = tr.css("a[href*='/startseite/verein/']")
        if len(links) < 2:
            continue

        home = links[0].text(strip=True)
        away = links[1].text(strip=True)

        # время
        raw_time = ""
        for td in tds:
            ttext = td.text(strip=True)
            if ":" in ttext and len(ttext) <= 5 and ttext.count(":") == 1:
                hh, mm = ttext.split(":")
                if hh.isdigit() and mm.isdigit() and int(hh) <= 23 and int(mm) <= 59:
                    raw_time = ttext
                    break

        match_id = extract_match_id(tr)
        dt_str = f"{current_date_text} {raw_time}".strip()

        fixtures.append({
            "match_id": match_id,
            "home": home,
            "away": away,
            "raw_date": current_date_text,
            "raw_time": raw_time,
            "dt_str": dt_str,
            "season": season,
        })

    return fixtures


def _parse_full_season_page(html: str, season: int) -> FixtureList:
    """
    Альтернативный парсер (страница полного сезона без фильтра по туру).
    Логика та же – используем универсальный метод.
    """
    return _parse_matchday_page(html, season)


# ---------- Основная функция: получить ближайшие матчи текущего (первого открытого) тура ----------

def fetch_current_matchday_upcoming(league_code: str, limit: int = 15) -> Tuple[FixtureList, Dict]:
    """
    Пытаемся:
      1) Найти первый тур (matchday) где есть будущие матчи (т.е. у нас сейчас нет инфы о времени -> считаем все будущими).
         Реально мы просто берём первый тур в диапазоне 1..MAX_MATCHDAY_SCAN где есть >=1 матч.
      2) Если туры не дали результатов -> fallback на полную страницу (все матчи сезона) и берём первые будущие.
    Возвращает (fixtures, meta) где fixtures – список матчей, meta – диагностика.
    """
    comp = TM_COMP_CODES[league_code]
    season = SEASON_START_YEAR
    attempts = []
    gathered: FixtureList = []

    bases = _choose_base_urls()

    # --- Скан по турам ---
    for md in range(1, MAX_MATCHDAY_SCAN + 1):
        found_any = False
        for base in bases:
            url = f"{base}/premier-league/gesamtspielplan/wettbewerb/{comp}?saison_id={season}&spieltagVon={md}&spieltagBis={md}"
            status, text = _fetch(url)
            if status == 200 and not text.startswith("__ERR__"):
                parsed = _parse_matchday_page(text, season)
                attempts.append({"md": md, "url": url, "status": status, "parsed": len(parsed)})
                if parsed:
                    gathered = parsed
                    found_any = True
                    break
            else:
                attempts.append({"md": md, "url": url, "status": status, "error": text})
        if found_any:
            break

    if not gathered:
        # --- Fallback: полная страница сезона на первом домене где 200 ---
        for base in bases:
            full_url = f"{base}/premier-league/gesamtspielplan/wettbewerb/{comp}/saison_id/{season}"
            status, text = _fetch(full_url)
            if status == 200 and not text.startswith("__ERR__"):
                parsed = _parse_full_season_page(text, season)
                attempts.append({"fallback_full": True, "url": full_url, "status": status, "parsed": len(parsed)})
                gathered = parsed
                break
            else:
                attempts.append({"fallback_full": True, "url": full_url, "status": status, "error": text})

    # Ограничим вывод
    if limit and len(gathered) > limit:
        gathered = gathered[:limit]

    meta = {
        "league_code": league_code,
        "season_start_year": season,
        "attempts": attempts,
        "match_count": len(gathered),
        "source": "Transfermarkt",
    }

    # Фильтрация «в будущем» сейчас условна (у нас нет нормального парсинга времени -> оставляем всё)
    return gathered, meta
    
