import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import init_db
from app.handlers import user, admin, payment, support, batch_processing
from app.middlewares import DbSessionMiddleware
from app.services.yandex_metrika import periodic_metrika_upload

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main bot function"""
    # Initialize database
    logger.info("Initializing database...")
    db = init_db(settings.database_url)

    # Create tables if they don't exist
    try:
        await db.create_tables()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return

    # Synchronize packages from config to database
    try:
        from app.database.crud import sync_packages_from_config
        async with db.get_session() as session:
            await sync_packages_from_config(session, settings.packages_config)
        logger.info("Packages synchronized successfully")
    except Exception as e:
        logger.error(f"Failed to synchronize packages: {e}")
        # Don't return - continue even if packages sync fails

    # Initialize bot and dispatcher
    bot = Bot(token=settings.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register middlewares
    dp.update.middleware(DbSessionMiddleware())

    # Register routers
    # IMPORTANT: batch_processing must be registered BEFORE user router
    # to handle media groups (albums) before single images
    dp.include_router(batch_processing.router)
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(payment.router)
    dp.include_router(support.router)

    # Start background task for periodic Metrika upload
    metrika_upload_task = None
    if settings.is_metrika_enabled:
        metrika_upload_task = asyncio.create_task(
            periodic_metrika_upload(db.get_session)
        )
        logger.info(
            f"Metrika upload task started. "
            f"Events will be uploaded every {settings.METRIKA_UPLOAD_INTERVAL}s"
        )
    else:
        logger.info("Metrika upload task skipped (Metrika is disabled)")

    logger.info("Bot started successfully")

    try:
        # Start polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Cancel background task on shutdown
        if metrika_upload_task:
            metrika_upload_task.cancel()
            try:
                await metrika_upload_task
            except asyncio.CancelledError:
                logger.info("Metrika upload task cancelled")
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped with error: {e}")
