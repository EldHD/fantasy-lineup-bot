import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.config import LEAGUES

logger = logging.getLogger(__name__)

# =====================================================================
# Попытка импортировать реальные CRUD функции. Если их нет – заглушки.
# =====================================================================
try:
    from bot.db.crud import (
        fetch_matches_by_league,
        fetch_match_with_teams,
        fetch_predictions_for_team_match,
        fetch_predictions_for_match,
    )
except ImportError:
    async def fetch_matches_by_league(league_code: str):
        # Заглушка: нет матчей
        return []

    async def fetch_match_with_teams(match_id: int):
        # Заглушка
        return None

    async def fetch_predictions_for_team_match(team_id: int, match_id: int):
        return []

    async def fetch_predictions_for_match(match_id: int):
        return []

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ПОСТРОЕНИЯ КЛАВИАТУР
# =====================================================================

def build_leagues_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for _, data in LEAGUES.items():
        rows.append([
            InlineKeyboardButton(
                text=data["name"],
                callback_data=f"league:{data['code']}"
            )
        ])
    return InlineKeyboardMarkup(rows)


def build_matches_keyboard(league_code: str, matches: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    matches: список словарей/объектов с полями id, home_name, away_name, kickoff (datetime).
    """
    rows = []
    for m in matches[:25]:  # ограничим чтобы не раздувать клавиатуру
        mid = getattr(m, "id", None) or m.get("id")
        home = getattr(m, "home_team_name", None) or m.get("home_team_name") or m.get("home_name") or "Home"
        away = getattr(m, "away_team_name", None) or m.get("away_team_name") or m.get("away_name") or "Away"
        text = f"{home} vs {away}"
        rows.append([InlineKeyboardButton(text, callback_data=f"match:{mid}:{league_code}")])

    rows.append([InlineKeyboardButton("⬅ Лиги", callback_data="back:leagues")])
    return InlineKeyboardMarkup(rows)


def build_teams_keyboard(match_id: int, league_code: str, home_team: Dict[str, Any], away_team: Dict[str, Any]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(home_team['name'], callback_data=f"team:{home_team['id']}:{match_id}:{league_code}")],
        [InlineKeyboardButton(away_team['name'], callback_data=f"team:{away_team['id']}:{match_id}:{league_code}")],
        [InlineKeyboardButton("⬅ Матчи", callback_data=f"back:matches:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]
    ]
    return InlineKeyboardMarkup(rows)


# =====================================================================
# /start
# =====================================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=build_leagues_keyboard())
    elif update.callback_query:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text("Выберите лигу:", reply_markup=build_leagues_keyboard())


# =====================================================================
# Callback: выбор лиги
# =====================================================================
async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    data = q.data  # format league:<code>
    parts = data.split(":", 1)
    if len(parts) != 2:
        return
    league_code = parts[1]

    # Получаем матчи
    try:
        matches = await fetch_matches_by_league(league_code)
    except Exception as e:
        logger.exception("Error fetching matches for league %s", league_code)
        await q.edit_message_text(f"Произошла ошибка при загрузке матчей для {league_code.upper()} :(",
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton("⬅ Лиги", callback_data="back:leagues")]
                                  ]))
        return

    if not matches:
        await q.edit_message_text(f"Нет доступных матчей для {league_code.upper()}",
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton("⬅ Лиги", callback_data="back:leagues")]
                                  ]))
        return

    # Показываем клавиатуру матчей
    await q.edit_message_text(
        text="Выберите матч:",
        reply_markup=build_matches_keyboard(league_code, matches)
    )


# =====================================================================
# Callback: выбор матча
# =====================================================================
async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    # format: match:<match_id>:<league_code>
    parts = q.data.split(":")
    if len(parts) != 3:
        return
    _, match_id_str, league_code = parts
    try:
        match_id = int(match_id_str)
    except ValueError:
        return

    match = await fetch_match_with_teams(match_id)
    if not match:
        await q.edit_message_text("Матч не найден.",
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton("⬅ Матчи", callback_data=f"back:matches:{league_code}")],
                                      [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]
                                  ]))
        return

    # Предполагаем, что match.home_team / match.away_team присутствуют
    # Приводим к словарям
    def to_team_dict(t):
        if t is None:
            return {"id": 0, "name": "Unknown"}
        return {
            "id": getattr(t, "id", None) or t.get("id"),
            "name": getattr(t, "name", None) or t.get("name") or "Unknown"
        }

    home_team = to_team_dict(getattr(match, "home_team", None) or getattr(match, "home", None) or {})
    away_team = to_team_dict(getattr(match, "away_team", None) or getattr(match, "away", None) or {})

    kickoff = getattr(match, "kickoff", None) or getattr(match, "kickoff_time", None)
    if isinstance(kickoff, datetime):
        ko_text = kickoff.strftime("%Y-%m-%d %H:%M UTC")
    else:
        ko_text = str(kickoff) if kickoff else "N/A"

    header = f"{home_team['name']} vs {away_team['name']}\nKickoff: {ko_text}"
    await q.edit_message_text(
        header + "\n\nВыберите команду:",
        reply_markup=build_teams_keyboard(match_id, league_code, home_team, away_team)
    )


# =====================================================================
# Callback: выбор команды для показа предиктов
# =====================================================================
async def team_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    # format: team:<team_id>:<match_id>:<league_code>
    parts = q.data.split(":")
    if len(parts) != 4:
        return
    _, team_id_str, match_id_str, league_code = parts
    try:
        team_id = int(team_id_str)
        match_id = int(match_id_str)
    except ValueError:
        return

    # Получаем предикты для одной команды в матче
    try:
        preds = await fetch_predictions_for_team_match(team_id, match_id)
    except Exception as e:
        logger.exception("Error fetching predictions")
        preds = []

    if not preds:
        text = "Нет предиктов для этой команды."
    else:
        # Пример формирования текста
        lines = ["Предикт стартового состава:"]
        for p in preds:
            # Предполагаем поля p.player_name, p.position, p.probability
            name = getattr(p, "player_name", None) or getattr(p, "name", None) or p.get("player_name", "Player")
            pos = getattr(p, "position", None) or p.get("position", "")
            prob = getattr(p, "probability", None) or p.get("probability", 0)
            lines.append(f"- {name} ({pos}) {int(prob)}%")
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Матчи", callback_data=f"back:matches:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]
    ])
    await q.edit_message_text(text=text, reply_markup=kb)


# =====================================================================
# Callback: назад к лигам
# =====================================================================
async def back_to_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("Выберите лигу:", reply_markup=build_leagues_keyboard())


# =====================================================================
# Callback: назад к матчам
# =====================================================================
async def back_to_matches_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    # формат: back:matches:<league_code>
    parts = q.data.split(":")
    if len(parts) != 3:
        return
    league_code = parts[2]

    try:
        matches = await fetch_matches_by_league(league_code)
    except Exception:
        matches = []

    if not matches:
        await q.edit_message_text(f"Нет доступных матчей для {league_code.upper()}",
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton("⬅ Лиги", callback_data="back:leagues")]
                                  ]))
        return

    await q.edit_message_text("Выберите матч:", reply_markup=build_matches_keyboard(league_code, matches))


# =====================================================================
# Команда: /sync_roster (ручной синк одной или двух команд) – заглушка
# =====================================================================
async def sync_roster_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Ручной синк (заглушка).")


# =====================================================================
# Команда: /resync_all – батчи по лигам (заглушка)
# =====================================================================
async def resync_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Ресинк всех команд (заглушка).")


# =====================================================================
# Команда: /export – экспорт предикта (заглушка)
# =====================================================================
async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Экспорт (заглушка).")


# =====================================================================
# Дополнительная команда для диагностики
# =====================================================================
async def debug_leagues_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = []
    for k, v in LEAGUES.items():
        lines.append(f"{k}: {v['code']} — {v['name']}")
    if update.message:
        await update.message.reply_text("LEAGUES:\n" + "\n".join(lines))


# =====================================================================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ (если где-то вызывается get_handlers())
# =====================================================================
def get_handlers():
    return [
        CommandHandler("start", start_cmd),
        CommandHandler("sync_roster", sync_roster_cmd),
        CommandHandler("resync_all", resync_all_cmd),
        CommandHandler("export", export_cmd),
        CommandHandler("debug_leagues", debug_leagues_cmd),

        CallbackQueryHandler(league_callback, pattern=r"^league:"),
        CallbackQueryHandler(match_callback, pattern=r"^match:"),
        CallbackQueryHandler(team_callback, pattern=r"^team:"),
        CallbackQueryHandler(back_to_matches_callback, pattern=r"^back:matches:"),
        CallbackQueryHandler(back_to_leagues_callback, pattern=r"^back:leagues$"),
    ]
