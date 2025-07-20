# bot/main.py
from telegram.ext import Application

from bot.config   import TELEGRAM_TOKEN
from bot.handlers import register_handlers


def main() -> None:
    """Единственная точка входа – без asyncio.run()."""
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # клавиатуры, /start и прочие callbacks
    register_handlers(app)

    # ⇣  внутри выполняет initialize → start → idle → shutdown
    app.run_polling()


if __name__ == "__main__":
    main()
