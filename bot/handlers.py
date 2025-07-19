from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .matches import (
    get_upcoming_matches,
    get_match,
    get_teams_for_match,
    get_dummy_lineup,
    format_kickoff,
)

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]

# ----- /start: сразу лиги -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    if update.message:
        await update.message.reply_text("Выберите лигу:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите лигу:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ----- Выбор лиги → список матчей -----
async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_code = query.data.split("_", 1)[1]

    matches = get_upcoming_matches(league_code)
    if not matches:
        buttons = [[InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")]]
        await query.edit_message_text(f"Пока нет матчей для {league_code.upper()}",
                                      reply_markup=InlineKeyboardMarkup(buttons))
        return

    buttons = []
    for m in matches:
        txt = f"{m['home_team']['name']} vs {m['away_team']['name']} • {format_kickoff(m['utc_kickoff'])}"
        buttons.append([InlineKeyboardButton(txt, callback_data=f"match_{m['id']}")])
    buttons.append([InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")])

    await query.edit_message_text(f"Матчи ({league_code.upper()}):",
                                  reply_markup=InlineKeyboardMarkup(buttons))

# ----- Назад к лигам -----
async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ----- Выбор матча → выбор команды -----
async def handle_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = query.data.split("_", 1)[1]
    match = get_match(match_id)
    if not match:
        await query.edit_message_text("Матч не найден (возможно устарел).",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("⬅ К лигам", callback_data="back_leagues")]]
                                      ))
        return

    home, away = match["home_team"], match["away_team"]
    buttons = [
        [InlineKeyboardButton(home['name'], callback_data=f"team_{match_id}_{home['code']}")],
        [InlineKeyboardButton(away['name'], callback_data=f"team_{match_id}_{away['code']}")],
        [InlineKeyboardButton("⬅ К матчам", callback_data=f"league_{match['league']}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    header = (f"{home['name']} vs {away['name']}\n"
              f"{match['round']}\n"
              f"Kickoff: {format_kickoff(match['utc_kickoff'])}\n\nВыберите команду:")

    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))

# ----- Предикт состава (заглушка) -----
async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный callback.")
        return
    match_id, team_code = parts[1], parts[2]
    match = get_match(match_id)
    if not match:
        await query.edit_message_text("Матч не найден.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("⬅ Лиги", callback_data="back_leagues")]]
                                      ))
        return
    lineup = get_dummy_lineup(match_id, team_code)
    lines = [
        f"{p['number']} {p['name']} — {p['position']} | {p['probability']}% | {p['reason']}"
        for p in lineup
    ]
    text = (f"Предикт состава {team_code}:\n"
            f"{match['home_team']['name']} vs {match['away_team']['name']}\n"
            f"{match['round']} • {format_kickoff(match['utc_kickoff'])}\n\n" +
            "\n".join(lines))
    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"match_{match_id}")],
        [InlineKeyboardButton("⬅ Матчи", callback_data=f"league_{match['league']}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(buttons))
