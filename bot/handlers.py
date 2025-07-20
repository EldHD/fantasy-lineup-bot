import logging
from datetime import datetime, timezone
from typing import List, Tuple, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.config import (
    LEAGUE_DISPLAY,         # dict: code -> human name (e.g. "epl": "Premier League")
    LEAGUE_CODES,           # iterable of league codes in порядке показа (e.g. ["epl","laliga","seriea",...])
)
from bot.matches import (
    load_matches_for_league,
    render_matches_text,
)

logger = logging.getLogger(__name__)


# ==============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================

def _kb(rows: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
    """
    Преобразует список строк с (text, callback_data) в InlineKeyboardMarkup.
    rows: [[("Text1","cb1"),("Text2","cb2")], [...], ...]
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=txt, callback_data=cb) for (txt, cb) in row]
        for row in rows
    ])


def _league_buttons() -> InlineKeyboardMarkup:
    """
    Кнопки выбора лиги (в 2 строки по несколько кнопок — можно менять).
    """
    # Разобьём просто подряд по 3–4 в строке
    per_row = 3
    rows: List[List[Tuple[str, str]]] = []
    row: List[Tuple[str, str]] = []
    for code in LEAGUE_CODES:
        row.append((LEAGUE_DISPLAY.get(code, code), f"league:{code}"))
        if len(row) >= per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return _kb(rows)


async def _load_and_render_matches(league_code: str):
    """
    Загружает матчи лиги и формирует текст + клавиатуру.
    Возвращает (text, keyboard)
    """
    display = LEAGUE_DISPLAY.get(league_code, league_code)
    matches, err = await load_matches_for_league(league_code)

    if err:
        # Ошибка парсинга / отсутствуют матчи
        text = err
        kb_rows = [
            [("🔄 Обновить", f"matches_refresh:{league_code}")],
            [("🏁 Лиги", "back_leagues")],
        ]
        return text, _kb(kb_rows)

    text = render_matches_text(display, matches)

    # Кнопки по матчам
    kb_rows: List[List[Tuple[str, str]]] = []
    for m in matches:
        home = m.get("home")
        away = m.get("away")
        mid = m.get("match_id")
        # Кнопка матча открывает выбор команды
        btn_txt = f"{home} vs {away}"
        kb_rows.append([(btn_txt, f"match:{league_code}:{mid}")])

    kb_rows.append([("🔄 Обновить", f"matches_refresh:{league_code}")])
    kb_rows.append([("🏁 Лиги", "back_leagues")])
    return text, _kb(kb_rows)


# ==============================
# ОБРАБОТЧИКИ КОМАНД
# ==============================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start – показать меню лиг.
    """
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите лигу:",
            reply_markup=_league_buttons()
        )


# ==============================
# ОБРАБОТЧИКИ CALLBACK
# ==============================

async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Нажата кнопка лиги: league:<code>
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""
    _, league_code = data.split(":", 1)

    display = LEAGUE_DISPLAY.get(league_code, league_code)

    # Сообщение-заглушка о загрузке
    try:
        await query.edit_message_text(
            text=f"Лига выбрана: {display}\nЗагружаю матчи..."
        )
    except Exception:
        # Если редактирование не прошло (например, старое сообщение), просто отправим новое
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Лига выбрана: {display}\nЗагружаю матчи..."
            )

    try:
        text, kb = await _load_and_render_matches(league_code)
    except Exception as e:
        logger.exception("Unhandled exception loading matches for %s", league_code)
        text = "⚠️ Внутренняя ошибка. Сообщите администратору."
        kb = _kb([[("🏁 Лиги", "back_leagues")]])

    # Показ результата
    if query.message:
        try:
            await query.edit_message_text(text=text, reply_markup=kb)
        except Exception:
            # fallback – отправить новое
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=kb
                )


