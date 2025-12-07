"""
Notification service for sending payment notifications to users and admins
"""
import logging
from typing import Optional
from aiogram import Bot

from app.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via Telegram"""

    @staticmethod
    async def notify_user_payment_success(
        bot: Bot,
        telegram_id: int,
        package_name: str,
        images_count: int,
        amount: float,
        new_balance: dict
    ):
        """
        Notify user about successful payment

        Args:
            bot: Bot instance
            telegram_id: User's telegram ID
            package_name: Name of purchased package
            images_count: Number of images in package
            amount: Payment amount
            new_balance: User's new balance dict with keys: free, paid, total
        """
        try:
            text = (
                "✅ <b>Оплата прошла успешно!</b>\n\n"
                f"📦 Пакет: {package_name}\n"
                f"💎 Изображений: {images_count}\n"
                f"💰 Сумма: {amount:.2f}₽\n\n"
                "📊 <b>Ваш новый баланс:</b>\n"
                f"🎁 Бесплатных: {new_balance['free']}\n"
                f"💎 Оплаченных: {new_balance['paid']}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📸 Всего доступно: {new_balance['total']}\n\n"
                "Спасибо за покупку! Можете приступать к обработке изображений."
            )

            await bot.send_message(telegram_id, text, parse_mode="HTML")
            logger.info(f"Payment success notification sent to user {telegram_id}")

        except Exception as e:
            logger.error(f"Failed to send payment notification to user {telegram_id}: {str(e)}")

    @staticmethod
    async def notify_admins_new_payment(
        bot: Bot,
        user_telegram_id: int,
        username: Optional[str],
        package_name: str,
        images_count: int,
        amount: float,
        order_id: int
    ):
        """
        Notify admins about new payment

        Args:
            bot: Bot instance
            user_telegram_id: User's telegram ID
            username: User's username
            package_name: Name of purchased package
            images_count: Number of images in package
            amount: Payment amount
            order_id: Order ID
        """
        try:
            text = (
                "💰 <b>Новая покупка!</b>\n\n"
                f"👤 Пользователь: @{username or 'Unknown'} ({user_telegram_id})\n"
                f"📦 Пакет: {package_name}\n"
                f"💎 Изображений: {images_count}\n"
                f"💰 Сумма: {amount:.2f}₽\n"
                f"📝 Заказ: #{order_id}"
            )

            # Send to all admins
            for admin_id in settings.admin_ids_list:
                try:
                    await bot.send_message(admin_id, text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {str(e)}")

            logger.info(f"Payment notification sent to admins for order {order_id}")

        except Exception as e:
            logger.error(f"Failed to send payment notification to admins: {str(e)}")

    @staticmethod
    async def notify_user_payment_failed(
        bot: Bot,
        telegram_id: int,
        package_name: str,
        error_message: Optional[str] = None
    ):
        """
        Notify user about failed payment

        Args:
            bot: Bot instance
            telegram_id: User's telegram ID
            package_name: Name of package
            error_message: Optional error message
        """
        try:
            text = (
                "❌ <b>Оплата не прошла</b>\n\n"
                f"📦 Пакет: {package_name}\n\n"
            )

            if error_message:
                text += f"Причина: {error_message}\n\n"

            text += (
                "Попробуйте еще раз или обратитесь в поддержку, "
                "если проблема повторяется."
            )

            await bot.send_message(telegram_id, text, parse_mode="HTML")
            logger.info(f"Payment failed notification sent to user {telegram_id}")

        except Exception as e:
            logger.error(f"Failed to send payment failed notification to user {telegram_id}: {str(e)}")

    @staticmethod
    async def notify_user_refund(
        bot: Bot,
        telegram_id: int,
        amount: float,
        images_used: int,
        images_total: int
    ):
        """
        Notify user about successful refund

        Args:
            bot: Bot instance
            telegram_id: User's telegram ID
            amount: Refund amount
            images_used: Number of images used
            images_total: Total images in package
        """
        try:
            text = (
                "💵 <b>Возврат оформлен</b>\n\n"
                f"💰 Сумма возврата: {amount:.2f}₽\n"
                f"📸 Использовано изображений: {images_used}/{images_total}\n\n"
                "Средства будут возвращены на вашу карту в течение 3-5 рабочих дней."
            )

            await bot.send_message(telegram_id, text, parse_mode="HTML")
            logger.info(f"Refund notification sent to user {telegram_id}")

        except Exception as e:
            logger.error(f"Failed to send refund notification to user {telegram_id}: {str(e)}")

    @staticmethod
    async def notify_admins_new_support_request(
        bot: Bot,
        ticket_id: int,
        user_telegram_id: int,
        username: Optional[str],
        message: str
    ):
        """
        Notify admins about new support request

        Args:
            bot: Bot instance
            ticket_id: Support ticket ID
            user_telegram_id: User telegram ID
            username: User username
            message: Support message
        """
        try:
            # Truncate message if too long
            display_message = message[:200] + "..." if len(message) > 200 else message

            text = (
                "💬 <b>Новое обращение в поддержку!</b>\n\n"
                f"🆔 Тикет: #{ticket_id}\n"
                f"👤 Пользователь: @{username or 'Unknown'} (ID: {user_telegram_id})\n\n"
                f"📝 Сообщение:\n{display_message}\n\n"
                f"Используйте /support_reply {ticket_id} для ответа"
            )

            # Send to all admins
            for admin_id in settings.admin_ids_list:
                try:
                    await bot.send_message(admin_id, text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {str(e)}")

            logger.info(f"Support request notification sent to admins for ticket {ticket_id}")

        except Exception as e:
            logger.error(f"Failed to send support notification to admins: {str(e)}")

    @staticmethod
    async def notify_admins_processing_error(
        bot: Bot,
        user_telegram_id: int,
        username: Optional[str],
        service_name: str,
        error_message: str
    ):
        """
        Notify admins about an image processing error.

        Args:
            bot: Bot instance
            user_telegram_id: User's telegram ID
            username: User's username
            service_name: Name of the service that failed (e.g., OpenRouter)
            error_message: The detailed error message
        """
        try:
            # Truncate error message if it's too long
            display_error = error_message[:1000] + "..." if len(error_message) > 1000 else error_message

            text = (
                "❌ <b>Ошибка обработки изображения!</b>\n\n"
                "Бот столкнулся с проблемой при обработке изображения для пользователя.\n\n"
                f"👤 <b>Пользователь:</b> @{username or 'Unknown'} ({user_telegram_id})\n"
                f"🔧 <b>Сервис:</b> {service_name}\n\n"
                "📋 <b>Сообщение об ошибке:</b>\n"
                f"<code>{display_error}</code>\n\n"
                "<i>Это может быть связано с проблемами API (например, закончились кредиты) или недоступностью сервиса. "
                "Пожалуйста, проверьте логи и состояние сервиса.</i>"
            )

            for admin_id in settings.admin_ids_list:
                try:
                    await bot.send_message(admin_id, text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id} about processing error: {str(e)}")

            logger.info(f"Processing error notification sent to admins for user {user_telegram_id}")

        except Exception as e:
            logger.error(f"Failed to send processing error notification to admins: {str(e)}")

    @staticmethod
    async def notify_user_support_reply(
        bot: Bot,
        telegram_id: int,
        ticket_id: int,
        admin_username: Optional[str],
        message: str
    ):
        """
        Notify user about admin reply to their support request

        Args:
            bot: Bot instance
            telegram_id: User telegram ID
            ticket_id: Support ticket ID
            admin_username: Admin username
            message: Admin's reply message
        """
        try:
            text = (
                "💬 <b>Ответ от поддержки</b>\n\n"
                f"🆔 Тикет: #{ticket_id}\n"
                f"👨‍💼 Администратор: @{admin_username or 'Support'}\n\n"
                f"📝 Ответ:\n{message}\n\n"
                "Если у вас остались вопросы, отправьте новое сообщение через меню поддержки."
            )

            await bot.send_message(telegram_id, text, parse_mode="HTML")
            logger.info(f"Support reply notification sent to user {telegram_id}")

        except Exception as e:
            logger.error(f"Failed to send support reply notification to user {telegram_id}: {str(e)}")
