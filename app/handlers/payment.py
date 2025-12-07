from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db
from app.database.crud import (
    get_package_by_id, create_order, get_order_by_invoice_id,
    mark_order_paid, get_user_orders
)
from app.services.yookassa import YookassaService
from app.keyboards.user_kb import (
    get_payment_confirmation, get_back_keyboard,
    get_payment_contact_keyboard, get_contact_skip_keyboard,
    get_support_contact_keyboard
)
from app.utils.validators import validate_email, normalize_phone_number
from app.utils.validators import validate_package_id

router = Router()


class PaymentStates(StatesGroup):
    waiting_for_contact = State()  # Waiting for user to choose contact method
    waiting_for_email = State()  # Waiting for manual email input
    waiting_for_payment = State()


@router.callback_query(F.data.startswith("buy_package:"))
async def buy_package_handler(callback: CallbackQuery, state: FSMContext):
    """Handle package purchase request - start contact collection flow"""
    package_id = int(callback.data.split(":")[1])

    db = get_db()
    async with db.get_session() as session:
        package = await get_package_by_id(session, package_id)

        if not package:
            await callback.answer("❌ Пакет не найден", show_alert=True)
            return

        # Save package info to state for later use
        await state.update_data(
            package_id=package_id,
            package_name=package.name,
            images_count=package.images_count,
            price_rub=float(package.price_rub)
        )
        await state.set_state(PaymentStates.waiting_for_contact)

        # Ask for contact info in friendly way
        text = (
            f"💎 <b>Покупка пакета: {package.name}</b>\n\n"
            f"📦 Изображений: {package.images_count}\n"
            f"💰 Стоимость: {package.price_rub}₽\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📧 <b>Получение чека об оплате</b>\n\n"
            "Согласно законодательству РФ (54-ФЗ), для проведения оплаты необходимо предоставить email или номер телефона для получения чека.\n\n"
            "Выберите удобный способ получения чека:\n"
            "• 📱 Через СМС на телефон\n"
            "• 📧 Через Email\n\n"
            "🔒 <i>Ваши данные в безопасности и используются только для отправки чека в соответствии с законодательством.</i>"
        )

        # Edit the inline message and send keyboard as new message
        await callback.message.edit_text(
            text,
            parse_mode="HTML"
        )

        # Send keyboard with contact options
        await callback.message.answer(
            "Выберите удобный способ:",
            reply_markup=get_payment_contact_keyboard()
        )

    await callback.answer()


@router.message(PaymentStates.waiting_for_contact, F.contact)
async def process_contact_shared(message: Message, state: FSMContext):
    """Handle phone contact shared by user"""
    phone = message.contact.phone_number

    # Normalize phone number to YooKassa format
    normalized_phone = normalize_phone_number(phone)

    # Save to state and proceed to payment creation
    await state.update_data(user_phone=normalized_phone)
    await create_payment_with_contact(message, state)


@router.message(PaymentStates.waiting_for_contact, F.text == "📧 Через Email")
async def request_manual_email(message: Message, state: FSMContext):
    """Handle manual email input request"""
    await state.set_state(PaymentStates.waiting_for_email)

    await message.answer(
        "📧 <b>Введите ваш email</b>\n\n"
        "На этот адрес будет отправлен чек об оплате.\n\n"
        "Пример: example@mail.ru",
        parse_mode="HTML",
        reply_markup=get_contact_skip_keyboard()
    )


@router.message(PaymentStates.waiting_for_email, F.text)
async def process_manual_email(message: Message, state: FSMContext):
    """Handle manual email input and validation"""
    email = message.text.strip()

    # Validate email format
    if not validate_email(email):
        await message.answer(
            "❌ <b>Неверный формат email</b>\n\n"
            "Пожалуйста, введите корректный email адрес.\n\n"
            "Пример: example@mail.ru",
            parse_mode="HTML",
            reply_markup=get_contact_skip_keyboard()
        )
        return

    # Save to state and proceed to payment creation
    await state.update_data(user_email=email)
    await create_payment_with_contact(message, state)


