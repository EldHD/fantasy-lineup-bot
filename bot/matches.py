import datetime as dt
from typing import List, Dict, Optional

# Пока делаем простую in-memory «базу».
# Время укажем в UTC (важно для твоего ТЗ).

# Структура матча:
# {
#   "id": "rpl_24012025_zen_csk",
#   "league": "rpl",
#   "round": "Round 18",
#   "utc_kickoff": dt.datetime(..., tzinfo=dt.timezone.utc),
#   "home_team": {"code": "ZEN", "name": "Zenit"},
#   "away_team": {"code": "CSK", "name": "CSKA"},
# }

_NOW = dt.datetime.now(dt.timezone.utc)

# Примерные ближайшие матчи (замени когда подключим парсер)
_MATCHES: List[Dict] = [
    {
        "id": "rpl_1_zen_csk",
        "league": "rpl",
        "round": "Matchday 1",
        "utc_kickoff": _NOW + dt.timedelta(hours=20),
        "home_team": {"code": "ZEN", "name": "Zenit"},
        "away_team": {"code": "CSK", "name": "CSKA Moscow"},
    },
    {
        "id": "rpl_1_spa_dyn",
        "league": "rpl",
        "round": "Matchday 1",
        "utc_kickoff": _NOW + dt.timedelta(hours=26),
        "home_team": {"code": "SPA", "name": "Spartak Moscow"},
        "away_team": {"code": "DYN", "name": "Dynamo Moscow"},
    },
    {
        "id": "epl_1_ars_che",
        "league": "epl",
        "round": "Matchweek 1",
        "utc_kickoff": _NOW + dt.timedelta(hours=30),
        "home_team": {"code": "ARS", "name": "Arsenal"},
        "away_team": {"code": "CHE", "name": "Chelsea"},
    },
    {
        "id": "epl_1_mci_liv",
        "league": "epl",
        "round": "Matchweek 1",
        "utc_kickoff": _NOW + dt.timedelta(hours=40),
        "home_team": {"code": "MCI", "name": "Manchester City"},
        "away_team": {"code": "LIV", "name": "Liverpool"},
    }
]


def format_kickoff(dt_obj: dt.datetime) -> str:
    return dt_obj.strftime("%Y-%m-%d %H:%M UTC")


def get_upcoming_matches(league_code: str, limit: int = 10) -> List[Dict]:
    matches = [m for m in _MATCHES if m["league"] == league_code]
    matches.sort(key=lambda m: m["utc_kickoff"])
    return matches[:limit]


def get_match(match_id: str) -> Optional[Dict]:
    for m in _MATCHES:
        if m["id"] == match_id:
            return m
    return None


def get_teams_for_match(match_id: str):
    match = get_match(match_id)
    if not match:
        return None
    return match["home_team"], match["away_team"]


# Заглушечный предикт состава
def get_dummy_lineup(match_id: str, team_code: str):
    # Вернём простой список (потом заменим на реальный объект из БД)
    # Для демонстрации позиции и вероятность.
    players = [
        {
            "name": "Player 1",
            "number": 1,
            "position": "goalkeeper (GK)",
            "probability": 95,
            "reason": "Основной вратарь, без травм",
        },
        {
            "name": "Player 2",
            "number": 4,
            "position": "defender (CB)",
            "probability": 90,
            "reason": "Стартовал в последних 5 матчах",
        },
        {
            "name": "Player 3",
            "number": 5,
            "position": "defender (CB)",
            "probability": 85,
            "reason": "Ротация минимальна",
        },
        {
            "name": "Player 4",
            "number": 2,
            "position": "defender (RB)",
            "probability": 80,
            "reason": "Тренер положительно отозвался на пресс-конференции",
        },
        {
            "name": "Player 5",
            "number": 3,
            "position": "defender (LB)",
            "probability": 88,
            "reason": "Нет конкурентов на позиции",
        },
        {
            "name": "Player 6",
            "number": 6,
            "position": "midfielder (DM)",
            "probability": 92,
            "reason": "Ключевой опорник",
        },
        {
            "name": "Player 7",
            "number": 8,
            "position": "midfielder (CM)",
            "probability": 87,
            "reason": "Форма хорошая по последним матчам",
        },
        {
            "name": "Player 8",
            "number": 10,
            "position": "midfielder (AM)",
            "probability": 89,
            "reason": "Создаёт моменты — высокий рейтинг",
        },
        {
            "name": "Player 9",
            "number": 7,
            "position": "forward (RW)",
            "probability": 83,
            "reason": "Конкурент травмирован",
        },
        {
            "name": "Player 10",
            "number": 11,
            "position": "forward (LW)",
            "probability": 86,
            "reason": "Стабильный стартовый игрок",
        },
        {
            "name": "Player 11",
            "number": 9,
            "position": "forward (CF)",
            "probability": 93,
            "reason": "Основной нападающий",
        },
    ]
    return players
