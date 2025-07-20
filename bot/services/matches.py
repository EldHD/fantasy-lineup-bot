import logging
from typing import List, Dict

from bot.external.tm_fixtures import fetch_league_fixtures, TMFixturesError

logger = logging.getLogger(__name__)

# Обёртка: сейчас не ходим в БД – просто парсим.
# Потом сюда добавим сохранение и кэш.

async def get_upcoming_matches_for_league(
    league_code: str,
    max_show: int = 12,
) -> List[Dict]:
    """
    Возвращает список ближайших (по порядку туров) матчей для лиги.
    Пока просто вытаскивает первые matchdays (до 5 максимум) и фильтрует будущие/с датой.
    """
    try:
        all_matches = await fetch_league_fixtures(league_code, start_matchday=1, max_matchdays=5)
    except TMFixturesError as e:
        logger.error("Fixtures parse error for %s: %s", league_code, e)
        return []

    # Сортируем по matchday и дате (если есть)
    def sort_key(m):
        return (
            m.get("matchday") or 9999,
            m.get("kickoff_utc") or m.get("matchday"),
            m.get("home_team"),
        )

    all_matches.sort(key=sort_key)

    if len(all_matches) > max_show:
        all_matches = all_matches[:max_show]

    return all_matches
