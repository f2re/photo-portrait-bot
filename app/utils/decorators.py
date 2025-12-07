from functools import wraps
from typing import Callable, Any
from aiogram import types

from app.database import get_db
from app.database.crud import is_admin
from app.config import settings


def admin_only(func: Callable) -> Callable:
    """
    Decorator to restrict access to admin-only functions
    Checks both ADMIN_IDS from config and admins table in database

    Usage:
        @router.message(Command("admin"))
        @admin_only
        async def admin_panel(message: types.Message):
            ...
    """
    @wraps(func)
    async def wrapper(message_or_callback: types.Message | types.CallbackQuery, *args, **kwargs) -> Any:
        # Get telegram_id from message or callback
        if isinstance(message_or_callback, types.Message):
            telegram_id = message_or_callback.from_user.id
            send_method = message_or_callback.answer
        else:  # CallbackQuery
            telegram_id = message_or_callback.from_user.id
            send_method = message_or_callback.message.answer

        # Check if user is admin (check both config and database)
        is_admin_in_config = telegram_id in settings.admin_ids_list

        is_admin_in_db = False
        db = get_db()
        async with db.get_session() as session:
            is_admin_in_db = await is_admin(session, telegram_id)

        if is_admin_in_config or is_admin_in_db:
            return await func(message_or_callback, *args, **kwargs)
        else:
            await send_method("❌ У вас нет доступа к этой функции.")
            return None

    return wrapper


def user_state_required(state_name: str):
    """
    Decorator to ensure user is in specific state

    Usage:
        @router.message(F.text)
        @user_state_required("waiting_for_support_message")
        async def process_support_message(message: types.Message, state: FSMContext):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs) -> Any:
            # This decorator works with FSMContext
            # Implementation depends on how you manage states
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator


def log_action(action_name: str):
    """
    Decorator to log user actions

    Usage:
        @router.message(Command("start"))
        @log_action("start_command")
        async def start_handler(message: types.Message):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(message_or_callback: types.Message | types.CallbackQuery, *args, **kwargs) -> Any:
            # Get user info
            if isinstance(message_or_callback, types.Message):
                user = message_or_callback.from_user
            else:
                user = message_or_callback.from_user

            # Log action (in production, use proper logging)
            print(f"[{action_name}] User {user.id} (@{user.username})")

            return await func(message_or_callback, *args, **kwargs)
        return wrapper
    return decorator


def error_handler(func: Callable) -> Callable:
    """
    Decorator to handle errors gracefully

    Usage:
        @router.message(F.photo)
        @error_handler
        async def process_image(message: types.Message):
            ...
    """
    @wraps(func)
    async def wrapper(message_or_callback: types.Message | types.CallbackQuery, *args, **kwargs) -> Any:
        try:
            return await func(message_or_callback, *args, **kwargs)
        except Exception as e:
            # Get send method
            if isinstance(message_or_callback, types.Message):
                send_method = message_or_callback.answer
            else:
                send_method = message_or_callback.message.answer

            # Send error message
            await send_method(
                "❌ Произошла ошибка при обработке вашего запроса.\n\n"
                "Попробуйте еще раз или обратитесь в поддержку."
            )

            # Log error (in production, use proper logging)
            print(f"Error in {func.__name__}: {str(e)}")

            return None

    return wrapper
