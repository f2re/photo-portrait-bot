import logging
import sys
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.handlers import get_routers
from app.database import init_db
from app.middlewares import DbSessionMiddleware

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL), stream=sys.stdout)
logger = logging.getLogger(__name__)

async def main():
    """Main entry point"""
    logger.info("Starting bot...")
    
    # Initialize Bot and Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Register middlewares
    dp.update.middleware(DbSessionMiddleware())

    # Include routers
    dp.include_routers(*get_routers())

    # Initialize database
    logger.info("Initializing database...")
    database = init_db(settings.database_url)

    # Delete webhook to ensure polling works
    logger.info("Removing webhook and dropping pending updates...")
    await bot.delete_webhook(drop_pending_updates=True)

    # Start polling
    logger.info("Starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")