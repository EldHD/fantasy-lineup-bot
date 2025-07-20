import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from bot.config import LEAGUE_CODES, LEAGUE_DISPLAY
from bot.matches import load_matches_for_league, render_matches_text

log = logging.getLogger(__name__)

def _leagues_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, code in enumerate(LEAGUE_CODES, 1):
        row.append(InlineKeyboardButton(LEAGUE_DISPLAY.get(code, code), callback_data=f"league:{code}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=_leagues_keyboard())

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq:
        return
    await cq.answer()
    data = cq.data or ""
    if data.startswith("league:"):
        league_code = data.split(":", 1)[1]
        await _send_matches(cq.message.chat_id, league_code, context)
    else:
        await cq.message.reply_text("Неизвестное действие.")

async def _send_matches(chat_id: int, league_code: str, context: ContextTypes.DEFAULT_TYPE):
    disp = LEAGUE_DISPLAY.get(league_code, league_code)
    await context.bot.send_message(chat_id, f"Лига выбрана: {disp}\nЗагружаю матчи...")
    matches, meta = load_matches_for_league(league_code, limit=15)
    text = render_matches_text(league_code, matches, meta)
    await context.bot.send_message(chat_id, text, reply_markup=_leagues_keyboard())

def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
