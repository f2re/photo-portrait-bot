"""
Webhook server for YooKassa payment notifications
This should be run as a separate service alongside the bot
"""
import logging
from aiohttp import web
from typing import Optional

from app.database import get_db, init_db
from app.config import settings

logger = logging.getLogger(__name__)


async def handle_yookassa_webhook(request: web.Request) -> web.Response:
    """
    Handle YooKassa webhook notification
    This is called when payment status changes

    YooKassa sends POST request with JSON body:
    {
        "type": "notification",
        "event": "payment.succeeded",
        "object": { ... payment data ... }
    }
    """
    try:
        # Get JSON body
        notification_data = await request.json()

        logger.info(f"Received YooKassa webhook: {notification_data.get('event')}")

        # Import here to avoid circular dependencies
        from app.handlers.payment import process_payment_webhook

        # Get bot instance from app state
        bot = request.app.get('bot')

        # Process payment webhook
        success = await process_payment_webhook(notification_data, bot)

        if success:
            # YooKassa requires HTTP 200 response to confirm receipt
            return web.Response(status=200)
        else:
            # Return 200 anyway to prevent retries for invalid notifications
            logger.warning("Webhook processing returned False, but returning 200 to YooKassa")
            return web.Response(status=200)

    except Exception as e:
        logger.error(f"Error processing YooKassa webhook: {str(e)}", exc_info=True)
        # Still return 200 to prevent YooKassa from retrying
        return web.Response(status=200)


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint"""
    return web.Response(text="OK")


def create_app(bot=None) -> web.Application:
    """
    Create aiohttp application for webhook server

    Args:
        bot: Optional Bot instance for sending notifications
    """
    app = web.Application()

    # Store bot instance in app state for use in handlers
    if bot:
        app['bot'] = bot

    # Add routes
    app.router.add_post('/yookassa/webhook', handle_yookassa_webhook)
    app.router.add_get('/health', health_check)

    return app


async def run_webhook_server(host: str = '0.0.0.0', port: int = 8080, bot=None):
    """
    Run webhook server

    Args:
        host: Server host
        port: Server port
        bot: Optional Bot instance for sending notifications
    """
    # Initialize database
    logger.info("Initializing database for webhook server...")
    init_db(settings.database_url)

    app = create_app(bot)

    logger.info(f"Starting webhook server on {host}:{port}")
    logger.info(f"YooKassa webhook URL: http://{host}:{port}/yookassa/webhook")
    logger.info("⚠️  Configure this URL in YooKassa dashboard: https://yookassa.ru/my/merchant/integration/http-notifications")

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info("Webhook server started successfully")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_webhook_server())
    loop.run_forever()
