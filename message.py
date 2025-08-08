import os
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import requests
from telegram import ReactionTypeEmoji, Update
from telegram.ext import ContextTypes

from scoring import Scorer
from holiday_evaluator import HolidayEvaluator

# NEW: работа с БД
from db.chat_repo import (
    ensure_chat, load_chat_config, save_chat_config,
    load_history, append_message, clear_history,
    was_holiday_sent_today, mark_holiday_sent,
    load_metrics, save_metrics
)


class Messenger:
    """Handle bot reactions and messages."""

    MAX_HISTORY = 50

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.system_prompt_override = None

    def _default_system_prompt(self, bot_username: str) -> str:
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

    def set_system_prompt(self, new_prompt: Optional[str]) -> None:
        self.system_prompt_override = new_prompt

    def get_current_system_prompt(self, bot_username: str) -> str:
        if self.system_prompt_override and self.system_prompt_override.strip():
            return self.system_prompt_override
        return self._default_system_prompt(bot_username)

    def _call_deepseek(self, messages, bot_username: str) -> str:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        system_prompt = self.get_current_system_prompt(bot_username)
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": system_prompt}] + messages,
        }
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def _maybe_add_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        reactions_enabled = context.chat_data.get("reactions_enabled", True)
        if not reactions_enabled:
            return
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

        # === БД: убедимся, что чат есть в таблице и подтащим конфиг/историю ===
        chat = update.effective_chat
        await ensure_chat(chat.id, chat.type, getattr(chat, 'title', None))

        cfg = await load_chat_config(chat.id) or {}
        history_limit = int(cfg.get("history_limit", self.MAX_HISTORY))
        # Синхронизируем флаги из БД в chat_data (кэш для текущей сессии)
        for k in ("autopost_enabled", "autopost_interval", "reactions_enabled", "muted_until"):
            if k in cfg and cfg[k] is not None:
                context.chat_data[k] = cfg[k]

        # История для промпта (берём из БД)
        history: List[Dict[str, str]] = await load_history(chat.id, history_limit)
        context.chat_data["history"] = history  # кэш для scoring и т.п.

        context.chat_data["last_message_time"] = datetime.utcnow()
        # Respect mute window
        muted_until = context.chat_data.get("muted_until")
        if muted_until:
            try:
                if datetime.utcnow() < muted_until:
                    return
            except Exception:
                pass

        # Mention-based help: '@bot помощь' / '@bot команды'
        try:
            bot_username = context.bot_data.get("bot_username", "").lower()
            lower_text = user_text.lower()
            if bot_username and (f"@{bot_username}" in lower_text):
                if any(k in lower_text for k in ["помощь", "команды", "help", "команда"]):
                    await context.bot_data["commands"].handle_mention_help(update, context)
                    return
        except Exception:
            logging.exception("Mention help handling failed")

        # Lazy-init background job (enabled by default unless disabled explicitly)
        if context.chat_data.get("autopost_enabled", True):
            interval = context.chat_data.get("autopost_interval", 3600)
            if "background_job" not in context.chat_data:
                context.chat_data["background_job"] = context.job_queue.run_repeating(
                    self.check_scheduled,
                    interval=interval,
                    first=interval,
                    chat_id=chat.id,
                )

        # === Scoring/решение отвечать ===
        scorer = Scorer(context.chat_data, context.bot_data["bot_username"], context.bot.id)
        decision = scorer.evaluate(update)

        await self._maybe_add_reaction(update, context)
        if not decision.get("respond"):
            # Можно по желанию синкать метрики в БД раз в N сообщений
            return

        mode = decision["mode"]
        bot_username = context.bot_data["bot_username"]

        async def reply_with_deepseek(messages_for_llm):
            try:
                reply = self._call_deepseek(messages_for_llm, bot_username).strip()
            except Exception:
                logging.exception("DeepSeek API failed")
                reply = "Бля в мозгу ошибка"
            if not reply or reply.endswith("NO_RESPONSE"):
                return
            await msg.reply_text(reply)
            logging.info(f"[REPLY] To {username}: {reply}")
            # Сохраняем ответ ассистента
            await append_message(chat.id, "assistant", reply, history_limit)
            # Обновим кэш истории в памяти (не обязательно)
            context.chat_data["history"] = await load_history(chat.id, history_limit)

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
            # Лог в БД как ответ ассистента
            await append_message(chat.id, "assistant", reply, history_limit)
            context.chat_data["history"] = await load_history(chat.id, history_limit)
            return

        elif mode == "immediate":
            # Добавим сообщение пользователя в историю (БД)
            await append_message(chat.id, "user", user_text, history_limit)
            # Собираем историю для LLM (можно просто снова загрузить)
            history = await load_history(chat.id, history_limit)
            await reply_with_deepseek(history)
            # Сохраним метрики
            await save_metrics(chat.id, context.chat_data.get("scoring", {}))
            return

        elif mode == "delayed":
            delay = int(decision.get("delay", 60))

            async def delayed_reply(ctx: ContextTypes.DEFAULT_TYPE):
                await append_message(chat.id, "user", user_text, history_limit)
                hist = await load_history(chat.id, history_limit)
                await reply_with_deepseek(hist)
                await save_metrics(chat.id, ctx.chat_data.get("scoring", {}))

            context.job_queue.run_once(delayed_reply, delay, chat_id=chat.id)
            logging.info(f"[DELAYED] Scheduled reply in {delay} seconds")
            return

    async def send_self_message(self, context: ContextTypes.DEFAULT_TYPE):
        now = datetime.utcnow()
        chat_id = context.job.chat_id

        # Подтянем актуальные настройки
        cfg = await load_chat_config(chat_id) or {}
        muted_until = cfg.get("muted_until")
        history_limit = int(cfg.get("history_limit", self.MAX_HISTORY))

        # Do not send autoposts when muted
        if muted_until and now < muted_until:
            return

        # Уважим «активность в последние сутки»
        last = context.chat_data.get("last_message_time")
        if last and now - last <= timedelta(days=1):
            return

        bot_username = context.bot_data["bot_username"]
        history = await load_history(chat_id, history_limit)
        content_type = random.choice(["шутку", "анекдот", "ситуацию"])
        system_prompt = self.get_current_system_prompt(bot_username)
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
            logging.exception("DeepSeek API failed (topic)")
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
            logging.exception("DeepSeek API failed (autopost)")
            return
        if not reply or reply.endswith("NO_RESPONSE"):
            return

        await context.bot.send_message(chat_id=chat_id, text=reply)
        await append_message(chat_id, "assistant", reply, history_limit)
        context.chat_data["last_message_time"] = now
        logging.info(f"[SELF MESSAGE] {reply}")

    async def send_holiday_congrats(self, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.utcnow().date()
        chat_id = context.job.chat_id

        # Уже отправляли сегодня?
        if await was_holiday_sent_today(chat_id, today):
            return

        holidays = HolidayEvaluator().evaluate()
        if not holidays:
            return

        bot_username = context.bot_data["bot_username"]
        history_limit = int((await load_chat_config(chat_id) or {}).get("history_limit", self.MAX_HISTORY))
        history = await load_history(chat_id, history_limit)

        holiday_names = ", ".join(holidays)
        prompt = f"Сегодня {today.strftime('%d.%m.%Y')} {holiday_names}. Поздравь чат от своего имени, сохраняя стиль."

        messages = history + [{"role": "user", "content": prompt}]
        try:
            reply = self._call_deepseek(messages, bot_username).strip()
        except Exception:
            logging.exception("DeepSeek API failed (holiday)")
            return
        if not reply or reply.endswith("NO_RESPONSE"):
            return

        await context.bot.send_message(chat_id=chat_id, text=reply)
        await append_message(chat_id, "assistant", reply, history_limit)
        await mark_holiday_sent(chat_id, today)
        context.chat_data["last_message_time"] = datetime.utcnow()
        logging.info(f"[HOLIDAY MESSAGE] {reply}")

    async def check_scheduled(self, context: ContextTypes.DEFAULT_TYPE):
        await self.send_self_message(context)
        await self.send_holiday_congrats(context)
