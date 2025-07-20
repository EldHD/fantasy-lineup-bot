from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from bot.matches import load_and_store_next_md

def register_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))

async def start_cmd(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Premier League", callback_data="epl")]
    ])
    await upd.effective_chat.send_message("Выберите лигу:", reply_markup=kb)

async def callback_router(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    league = upd.callback_query.data
    await upd.callback_query.answer()
    matches = await load_and_store_next_md(league)
    if not matches:
        await upd.effective_chat.send_message("Пока нет матчей 🚫")
        return
    lines = [
        f"MD {m.matchday}: {m.utc_kickoff:%d %b %H:%M}  "
        f"{m.home_team.name} — {m.away_team.name}"
        for m in matches
    ]
    await upd.effective_chat.send_message("\n".join(lines))
