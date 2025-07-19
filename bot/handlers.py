import logging
from typing import Optional, Dict, Any

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


# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------

def build_leagues_keyboard() -> InlineKeyboardMarkup:
    """
    НЕ мутирует LEAGUES. Просто строит новую клавиатуру.
    Каждая лига в своей строке.
    """
    rows = []
    for key, data in LEAGUES.items():
        rows.append([
            InlineKeyboardButton(
                text=data["name"],
                callback_data=f"league:{data['code']}"
            )
        ])
    return InlineKeyboardMarkup(rows)


def build_matches_keyboard(dummy_league_code: str) -> InlineKeyboardMarkup:
    """
    Заглушка – тут должна быть реальная загрузка матчей.
    Сейчас просто возвращаем кнопку '⬅ Лиги'.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Лиги", callback_data="back:leagues")]
    ])


# ---------- HANDLERS / CALLBACKS ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /start – всегда печатаем полный список лиг.
    """
    markup = build_leagues_keyboard()

    # Если это обычное сообщение
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=markup)
    # Если хотим реагировать ещё и на callback (например, из других мест)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text="Выберите лигу:",
            reply_markup=markup
        )


async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработка нажатия на кнопку лиги.
    callback_data формата 'league:<code>'
    """
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    parts = query.data.split(":", 1)
    if len(parts) != 2:
        return

    league_code = parts[1]

    # Здесь должна быть загрузка матчей из БД (по реальному league_code).
    # Пока выводим заглушку.
    text = f"Матчи для лиги: {league_code.upper()} (заглушка)\n(Тут появится список матчей)"

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Лиги", callback_data="back:leagues")]
    ])

    await query.edit_message_text(text=text, reply_markup=markup)


async def back_to_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Возврат к списку лиг из любых внутренних экранов.
    """
    query = update.callback_query
    if query:
        await query.answer()
        markup = build_leagues_keyboard()
        await query.edit_message_text("Выберите лигу:", reply_markup=markup)


async def debug_leagues_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда для проверки, что в памяти полный словарь LEAGUES
    и он не усечён.
    """
    lines = []
    for k, v in LEAGUES.items():
        lines.append(f"{k}: {v['code']} — {v['name']}")
    text = "LEAGUES сейчас:\n" + "\n".join(lines)
    if update.message:
        await update.message.reply_text(text)


# ---------- РЕГИСТРАЦИЯ ХЕНДЛЕРОВ ----------

def get_handlers():
    """
    Возвращает список готовых хендлеров, чтобы main.py их подключил.
    """
    return [
        CommandHandler("start", start_cmd),
        CommandHandler("debug_leagues", debug_leagues_cmd),
        CallbackQueryHandler(league_callback, pattern=r"^league:"),
        CallbackQueryHandler(back_to_leagues_callback, pattern=r"^back:leagues$"),
    ]
