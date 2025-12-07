import logging
import sys
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.config import settings
from app.handlers import get_routers
from app.database import init_db
from app.middlewares import DbSessionMiddleware

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL), stream=sys.stdout)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    """Startup hook"""
    logger.info("Initializing database...")
    init_db(settings.database_url)
    
    logger.info(f"Setting webhook to {settings.WEBHOOK_URL}...")
    await bot.set_webhook(
        f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}",
        drop_pending_updates=True
    )
    logger.info("Webhook set.")

async def on_shutdown(bot: Bot):
    """Shutdown hook"""
    logger.info("Removing webhook...")
    await bot.delete_webhook()
    logger.info("Webhook removed.")

def main():
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

    # Startup/Shutdown events
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Create web app
    app = web.Application()
    
    # Create request handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    
    # Register webhook handler
    webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
    
    # Mount dispatcher and bot to app
    setup_application(app, dp, bot=bot)

    # Start server
    logger.info(f"Starting web server on port {settings.PORT}")
    web.run_app(app, host="0.0.0.0", port=settings.PORT)

if __name__ == "__main__":
    main()
