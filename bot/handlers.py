import logging
from typing import List, Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    Application,
)

from bot.config import LEAGUES, LEAGUE_DISPLAY
from bot.matches import (
    load_matches_for_league,
    render_matches_text,
    render_no_matches_error,
)

# Если у тебя есть модули предиктов / БД – импортируй тут:
# from bot.db.crud import fetch_predictions_for_team_match ...
# from bot.services.predictions import build_prediction_text ...

logger = logging.getLogger(__name__)


# ---------------- ВСПОМОГАТЕЛЬНО ----------------
def _league_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for code in LEAGUES:
        row.append(InlineKeyboardButton(LEAGUE_DISPLAY.get(code, code), callback_data=f"league:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери лигу:", reply_markup=_league_keyboard()
    )


# Храним временно (на сессию процесса) найденные матчи по лиге, чтобы по id быстро достать
# key: league_code -> list[dict]
_MATCH_CACHE: dict[str, List[dict]] = {}


async def _load_and_render_matches(league_code: str) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    matches, err = await load_matches_for_league(league_code, limit=60)
    if err:
        text = render_no_matches_error(league_code, err)
        return text, None
    if not matches:
        return f"Нет матчей (лига: {LEAGUE_DISPLAY.get(league_code, league_code)})", None

    _MATCH_CACHE[league_code] = matches  # кэшируем

    # Текст “шапки”
    text = render_matches_text(league_code, matches)

    # Кнопки: каждый матч – своя кнопка
    kb_rows = []
    for m in matches:
        label = f"{m['home']} vs {m['away']}"
        if m.get("date"):
            label += f" {m['date']}"
        btn_data = f"match:{league_code}:{m['id'] or 'na'}:{m['home']}|{m['away']}"
        kb_rows.append([InlineKeyboardButton(label, callback_data=btn_data)])

    kb_rows.append([InlineKeyboardButton("← Назад к лигам", callback_data="back:leagues")])
    return text, InlineKeyboardMarkup(kb_rows)


async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, league_code = query.data.split(":", 1)
    text, kb = await _load_and_render_matches(league_code)
    if kb:
        await query.edit_message_text(text, reply_markup=kb)
    else:
        await query.edit_message_text(text, reply_markup=_league_keyboard())


def _find_match(league_code: str, match_id: str, home: str, away: str):
    lst = _MATCH_CACHE.get(league_code) or []
    if match_id != "na":
        for m in lst:
            if str(m.get("id")) == match_id:
                return m
    # fallback поиск по парам
    for m in lst:
        if m.get("home") == home and m.get("away") == away:
            return m
    return None


async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # формат: match:<league_code>:<id|na>:<home>|<away>
    _, league_code, match_id, teams_part = query.data.split(":", 3)
    home, away = teams_part.split("|", 1)
    match = _find_match(league_code, match_id, home, away)
    if not match:
        await query.edit_message_text(
            f"Матч не найден (вероятно кэш сброшен).", reply_markup=_league_keyboard()
        )
        return

    title = f"{home} vs {away}"
    dt = ""
    if match.get("date") and match.get("time"):
        dt = f"{match['date']} {match['time']}"
    elif match.get("date"):
        dt = f"{match['date']}"

    text = f"{title}\n{dt}\nВыбери команду для предикта состава:"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(home, callback_data=f"team:{league_code}:{match.get('id') or 'na'}:{home}"),
            InlineKeyboardButton(away, callback_data=f"team:{league_code}:{match.get('id') or 'na'}:{away}")
        ],
        [InlineKeyboardButton("← Назад к матчам", callback_data=f"league:{league_code}")],
        [InlineKeyboardButton("← Все лиги", callback_data="back:leagues")]
    ])
    await query.edit_message_text(text, reply_markup=kb)


async def team_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # team:<league_code>:<match_id>:<team_name>
    _, league_code, match_id, team_name = query.data.split(":", 3)
    lst = _MATCH_CACHE.get(league_code) or []
    # Подберем матч для контекста (по id или по участию команды)
    match = None
    for m in lst:
        if match_id != "na" and str(m.get("id")) == match_id:
            match = m
            break
    if not match:
        for m in lst:
            if team_name in (m.get("home"), m.get("away")):
                match = m
                break

    # Здесь вставить логику получения предикта:
    # predictions = await fetch_predictions_for_team_match(...)
    # text = build_prediction_text(predictions, match, team_name)
    demo_text = f"Предикт состава для **{team_name}** (демо).\n" \
                f"Матч: {match.get('home')} vs {match.get('away')} (ID: {match.get('id')})\n" \
                f"Дата: {match.get('date')} {match.get('time') or ''}\n\n" \
                f"_TODO: интегрировать реальный модуль предиктов._"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("← Другая команда", callback_data=f"match:{league_code}:{match.get('id') or 'na'}:{match.get('home')}|{match.get('away')}")],
        [InlineKeyboardButton("← Матчи", callback_data=f"league:{league_code}")],
        [InlineKeyboardButton("← Лиги", callback_data="back:leagues")]
    ])
    await query.edit_message_text(demo_text, reply_markup=kb, parse_mode="Markdown")


async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выбери лигу:", reply_markup=_league_keyboard())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await update.effective_chat.send_message("Произошла ошибка. Попробуйте позже.")
        except Exception:
            pass


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    app.add_handler(CallbackQueryHandler(match_callback, pattern=r"^match:"))
    app.add_handler(CallbackQueryHandler(team_callback, pattern=r"^team:"))
    app.add_handler(CallbackQueryHandler(back_callback, pattern=r"^back:leagues$"))
    app.add_error_handler(error_handler)
