import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from message import Messenger

# Загрузка переменных из .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ебать, здарова 2!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    messenger: Messenger = context.bot_data["messenger"]
    await messenger.handle_message(update, context)


async def post_init(application):
    bot = await application.bot.get_me()
    application.bot_data["bot_username"] = bot.username
    application.bot_data["messenger"] = Messenger()
    logging.info(f"Bot username: {bot.username}")


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN must be set")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()
