import logging
from datetime import timezone
from typing import List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.services.matches import get_upcoming_matches_for_league, clear_matches_cache

logger = logging.getLogger(__name__)

# --------- КОНСТАНТЫ / КОНФИГ ---------

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]

# --------- УТИЛИТЫ КЛАВИАТУР ---------

def leagues_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"league:{code}")]
            for name, code in LEAGUES]
    return InlineKeyboardMarkup(rows)

def matches_keyboard(league_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("♻️ Обновить", callback_data=f"refresh_matches:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")],
    ])

def match_team_select_keyboard(league_code: str, match_index: int, home: str, away: str) -> InlineKeyboardMarkup:
    # (Заготовка — если позже будете выбирать команду)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(home, callback_data=f"team:{league_code}:{match_index}:home")],
        [InlineKeyboardButton(away, callback_data=f"team:{league_code}:{match_index}:away")],
        [InlineKeyboardButton("🏟 Матчи", callback_data=f"refresh_matches:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")],
    ])

# --------- /start ---------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())

# --------- CALLBACK: ВЫБОР ЛИГИ ---------

async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, league_code = query.data.split(":", 1)
    await query.edit_message_text(f"Лига выбрана: {league_code if league_code!='epl' else 'Premier League'}\nЗагружаю матчи...")
    await send_matches_list(query, league_code)

# --------- CALLBACK: ОБНОВЛЕНИЕ МАТЧЕЙ ---------

async def refresh_matches_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, league_code = query.data.split(":", 1)
    # Сбрасываем кэш чтобы принудительно перезагрузить
    clear_matches_cache(league_code)
    await query.edit_message_text("Обновление матчей...")
    await send_matches_list(query, league_code)

# --------- CALLBACK: НАЗАД К ЛИГАМ ---------

async def back_to_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Выберите лигу:", reply_markup=leagues_keyboard())

# --------- ВЫВОД СПИСКА МАТЧЕЙ (общая функция) ---------

async def send_matches_list(query, league_code: str):
    matches, meta = await get_upcoming_matches_for_league(league_code, limit=8)

    if matches:
        lines: List[str] = []
        lines.append(f"Матчи ({league_code}):")
        for idx, m in enumerate(matches, start=1):
            dt = m["kickoff_utc"].strftime("%Y-%m-%d %H:%M UTC")
            md = m.get("matchday") or "-"
            lines.append(f"{idx}. {m['home_team']} vs {m['away_team']} — {dt} (тур/раунд: {md})")
        text = "\n".join(lines)
        await query.edit_message_text(text, reply_markup=matches_keyboard(league_code))
    else:
        # Формируем диагностический блок
        reason = meta.get("reason") or "Причина не определена"
        season = meta.get("season_id")
        req_lines = []
        for r in meta.get("requests", []):
            req_lines.append(f"{r['status']} {'OK' if r['status']==200 else ''} {r['url'].split('/api/')[1][:60]}{'' if not r.get('err') else ' ERR'}")
        req_block = "\n".join(req_lines) if req_lines else "нет запросов"

        link = meta.get("link")
        text = (
            f"Нет матчей (лига: {league_code})\n"
            f"Причина: {reason}\n"
            f"Сезон: {season}\n"
            f"Запросы:\n{req_block}"
        )
        if link:
            text += f"\nИсточник: {link}"
        await query.edit_message_text(text, reply_markup=matches_keyboard(league_code))

# --------- РЕГИСТРАЦИЯ ХЕНДЛЕРОВ ---------

def register_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))

    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    app.add_handler(CallbackQueryHandler(refresh_matches_callback, pattern=r"^refresh_matches:"))
    app.add_handler(CallbackQueryHandler(back_to_leagues_callback, pattern=r"^back:leagues"))

# (Остальные ваши хендлеры добавьте аналогично)v