async def matches_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Нажата кнопка обновления матчей: matches_refresh:<league_code>
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    _, league_code = data.split(":", 1)
    display = LEAGUE_DISPLAY.get(league_code, league_code)

    # Обновляем текст “Обновление матчей...”
    try:
        await query.edit_message_text(
            text=f"Лига: {display}\nОбновление матчей..."
        )
    except Exception:
        pass

    try:
        text, kb = await _load_and_render_matches(league_code)
    except Exception:
        logger.exception("Error refreshing matches %s", league_code)
        text = "⚠️ Внутренняя ошибка. Сообщите администратору."
        kb = _kb([[("🏁 Лиги", "back_leagues")]])

    if query.message:
        try:
            await query.edit_message_text(text=text, reply_markup=kb)
        except Exception:
            if update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=kb
                )


async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Нажата кнопка матча: match:<league_code>:<match_id>
    Здесь можно показать выбор команды (home/away) или сразу предикты.
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, league_code, match_id_str = (query.data or "").split(":")
    match_id = int(match_id_str)

    # Заглушка (в дальнейшем: подтянуть данные, предикты, составы)
    text = (
        f"Матч ID: {match_id}\n"
        f"Лига: {LEAGUE_DISPLAY.get(league_code, league_code)}\n\n"
        "Выберите команду для просмотра предикта (пока заглушка):"
    )

    kb = _kb([
        [("Home состав", f"team:{league_code}:{match_id}:home")],
        [("Away состав", f"team:{league_code}:{match_id}:away")],
        [("⬅️ Назад к матчам", f"matches_refresh:{league_code}")],
        [("🏁 Лиги", "back_leagues")],
    ])
    try:
        await query.edit_message_text(text=text, reply_markup=kb)
    except Exception:
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=kb
            )


async def team_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Нажатие на выбор команды: team:<league_code>:<match_id>:<side>
    Здесь должны формироваться и показываться предсказания стартового состава.
    Пока — демонстрационная заглушка.
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, league_code, match_id_str, side = (query.data or "").split(":")
    match_id = int(match_id_str)

    # TODO: заменить на реальную загрузку предиктов
    text = (
        f"Предикт состава (пока заглушка)\n"
        f"Матч #{match_id}\n"
        f"Команда: {'Home' if side == 'home' else 'Away'}\n"
        f"Лига: {LEAGUE_DISPLAY.get(league_code, league_code)}\n\n"
        "Скоро здесь будет список позиций и процентов."
    )

    kb = _kb([
        [("⬅️ Назад к матчу", f"match:{league_code}:{match_id}")],
        [("🏁 Лиги", "back_leagues")],
    ])

    try:
        await query.edit_message_text(text=text, reply_markup=kb)
    except Exception:
        if update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=kb
            )


async def back_leagues_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Возврат к списку лиг: back_leagues
    """
    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.edit_message_text("Выберите лигу:", reply_markup=_league_buttons())
            return
        except Exception:
            pass
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите лигу:",
            reply_markup=_league_buttons()
        )


# ==============================
# ОБРАБОТКА ОШИБОК
# ==============================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Глобальный обработчик исключений.
    Логируем полный stacktrace, пользователю — короткое сообщение.
    """
    logger.exception("Unhandled exception: update=%s error=%s", update, context.error)
    # Уведомим пользователя, если это Update с чатом
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Внутренняя ошибка. Попробуйте позже."
            )
    except Exception:  # noqa
        pass


# ==============================
# РЕГИСТРАЦИЯ
# ==============================

def register_handlers(app: Application):
    """
    Подключение всех хендлеров к Application.
    Вызвать один раз при инициализации.
    """
    app.add_handler(CommandHandler("start", start_cmd))

    # OPTIONAL: Добавь сюда свои команды (если нужны):
    # app.add_handler(CommandHandler("sync_roster", sync_roster_cmd))
    # app.add_handler(CommandHandler("resync_all", resync_all_cmd))
    # app.add_handler(CommandHandler("export", export_cmd))

    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    app.add_handler(CallbackQueryHandler(matches_refresh_callback, pattern=r"^matches_refresh:"))
    app.add_handler(CallbackQueryHandler(match_callback, pattern=r"^match:"))
    app.add_handler(CallbackQueryHandler(team_callback, pattern=r"^team:"))
    app.add_handler(CallbackQueryHandler(back_leagues_callback, pattern=r"^back_leagues$"))

    # Глобальный обработчик ошибок
    app.add_error_handler(error_handler)
