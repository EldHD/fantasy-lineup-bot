# bot/handlers.py

import datetime as dt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, Application, CommandHandler, CallbackQueryHandler
)
from sqlalchemy import select
from bot.db.database import async_session
from bot.db.models   import Tournament, Match

LEAGUES = {
    "Premier League": "epl",
    # можно добавить ещё: "La Liga": "laliga", "RPL": "rpl", и т.д.
}

# ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(txt, callback_data=f"league:{code}")]
          for txt, code in LEAGUES.items()]
    await update.message.reply_text("Выберите лигу:",
                                    reply_markup=InlineKeyboardMarkup(kb))


async def league_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    code = update.callback_query.data.split(":")[1]

    async with async_session() as s:
        t = await s.scalar(select(Tournament).where(Tournament.code == code))
        if not t:
            await update.callback_query.edit_message_text("Пока нет матчей 🚫")
            return

        now  = dt.datetime.now(dt.timezone.utc)
        rows = await s.scalars(
            select(Match)
            .where((Match.tournament_id == t.id) & (Match.utc_kickoff > now))
            .order_by(Match.utc_kickoff)
        )
        matches = rows.all()

    if not matches:
        await update.callback_query.edit_message_text("Пока нет матчей 🚫")
        return

    kb = []
    for m in matches:
        txt = f"{m.home_team.name} — {m.away_team.name} " \
              f"({m.utc_kickoff:%d %b %H:%M})"
        kb.append([InlineKeyboardButton(txt, callback_data=f"match:{m.id}")])

    await update.callback_query.edit_message_text(
        "Ближайшие матчи:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def match_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "⚙️ Составы пока не готовы. Будет позже 🙂"
    )


def register(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(league_cb, pattern="^league:"))
    app.add_handler(CallbackQueryHandler(match_cb,  pattern="^match:"))
