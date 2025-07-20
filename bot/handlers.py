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
    Application,
)
import bot.config as cfg
from bot.matches import load_matches_for_league, render_fixtures_text

# ====== /start ======
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [
            InlineKeyboardButton(
                cfg.LEAGUE_DISPLAY.get(code, code),
                callback_data=f"league:{code}"
            )
        ]
        for code in cfg.LEAGUE_CODES
    ]
    await update.message.reply_text(
        "Выбери лигу:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ====== CALLBACK: Выбор лиги ======
async def league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    _, league_code = data.split(":", 1)

    # Пока всегда matchday=1 (можно расширить позже)
    matchday = 1
    fixtures, err = await load_matches_for_league(league_code, matchday=matchday)
    if err or not fixtures:
        text = f"Нет матчей (лига: {cfg.LEAGUE_DISPLAY.get(league_code, league_code)})\nПричина: {err or 'Unknown'}"
        await q.edit_message_text(text)
        return

    # Кнопки по каждому матчу: callback match:<league>:<match_id>
    buttons = []
    for fx in fixtures[:cfg.DEFAULT_MAX_INLINE_BUTTONS]:
        label = f"{fx['home']} vs {fx['away']}"
        match_id = fx.get("match_id") or 0
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"match:{league_code}:{match_id}")
        ])

    text = render_fixtures_text(league_code, fixtures, matchday)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# ====== CALLBACK: Выбор матча (заглушка) ======
async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        await q.edit_message_text("Некорректный callback данных матча.")
        return
    _, league_code, match_id = parts
    await q.edit_message_text(
        f"Матч #{match_id} ({cfg.LEAGUE_DISPLAY.get(league_code, league_code)})\n"
        f"Здесь будет выбор команды и предикты (ещё не реализовано)."
    )

# ====== Ошибки ======
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Логирование можно расширить
    print("Ошибка:", context.error)

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(league_callback, pattern=r"^league:"))
    app.add_handler(CallbackQueryHandler(match_callback, pattern=r"^match:"))
    app.add_error_handler(error_handler)
