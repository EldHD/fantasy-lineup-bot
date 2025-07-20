import logging
from typing import List, Dict, Optional

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

from bot.services.matches import get_upcoming_matches_for_league

logger = logging.getLogger(__name__)

# ---------------------------
# Справочники лиг
# ---------------------------
LEAGUES = {
    "epl": "Premier League",
    "laliga": "La Liga",
    "seriea": "Serie A",
    "bundesliga": "Bundesliga",
    "ligue1": "Ligue 1",
    "rpl": "Russian Premier League",
}

LEAGUE_BUTTONS_ORDER = ["epl", "laliga", "seriea", "bundesliga", "ligue1", "rpl"]


# ---------------------------
# Вспомогательные клавиатуры
# ---------------------------
def leagues_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(LEAGUES[c], callback_data=f"league:{c}")]
        for c in LEAGUE_BUTTONS_ORDER
    ]
    return InlineKeyboardMarkup(rows)


def matches_nav_keyboard(league_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{league_code}"),
            ],
            [
                InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues"),
            ],
        ]
    )


# ---------------------------
# Форматирование матчей
# ---------------------------
def format_matches(league_code: str, matches: List[Dict]) -> str:
    if not matches:
        return f"Нет матчей (лига: {LEAGUES.get(league_code, league_code)})"

    lines = [f"🗓 Матчи: {LEAGUES.get(league_code, league_code)}"]
    current_md = None
    for m in matches:
        md = m.get("matchday")
        if md != current_md:
            lines.append(f"\nТур {md}:")
            current_md = md
        ko = m.get("kickoff_utc")
        if ko:
            ko_txt = ko.strftime("%Y-%m-%d %H:%M UTC")
        else:
            # fallback raw
            date_raw = m.get("date_raw") or "?"
            time_raw = m.get("time_raw") or ""
            ko_txt = f"{date_raw} {time_raw}".strip()

        lines.append(f"• {m['home_team']} vs {m['away_team']} — {ko_txt}")
    return "\n".join(lines)[:3900]  # ограничим чтобы не превысить лимит сообщения


# ---------------------------
# Команды
# ---------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – выбрать лигу\n"
        "После выбора лиги парсим ближайшие матчи (демо)."
    )


# ---------------------------
# Callbacks
# ---------------------------
async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # league:<code>
    _, league_code = data.split(":", 1)

    await query.edit_message_text(f"Лига выбрана: {LEAGUES.get(league_code, league_code)}\nЗагружаю матчи...")
    matches = await get_upcoming_matches_for_league(league_code)
    text = format_matches(league_code, matches)
    await query.message.reply_text(text, reply_markup=matches_nav_keyboard(league_code))


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, league_code = query.data.split(":", 1)
    await query.edit_message_text("Обновление матчей...")
    matches = await get_upcoming_matches_for_league(league_code)
    text = format_matches(league_code, matches)
    await query.message.reply_text(text, reply_markup=matches_nav_keyboard(league_code))


async def back_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выберите лигу:", reply_markup=leagues_keyboard())


# ---------------------------
# Регистрация хэндлеров
# ---------------------------
def get_handlers():
    return [
        CommandHandler("start", start_cmd),
        CommandHandler("help", help_cmd),
        CallbackQueryHandler(league_callback, pattern=r"^league:"),
        CallbackQueryHandler(refresh_callback, pattern=r"^refresh:"),
        CallbackQueryHandler(back_leagues_callback, pattern=r"^back:leagues$"),
    ]