async def create_payment_with_contact(message: Message, state: FSMContext):
    """
    Create payment with collected contact info

    Args:
        message: Message instance to reply to
        state: FSM context with package and contact data
    """
    import time
    import logging
    from aiogram.types import ReplyKeyboardRemove

    logger = logging.getLogger(__name__)
    data = await state.get_data()

    package_id = data.get("package_id")
    user_email = data.get("user_email")
    user_phone = data.get("user_phone")

    # Validate that contact info is provided (required by 54-ФЗ)
    if not user_email and not user_phone:
        logger.error(f"Payment creation attempted without contact info for user {message.from_user.id}")
        await message.answer(
            "❌ <b>Ошибка создания платежа</b>\n\n"
            "Для проведения оплаты необходимо предоставить email или номер телефона для получения чека (требование 54-ФЗ).\n\n"
            "Пожалуйста, выберите способ получения чека.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return

    db = get_db()
    async with db.get_session() as session:
        package = await get_package_by_id(session, package_id)

        if not package:
            await message.answer(
                "❌ Пакет не найден. Попробуйте еще раз.",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()
            return

        # Generate unique order ID for YooKassa metadata
        order_id_str = f"order_{message.from_user.id}_{int(time.time())}"

        # Create order in database (temporarily without payment_id)
        order = await create_order(
            session,
            telegram_id=message.from_user.id,
            package_id=package.id,
            invoice_id=order_id_str,
            amount=float(package.price_rub)
        )

        try:
            # Create payment via YooKassa with contact info
            yookassa = YookassaService()
            payment_info = yookassa.create_payment(
                amount=float(package.price_rub),
                description=f"Покупка пакета: {package.name}",
                order_id=order_id_str,
                user_email=user_email,
                user_phone=user_phone
            )

            # Update order with YooKassa payment_id
            order.invoice_id = payment_info["payment_id"]
            await session.commit()

            payment_url = payment_info["confirmation_url"]

            # Save payment data to state
            await state.update_data(
                order_id=order.id,
                payment_id=payment_info["payment_id"]
            )
            await state.set_state(PaymentStates.waiting_for_payment)

            # Prepare receipt info text
            receipt_info = ""
            if user_phone:
                receipt_info = f"\n📱 Чек будет отправлен по SMS на номер {user_phone}"
            elif user_email:
                receipt_info = f"\n✉️ Чек будет отправлен на email {user_email}"

            text = (
                f"✅ <b>Платёж создан</b>\n\n"
                f"💎 Пакет: {package.name}\n"
                f"📦 Изображений: {package.images_count}\n"
                f"💰 Стоимость: {package.price_rub}₽\n"
                f"{receipt_info}\n\n"
                "Нажмите кнопку ниже для перехода к оплате.\n\n"
                "После успешной оплаты изображения будут автоматически начислены на ваш баланс."
            )

            await message.answer(
                text,
                parse_mode="HTML",
                reply_markup=get_payment_confirmation(payment_url, payment_info["payment_id"])
            )

            # Remove custom keyboard
            await message.answer(
                "Для возврата в главное меню используйте /start",
                reply_markup=ReplyKeyboardRemove()
            )

            # Start automatic payment checking in background
            import asyncio
            from aiogram import Bot
            from app.services.payment_checker import PaymentChecker

            # Get bot instance from message
            bot = message.bot

            # Create background task for automatic payment checking
            asyncio.create_task(
                auto_check_and_notify(
                    payment_id=payment_info["payment_id"],
                    bot=bot,
                    user_telegram_id=message.from_user.id,
                    chat_id=message.chat.id
                )
            )

        except Exception as e:
            # Mark order as failed
            order.status = "failed"
            await session.commit()

            # Show user-friendly error message
            logger.error(f"Payment creation error: {str(e)}")

            error_text = (
                "❌ <b>Ошибка при создании платежа</b>\n\n"
                "К сожалению, не удалось создать платёж. "
                "Пожалуйста, попробуйте позже или обратитесь в поддержку.\n\n"
                f"Код ошибки: {type(e).__name__}"
            )

            await message.answer(
                error_text,
                parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_handler(callback: CallbackQuery, state: FSMContext):
    """Handle payment cancellation"""
    from aiogram.types import ReplyKeyboardRemove

    await state.clear()
    await callback.message.edit_text(
        "❌ Оплата отменена.\n\n"
        "Вы можете выбрать другой пакет или вернуться в главное меню.",
        reply_markup=get_back_keyboard()
    )

    # Remove custom keyboard if it was shown
    await callback.message.answer(
        "Используйте /start для возврата в главное меню.",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment_button_handler(callback: CallbackQuery, state: FSMContext):
    """Handle 'I paid' button click"""
    import asyncio
    from app.services.payment_checker import PaymentChecker

    payment_id = callback.data.split(":")[1]

    # Show processing message
    await callback.answer("🔄 Проверяем статус платежа...", show_alert=False)

    # Edit message to show checking status
    await callback.message.edit_text(
        "🔄 <b>Проверка платежа...</b>\n\n"
        "Пожалуйста, подождите. Мы проверяем статус вашего платежа в системе ЮКасса.\n\n"
        "Это может занять несколько секунд.",
        parse_mode="HTML"
    )

    # Check payment status
    checker = PaymentChecker()
    payment_info = await checker.check_payment_status(payment_id)

    if not payment_info:
        await callback.message.edit_text(
            "❌ <b>Ошибка проверки платежа</b>\n\n"
            "Не удалось получить статус платежа. Попробуйте еще раз через несколько секунд.\n\n"
            "Если проблема сохраняется, обратитесь в поддержку.",
            parse_mode="HTML",
            reply_markup=get_support_contact_keyboard()
        )
        return

    status = payment_info['status']

    if status == 'succeeded' and payment_info.get('paid'):
        # Payment successful! Process it
        success = await checker.process_successful_payment(
            payment_id=payment_id,
            bot=callback.bot,
            user_telegram_id=callback.from_user.id
        )

        if success:
            await state.clear()
            await callback.message.edit_text(
                "✅ <b>Оплата подтверждена!</b>\n\n"
                "Пакеты успешно зачислены на ваш баланс.\n"
                "Можете приступать к обработке изображений!",
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                "⚠️ <b>Платеж получен, но возникла проблема</b>\n\n"
                "Платеж успешно проведен, но произошла ошибка при зачислении пакета.\n\n"
                "Пожалуйста, обратитесь в поддержку с номером платежа:\n"
                f"<code>{payment_id}</code>",
                parse_mode="HTML",
                reply_markup=get_support_contact_keyboard()
            )

    elif status == 'pending' or status == 'waiting_for_capture':
        await callback.message.edit_text(
            "⏳ <b>Платеж в обработке</b>\n\n"
            "Ваш платеж еще обрабатывается. Обычно это занимает 1-3 минуты.\n\n"
            "✅ Мы автоматически проверяем статус платежа каждые 30 секунд в течение 10 минут.\n"
            "💬 Вы получите уведомление, как только платеж будет подтвержден.\n\n"
            "Или нажмите кнопку '✅ Я оплатил' еще раз через минуту для повторной проверки.",
            parse_mode="HTML",
            reply_markup=get_payment_confirmation(
                payment_url=f"https://yookassa.ru/checkout/payments/{payment_id}",
                payment_id=payment_id
            )
        )

    elif status == 'canceled':
        await state.clear()
        await callback.message.edit_text(
            "❌ <b>Платеж отменен</b>\n\n"
            "Ваш платеж был отменен.\n\n"
            "Если это произошло по ошибке, вы можете создать новый платеж.",
            parse_mode="HTML",
            reply_markup=get_back_keyboard()
        )

    else:
        await callback.message.edit_text(
            f"ℹ️ <b>Статус платежа: {status}</b>\n\n"
            "Платеж находится в необычном статусе.\n\n"
            "Если у вас возникли вопросы, обратитесь в поддержку с номером платежа:\n"
            f"<code>{payment_id}</code>",
            parse_mode="HTML",
            reply_markup=get_support_contact_keyboard()
        )


async def auto_check_and_notify(
    payment_id: str,
    bot,
    user_telegram_id: int,
    chat_id: int
):
    """
    Automatically check payment status and notify user when completed

    Args:
        payment_id: YooKassa payment ID
        bot: Bot instance
        user_telegram_id: User's telegram ID
        chat_id: Chat ID to send notifications
    """
    import asyncio
    import logging
    from app.services.payment_checker import PaymentChecker
    from app.keyboards.user_kb import get_support_contact_keyboard

    logger = logging.getLogger(__name__)

    logger.info(f"Starting auto-check for payment {payment_id}")

    checker = PaymentChecker()

    # Run automatic checking (returns final status or None if timeout)
    final_status = await checker.auto_check_payment(
        payment_id=payment_id,
        bot=bot,
        user_telegram_id=user_telegram_id,
        max_duration_minutes=10
    )

    # Send notification based on final status
    if final_status == 'succeeded':
        # User already notified by process_successful_payment
        logger.info(f"Payment {payment_id} auto-check completed: succeeded")

    elif final_status == 'canceled':
        try:
            await bot.send_message(
                chat_id,
                "❌ <b>Платеж отменен</b>\n\n"
                "Ваш платеж был отменен.\n\n"
                "Если это произошло по ошибке, вы можете создать новый платеж через меню 💎 Купить пакет.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send cancellation notification: {str(e)}")

    elif final_status is None:
        # Timeout - payment still pending after 10 minutes
        try:
            await bot.send_message(
                chat_id,
                "⏱ <b>Время ожидания истекло</b>\n\n"
                "Мы проверяли статус вашего платежа в течение 10 минут, но он все еще находится в обработке.\n\n"
                "🔹 Обычно платежи обрабатываются быстрее, но иногда это может занять больше времени.\n"
                "🔹 Как только платеж будет подтвержден, пакеты будут автоматически зачислены на ваш баланс.\n\n"
                "Если пакеты не зачислены в течение 1 часа, пожалуйста, обратитесь в поддержку с номером платежа:\n"
                f"<code>{payment_id}</code>",
                parse_mode="HTML",
                reply_markup=get_support_contact_keyboard()
            )
        except Exception as e:
            logger.error(f"Failed to send timeout notification: {str(e)}")

    logger.info(f"Auto-check for payment {payment_id} finished with status: {final_status}")


async def notify_payment_success(bot, order_id: int):
    """
    Send notifications after successful payment

    Args:
        bot: Bot instance
        order_id: Order ID
    """
    from app.database.models import Order, User, Package
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.services.notification_service import NotificationService
    from app.services.yandex_metrika import metrika_service
    from app.database.crud import get_user_balance

    db = get_db()
    async with db.get_session() as session:
        # Get order with related data
        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.user), selectinload(Order.package))
        )
        order = result.scalar_one_or_none()

        if not order:
            return

        # Track purchase event to database and Yandex Metrika
        await metrika_service.track_event(
            session=session,
            user_id=order.user.id,
            event_type="purchase",
            event_value=float(order.amount),
            currency="RUB"
        )

        # Get user's new balance
        new_balance = await get_user_balance(session, order.user.telegram_id)

        # Notify user
        await NotificationService.notify_user_payment_success(
            bot=bot,
            telegram_id=order.user.telegram_id,
            package_name=order.package.name,
            images_count=order.package.images_count,
            amount=float(order.amount),
            new_balance=new_balance
        )

        # Notify admins
        await NotificationService.notify_admins_new_payment(
            bot=bot,
            user_telegram_id=order.user.telegram_id,
            username=order.user.username,
            package_name=order.package.name,
            images_count=order.package.images_count,
            amount=float(order.amount),
            order_id=order.id
        )


async def process_payment_webhook(notification_data: dict, bot=None) -> bool:
    """
    Process payment webhook from YooKassa

    Args:
        notification_data: Raw notification data from YooKassa webhook
        bot: Optional bot instance for sending notifications

    Returns:
        True if payment was processed successfully
    """
    import logging
    logger = logging.getLogger(__name__)

    # Verify and parse webhook notification
    yookassa = YookassaService()
    payment_info = yookassa.verify_webhook_notification(notification_data)

    if not payment_info:
        logger.error("Invalid webhook notification")
        return False

    # Check if payment is successful
    if payment_info["status"] != "succeeded" or not payment_info["paid"]:
        logger.info(f"Payment {payment_info['payment_id']} status: {payment_info['status']}")
        return False

    payment_id = payment_info["payment_id"]

    # Mark order as paid
    db = get_db()
    async with db.get_session() as session:
        order = await mark_order_paid(session, payment_id)

        if not order:
            logger.info(f"Order for payment_id {payment_id} not found or already paid - skipping duplicate processing")
            return False

        # Payment successful
        logger.info(f"Payment successful for order {order.id}")

        # Send notifications if bot instance is provided
        if bot:
            try:
                await notify_payment_success(bot, order.id)
            except Exception as e:
                logger.error(f"Failed to send notifications for order {order.id}: {str(e)}")

        return True
