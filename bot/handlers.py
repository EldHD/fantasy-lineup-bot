from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_team_lineup_predictions,
)
from bot.db.seed import force_players_reset  # оставь, если используешь /force_seed


LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]


# ----- /start -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=markup)
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите лигу:",
            reply_markup=markup
        )


# ----- Назад к лигам -----
async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


# ----- Лига → матчи -----
async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_code = query.data.split("_", 1)[1]

    matches = await fetch_matches_by_league(league_code)
    if not matches:
        buttons = [[InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")]]
        await query.edit_message_text(
            f"Нет доступных матчей для {league_code.upper()}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    buttons = []
    for m in matches:
        txt = f"{m['home_team_name']} vs {m['away_team_name']} • {m['utc_kickoff']:%Y-%m-%d %H:%M UTC}"
        buttons.append([InlineKeyboardButton(txt, callback_data=f"matchdb_{m['id']}")])

    buttons.append([InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")])

    await query.edit_message_text(
        f"Матчи ({league_code.upper()}):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ----- Матч → выбор команды -----
async def handle_db_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = int(query.data.split("_", 1)[1])

    match = await fetch_match_with_teams(match_id)
    if not match:
        await query.edit_message_text(
            "Матч не найден.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅ Лиги", callback_data="back_leagues")]]
            )
        )
        return

    buttons = [
        [InlineKeyboardButton(match["home"]["name"], callback_data=f"teamdb_{match['id']}_{match['home']['id']}")],
        [InlineKeyboardButton(match["away"]["name"], callback_data=f"teamdb_{match['id']}_{match['away']['id']}")],
        [InlineKeyboardButton("⬅ Матчи", callback_data=f"league_{match['tournament_code']}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    header = (
        f"{match['home']['name']} vs {match['away']['name']}\n"
        f"{match['round']}\n"
        f"Kickoff: {match['utc_kickoff']:%Y-%m-%d %H:%M UTC}\n\nВыберите команду:"
    )
    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))


# ----- Команда → предикт состава -----
async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный формат callback.")
        return

    match_id = int(parts[1])
    team_id = int(parts[2])

    rows = await fetch_team_lineup_predictions(match_id, team_id)
    if not rows:
        await query.edit_message_text(
            "Нет предиктов для этой команды.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅ Назад", callback_data=f"matchdb_{match_id}")]]
            )
        )
        return

    starters = []
    out_or_doubt = []

    for r in rows:
        pos = r["position_detail"] or r["position_main"]
        availability_tag = ""
        if r["status_availability"] == "OUT":
            availability_tag = "❌ OUT"
        elif r["status_availability"] == "DOUBT":
            availability_tag = "❓ Doubt"

        line = f"{r['number'] or '-'} {r['full_name']} — {pos} | {r['probability']}%"
        if availability_tag:
            line += f" | {availability_tag}"

        explain_parts = []
        if r["explanation"]:
            explain_parts.append(r["explanation"])
        if r["status_reason"]:
            explain_parts.append(r["status_reason"])
        explain = "; ".join(explain_parts)
        if explain:
            line += "\n  " + explain

        if r["status_availability"] in ("OUT", "DOUBT"):
            out_or_doubt.append(line)
        else:
            starters.append(line)

    text_parts = ["Предикт стартового состава:\n"]
    if starters:
        text_parts.append("✅ Ожидаемые в старте:\n" + "\n".join(starters))
    if out_or_doubt:
        text_parts.append("\n🚑 OUT / DOUBT:\n" + "\n".join(out_or_doubt))

    text = "\n".join(text_parts)
    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text[:3900], reply_markup=InlineKeyboardMarkup(buttons))


# ----- /force_seed (опционально) -----
async def force_seed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Пересоздаю игроков/предикты/статусы...")
    await force_players_reset()
    await update.message.reply_text("✅ Готово. /start")
