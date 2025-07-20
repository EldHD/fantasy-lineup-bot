from typing import List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from bot.config import LEAGUE_CODES, LEAGUE_DISPLAY, FETCH_LIMIT_PER_LEAGUE
from bot.matches import load_matches_for_league, render_matches_text


def _league_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for code in LEAGUE_CODES:
        row.append(InlineKeyboardButton(LEAGUE_DISPLAY.get(code, code),
                                        callback_data=f"league:{code}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _matches_keyboard(matches: List[dict], league_code: str) -> InlineKeyboardMarkup:
    btn_rows = []
    row = []
    for m in matches:
        short = f"{m['home'][:3]}-{m['away'][:3]}"
        row.append(InlineKeyboardButton(short, callback_data=f"match:{m['id']}"))
        if len(row) == 3:
            btn_rows.append(row)
            row = []
    if row:
        btn_rows.append(row)
    btn_rows.append([
        InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{league_code}"),
        InlineKeyboardButton("🏁 Лиги", callback_data="back:leagues")
    ])
    return InlineKeyboardMarkup(btn_rows)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите лигу:", reply_markup=_league_keyboard())


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq:
        return
    await cq.answer()
    data = cq.data or ""
    if data.startswith("league:"):
        league_code = data.split(":", 1)[1]
        await cq.message.reply_text(
            f"Лига выбрана: {LEAGUE_DISPLAY.get(league_code, league_code)}\nЗагружаю матчи..."
        )
        await _send_matches(cq.message.chat_id, league_code, context)
    elif data.startswith("refresh:"):
        league_code = data.split(":", 1)[1]
        await cq.message.reply_text("Обновление матчей...")
        await _send_matches(cq.message.chat_id, league_code, context, force=True)
    elif data == "back:leagues":
        await cq.message.reply_text("Выберите лигу:", reply_markup=_league_keyboard())
    elif data.startswith("match:"):
        match_id = data.split(":", 1)[1]
        await cq.message.reply_text(f"Матч #{match_id}: предикты будут позже.")
    else:
        await cq.message.reply_text("Неизвестное действие.")


async def _send_matches(chat_id: int, league_code: str,
                        context: ContextTypes.DEFAULT_TYPE, force: bool = False):
    matches, meta = await load_matches_for_league(league_code, FETCH_LIMIT_PER_LEAGUE)
    text = render_matches_text(league_code, matches, meta)
    kb = _matches_keyboard(matches, league_code) if matches else _league_keyboard()
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
