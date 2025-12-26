import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from holiday_evaluator import HolidayEvaluator

# NEW: БД-репозиторий
from db.chat_repo import (
    load_chat_config, save_chat_config,
    clear_history, load_history,
    get_user_role, set_user_role, ensure_user, get_all_admins, remove_user_role
)
from db.permissions import check_permission, is_owner, is_admin


class BotCommands:
    """Команды управления ботом, теперь с сохранением настроек в БД."""

    def __init__(self, messenger):
        # Messenger instance создаётся в post_init и пробрасывается сюда
        self.messenger = messenger

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        user_role = await get_user_role(user_id)
        
        # Базовые команды для всех пользователей
        text = "📋 Доступные команды:\n\n"
        text += "👤 Для всех пользователей:\n"
        text += "/help — показать это сообщение\n"
        text += "/get_prompt — показать текущий системный промпт\n"
        text += "/status — текущее состояние бота\n"
        text += "/metrics — показать счётчики\n"
        text += "/send_test <текст> — отправить тест к DeepSeek\n"
        text += "/holiday_check — проверить праздники на сегодня\n"
        
        # Команды для админов
        if await is_admin(update, context):
            text += "\n🔧 Для администраторов:\n"
            text += "/set_prompt <текст> — изменить системный промпт\n"
            text += "/reset_prompt — сбросить промпт к значению по умолчанию\n"
            text += "/set_history_limit <число> — установить лимит хранимых сообщений\n"
            text += "/set_autopost_interval <сек> — интервал автосообщений\n"
            text += "/enable_autopost — включить автосообщения\n"
            text += "/disable_autopost — выключить автосообщения\n"
            text += "/enable_reactions — включить автоматические реакции\n"
            text += "/disable_reactions — выключить реакции\n"
            text += "/clear_history — очистить историю сообщений\n"
            text += "/mute <минуты> — замьютить на указанное время\n"
            text += "/unmute — снять мьют\n"
            text += "/say <chat_id> <текст> — отправить сообщение в другой чат\n"
        
        # Команды для owner
        if await is_owner(update, context):
            text += "\n👑 Для владельца:\n"
            text += "/add_admin <user_id> — добавить администратора\n"
            text += "/remove_admin <user_id> — удалить администратора\n"
            text += "/list_admins — список всех администраторов\n"
            text += "/set_owner <user_id> — передать права владельца\n"
        
        text += f"\n\nВаша роль: {user_role}"
        await update.message.reply_text(text)

    async def set_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        new_prompt = " ".join(context.args).strip()
        if not new_prompt:
            await update.message.reply_text("Укажите текст промпта: /set_prompt <текст>")
            return

        self.messenger.set_system_prompt(chat_id, new_prompt)  # локально (пер-чат)
        await save_chat_config(chat_id, system_prompt=new_prompt)
        await clear_history(chat_id)  # чистим историю в БД

        # Обновить кэш в памяти
        context.chat_data["history"] = []
        await update.message.reply_text("Команда выполнена.")

    async def say(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return

        if len(context.args) < 2:
            await update.message.reply_text("❌ Формат: /say <CHAT_ID> <Текст сообщения>")
            return

        try:
            target_chat_id = int(context.args[0])
            # Собираем весь оставшийся текст как сообщение
            text_to_send = " ".join(context.args[1:])
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID чата. ID должен быть числом.")
            return
        
        if not text_to_send.strip():
            await update.message.reply_text("❌ Сообщение не может быть пустым.")
            return

        try:
            # 1. Отправляем сообщение в целевой чат
            sent_msg = await context.bot.send_message(chat_id=target_chat_id, text=text_to_send)
            
            # 2. Сохраняем в историю как ответ ассистента (role='assistant'), 
            # чтобы бот "помнил" об этом сообщении.
            
            # Получим лимит истории для этого чата. MAX_HISTORY по умолчанию 50 (из message.py)
            cfg = await load_chat_config(target_chat_id) or {}
            limit = int(cfg.get("history_limit", 50)) 
            
            # await append_message(target_chat_id, "assistant", text_to_send, limit)

            await update.message.reply_text(
                f"✅ Сообщение отправлено в чат **`{target_chat_id}`**:\n"
                f"**{text_to_send[:50]}...**\n"
                f"и сохранено в историю как ответ бота."
            )

        except Exception as e:
            logging.error(f"Error in /say command for chat {target_chat_id}: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка отправки: {e}")
    
    async def get_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        bot_username = context.bot_data.get("bot_username", "bot")

        cfg = await load_chat_config(chat_id) or {}
        prompt = cfg.get("system_prompt")
        if not prompt:
            prompt = self.messenger.get_current_system_prompt(chat_id, bot_username)
        await update.message.reply_text(prompt)

    async def reset_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        self.messenger.set_system_prompt(chat_id, None)
        await save_chat_config(chat_id, system_prompt=None)
        await clear_history(chat_id)

        context.chat_data["history"] = []
        await update.message.reply_text("Команда выполнена.")

    async def clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        await clear_history(chat_id)
        context.chat_data["history"] = []
        await update.message.reply_text("История сообщений очищена.")

    async def mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        if not context.args:
            await update.message.reply_text("Укажите длительность в минутах: /mute <минуты>")
            return
        try:
            minutes = int(context.args[0])
            if minutes <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Некорректное число. Укажите положительное целое.")
            return

        until = datetime.utcnow() + timedelta(minutes=minutes)
        await save_chat_config(chat_id, muted_until=until)
        context.chat_data["muted_until"] = until
        await update.message.reply_text(
            f"Бот замьючен на {minutes} мин. До {until.strftime('%H:%M:%S %d.%m.%Y UTC')}"
        )

    async def unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        await save_chat_config(chat_id, muted_until=None)
        context.chat_data.pop("muted_until", None)
        await update.message.reply_text("Бот размьючен.")

    async def set_history_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        if not context.args:
            await update.message.reply_text("Укажите число: /set_history_limit <число>")
            return
        try:
            limit = int(context.args[0])
            if limit <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Некорректное число. Укажите положительное целое.")
            return

        await save_chat_config(chat_id, history_limit=limit)
        # Примечание: история больше не обрезается при сохранении, все сообщения сохраняются
        # Для промпта всегда используется PROMPT_HISTORY_LIMIT (35 сообщений)
        from db.chat_repo import PROMPT_HISTORY_LIMIT
        hist = await load_history(chat_id, PROMPT_HISTORY_LIMIT)
        context.chat_data["history"] = hist
        await update.message.reply_text(
            f"Лимит истории установлен: {limit} (для отображения). "
            f"В промпт всегда загружается {PROMPT_HISTORY_LIMIT} последних сообщений."
        )

    async def set_autopost_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        if not context.args:
            await update.message.reply_text("Укажите число секунд: /set_autopost_interval <сек>")
            return
        try:
            interval = int(context.args[0])
            if interval <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Некорректное число. Укажите положительное целое.")
            return

        await save_chat_config(chat_id, autopost_interval=interval)
        context.chat_data["autopost_interval"] = interval

        if context.chat_data.get("autopost_enabled", True):
            # Перезапустить задачу
            job = context.chat_data.get("background_job")
            if job is not None:
                try:
                    job.schedule_removal()
                except Exception:
                    logging.exception("Failed to remove previous background job")
                context.chat_data.pop("background_job", None)
            job = context.job_queue.run_repeating(
                self.messenger.check_scheduled,
                interval=interval,
                first=interval,
                chat_id=chat_id,
            )
            context.chat_data["background_job"] = job
        await update.message.reply_text(f"Интервал автосообщений: {interval} сек")

    async def enable_autopost(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        await save_chat_config(chat_id, autopost_enabled=True)
        context.chat_data["autopost_enabled"] = True

        interval = context.chat_data.get("autopost_interval", 3600)
        job = context.chat_data.get("background_job")
        if job is None:
            job = context.job_queue.run_repeating(
                self.messenger.check_scheduled,
                interval=interval,
                first=interval,
                chat_id=chat_id,
            )
            context.chat_data["background_job"] = job
        await update.message.reply_text("Автосообщения включены.")

    async def disable_autopost(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        await save_chat_config(chat_id, autopost_enabled=False)
        context.chat_data["autopost_enabled"] = False

        job = context.chat_data.get("background_job")
        if job is not None:
            try:
                job.schedule_removal()
            except Exception:
                logging.exception("Failed to remove background job")
            context.chat_data.pop("background_job", None)
        await update.message.reply_text("Автосообщения выключены.")

    async def enable_reactions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        await save_chat_config(chat_id, reactions_enabled=True)
        context.chat_data["reactions_enabled"] = True
        await update.message.reply_text("Реакции включены.")

    async def disable_reactions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await is_admin(update, context):
            return
        chat_id = update.effective_chat.id
        await save_chat_config(chat_id, reactions_enabled=False)
        context.chat_data["reactions_enabled"] = False
        await update.message.reply_text("Реакции выключены.")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        bot_username = context.bot_data.get("bot_username", "bot")

        cfg = await load_chat_config(chat_id) or {}
        prompt = cfg.get("system_prompt") or self.messenger.get_current_system_prompt(chat_id, bot_username)
        is_custom = cfg.get("system_prompt") is not None

        from db.chat_repo import PROMPT_HISTORY_LIMIT
        history_limit = int(cfg.get("history_limit", getattr(self.messenger, "MAX_HISTORY", 50)))
        # Используем PROMPT_HISTORY_LIMIT для загрузки истории (всегда 35 сообщений для промпта)
        history = await load_history(chat_id, PROMPT_HISTORY_LIMIT)

        autopost_enabled = bool(cfg.get("autopost_enabled", True))
        autopost_interval = int(cfg.get("autopost_interval", 3600))
        reactions_enabled = bool(cfg.get("reactions_enabled", True))
        muted_until = cfg.get("muted_until")
        now = datetime.utcnow()
        muted_str = (
            f"до {muted_until.strftime('%H:%M:%S %d.%m.%Y UTC')}"
            if muted_until and muted_until > now else "нет"
        )
        parts = [
            f"Промпт: {'кастомный' if is_custom else 'по умолчанию'}",
            f"Длина промпта: {len(prompt)} символов",
            f"История: {len(history)}/{history_limit}",
            f"Автосообщения: {'включены' if autopost_enabled else 'выключены'} (интервал {autopost_interval} сек)",
            f"Реакции: {'включены' if reactions_enabled else 'выключены'}",
            f"Мьют: {muted_str}",
        ]
        await update.message.reply_text("\n".join(parts))

    async def metrics(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Метрики хранятся в chat_data['scoring'] и периодически синкаются в БД (см. message.py).
        scoring = context.chat_data.get("scoring", {})
        message_counter = scoring.get("message_counter", 0)
        user_streaks = scoring.get("user_streaks", {})
        responded = scoring.get("responded", set())
        reply_counts = scoring.get("reply_counts", {})
        reaction_counts = scoring.get("reaction_counts", {})

        top_streak = 0
        if user_streaks:
            try:
                top_streak = max(v[0] for v in user_streaks.values())
            except Exception:
                top_streak = 0

        lines = [
            f"Всего сообщений: {message_counter}",
            f"Уникальных пользователей со стриком: {len(user_streaks)}",
            f"Максимальный стрик: {top_streak}",
            f"Ответов на сообщения (уникальные): {len(responded)}",
            f"Сообщений с ответами других пользователей: {len(reply_counts)}",
            f"Сообщений с реакциями: {len(reaction_counts)}",
        ]
        await update.message.reply_text("\n".join(lines))

    async def send_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = " ".join(context.args).strip()
        if not query:
            await update.message.reply_text("Укажите текст: /send_test <текст>")
            return
        bot_username = context.bot_data.get("bot_username", "bot")
        chat_id = update.effective_chat.id
        cfg = await load_chat_config(chat_id) or {}
        sys_prompt = cfg.get("system_prompt")
        try:
            reply = self.messenger._call_deepseek([{"role": "user", "content": query}], bot_username, chat_id, system_prompt=sys_prompt).strip()
        except Exception:
            logging.exception("DeepSeek test call failed")
            await update.message.reply_text("Ошибка при обращении к DeepSeek")
            return
        await update.message.reply_text(reply or "(пустой ответ)")

    async def holiday_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = datetime.utcnow().date()
        holidays = HolidayEvaluator().evaluate()
        if not holidays:
            await update.message.reply_text(f"Сегодня {today.strftime('%d.%m.%Y')} праздников нет.")
            return
        bot_username = context.bot_data.get("bot_username", "bot")
        holiday_names = ", ".join(holidays)
        prompt = f"Сегодня {today.strftime('%d.%m.%Y')} {holiday_names}. Поздравь чат от своего имени, сохраняя стиль."
        chat_id = update.effective_chat.id
        cfg = await load_chat_config(chat_id) or {}
        sys_prompt = cfg.get("system_prompt")
        try:
            reply = self.messenger._call_deepseek([{"role": "user", "content": prompt}], bot_username, chat_id, system_prompt=sys_prompt).strip()
        except Exception:
            logging.exception("DeepSeek holiday_check call failed")
            await update.message.reply_text("Ошибка DeepSeek при генерации поздравления")
            return
        await update.message.reply_text(
            f"Праздники: {holiday_names}\n\nПример ответа бота:\n{reply}"
        )

    # --- Owner commands ---
    async def add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Добавить администратора (только для owner)"""
        if not await is_owner(update, context):
            return
        
        if not context.args:
            await update.message.reply_text("❌ Формат: /add_admin <user_id>")
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя. ID должен быть числом.")
            return
        
        if target_user_id == update.effective_user.id:
            await update.message.reply_text("❌ Вы не можете добавить самого себя.")
            return
        
        username = update.effective_user.username
        success = await set_user_role(target_user_id, username, "admin")
        if success:
            await update.message.reply_text(f"✅ Пользователь {target_user_id} добавлен как администратор.")
        else:
            await update.message.reply_text("❌ Ошибка при добавлении администратора.")
    
    async def remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Удалить администратора (только для owner)"""
        if not await is_owner(update, context):
            return
        
        if not context.args:
            await update.message.reply_text("❌ Формат: /remove_admin <user_id>")
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя. ID должен быть числом.")
            return
        
        if target_user_id == update.effective_user.id:
            await update.message.reply_text("❌ Вы не можете удалить самого себя.")
            return
        
        success = await remove_user_role(target_user_id)
        if success:
            await update.message.reply_text(f"✅ Пользователь {target_user_id} удален из администраторов.")
        else:
            await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден среди администраторов.")
    
    async def list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать список всех администраторов (только для owner)"""
        if not await is_owner(update, context):
            return
        
        admins = await get_all_admins()
        if not admins:
            await update.message.reply_text("📋 Администраторы не найдены.")
            return
        
        lines = ["📋 Список администраторов:\n"]
        for admin in admins:
            role_emoji = "👑" if admin["role"] == "owner" else "🔧"
            username = admin.get("username") or "без username"
            lines.append(f"{role_emoji} {admin['role']}: {admin['user_id']} (@{username})")
        
        await update.message.reply_text("\n".join(lines))
    
    async def set_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Передать права владельца другому пользователю (только для текущего owner)"""
        if not await is_owner(update, context):
            return
        
        if not context.args:
            await update.message.reply_text("❌ Формат: /set_owner <user_id>")
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя. ID должен быть числом.")
            return
        
        if target_user_id == update.effective_user.id:
            await update.message.reply_text("❌ Вы уже являетесь владельцем.")
            return
        
        # Устанавливаем новому пользователю роль owner
        username = update.effective_user.username
        success = await set_user_role(target_user_id, username, "owner")
        if success:
            # Старому owner устанавливаем роль admin
            await set_user_role(update.effective_user.id, update.effective_user.username, "admin")
            await update.message.reply_text(
                f"✅ Права владельца переданы пользователю {target_user_id}.\n"
                f"Ваша роль изменена на администратора."
            )
        else:
            await update.message.reply_text("❌ Ошибка при передаче прав владельца.")
    
    # Utility used by Messenger for mention-based help
    async def handle_mention_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.help(update, context)
