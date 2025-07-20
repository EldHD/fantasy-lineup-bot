import logging
from typing import Tuple, Optional, List

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

from bot.config import (
    LEAGUES,
    LEAGUE_DISPLAY,
)
from bot.matches import (
    load_matches_for_league,
    render_matches_text,
    render_no_matches_error,
)

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Вспомогательные keyboards
# -------------------------------------------------
def leagues_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for code in LEAGUES:
        rows.append([InlineKeyboardButton(LEAGUE_DISPLAY.get(code, code), callback_data=f"league:{code}")])
    return InlineKeyboardMarkup(rows)

def matches_keyboard(league_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")],
    ])

# -------------------------------------------------
# /start
# -------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())

# -------------------------------------------------
# Внутренняя функция загрузки + сбор текста/кнопок
# -------------------------------------------------
async def _load_and_render_matches(league_code: str) -> Tuple[str, InlineKeyboardMarkup]:
    # Показываем “загружаю…” отдельно – вызывается в handler
    matches, err = await load_matches_for_league(league_code, limit=15)
    if err:
        text = render_no_matches_error(league_code, err)
    else:
        text = render_matches_text(league_code, matches)
    kb = matches_keyboard(league_code)
    return text, kb

# -------------------------------------------------
# Callback: выбор лиги
# -------------------------------------------------
async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    _, league_code = data.split(":", 1)
    await query.edit_message_text(f"Лига выбрана: {LEAGUE_DISPLAY.get(league_code, league_code)}\nЗагружаю матчи...")
    try:
        text, kb = await _load_and_render_matches(league_code)
        await query.message.reply_text(text, reply_markup=kb)
    except Exception as e:
        logger.exception("Unhandled error loading matches")
        await query.message.reply_text("⚠️ Внутренняя ошибка. Сообщите администратору.")

# -------------------------------------------------
# Callback: обновление матчей
# -------------------------------------------------
async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, league_code = query.data.split(":", 1)
    await query.edit_message_text("Обновление матчей...")
    try:
        text, kb = await _load_and_render_matches(league_code)
        await query.edit_message_text(text, reply_markup=kb)
    except Exception:
        logger.exception("Error refreshing matches")
        await query.edit_message_text("⚠️ Ошибка при обновлении.")
    
# -------------------------------------------------
# Callback: назад к лигам
# -------------------------------------------------
async def back_to_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Выберите лигу:", reply_markup=leagues_keyboard())

# -------------------------------------------------
# Регистрация
# -------------------------------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern=r"^refresh:"))
    app.add_handler(CallbackQueryHandler(back_to_leagues_callback, pattern=r"^back:leagues$"))
