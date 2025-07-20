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
from bot.config import LEAGUE_CODES, LEAGUE_DISPLAY
from bot.matches import load_matches_for_league, render_matches_text

# ---------- Вспомогательный UI ----------

def league_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for code in LEAGUE_CODES:
        row.append(InlineKeyboardButton(LEAGUE_DISPLAY.get(code, code), callback_data=f"lg:{code}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def refresh_keyboard(league_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"rf:{league_code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")]
    ])

# ---------- Команды ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=league_keyboard())

# ---------- Callback ----------

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.callback_query:
        return
    cq = update.callback_query
    data = cq.data or ""
    await cq.answer()

    if data.startswith("lg:"):
        league_code = data.split(":", 1)[1]
        await cq.message.reply_text(f"Лига выбрана: {LEAGUE_DISPLAY.get(league_code, league_code)}\nЗагружаю матчи...")
        await _send_matches(cq.message.chat_id, league_code, context)
    elif data.startswith("rf:"):
        league_code = data.split(":", 1)[1]
        await cq.message.reply_text("Обновление матчей...")
        await _send_matches(cq.message.chat_id, league_code, context)
    elif data == "back:leagues":
        await cq.message.reply_text("Выберите лигу:", reply_markup=league_keyboard())

async def _send_matches(chat_id: int, league_code: str, context: ContextTypes.DEFAULT_TYPE):
    matches, meta = await load_matches_for_league(league_code, limit=15)
    text = render_matches_text(league_code, matches, meta)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=refresh_keyboard(league_code)
    )

# ---------- Регистрация ----------

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
