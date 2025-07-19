from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]

def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    update.message.reply_text(
        "Выберите чемпионат:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def handle_league_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    league_code = query.data.split("_", 1)[1]
    query.edit_message_text(
        f"Вы выбрали лигу: {league_code.upper()}\n"
        f"Скоро здесь появится список ближайших матчей."
    )
