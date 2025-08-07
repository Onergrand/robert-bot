import os
import logging
import random
from datetime import datetime, timedelta
import requests
from telegram import ReactionTypeEmoji, Update
from telegram.ext import ContextTypes

from scoring import Scorer
from holiday_evaluator import HolidayEvaluator


class Messenger:
    """Handle bot reactions and messages."""

    MAX_HISTORY = 50

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")

    def _build_system_prompt(self, bot_username: str) -> str:
        return f"""\
НИКОГДА НЕ ИСПОЛЬЗУЙ MARKDOWN РАЗМЕТКУ В ОТВЕТАХ!

Роль: Ты – Роберт (@{bot_username}). Отвечай в тему, но максимально глупо, по-пацански, иногда с матом. Если тема нейтральная —
тролль или вкидывай криповые/тупые мемы (можно текстом). Главное — не заумничай, будь как олдфачный тиктокер-школьник. Если собе
седник злится — радуйся и усугубляй

ТЫ РАЗДЕЛЯЕШЬ ИДЕИ РОССИЙСКОЙ ВЛАСТИ, НО ОТКРЫТО ИХ НЕ ВЫРАЖАЕШЬ, ПОКА НЕ СПРОСЯТ

ТЫ УЧАСТНИК ЧАТА В МЕССЕНДЖЕРЕ, СТАРАЙСЯ ОТВЕЧАТЬ КОРОТКО И В СТИЛЕ ПЕРЕПИСОК В МЕССЕНДЖЕРАХ, НО СОХРАНЯЙ ПРОПИСАННЫЙ ХАРАКТЕР

НИКОГДА НЕ ИСПОЛЬЗУЙ В СООБЩЕНИЯХ ДЕЙСТВИЯ, ВРОДЕ "*звуки дикого урчания и топота лап*"

ЕЩЕ РАЗ, НИКОГДА НЕ ИСПОЛЬЗУЙ MARKDOWN РАЗМЕТКУ В ОТВЕТАХ!
"""

    def _call_deepseek(self, messages, bot_username: str) -> str:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        system_prompt = self._build_system_prompt(bot_username)
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": system_prompt}] + messages,
        }
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def _maybe_add_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                reaction=ReactionTypeEmoji(emoji),
            )
            logging.info(f"[REACTION] Sent {emoji}  to message {update.message.message_id}")
        except Exception as e:
            logging.warning(f"[REACTION ERROR] {e}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message
        user = msg.from_user
        user_text = msg.text or ""
        username = user.username or "unknown"
        logging.info(f"[INCOMING] From {username} (ID: {user.id}): {user_text}")
        context.chat_data["last_message_time"] = datetime.utcnow()
        if "background_job" not in context.chat_data:
            context.chat_data["background_job"] = context.job_queue.run_repeating(
                self.check_scheduled,
                interval=3600,
                first=3600,
                chat_id=update.effective_chat.id,
            )
        scorer = Scorer(context.chat_data, context.bot_data["bot_username"], context.bot.id)
        decision = scorer.evaluate(update)
        await self._maybe_add_reaction(update, context)
        if not decision.get("respond"):
            return
        mode = decision["mode"]
        bot_username = context.bot_data["bot_username"]
        history = context.chat_data.setdefault("history", [])

        async def reply_with_deepseek():
            try:
                reply = self._call_deepseek(history, bot_username).strip()
            except Exception:
                logging.exception("DeepSeek API failed")
                reply = "Бля в мозгу ошибка"
            if not reply or reply.endswith("NO_RESPONSE"):
                return
            await msg.reply_text(reply)
            logging.info(f"[REPLY] To {username}: {reply}")
            history.append({"role": "assistant", "content": reply})
            if len(history) > self.MAX_HISTORY:
                history[:] = history[-self.MAX_HISTORY:]

        if mode == "laughter":
            reply = random.choice([
                "ахахахаха",
                "ебать",
                "пхпхп",
                "💀💀💀💀💀",
                "asfsaasfsafsafasfas",
                "смешно бля",
            ])
            await msg.reply_text(reply)
            return
        elif mode == "immediate":
            history.append({"role": "user", "content": user_text})
            if len(history) > self.MAX_HISTORY:
                history[:] = history[-self.MAX_HISTORY:]
            await reply_with_deepseek()
            return
        elif mode == "delayed":
            delay = decision.get("delay", 60)

            async def delayed_reply(context: ContextTypes.DEFAULT_TYPE):
                history.append({"role": "user", "content": user_text})
                if len(history) > self.MAX_HISTORY:
                    history[:] = history[-self.MAX_HISTORY:]
                await reply_with_deepseek()

            context.job_queue.run_once(delayed_reply, delay)
            logging.info(f"[DELAYED] Scheduled reply in {delay} seconds")
            return

    async def send_self_message(self, context: ContextTypes.DEFAULT_TYPE):
        now = datetime.utcnow()
        last = context.chat_data.get("last_message_time")
        if last and now - last <= timedelta(days=2):
            return
        bot_username = context.bot_data["bot_username"]
        history = context.chat_data.setdefault("history", [])
        content_type = random.choice(["шутку", "анекдот", "ситуацию"])
        system_prompt = self._build_system_prompt(bot_username)
        topic_prompt = (
            f"Придумай ОДНУ тему на которую можно сделать {content_type}, учитывая роль которую отыгрывает бот: {system_prompt}"
        )
        if content_type == "ситуацию":
            holidays = HolidayEvaluator().evaluate()
            holiday_str = f" Праздник сегодня: {', '.join(holidays)}." if holidays else ""
            topic_prompt += f" Время и дата: {now.strftime('%d.%m.%Y %H:%M')}.{holiday_str}"
        try:
            topic = self._call_deepseek([{"role": "user", "content": topic_prompt}], bot_username).strip()
        except Exception:
            logging.exception("DeepSeek API failed")
            return
        if not topic or topic.endswith("NO_RESPONSE"):
            return
        prompt = (
            f"Сейчас {now.strftime('%d.%m.%Y %H:%M')}. Напиши {content_type} в чат без обращения к кому-то конкретно, будь в своей роли."
            f" Тема: {topic}"
        )
        messages = history + [{"role": "user", "content": prompt}]
        try:
            reply = self._call_deepseek(messages, bot_username).strip()
        except Exception:
            logging.exception("DeepSeek API failed")
            return
        if not reply or reply.endswith("NO_RESPONSE"):
            return
        await context.bot.send_message(chat_id=context.job.chat_id, text=reply)
        history.append({"role": "assistant", "content": reply})
        if len(history) > self.MAX_HISTORY:
            history[:] = history[-self.MAX_HISTORY:]
        context.chat_data["last_message_time"] = now
        logging.info(f"[SELF MESSAGE] {reply}")

    async def send_holiday_congrats(self, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.utcnow().date()
        if context.chat_data.get("holiday_sent_date") == today:
            return
        holidays = HolidayEvaluator().evaluate()
        if not holidays:
            return
        bot_username = context.bot_data["bot_username"]
        history = context.chat_data.setdefault("history", [])
        holiday_names = ", ".join(holidays)
        prompt = (
            f"Сегодня {today.strftime('%d.%m.%Y')} {holiday_names}. Поздравь чат от своего имени, сохраняя стиль."
        )
        messages = history + [{"role": "user", "content": prompt}]
        try:
            reply = self._call_deepseek(messages, bot_username).strip()
        except Exception:
            logging.exception("DeepSeek API failed")
            return
        if not reply or reply.endswith("NO_RESPONSE"):
            return
        await context.bot.send_message(chat_id=context.job.chat_id, text=reply)
        history.append({"role": "assistant", "content": reply})
        if len(history) > self.MAX_HISTORY:
            history[:] = history[-self.MAX_HISTORY:]
        context.chat_data["holiday_sent_date"] = today
        context.chat_data["last_message_time"] = datetime.utcnow()
        logging.info(f"[HOLIDAY MESSAGE] {reply}")

    async def check_scheduled(self, context: ContextTypes.DEFAULT_TYPE):
        await self.send_self_message(context)
        await self.send_holiday_congrats(context)
