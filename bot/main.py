# bot/main.py
import asyncio
from telegram.ext import Application, CommandHandler
from bot.config import TELEGRAM_TOKEN
from bot.handlers import start             # ваш start-callback

async def start_bot() -> None:
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))

    # --------------------- главное изменение --------------------
    #   Было:  await app.updater.idle()
    #   Стало: await app.run_polling()
    # ------------------------------------------------------------
    await app.run_polling()   # асинхронный удобный one-liner

if __name__ == "__main__":
    asyncio.run(start_bot())
