from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db.crud import (
    fetch_matches_by_league,
    fetch_match_with_teams,
    fetch_team_lineup_predictions,
)

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Выберите лигу:", reply_markup=markup)


async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)


async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_code = query.data.split("_", 1)[1]

    matches = await fetch_matches_by_league(league_code)
    if not matches:
        buttons = [
            [InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")]
        ]
        await query.edit_message_text(f"Нет доступных матчей для {league_code.upper()}",
                                      reply_markup=InlineKeyboardMarkup(buttons))
        return

    buttons = []
    for m in matches:
        txt = f"{m.home_team.name} vs {m.away_team.name} • {m.utc_kickoff:%Y-%m-%d %H:%M UTC}"
        buttons.append([InlineKeyboardButton(txt, callback_data=f"matchdb_{m.id}")])

    buttons.append([InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")])

    await query.edit_message_text(
        f"Матчи ({league_code.upper()}):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def handle_db_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = int(query.data.split("_", 1)[1])

    match = await fetch_match_with_teams(match_id)
    if not match:
        await query.edit_message_text("Матч не найден.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("⬅ Лиги", callback_data="back_leagues")]]
                                      ))
        return

    buttons = [
        [InlineKeyboardButton(match.home_team.name, callback_data=f"teamdb_{match.id}_{match.home_team.id}")],
        [InlineKeyboardButton(match.away_team.name, callback_data=f"teamdb_{match.id}_{match.away_team.id}")],
        [InlineKeyboardButton("⬅ Матчи", callback_data=f"league_{match.tournament.code}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    header = (
        f"{match.home_team.name} vs {match.away_team.name}\n"
        f"{match.round}\n"
        f"Kickoff: {match.utc_kickoff:%Y-%m-%d %H:%M UTC}\n\nВыберите команду:"
    )
    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный формат callback.")
        return

    match_id = int(parts[1])
    team_id = int(parts[2])

    preds = await fetch_team_lineup_predictions(match_id, team_id)
    if not preds:
        await query.edit_message_text("Нет предиктов для этой команды (пока).",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("⬅ Назад", callback_data=f"matchdb_{match_id}")]]
                                      ))
        return

    lines = []
    for pr in preds:
        p = pr.player
        pos = p.position_detail or p.position_main
        status = "START" if pr.will_start else "OUT"
        lines.append(
            f"{p.shirt_number or '-'} {p.full_name} — {pos} | {status} | {pr.probability}%\n"
            f"  {pr.explanation}"
        )

    text = "Предикт стартового состава:\n\n" + "\n".join(lines)
    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text[:3900], reply_markup=InlineKeyboardMarkup(buttons))
