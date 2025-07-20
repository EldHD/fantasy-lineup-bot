import asyncio
import re
import random
from datetime import datetime, date, time, timezone
from typing import List, Tuple, Optional, Dict, Any

import httpx

from bot.config import (
    TM_BASE_WORLD,
    TM_BASE_COM,
    TM_TIMEOUT,
    TM_USER_AGENTS,
    TM_COMP_CODES,
    SEASON_START_YEAR,
    MAX_MATCHDAY_SCAN,
    TM_WORLD_EN_SLUG,
    TM_WORLD_LOCAL_SLUG,
    TM_COM_EN_SLUG,
)
import os
import logging

logger = logging.getLogger(__name__)

FIXTURES_ONLY_UPCOMING = os.getenv("FIXTURES_ONLY_UPCOMING", "0") == "1"
TM_FIXTURE_DEBUG = os.getenv("TM_FIXTURE_DEBUG", "0") == "1"

# --------- Helpers ---------

_MATCH_ROW_RE = re.compile(r"/spielbericht/(\d+)")
# Дата форматы, которые встречались (добавлено несколько)
DATE_PATTERNS = [
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M %Z",
    "%d/%m/%Y",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
]
# Иногда год на странице отсутствует: "15/08/2025" — в туре есть год,
# но бывает формат "15/08" -> добавим сезонный год
SHORT_DAY_RE = re.compile(r"(\d{1,2})[./](\d{1,2})(?!\d)")

def _pick_ua() -> str:
    return random.choice(TM_USER_AGENTS)

def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())

def _parse_datetime(raw: str, fallback_year: int) -> Optional[datetime]:
    raw = raw.strip()
    # Если отсутствует год — подставим fallback_year
    if SHORT_DAY_RE.search(raw) and not re.search(r"\d{4}", raw):
        # Добавим /YYYY
        raw_variants = []
        if " " in raw:
            part_date, *rest = raw.split(" ")
            raw_variants.append(f"{part_date}/{fallback_year} {' '.join(rest)}")
        else:
            raw_variants.append(f"{raw}/{fallback_year}")
        for candidate in raw_variants:
            for fmt in DATE_PATTERNS:
                try:
                    dt = datetime.strptime(candidate, fmt)
                    return dt.replace(tzinfo=timezone.utc)  # упрощенно, можно попытаться угадать TZ
                except ValueError:
                    pass
    else:
        for fmt in DATE_PATTERNS:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None

# --------- Core parsing ---------

async def _fetch(client: httpx.AsyncClient, url: str) -> Tuple[int, str]:
    try:
        r = await client.get(url, timeout=TM_TIMEOUT)
        return r.status_code, r.text
    except Exception as e:
        logger.warning("Fixture fetch exception %s: %s", url, e)
        return 0, ""

def _extract_rows(html: str) -> List[str]:
    # Грубая сегментация по строкам таблицы
    # На transfermarkt строки матчей обычно содержат /spielbericht/<id>
    rows = []
    for m in _MATCH_ROW_RE.finditer(html):
        # Захватим небольшое окно вокруг совпадения, чтобы потом парсить поля
        start = max(0, m.start() - 500)
        end = m.end() + 500
        snippet = html[start:end]
        rows.append(snippet)
    return rows

def _parse_row(snippet: str, fallback_year: int) -> Optional[Dict[str, Any]]:
    # ID матча
    m_id = _MATCH_ROW_RE.search(snippet)
    if not m_id:
        return None
    match_id = int(m_id.group(1))

    # Имя хозяев и гостей — ищем два блока ссылок команд (/verein/)
    team_links = re.findall(r"/(verein|club)/\d+/(?:[^\"/]+?)\"", snippet)
    # Это может выдать лишнее; попробуем альтернативу: названия в alt/title
    # Попробуем вытянуть наименования из title картинки эмблемы
    names = re.findall(r'title="([^"]+)"', snippet)
    # Отфильтруем очевидный "Logo" и т.п.
    names = [n for n in names if not re.search(r"[Ll]ogo", n)]
    home = away = None
    if len(names) >= 2:
        home, away = names[0], names[1]
    else:
        # fallback — по разделителю внутри строки
        # Иногда формат: <a ...>Home</a> - <a ...>Away</a>
        # Возьмём кусок между report ID и концом snippet
        dash_split = re.split(r"&ndash;| - ", snippet)
        if len(dash_split) >= 2:
            # Очень приблизительно — не всегда сработает
            pass

    # Время/дата: попробуем найти фрагмент с <td class="zentriert">...число...
    # Упростим: ищем что-то похожее на dd/mm/yyyy hh:mm или dd.mm.yyyy hh:mm
    date_match = re.search(r"(\d{1,2}[./]\d{1,2}[./]\d{2,4}(?:\s+\d{1,2}:\d{2})?)", snippet)
    kickoff = None
    if date_match:
        kickoff_raw = date_match.group(1)
        kickoff = _parse_datetime(kickoff_raw, fallback_year)

    if not home or not away:
        return None

    return {
        "match_id": match_id,
        "home": _normalize_whitespace(home),
        "away": _normalize_whitespace(away),
        "kickoff": kickoff,
    }

