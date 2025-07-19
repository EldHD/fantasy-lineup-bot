import logging
from typing import List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
)

from bot.config import LEAGUES

logger = logging.getLogger(__name__)


# ================== Кнопочные клавиатуры =====================================

def leagues_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for code, data in LEAGUES.items():
        rows.append([InlineKeyboardButton(data["name"], callback_data=f"league:{code}")])
    return InlineKeyboardMarkup(rows)


# ================== Команды ==================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())


# ================== Callback'и ===============================================

async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора лиги"""
    query = update.callback_query
    await query.answer()
    data = query.data  # формата league:epl
    _, league_code = data.split(":", 1)

    # Пока просто подтверждаем. Здесь ты дальше вызываешь загрузку матчей.
    await query.edit_message_text(
        f"Лига выбрана: {LEAGUES.get(league_code, {}).get('name', league_code)}"
    )


# ================== Ошибки ===================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error: %s", context.error)
    if isinstance(update, Update):
        try:
            if update.effective_message:
                await update.effective_message.reply_text("⚠️ Внутренняя ошибка.")
        except Exception:
            pass
