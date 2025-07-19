from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

LEAGUES = [
    ("Premier League", "epl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("Russian Premier League", "rpl"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"league_{code}")]
        for name, code in LEAGUES
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # update.message может быть None (например, если команда пришла как callback – редко, но на будущее)
    if update.message:
        await update.message.reply_text("Выберите чемпионат:", reply_markup=reply_markup)
    else:
        # fallback: пробуем ответить в чате через context
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите чемпионат:",
            reply_markup=reply_markup
        )


async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    league_code = query.data.split("_", 1)[1]

    # Заглушка – позже заменим на реальный список матчей
    text = (
        f"Вы выбрали лигу: {league_code.upper()}\n"
        "Скоро здесь появится список ближайших матчей.\n"
        "⏳ Работаем над парсером…"
    )

    await query.edit_message_text(text)
