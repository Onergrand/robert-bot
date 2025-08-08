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
from bot_commands import BotCommands

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
    messenger = Messenger()
    application.bot_data["messenger"] = messenger
    application.bot_data["commands"] = BotCommands(messenger)
    logging.info(f"Bot username: {bot.username}")


# Wrapper callbacks that delegate to BotCommands stored in bot_data
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].help(update, context)


async def cmd_set_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].set_prompt(update, context)


async def cmd_get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].get_prompt(update, context)


async def cmd_reset_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].reset_prompt(update, context)


async def cmd_set_history_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].set_history_limit(update, context)


async def cmd_set_autopost_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].set_autopost_interval(update, context)


async def cmd_enable_autopost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].enable_autopost(update, context)


async def cmd_disable_autopost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].disable_autopost(update, context)


async def cmd_enable_reactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].enable_reactions(update, context)


async def cmd_disable_reactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].disable_reactions(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].status(update, context)


async def cmd_metrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].metrics(update, context)


async def cmd_send_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].send_test(update, context)


async def cmd_holiday_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].holiday_check(update, context)


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN must be set")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("set_prompt", cmd_set_prompt))
    application.add_handler(CommandHandler("get_prompt", cmd_get_prompt))
    application.add_handler(CommandHandler("reset_prompt", cmd_reset_prompt))
    application.add_handler(CommandHandler("set_history_limit", cmd_set_history_limit))
    application.add_handler(CommandHandler("set_autopost_interval", cmd_set_autopost_interval))
    application.add_handler(CommandHandler("enable_autopost", cmd_enable_autopost))
    application.add_handler(CommandHandler("disable_autopost", cmd_disable_autopost))
    application.add_handler(CommandHandler("enable_reactions", cmd_enable_reactions))
    application.add_handler(CommandHandler("disable_reactions", cmd_disable_reactions))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("metrics", cmd_metrics))
    application.add_handler(CommandHandler("send_test", cmd_send_test))
    application.add_handler(CommandHandler("holiday_check", cmd_holiday_check))
    application.add_handler(CommandHandler("clear_history", lambda u, c: c.bot_data["commands"].clear_history(u, c)))
    application.add_handler(CommandHandler("mute", lambda u, c: c.bot_data["commands"].mute(u, c)))
    application.add_handler(CommandHandler("unmute", lambda u, c: c.bot_data["commands"].unmute(u, c)))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()
