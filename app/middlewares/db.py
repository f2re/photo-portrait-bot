from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from app.database import get_db

class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        db = get_db()
        if db is None:
            # Should not happen if init_db is called
            raise RuntimeError("Database is not initialized")
            
        async with db.get_session() as session:
            data["session"] = session
            return await handler(event, data)
