import logging
import traceback
from typing import List, Tuple

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from bot.matches import load_matches_for_league, format_events_short

logger = logging.getLogger(__name__)

# Заполни своими chat_id (админы)
ADMIN_IDS: List[int] = []

# (код, название)
LEAGUES: List[Tuple[str, str]] = [
    ("epl", "Premier League"),
    ("laliga", "La Liga"),
    ("seriea", "Serie A"),
    ("bundesliga", "Bundesliga"),
    ("ligue1", "Ligue 1"),
    ("rpl", "Russian Premier League"),
]


def make_leagues_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for code, title in LEAGUES:
        rows.append([InlineKeyboardButton(title, callback_data=f"league:{code}")])
    return InlineKeyboardMarkup(rows)


def make_refresh_keyboard(league_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{league_code}")],
            [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")],
        ]
    )


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите лигу:", reply_markup=make_leagues_keyboard()
    )


async def leagues_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Выберите лигу:", reply_markup=make_leagues_keyboard()
    )


async def _load_and_render_matches(league_code: str, force: bool = True) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Унифицированная функция получения текста и клавиатуры для вывода матчей.
    """
    league_code_norm = (league_code or "").lower()
    result = await load_matches_for_league(
        league_code_norm,
        force_refresh=force,
        limit=30,  # можно регулировать
    )

    if not result["ok"]:
        err = result.get("error") or "Неизвестная ошибка"
        season_id = result.get("season_id")
        attempts = result.get("attempts") or []
        text = (
            f"Нет матчей (лига: {league_code_norm})\n"
            f"Season ID: {season_id}\n"
            f"Причина: {err}\n"
            f"Попытки: {attempts[:2]}"
        )
        return text, make_refresh_keyboard(league_code_norm)

    events = result["events"]
    text_block = format_events_short(events, limit=30)
    header = f"Матчи ({league_code_norm.upper()}), сезон {result['season_id']}:\n"
    return header + (text_block or "Нет данных"), make_refresh_keyboard(league_code_norm)


async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, code = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("Некорректные данные кнопки.")
        return

    league_code = code.lower()
    await query.edit_message_text(
        f"Лига выбрана: {league_code.upper()}\nЗагружаю матчи..."
    )

    try:
        text, kb = await _load_and_render_matches(league_code, force=True)
        await query.edit_message_text(text, reply_markup=kb)
    except Exception as e:
        logger.error("Unhandled error", exc_info=True)
        await query.edit_message_text(
            "⚠️ Внутренняя ошибка при загрузке матчей.",
            reply_markup=make_leagues_keyboard(),
        )
        tb = traceback.format_exc()
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"[ADMIN] Exception league={league_code}\n{tb[:3500]}",
                )
            except Exception:
                pass


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, code = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("Некорректные данные кнопки.")
        return

    league_code = code.lower()
    await query.edit_message_text("Обновление матчей...")

    try:
        text, kb = await _load_and_render_matches(league_code, force=True)
        await query.edit_message_text(text, reply_markup=kb)
    except Exception:
        logger.error("Unhandled error (refresh)", exc_info=True)
        await query.edit_message_text(
            "⚠️ Внутренняя ошибка.",
            reply_markup=make_refresh_keyboard(league_code),
        )
        tb = traceback.format_exc()
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"[ADMIN] Exception refresh league={league_code}\n{tb[:3500]}",
                )
            except Exception:
                pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Global error handler: %s", context.error, exc_info=True)

    target_chat_id = None
    if isinstance(update, Update) and update.effective_chat:
        target_chat_id = update.effective_chat.id

    if target_chat_id:
        try:
            await context.bot.send_message(
                chat_id=target_chat_id, text="⚠️ Внутренняя ошибка. Попробуйте позже."
            )
        except Exception:
            pass

    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"[ADMIN][GlobalError]\n{tb[:3500]}",
            )
        except Exception:
            pass


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(leagues_back_callback, pattern=r"^back:leagues$"))
    app.add_handler(CallbackQueryHandler(refresh_callback, pattern=r"^refresh:"))
    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    app.add_error_handler(error_handler)
