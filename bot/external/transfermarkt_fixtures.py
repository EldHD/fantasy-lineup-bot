import httpx
from selectolax.parser import HTMLParser
import asyncio
import random
from typing import List, Tuple, Optional, Dict

import bot.config as cfg

# Тип результата парсера: список словарей с полями матча + текст ошибки (или None)
FixtureList = List[Dict]


def _choose_base_domains() -> List[str]:
    # Порядок: пробуем WORLD потом COM
    return [cfg.TM_BASE_WORLD, cfg.TM_BASE_COM]


async def fetch_current_matchday_upcoming(league_code: str, matchday: int = 1) -> Tuple[FixtureList, Optional[str], dict]:
    """
    Парсит ТОЛЬКО указанный тур (matchday -> matchday) для лиги league_code
    Возвращает: (fixtures, error, debug_info)
    Если матчей нет — fixtures пуст и в error текст причины.
    """
    comp = cfg.TM_COMP_CODES.get(league_code)
    if not comp:
        return [], f"Unknown league_code '{league_code}'", {"league_code": league_code}

    season = cfg.TM_SEASON_YEAR
    debug_attempts = []
    fixtures: FixtureList = []

    headers_base = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/",
    }

    domains = _choose_base_domains()
    url_patterns = cfg.TM_FIXTURE_URL_PATTERNS

    async def try_fetch(client: httpx.AsyncClient, url: str):
        try:
            r = await client.get(url, timeout=cfg.TM_TIMEOUT)
            return r
        except Exception as e:
            return e

    for domain in domains:
        for pattern in url_patterns:
            url = pattern.format(
                base=domain,
                comp=comp,
                season=season,
                matchday=matchday
            )
            ua = cfg.pick_user_agent()
            headers = dict(headers_base)
            headers["User-Agent"] = ua

            for attempt in range(1, cfg.TM_MAX_RETRIES + 1):
                async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
                    resp = await try_fetch(client, url)
                if isinstance(resp, Exception):
                    debug_attempts.append({
                        "url": url,
                        "attempt": attempt,
                        "error": f"EXC {resp.__class__.__name__}: {resp}"
                    })
                    await asyncio.sleep(cfg.TM_RETRY_SLEEP_BASE + random.uniform(0, cfg.TM_RETRY_SLEEP_JITTER))
                    continue

                status = resp.status_code
                if status != 200:
                    debug_attempts.append({
                        "url": url,
                        "attempt": attempt,
                        "status": status,
                        "error": f"HTTP {status}"
                    })
                    await asyncio.sleep(cfg.TM_RETRY_SLEEP_BASE + random.uniform(0, cfg.TM_RETRY_SLEEP_JITTER))
                    continue

                html = resp.text
                parsed = _parse_matchday_page(html, season=season)
                debug_attempts.append({
                    "url": url,
                    "attempt": attempt,
                    "status": status,
                    "parsed": len(parsed)
                })
                if parsed:
                    fixtures.extend(parsed)
                    # Если нашли — выходим (нужно только этот тур)
                    return fixtures, None, {
                        "season": season,
                        "matchday": matchday,
                        "attempts": debug_attempts
                    }
                # parsed == 0
                await asyncio.sleep(0.4 + random.uniform(0, 0.6))

    # Ничего не нашли
    return [], "No matches parsed", {
        "season": season,
        "matchday": matchday,
        "attempts": debug_attempts
    }


def _parse_matchday_page(html: str, season: int) -> FixtureList:
    """
    Парсинг таблицы матчей тура.
    Transfermarkt 'gesamtspielplan' — строки с классами alternating, odd, even etc.
    Ищем даты и пары команд.
    Воспринимаем только матчи у которых есть обе команды и дата в будущем/настоящем.
    """
    tree = HTMLParser(html)

    # Секции дат могут быть в элементах с классами: "content-box-headline" или date tags.
    # Сами строки матчей часто <tr class="begegnungZeile ...">
    rows = tree.css("tr.begegnungZeile")
    fixtures: FixtureList = []

    for tr in rows:
        # Ищем id матча (data-id или ссылку на spielbericht)
        link = tr.css_first("a.ergebnis-link, a.matchreport, a[href*='spielbericht']")
        match_id = None
        if link:
            href = link.attributes.get("href", "")
            # ссылки содержат .../spielbericht/index/spielbericht/{id}
            parts = href.strip("/").split("/")
            for part in reversed(parts):
                if part.isdigit():
                    match_id = int(part)
                    break

        home_el = tr.css_first("td:nth-child(4) a[href*='/startseite/']")
        away_el = tr.css_first("td:nth-child(6) a[href*='/startseite/']")
        if not home_el or not away_el:
            continue
        home_name = home_el.text(strip=True)
        away_name = away_el.text(strip=True)

        date_el = tr.css_first("td:nth-child(2)")
        time_el = tr.css_first("td:nth-child(3)")

        raw_date = date_el.text(strip=True) if date_el else ""
        raw_time = time_el.text(strip=True) if time_el else ""

        # Дата может быть в формате 15/08/2025 или 15.08.2025 — нормализуем
        dt_str = f"{raw_date} {raw_time}".strip()

        fixtures.append({
            "match_id": match_id,
            "home": home_name,
            "away": away_name,
            "raw_date": raw_date,
            "raw_time": raw_time,
            "dt_str": dt_str,
            "season": season,
        })

    return fixtures
