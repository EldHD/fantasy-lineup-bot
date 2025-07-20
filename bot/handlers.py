import logging
from typing import List, Tuple, Optional

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

# Парсер матчей (наш новый модуль)
from bot.matches import load_matches_for_league

logger = logging.getLogger(__name__)

# --- Константы / настройки ---

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]

# CallbackData “простого” формата:
#   league:<code>
#   refresh_matches:<code>
#   back:leagues
#   match:<league_code>:<match_id>
#
# (match_id пока не используется если нет реальных матчей – оставлено для будущего.)

# --- Утилиты формирования клавиатур ---

def leagues_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for title, code in LEAGUES:
        rows.append([InlineKeyboardButton(title, callback_data=f"league:{code}")])
    return InlineKeyboardMarkup(rows)

def matches_keyboard(league_code: str, matches: List[dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура списка матчей:
      - каждая строка: "Home vs Away" (match:<league_code>:<id>)
      - внизу: Обновить / Лиги
    """
    rows: List[List[InlineKeyboardButton]] = []
    for m in matches:
        # Фолбэк если нет id
        mid = m.get("id") or 0
        home = m.get("home") or "?"
        away = m.get("away") or "?"
        caption = f"{home} vs {away}"
        rows.append([
            InlineKeyboardButton(
                caption,
                callback_data=f"match:{league_code}:{mid}"
            )
        ])
    rows.append([
        InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_matches:{league_code}")
    ])
    rows.append([
        InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")
    ])
    return InlineKeyboardMarkup(rows)

def error_matches_keyboard(league_code: str) -> InlineKeyboardMarkup:
    """
    Клавиатура при ошибке / отсутствии матчей – только Обновить + Лиги
    """
    rows = [
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh_matches:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")],
    ]
    return InlineKeyboardMarkup(rows)

def back_leagues_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]
    ])

# --- ХЕЛПЕР: загрузка матчей и форматирование ответа ---

async def _load_and_render_matches(league_code: str) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Загружает матчи для лиги. Возвращает текст и клавиатуру.
    Если есть матчи – список.
    Если нет – подробное сообщение об ошибке.
    """
    matches, err = await load_matches_for_league(league_code, limit=15)
    if err:
        text = err
        kb = error_matches_keyboard(league_code)
        return text, kb

    if not matches:
        text = f"Нет матчей (лига: {league_code}) – пустой список без явной ошибки."
        kb = error_matches_keyboard(league_code)
        return text, kb

    # Формируем человекочитаемый список
    lines = [f"Матчи (лига: {league_code}, найдено: {len(matches)}):"]
    for i, m in enumerate(matches, 1):
        home = m.get("home") or "?"
        away = m.get("away") or "?"
        ts = m.get("startTimestamp")
        # TODO: при желании форматировать время (UTC → локально).
        lines.append(f"{i}. {home} vs {away} (id={m.get('id')}, ts={ts})")
    lines.append("")
    lines.append("Выберите матч для (в будущем) показа предикта состава.")
    text = "\n".join(lines)
    kb = matches_keyboard(league_code, matches)
    return text, kb

# --- HANDLERS ---

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /start – показывает список лиг.
    """
    await update.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())

async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Пользователь выбрал лигу (callback_data=league:<code>)
    1. Отвечаем "Лига выбрана..."
    2. Пишем "Загружаю матчи..."
    3. Грузим матчи
    4. Редактируем сообщение результатом
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data  # league:epl
    _, league_code = data.split(":", 1)

    # Сообщение о выборе
    await query.edit_message_text(f"Лига выбрана: {league_code.title()}\nЗагружаю матчи...")
    # Вставим временно “Обновление матчей...” чтобы показать прогресс (не обязательно)
    # Можно послать новое сообщение, но изменим текущее.
    await query.message.chat.send_message("Обновление матчей...")

    text, kb = await _load_and_render_matches(league_code)
    await query.message.chat.send_message(text, reply_markup=kb)

async def refresh_matches_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback "refresh_matches:<code>" – заново подгружает матчи.
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, league_code = query.data.split(":", 1)

    # Обновим это сообщение (query.message) текстом “Обновление матчей...”
    try:
        await query.edit_message_text(f"Обновление матчей... (лига: {league_code})")
    except Exception:
        # Если не можем редактировать (возможно уже обновлено) – проигнорируем
        pass

    text, kb = await _load_and_render_matches(league_code)
    # Отправим отдельным сообщением (чтобы гарантированно показать даже если редакт нельзя)
    await query.message.chat.send_message(text, reply_markup=kb)

async def back_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Возврат к списку лиг.
    """
    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.edit_message_text("Выберите лигу:", reply_markup=leagues_keyboard())
            return
        except Exception:
            pass
        await query.message.chat.send_message("Выберите лигу:", reply_markup=leagues_keyboard())
    else:
        # На всякий случай если кто-то вызовет напрямую
        await update.message.reply_text("Выберите лигу:", reply_markup=leagues_keyboard())

async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Пользователь нажал на конкретный матч.
    Пока просто заглушка – здесь интегрируете предикт состава.
    callback_data = match:<league_code>:<match_id>
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, league_code, match_id = query.data.split(":", 2)

    # TODO: здесь вытягиваете подробности матча + предикты.
    # Например:
    # predictions = await fetch_predictions_for_match(match_id)  # если реализуете
    text = (
        f"Матч выбран (лига={league_code}, id={match_id}).\n"
        f"Пока предиктов нет.\n"
        f"Нажмите ▷ Лиги для возврата."
    )
    await query.edit_message_text(text, reply_markup=back_leagues_keyboard())

# Глобальный error handler (опционально – чтобы ловить исключения)
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error", exc_info=context.error)
    try:
        if isinstance(update, Update):
            if update.effective_chat:
                await update.effective_chat.send_message("⚠️ Внутренняя ошибка. Сообщите администратору.")
    except Exception:
        pass

# --- РЕГИСТРАЦИЯ ХЕНДЛЕРОВ ---

def register_handlers(application):
    """
    Удобная функция – вызывается из main.py:
        from bot.handlers import register_handlers
        register_handlers(app)
    """
    application.add_handler(CommandHandler("start", start_cmd))

    # Колбэки
    application.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    application.add_handler(CallbackQueryHandler(refresh_matches_callback, pattern=r"^refresh_matches:"))
    application.add_handler(CallbackQueryHandler(back_leagues_callback, pattern=r"^back:leagues$"))
    application.add_handler(CallbackQueryHandler(match_callback, pattern=r"^match:"))

    # Ошибки
    application.add_error_handler(error_handler)

# (Если старый код ожидал прямые имена – оставим их экспортируемыми)
__all__ = [
    "start_cmd",
    "league_callback",
    "refresh_matches_callback",
    "back_leagues_callback",
    "match_callback",
    "error_handler",
    "register_handlers",
]
