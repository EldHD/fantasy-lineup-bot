import logging
from datetime import datetime
from typing import List, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    Application,
)
from bot.config import LEAGUE_DISPLAY, DEFAULT_MATCH_LIMIT, END_USER_INTERNAL_ERROR_MESSAGE
from bot.matches import (
    load_matches_for_league,
    render_matches_text,
    render_no_matches_error,
)

logger = logging.getLogger(__name__)


# ---------- Вспомогательные клавиатуры ----------

def leagues_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=LEAGUE_DISPLAY["epl"], callback_data="league:epl")],
        [InlineKeyboardButton(text=LEAGUE_DISPLAY["laliga"], callback_data="league:laliga")],
        [InlineKeyboardButton(text=LEAGUE_DISPLAY["serie_a"], callback_data="league:serie_a")],
        [InlineKeyboardButton(text=LEAGUE_DISPLAY["bundesliga"], callback_data="league:bundesliga")],
        [InlineKeyboardButton(text=LEAGUE_DISPLAY["ligue1"], callback_data="league:ligue1")],
        [InlineKeyboardButton(text=LEAGUE_DISPLAY["rpl"], callback_data="league:rpl")],
    ]
    return InlineKeyboardMarkup(buttons)


def matches_actions_keyboard(league_code: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")],
    ]
    return InlineKeyboardMarkup(buttons)


# ---------- Команды ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())


# ---------- Коллбэки ----------

async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, league_code = query.data.split(":", 1)

    await query.edit_message_text(f"Лига выбрана: {LEAGUE_DISPLAY.get(league_code, league_code)}\nЗагружаю матчи...")
    text, kb = await _load_and_render_matches(league_code)
    await query.message.reply_text(text, reply_markup=kb)


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, league_code = query.data.split(":", 1)

    await query.edit_message_text("Обновление матчей...")
    text, kb = await _load_and_render_matches(league_code)
    await query.message.reply_text(text, reply_markup=kb)


async def back_to_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())


# ---------- Вспомогательная логика загрузки матчей ----------

async def _load_and_render_matches(league_code: str) -> Tuple[str, InlineKeyboardMarkup]:
    try:
        matches, err = await load_matches_for_league(league_code, limit=DEFAULT_MATCH_LIMIT)
        if err:
            text = render_no_matches_error(league_code, err)
        else:
            if not matches:
                text = f"Нет матчей (лига: {LEAGUE_DISPLAY.get(league_code, league_code)})"
            else:
                text = render_matches_text(league_code, matches)
    except Exception as e:
        logger.exception("Unexpected error while loading matches for %s", league_code)
        text = f"{END_USER_INTERNAL_ERROR_MESSAGE}"
    kb = matches_actions_keyboard(league_code)
    return text, kb


# ---------- Error Handler ----------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error (update=%r)", update)
    # Пытаемся ответить пользователю (если это сообщение / callback)
    try:
        if isinstance(update, Update):
            if update.callback_query:
                await update.callback_query.message.reply_text(END_USER_INTERNAL_ERROR_MESSAGE)
            elif update.message:
                await update.message.reply_text(END_USER_INTERNAL_ERROR_MESSAGE)
    except Exception:
        pass


# ---------- Регистрация ----------

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern=r"^refresh:"))
    app.add_handler(CallbackQueryHandler(back_to_leagues_callback, pattern=r"^back:leagues$"))
    app.add_error_handler(error_handler)
