"""
Payment status checker service for polling-based payment verification
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy import select
from aiogram import Bot
from app.services.yookassa import YookassaService
from app.database import get_db
from app.database.crud import mark_order_paid, get_user_balance
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class PaymentChecker:
    """Service for checking payment status via polling"""

    def __init__(self):
        self.yookassa = YookassaService()

    async def check_payment_status(self, payment_id: str) -> Optional[dict]:
        """
        Check payment status via YooKassa API

        Args:
            payment_id: YooKassa payment ID

        Returns:
            Dict with payment info or None if error
        """
        try:
            payment_info = self.yookassa.get_payment_status(payment_id)
            logger.info(f"Payment {payment_id} status: {payment_info['status']}")
            return payment_info
        except Exception as e:
            logger.error(f"Failed to check payment status for {payment_id}: {str(e)}")
            return None

    async def process_successful_payment(
        self,
        payment_id: str,
        bot: Bot,
        user_telegram_id: int
    ) -> bool:
        """
        Process successful payment: mark as paid and send notifications

        Args:
            payment_id: YooKassa payment ID
            bot: Bot instance for sending notifications
            user_telegram_id: User's telegram ID

        Returns:
            True if payment was processed successfully
        """
        db = get_db()
        async with db.get_session() as session:
            # Mark order as paid
            order = await mark_order_paid(session, payment_id)

            if not order:
                logger.info(f"Order for payment_id {payment_id} not found or already paid - skipping duplicate processing")
                return False

            logger.info(f"Order {order.id} marked as paid successfully")

            # Load related data for notifications
            from app.database.models import Order
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            result = await session.execute(
                select(Order)
                .where(Order.id == order.id)
                .options(selectinload(Order.user), selectinload(Order.package))
            )
            order = result.scalar_one_or_none()

            if not order:
                return False

            # Get user's new balance
            new_balance = await get_user_balance(session, user_telegram_id)

            # Notify user
            try:
                await NotificationService.notify_user_payment_success(
                    bot=bot,
                    telegram_id=user_telegram_id,
                    package_name=order.package.name,
                    images_count=order.package.images_count,
                    amount=float(order.amount),
                    new_balance=new_balance
                )
            except Exception as e:
                logger.error(f"Failed to send user notification: {str(e)}")

            # Notify admins
            try:
                await NotificationService.notify_admins_new_payment(
                    bot=bot,
                    user_telegram_id=user_telegram_id,
                    username=order.user.username,
                    package_name=order.package.name,
                    images_count=order.package.images_count,
                    amount=float(order.amount),
                    order_id=order.id
                )
            except Exception as e:
                logger.error(f"Failed to send admin notifications: {str(e)}")

            # Notify referrer if this user was referred
            if order.user.referred_by_id:
                from app.config import settings

                # Calculate reward
                referral_reward = int(order.package.images_count * settings.REFERRAL_REWARD_PURCHASE_PERCENT / 100)

                if referral_reward > 0:
                    try:
                        # Get referrer from database
                        from app.database.models import User
                        referrer_result = await session.execute(
                            select(User).where(User.id == order.user.referred_by_id)
                        )
                        referrer = referrer_result.scalar_one_or_none()

                        if referrer:
                            await bot.send_message(
                                referrer.telegram_id,
                                f"💰 <b>Вознаграждение от реферальной программы!</b>\n\n"
                                f"Ваш реферал совершил покупку!\n"
                                f"🎁 Вам начислено <b>{referral_reward}</b> бесплатных обработок!\n\n"
                                f"📦 Пакет реферала: {order.package.name} ({order.package.images_count} изображений)\n"
                                f"💵 Ваша доля: {settings.REFERRAL_REWARD_PURCHASE_PERCENT}%\n\n"
                                f"Продолжайте делиться ссылкой и получайте еще больше! 🚀",
                                parse_mode="HTML"
                            )
                            logger.info(f"Referrer {referrer.telegram_id} notified about reward: {referral_reward} images")
                    except Exception as e:
                        logger.error(f"Failed to notify referrer: {str(e)}")

            return True

    async def auto_check_payment(
        self,
        payment_id: str,
        bot: Bot,
        user_telegram_id: int,
        max_duration_minutes: int = 10
    ) -> Optional[str]:
        """
        Automatically check payment status with intervals:
        - After 1 minute
        - After 30 seconds (1.5 min total)
        - After 1 minute (2.5 min total)
        - Then every 30 seconds until max_duration_minutes

        Args:
            payment_id: YooKassa payment ID
            bot: Bot instance
            user_telegram_id: User's telegram ID
            max_duration_minutes: Maximum duration to check in minutes

        Returns:
            Payment status ('succeeded', 'canceled', 'pending', or None if timeout)
        """
        check_intervals = [60, 30, 60]  # First checks: 1min, 30sec, 1min
        remaining_checks_interval = 30  # Then every 30 seconds

        start_time = datetime.utcnow()
        max_duration = timedelta(minutes=max_duration_minutes)

        # Perform scheduled checks
        for interval in check_intervals:
            await asyncio.sleep(interval)

            # Check if max duration exceeded
            if datetime.utcnow() - start_time > max_duration:
                logger.info(f"Payment check timeout for {payment_id}")
                return None

            payment_info = await self.check_payment_status(payment_id)

            if not payment_info:
                continue

            status = payment_info['status']

            if status == 'succeeded' and payment_info.get('paid'):
                # Payment successful!
                await self.process_successful_payment(payment_id, bot, user_telegram_id)
                return 'succeeded'

            elif status == 'canceled':
                logger.info(f"Payment {payment_id} was canceled")
                return 'canceled'

        # Continue checking every 30 seconds until timeout
        while datetime.utcnow() - start_time < max_duration:
            await asyncio.sleep(remaining_checks_interval)

            payment_info = await self.check_payment_status(payment_id)

            if not payment_info:
                continue

            status = payment_info['status']

            if status == 'succeeded' and payment_info.get('paid'):
                await self.process_successful_payment(payment_id, bot, user_telegram_id)
                return 'succeeded'

            elif status == 'canceled':
                return 'canceled'

        # Timeout reached
        logger.info(f"Payment check timeout for {payment_id} after {max_duration_minutes} minutes")
        return None
