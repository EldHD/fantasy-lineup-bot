from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db.crud import fetch_matches_by_league, fetch_match_with_teams

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]

# ----- /start: сразу показать лиги -----
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

# ----- Назад к лигам -----
async def back_to_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ----- Выбор лиги → список матчей из БД -----
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

# ----- Выбор матча → выбор команды -----
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

# ----- Заглушка для состава: позже заменим на игроков из БД -----
async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный формат callback.")
        return
    match_id = parts[1]
    team_id = parts[2]
    # Пока просто выводим заглушку
    text = (
        f"Состав (пока заглушка)\n"
        f"match_id={match_id}, team_id={team_id}\n\n"
        f"На следующем шаге подключим игроков и предикты."
    )
    buttons = [
        [InlineKeyboardButton("⬅ Назад к матчу", callback_data=f"matchdb_{match_id}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="back_leagues")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# Переименовали для main.py
handle_team_selection = handle_team_selection
