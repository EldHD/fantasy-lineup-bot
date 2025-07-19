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

# ---------- /start ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Выбрать чемпионат", callback_data="choose_league")],
        [InlineKeyboardButton("Предсказать состав", callback_data="choose_league")]  # пока тот же шаг
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Привет! Выберите действие:", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Привет! Выберите действие:", reply_markup=reply_markup)

# ---------- Выбор лиг ----------

async def show_leagues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    await query.edit_message_text(
        "Выберите лигу:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- После выбора лиги: список матчей ----------

async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league_code = query.data.split("_", 1)[1]

    matches = get_upcoming_matches(league_code)
    if not matches:
        await query.edit_message_text(f"Пока нет матчей для лиги {league_code.upper()}")
        return

    buttons = []
    for m in matches:
        txt = f"{m['home_team']['name']} vs {m['away_team']['name']} • {format_kickoff(m['utc_kickoff'])}"
        buttons.append([InlineKeyboardButton(txt, callback_data=f"match_{m['id']}")])

    buttons.append([InlineKeyboardButton("⬅ Назад к лигам", callback_data="choose_league")])

    await query.edit_message_text(
        f"Матчи ({league_code.upper()}):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ---------- После выбора матча: выбрать команду ----------

async def handle_match_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = query.data.split("_", 1)[1]
    match = get_match(match_id)
    if not match:
        await query.edit_message_text("Матч не найден или устарел.")
        return

    home, away = match["home_team"], match["away_team"]

    buttons = [
        [InlineKeyboardButton(f"{home['name']}", callback_data=f"team_{match_id}_{home['code']}")],
        [InlineKeyboardButton(f"{away['name']}", callback_data=f"team_{match_id}_{away['code']}")],
        [InlineKeyboardButton("⬅ К матчам", callback_data=f"league_{match['league']}")]
    ]

    header = (f"{home['name']} vs {away['name']}\n"
              f"{match['round']}\n"
              f"Kickoff: {format_kickoff(match['utc_kickoff'])}\n\nВыберите команду:")

    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))

# ---------- Предикт состава (заглушка) ----------

async def handle_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # callback: team_<matchid>_<teamcode>
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("Некорректный callback.")
        return
    match_id = parts[1]
    team_code = parts[2]

    match = get_match(match_id)
    if not match:
        await query.edit_message_text("Матч не найден.")
        return

    lineup = get_dummy_lineup(match_id, team_code)

    lines = []
    for p in lineup:
        lines.append(f"{p['number']} {p['name']} — {p['position']} | {p['probability']}% | {p['reason']}")
    text = (f"Предикт стартового состава для {team_code}:\n"
            f"{match['home_team']['name']} vs {match['away_team']['name']}\n"
            f"{match['round']} • {format_kickoff(match['utc_kickoff'])}\n\n" +
            "\n".join(lines) +
            "\n\n(Позже: добавим источники, статусы OUT и т.д.)")

    buttons = [
        [InlineKeyboardButton("⬅ Другая команда", callback_data=f"match_{match_id}")],
        [InlineKeyboardButton("⬅ К матчам", callback_data=f"league_{match['league']}")],
        [InlineKeyboardButton("🏁 Лиги", callback_data="choose_league")]
    ]

    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(buttons))  # Telegram лимит
