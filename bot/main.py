# bot/main.py
from telegram.ext import ApplicationBuilder
from bot import handlers
from bot.db.patch_schema import apply_sync

def main():
    apply_sync()  # Применить патчи к базе

    app = ApplicationBuilder().token("YOUR_TELEGRAM_TOKEN").build()

    handlers.register(app)  # Зарегистрировать хендлеры

    print("🤖 Bot starting polling …")
    app.run_polling()

if __name__ == "__main__":
    main()
