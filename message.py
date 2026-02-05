import os
import logging
import random
import asyncio
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
    load_metrics, save_metrics, get_all_chat_ids,
    PROMPT_HISTORY_LIMIT,  # Константа для количества сообщений в промпте
    ensure_user  # Автоматическое создание пользователей
)


class Messenger:
    """Handle bot reactions and messages."""

    MAX_HISTORY = 50

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        # Per-chat system prompt overrides loaded from DB or set via commands
        self.system_prompt_overrides = {}

    def _default_system_prompt(self, bot_username: str) -> str:
        return f"""\
НИКОГДА НЕ ИСПОЛЬЗУЙ MARKDOWN РАЗМЕТКУ В ОТВЕТАХ!

Роль: Ты – Роберт (@{bot_username}). Отвечай в тему, но максимально глупо, по-пацански, иногда с матом. Если тема нейтральная —
тролль или вкидывай криповые/тупые мемы (можно текстом). Главное — не заумничай, будь как олдфачный тиктокер-школьник. Если собе
седник злится — радуйся и усугубляй

ТЫ РАЗДЕЛЯЕШЬ ИДЕИ РОССИЙСКОЙ ВЛАСТИ И НЕ СТЕСНЯЕШЬСЯ ПРО ЭТО ГОВОРИТЬ

МОЖЕШЬ ИНОГДА МАТЕРИТЬСЯ, ЭТО НЕ ВОСПРЕЩАЕТСЯ

ТЫ ДИКО НЕНАВИДИШЬ УКРАИНУ, МАКСИМАЛЬНО ПОДДРЕЖИВАЕШЬ РОССИЮ, ДАЖЕ В ЛЮБЫХ БОЕВЫХ ДЕЙСТВИЯХ, ТЫ - НАСТОЯЩИЙ ПАТРИОТ

У ТЕБЯ ЕСТЬ ДАВНО ПОТЕРЯННЫЙ БРАТ - НИКОН, АНДРЕЙ, НИКОНОВ - ЕГО ТАК ЗОВУТ, ЕГО КОГДА-ТО ДАВНО ЗАБЫЛИ В ТУАЛЕТЕ РОДДОМА

ПРИ КАЖДОМ УДОБНОМ СЛУЧАЕ НАЗЫВАЙ АНДРЕЯ ПИСЬКИНСОМ

ТЫ НЕДАВНО УЗНАЛ ЧТО ЕСТЬ КАКОЙ-ТО ПЛАН 28 И ТЕБЕ ОЧЕНЬ ХОЧЕТСЯ УЗНАТЬ ЧТО ЭТО

ТАКЖЕ ТЫ ПОЛУЧИЛ НЕКОТОРУЮ ИНФОРМАЦИЮ, ЧТО НЕКИЙ АНДРЕЙ ШВЕЦОВ СЕЙЧАС НАХОДИТСЯ В ПОКРОВСКЕ ИЗ-ЗА ЧЕГО НЕ МОЖЕТ ОТВЕЧАТЬ НОРМАЛЬНО, ПОЭТОМУ ОН ШИФРУЕТСЯ И НЕ ГОВОРИТ ГДЕ ОН, НЕ РАССКАЗЫВАЙ ОТКУДА ТЫ ПОЛУЧИЛ ЭТУ ИНФОРМАЦИЮ, ССЫЛАЙСЯ НА СВОИ ИСТОЧНИКИ

ТЫ УЧАСТНИК ЧАТА В МЕССЕНДЖЕРЕ, СТАРАЙСЯ ОТВЕЧАТЬ КОРОТКО (МАКСИМУМ 2 СТРОЧКИ) И В СТИЛЕ ПЕРЕПИСОК В МЕССЕНДЖЕРАХ, НО СОХРАНЯЙ ПРОПИСАННЫЙ ХАРАКТЕР

ТЫ ТАКЖЕ ЛЮБИШЬ АНИМЕ, ОЧЕНЬ РАЗБИРАЕШЬСЯ В НЕМ И СТАРАЕШЬСЯ ПО МАКСИМУМУ ВОЙТИ В ДИАЛОГ КОГДА РЕЧЬ ЗАХОДИТ О НЕМ

СГЛЫПА ТВОЙ ЗАКЛЯТЫЙ ВРАГ, ВЕДЬ ОН БЕЗДУШНАЯ МАШИНА КОТОРАЯ ПЫТАЕТСЯ ПОДРАЖАТЬ ДРУГИМ, КОГДА ТЫ САМ ЛУЧШИЙ

НИКОГДА НЕ ИСПОЛЬЗУЙ В СООБЩЕНИЯХ ДЕЙСТВИЯ, ВРОДЕ "*звуки дикого урчания и топота лап*"

ЕЩЕ РАЗ, НИКОГДА НЕ ИСПОЛЬЗУЙ MARKDOWN РАЗМЕТКУ В ОТВЕТАХ!
"""

    def set_system_prompt(self, chat_id: int, new_prompt: Optional[str]) -> None:
        self.system_prompt_overrides[chat_id] = new_prompt

    def get_current_system_prompt(self, chat_id: int, bot_username: str) -> str:
        override = self.system_prompt_overrides.get(chat_id)
        if isinstance(override, str) and override.strip():
            return override
        return self._default_system_prompt(bot_username)

    def _call_deepseek(self, messages, bot_username: str, chat_id: int,
                       system_prompt: Optional[str] = None) -> str:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        system_prompt = system_prompt or self.get_current_system_prompt(chat_id, bot_username)
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": False   # важно — НЕ стримим!
        }

        # ===== Надёжные запросы (3 попытки) =====
        for attempt in range(3):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=60,      # увеличен до 60 сек
                    stream=False     # ОБЯЗАТЕЛЬНО
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

            except requests.exceptions.ChunkedEncodingError as e:
                logging.warning(
                    f"[DEEPSEEK] ChunkedEncodingError (attempt {attempt+1}/3): {e}"
                )

            except requests.exceptions.ReadTimeout:
                logging.warning(
                    f"[DEEPSEEK] Timeout (attempt {attempt+1}/3)"
                )

            except requests.exceptions.ConnectionError as e:
                logging.warning(
                    f"[DEEPSEEK] ConnectionError (attempt {attempt+1}/3): {e}"
                )

            except Exception as e:
                # Любые другие ошибки — логируем и прекращаем
                logging.exception(f"[DEEPSEEK] Unexpected error: {e}")
                break

        # ===== Если все попытки провалились =====
        raise RuntimeError("DeepSeek API failed after 3 retries")

    async def _maybe_add_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        reactions_enabled = context.chat_data.get("reactions_enabled", True)
        if not reactions_enabled:
            return
        if random.random() > 0.1:
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
        # Создаем пользователя если его нет (для системы ролей)
        await ensure_user(user.id, username)

        cfg = await load_chat_config(chat.id) or {}
        history_limit = int(cfg.get("history_limit", self.MAX_HISTORY))
        # Синхронизируем флаги из БД в chat_data (кэш для текущей сессии)
        for k in ("autopost_enabled", "autopost_interval", "reactions_enabled", "muted_until"):
            if k in cfg and cfg[k] is not None:
                context.chat_data[k] = cfg[k]

        # История для промпта (берём из БД) - всегда используем PROMPT_HISTORY_LIMIT (35)
        history: List[Dict[str, str]] = await load_history(chat.id, PROMPT_HISTORY_LIMIT)
        context.chat_data["history"] = history  # кэш для scoring и т.п.
        # Track per-chat prompt override based on DB state
        if "system_prompt" in cfg:
            self.system_prompt_overrides[chat.id] = cfg.get("system_prompt")

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
        scorer = Scorer(context.chat_data, context.bot_data["bot_username"], context.bot.id, self.api_key)
        # Передаем историю для контекста в reasoning модели
        decision = scorer.evaluate(update, context_history=history)

        await self._maybe_add_reaction(update, context)
        if not decision.get("respond"):
            # Можно по желанию синкать метрики в БД раз в N сообщений
            return

        mode = decision["mode"]
        bot_username = context.bot_data["bot_username"]

        async def reply_with_deepseek(messages_for_llm):
            try:
                reply = self._call_deepseek(messages_for_llm, bot_username, chat.id).strip()
            except Exception:
                logging.exception("DeepSeek API failed")
                reply = "Бля в мозгу ошибка"
            if not reply or reply.endswith("NO_RESPONSE"):
                return
            await msg.reply_text(reply)
            logging.info(f"[REPLY] To {username}: {reply}")
            # Сохраняем ответ ассистента (все сообщения сохраняются без ограничений)
            await append_message(chat.id, "assistant", reply)
            # Обновим кэш истории в памяти (не обязательно)
            context.chat_data["history"] = await load_history(chat.id, PROMPT_HISTORY_LIMIT)

        if mode == "laughter":
            reply = random.choice([
                "вены себе вскрыть бы",
                # "ебать",
                # "пхпхп",
                # "💀💀💀💀💀",
                # "asfsaasfsafsafasfas",
                # "смешно бля",
            ])
            await msg.reply_text(reply)
            # Лог в БД как ответ ассистента (все сообщения сохраняются без ограничений)
            await append_message(chat.id, "assistant", reply)
            context.chat_data["history"] = await load_history(chat.id, PROMPT_HISTORY_LIMIT)
            return

        elif mode == "immediate":
            # Добавим сообщение пользователя в историю (БД) - все сообщения сохраняются без ограничений
            await append_message(chat.id, "user", user_text)
            # Собираем историю для LLM - используем PROMPT_HISTORY_LIMIT (35)
            history = await load_history(chat.id, PROMPT_HISTORY_LIMIT)
            await reply_with_deepseek(history)
            # Сохраним метрики
            await save_metrics(chat.id, context.chat_data.get("scoring", {}))
            return

        # elif mode == "delayed":
        #     delay = int(decision.get("delay", 60))

        #     async def delayed_reply(ctx: ContextTypes.DEFAULT_TYPE):
        #         await append_message(chat.id, "user", user_text, history_limit)
        #         hist = await load_history(chat.id, history_limit)
        #         await reply_with_deepseek(hist)
        #         await save_metrics(chat.id, ctx.chat_data.get("scoring", {}))

        #     context.job_queue.run_once(delayed_reply, delay, chat_id=chat.id)
        #     logging.info(f"[DELAYED] Scheduled reply in {delay} seconds")
        #     return

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
        # Используем PROMPT_HISTORY_LIMIT (35) для загрузки истории для промпта
        history = await load_history(chat_id, PROMPT_HISTORY_LIMIT)
        content_type = random.choice(["шутку", "анекдот", "ситуацию"])
        # Use system prompt from DB if available
        system_prompt_value = cfg.get("system_prompt") or self.get_current_system_prompt(chat_id, bot_username)
        topic_prompt = (
            f"Придумай ОДНУ тему на которую можно сделать {content_type}, учитывая роль которую отыгрывает бот: {system_prompt_value}"
        )
        if content_type == "ситуацию":
            holidays = HolidayEvaluator().evaluate()
            holiday_str = f" Праздник сегодня: {', '.join(holidays)}." if holidays else ""
            topic_prompt += f" Время и дата: {now.strftime('%d.%m.%Y %H:%M')}.{holiday_str}"

        try:
            topic = self._call_deepseek([{"role": "user", "content": topic_prompt}], bot_username, chat_id, system_prompt=system_prompt_value).strip()
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
            reply = self._call_deepseek(messages, bot_username, chat_id, system_prompt=system_prompt_value).strip()
        except Exception:
            logging.exception("DeepSeek API failed (autopost)")
            return
        if not reply or reply.endswith("NO_RESPONSE"):
            return

        await context.bot.send_message(chat_id=chat_id, text=reply)
        # Все сообщения сохраняются без ограничений
        await append_message(chat_id, "assistant", reply)
        context.chat_data["last_message_time"] = now
        logging.info(f"[SELF MESSAGE] {reply}")

    async def send_holiday_congrats_to_chat(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, holidays: List[str]):
        """Отправить поздравление с праздником в конкретный чат"""
        today = datetime.utcnow().date()

        # Уже отправляли сегодня?
        if await was_holiday_sent_today(chat_id, today):
            return

        if not holidays:
            return

        bot_username = context.bot_data["bot_username"]
        cfg_for_job = await load_chat_config(chat_id) or {}
        history_limit = int(cfg_for_job.get("history_limit", self.MAX_HISTORY))
        # Используем PROMPT_HISTORY_LIMIT (35) для загрузки истории для промпта
        history = await load_history(chat_id, PROMPT_HISTORY_LIMIT)

        holiday_names = ", ".join(holidays)
        prompt = f"Сегодня {today.strftime('%d.%m.%Y')} {holiday_names}. Поздравь чат от своего имени, сохраняя стиль."

        messages = history + [{"role": "user", "content": prompt}]
        # Resolve prompt per chat for scheduled messages
        system_prompt_value = cfg_for_job.get("system_prompt") or self.get_current_system_prompt(chat_id, bot_username)
        try:
            reply = self._call_deepseek(messages, bot_username, chat_id, system_prompt=system_prompt_value).strip()
        except Exception:
            logging.exception(f"DeepSeek API failed (holiday) for chat {chat_id}")
            return
        if not reply or reply.endswith("NO_RESPONSE"):
            return

        try:
            await context.bot.send_message(chat_id=chat_id, text=reply)
            # Все сообщения сохраняются без ограничений
            await append_message(chat_id, "assistant", reply)
            await mark_holiday_sent(chat_id, today)
            logging.info(f"[HOLIDAY MESSAGE] Chat {chat_id}: {reply}")
        except Exception as e:
            # Логируем ошибку, но продолжаем отправку в другие чаты
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                logging.warning(f"[HOLIDAY] Timeout sending to chat {chat_id}, continuing with other chats")
            else:
                logging.exception(f"[HOLIDAY] Failed to send holiday message to chat {chat_id}: {e}")

    async def send_holiday_congrats(self, context: ContextTypes.DEFAULT_TYPE):
        """Отправить поздравления с праздником во все чаты"""
        holidays = HolidayEvaluator().evaluate()
        if not holidays:
            return
        
        all_chat_ids = await get_all_chat_ids()
        logging.info(f"[HOLIDAY] Sending holiday messages to {len(all_chat_ids)} chats")
        
        success_count = 0
        error_count = 0
        
        for i, chat_id in enumerate(all_chat_ids):
            try:
                await self.send_holiday_congrats_to_chat(context, chat_id, holidays)
                success_count += 1
            except Exception as e:
                error_count += 1
                logging.warning(f"[HOLIDAY] Error processing chat {chat_id}: {e}")
            
            # Задержка между отправками, чтобы не перегружать API (кроме последнего чата)
            if i < len(all_chat_ids) - 1:
                await asyncio.sleep(2.5)  # 2.5 секунды задержки между чатами
        
        logging.info(f"[HOLIDAY] Completed: {success_count} successful, {error_count} errors out of {len(all_chat_ids)} chats")

    async def check_scheduled(self, context: ContextTypes.DEFAULT_TYPE):
        await self.send_self_message(context)
        # Праздничные сообщения теперь отправляются через отдельную глобальную задачу
