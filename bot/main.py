# bot/main.py
import asyncio
from telegram.ext import Application
from bot.config import TELEGRAM_TOKEN
from bot.handlers import register_handlers        # ← вместо «start»

async def start_bot() -> None:
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    # все /start-, callback- и другие хендлеры
    # регистрируются одной функцией ↓
    register_handlers(app)

    await app.run_polling()      # запускает initialize / start / idle

if __name__ == "__main__":
    asyncio.run(start_bot())