async def fetch_current_matchday_upcoming(league_code: str,
                                          season_year: int = SEASON_START_YEAR,
                                          max_md: int = MAX_MATCHDAY_SCAN) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Возвращает матчи ближайшего тура (matchday), где есть несыгранные (или первый тур, если сезон ещё не начался).
    Если FIXTURES_ONLY_UPCOMING=1 — отфильтровывает только будущие, иначе отдаёт все матчи тура.
    """
    comp = TM_COMP_CODES.get(league_code)
    if not comp:
        return [], f"Unknown league_code={league_code}"

    # Возможные URL шаблоны (порядок пробуем)
    local_slug = TM_WORLD_LOCAL_SLUG.get(league_code, "")
    en_slug_world = TM_WORLD_EN_SLUG.get(league_code, "")
    en_slug_com = TM_COM_EN_SLUG.get(league_code, "")

    url_templates = []
    if local_slug:
        url_templates.append(f"{TM_BASE_WORLD}/{local_slug}/gesamtspielplan/wettbewerb/{comp}?saison_id={{year}}&spieltagVon={{md}}&spieltagBis={{md}}")
    if en_slug_world:
        url_templates.append(f"{TM_BASE_WORLD}/{en_slug_world}/gesamtspielplan/wettbewerb/{comp}?saison_id={{year}}&spieltagVon={{md}}&spieltagBis={{md}}")
    if en_slug_com:
        url_templates.append(f"{TM_BASE_COM}/{en_slug_com}/gesamtspielplan/wettbewerb/{comp}?saison_id={{year}}&spieltagVon={{md}}&spieltagBis={{md}}")

    attempts_debug = []
    chosen_matches: List[Dict[str, Any]] = []
    chosen_md = None

    now_utc = datetime.now(timezone.utc)
    season_not_started = True  # если найдём матч с датой <= now → сезон начат

    async with httpx.AsyncClient(headers={"User-Agent": _pick_ua()}) as client:
        for md in range(1, max_md + 1):
            md_all: List[Dict[str, Any]] = []
            md_future: List[Dict[str, Any]] = []
            last_status = 0
            last_rows = 0
            last_parsed = 0

            for tpl in url_templates:
                url = tpl.format(year=season_year, md=md)
                status, html = await _fetch(client, url)
                if status == 0:
                    attempts_debug.append(f"MD {md} {url} status=0 (network)")
                    continue

                rows = _extract_rows(html)
                parsed: List[Dict[str, Any]] = []
                for snip in rows:
                    item = _parse_row(snip, season_year)
                    if item:
                        parsed.append(item)

                last_status = status
                last_rows = len(rows)
                last_parsed = len(parsed)

                # Сохраним первую успешную попытку этого тура
                if not md_all and parsed:
                    md_all = parsed

                # Если что-то распарсили — нет смысла пробовать следующие шаблоны этого же тура
                if parsed:
                    break

            # Проверим future
            for m in md_all:
                if m["kickoff"] and m["kickoff"] > now_utc:
                    md_future.append(m)
                elif m["kickoff"] and m["kickoff"] <= now_utc:
                    season_not_started = False

            attempts_debug.append(
                f"MD {md}: status={last_status} rows={last_rows} parsed={last_parsed} future={len(md_future)}"
            )

            if not md_all:
                # Ничего не распарсили — перейдём к следующему туру
                continue

            # Критерии выбора
            if md_future:
                chosen_matches = md_future if FIXTURES_ONLY_UPCOMING else md_all
                chosen_md = md
                break
            else:
                # Если сезон ещё не стартовал и это MD=1 — берём его (все матчи)
                if md == 1 and season_not_started:
                    chosen_matches = md_all
                    chosen_md = md
                    break
                # Иначе ищем следующий
                continue

    if not chosen_matches:
        reason = "No upcoming matches in scanned matchdays"
        dbg = ""
        if TM_FIXTURE_DEBUG:
            dbg = "\nAttempts:\n - " + "\n - ".join(attempts_debug)
        err = (
            f"{reason}\nSeason start year: {season_year}\nПросмотрено туров до: {max_md}\n"
            f"Источник: Transfermarkt (matchday filtered){dbg}"
        )
        return [], err

    # Сортируем по времени (если есть)
    chosen_matches.sort(key=lambda x: x["kickoff"] or datetime(2100, 1, 1, tzinfo=timezone.utc))

    return chosen_matches, None
