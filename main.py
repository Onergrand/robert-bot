import os
import logging
# from telegram.ext._contexttypes import DEFAULT_TYPE
from typing import Any
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
from db.db import healthcheck  # NEW
from db.chat_repo import ensure_user, set_user_role, get_user_role
from db.migrations import run_migrations  # Миграции БД

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
    # Пишем имя бота в bot_data
    bot = await application.bot.get_me()
    application.bot_data["bot_username"] = bot.username

    # Создаём единый Messenger и BotCommands
    messenger = Messenger()
    application.bot_data["messenger"] = messenger
    application.bot_data["commands"] = BotCommands(messenger)
    logging.info(f"Bot username: {bot.username}")

    # Проверяем подключение к БД при старте
    try:
        await healthcheck()
        logging.info("DB connection OK")
    except Exception:
        logging.exception("DB connection failed")
        # Можно падать сразу:
        # raise
    
    # Выполняем миграции (создание таблиц если их нет)
    try:
        await run_migrations()
        logging.info("Migrations completed")
    except Exception:
        logging.exception("Migration failed")
        # Продолжаем работу, но могут быть проблемы
    
    # Инициализация первого owner из переменной окружения
    owner_id_str = os.getenv("OWNER_ID")
    if owner_id_str:
        try:
            owner_id = int(owner_id_str)
            current_role = await get_user_role(owner_id)
            if current_role != "owner":
                await set_user_role(owner_id, None, "owner")
                logging.info(f"Owner initialized: {owner_id}")
            else:
                logging.info(f"Owner already exists: {owner_id}")
        except (ValueError, Exception) as e:
            logging.warning(f"Failed to initialize owner from OWNER_ID: {e}")

    # Создаём глобальную задачу для отправки праздничных сообщений во все чаты
    # Запускается каждый день в 10:00 UTC (можно изменить время)
    from datetime import time
    job_queue = application.job_queue
    job_queue.run_daily(
        messenger.send_holiday_congrats,
        time=time(hour=5, minute=35),  # 10:00 UTC каждый день
        name="holiday_congrats_all_chats"
    )
    logging.info("Global holiday message job scheduled (daily at 10:00 UTC)")


# Обёртки, чтобы дергать методы BotCommands из bot_data
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

async def cmd_clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].clear_history(update, context)

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].mute(update, context)

async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].unmute(update, context)

async def cmd_say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].say(update, context)

async def cmd_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].add_admin(update, context)

async def cmd_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].remove_admin(update, context)

async def cmd_list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].list_admins(update, context)

async def cmd_set_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["commands"].set_owner(update, context)

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN must be set")

    # Увеличенные таймауты для избежания проблем с соединением
    application = ApplicationBuilder().token(TELEGRAM_TOKEN)\
        .connect_timeout(60)\
        .read_timeout(60)\
        .write_timeout(60)\
        .pool_timeout(60)\
        .post_init(post_init).build()

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
    application.add_handler(CommandHandler("clear_history", cmd_clear_history))
    application.add_handler(CommandHandler("mute", cmd_mute))
    application.add_handler(CommandHandler("unmute", cmd_unmute))
    application.add_handler(CommandHandler("say", cmd_say))
    application.add_handler(CommandHandler("add_admin", cmd_add_admin))
    application.add_handler(CommandHandler("remove_admin", cmd_remove_admin))
    application.add_handler(CommandHandler("list_admins", cmd_list_admins))
    application.add_handler(CommandHandler("set_owner", cmd_set_owner)) 
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()
