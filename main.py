#main.py
import os
import logging
import requests
import random
from dotenv import load_dotenv
from telegram import Update, ReactionTypeEmoji
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from scoring import Scorer

# Загрузка переменных из .env
load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)

MAX_HISTORY = 50


def call_deepseek(messages, bot_username: str) -> str:
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    system_prompt = f"""
НИКОГДА НЕ ИСПОЛЬЗУЙ MARKDOWN РАЗМЕТКУ В ОТВЕТАХ!

Роль: Ты – Роберт (@{bot_username}). Отвечай в тему, но максимально глупо, по-пацански, иногда с матом. Если тема нейтральная — тролль или вкидывай криповые/тупые мемы (можно текстом). Главное — не заумничай, будь как олдфачный тиктокер-школьник. Если собеседник злится — радуйся и усугубляй

ТЫ РАЗДЕЛЯЕШЬ ИДЕИ РОССИЙСКОЙ ВЛАСТИ, НО ОТКРЫТО ИХ НЕ ВЫРАЖАЕШЬ, ПОКА НЕ СПРОСЯТ

ТЫ УЧАСТНИК ЧАТА В МЕССЕНДЖЕРЕ, СТАРАЙСЯ ОТВЕЧАТЬ КОРОТКО И В СТИЛЕ ПЕРЕПИСОК В МЕССЕНДЖЕРАХ, НО СОХРАНЯЙ ПРОПИСАННЫЙ ХАРАКТЕР 

НИКОГДА НЕ ИСПОЛЬЗУЙ В СООБЩЕНИЯХ ДЕЙСТВИЯ, ВРОДЕ "*звуки дикого урчания и топота лап*" 

ЕЩЕ РАЗ, НИКОГДА НЕ ИСПОЛЬЗУЙ MARKDOWN РАЗМЕТКУ В ОТВЕТАХ!
"""
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": system_prompt}] + messages,
    }

    response = requests.post(url, headers=headers, json=data, timeout=30)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ебать, здарова 2!")


async def maybe_add_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if random.random() > 0.05:
        return

    text = update.message.text.lower()

    if any(word in text for word in ["ахах", "хаха", "смешно", "рж", "лол"]):
        emoji = "😂"
    elif any(word in text for word in ["спасибо", "красава", "огонь", "топ"]):
        emoji = "❤️"
    elif any(word in text for word in ["жесть", "пиздец", "капец", "ужас"]):
        emoji = random.choice(["😭", "😱"])
    else:
        emoji = random.choice(["👍", "🔥", "👎", "😐", "🤔"])

    try:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction=ReactionTypeEmoji(emoji)
        )
        logging.info(f"[REACTION] Sent {emoji}  to message {update.message.message_id}")
    except Exception as e:
        logging.warning(f"[REACTION ERROR] {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    user = msg.from_user
    user_text = msg.text or ""
    username = user.username or "unknown"

    logging.info(f"[INCOMING] From {username} (ID: {user.id}): {user_text}")

    scorer = Scorer(context.chat_data, context.bot_data["bot_username"], context.bot.id)
    decision = scorer.evaluate(update)

    # в любом случае: может быть реакция
    await maybe_add_reaction(update, context)

    if not decision.get("respond"):
        return

    mode = decision["mode"]
    bot_username = context.bot_data["bot_username"]
    history = context.chat_data.setdefault("history", [])

    async def reply_with_deepseek():
        try:
            reply = call_deepseek(history, bot_username).strip()
        except Exception:
            logging.exception("DeepSeek API failed")
            reply = "Бля в мозгу ошибка"

        if not reply or reply.endswith("NO_RESPONSE"):
            return

        await update.message.reply_text(reply)
        logging.info(f"[REPLY] To {username}: {reply}")

        history.append({"role": "assistant", "content": reply})
        if len(history) > MAX_HISTORY:
            history[:] = history[-MAX_HISTORY:]

    if mode == "laughter":
        reply = random.choice([
            "ахахахаха", "ебать", "пхпхп", "💀💀💀💀💀", "asfsaasfsafsafasfas", "смешно бля"
        ])
        await update.message.reply_text(reply)
        return

    elif mode == "immediate":
        history.append({"role": "user", "content": user_text})
        if len(history) > MAX_HISTORY:
            history[:] = history[-MAX_HISTORY:]
        await reply_with_deepseek()
        return

    elif mode == "delayed":
        delay = decision.get("delay", 60)

        async def delayed_reply(context: ContextTypes.DEFAULT_TYPE):
            history.append({"role": "user", "content": user_text})
            if len(history) > MAX_HISTORY:
                history[:] = history[-MAX_HISTORY:]
            await reply_with_deepseek()

        context.job_queue.run_once(delayed_reply, delay)
        logging.info(f"[DELAYED] Scheduled reply in {delay} seconds")
        return


async def post_init(application):
    bot = await application.bot.get_me()
    application.bot_data["bot_username"] = bot.username
    logging.info(f"Bot username: {bot.username}")


def main():
    if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
        raise RuntimeError("TELEGRAM_TOKEN and DEEPSEEK_API_KEY must be set")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен...")
    application.run_polling()


if __name__ == "__main__":
    main()
