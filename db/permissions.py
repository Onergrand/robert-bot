# permissions.py
"""
Система прав доступа для бота.
Роли: owner > admin > user
"""
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from db.chat_repo import get_user_role

# Роли в порядке приоритета
ROLES = {"owner": 3, "admin": 2, "user": 1}


def get_role_level(role: str) -> int:
    """Получить числовой уровень роли"""
    return ROLES.get(role, 0)


async def check_permission(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    required_role: str = "user"
) -> bool:
    """
    Проверить, имеет ли пользователь необходимую роль.
    required_role: 'owner', 'admin' или 'user'
    """
    from db.chat_repo import ensure_user
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    # Убедимся, что пользователь существует в БД
    await ensure_user(user_id, username)
    
    user_role = await get_user_role(user_id)
    
    required_level = get_role_level(required_role)
    user_level = get_role_level(user_role)
    
    return user_level >= required_level


async def require_role(required_role: str = "user"):
    """
    Декоратор для проверки прав доступа к команде.
    Использование:
        @require_role("admin")
        async def my_command(update, context):
            ...
    """
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not await check_permission(update, context, required_role):
                role_name = {"owner": "владельца", "admin": "администратора", "user": "пользователя"}.get(required_role, required_role)
                await update.message.reply_text(
                    f"⛔️ У вас нет прав на эту команду. Требуется роль {role_name}."
                )
                return
            return await func(update, context)
        return wrapper
    return decorator


async def is_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить, является ли пользователь owner"""
    return await check_permission(update, context, "owner")


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить, является ли пользователь admin или owner"""
    return await check_permission(update, context, "admin")


async def is_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверить, является ли пользователь хотя бы user (всегда True)"""
    return await check_permission(update, context, "user")

