from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db
from app.database.crud import (
    get_statistics, get_open_tickets, resolve_ticket,
    get_or_create_user, get_user_balance, get_ticket_by_id,
    add_support_message, get_utm_statistics, get_conversion_funnel,
    get_utm_events_summary, get_utm_sync_status
)
from app.services.notification_service import NotificationService
from app.services.yandex_metrika import metrika_service
from app.keyboards.admin_kb import (
    get_admin_menu, get_ticket_actions, get_admin_back, get_admin_cancel, get_admin_utm_menu
)
from app.utils.decorators import admin_only

router = Router()


class AdminStates(StatesGroup):
    waiting_for_ticket_reply = State()
    waiting_for_user_id = State()
    waiting_for_images_count = State()


@router.message(Command("admin"))
@admin_only
async def admin_panel(message: Message):
    """Show admin panel"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "🔐 <b>Админ-панель</b>\n\n"
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽ ({stats['paid_orders']} заказов)\n"
        f"📦 Активных заказов: {stats['active_orders']}\n"
        f"💬 Открытых обращений: {stats['open_tickets']}"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_menu())


@router.callback_query(F.data == "admin_refresh")
@admin_only
async def admin_refresh(callback: CallbackQuery):
    """Refresh admin panel"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "🔐 <b>Админ-панель</b>\n\n"
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽ ({stats['paid_orders']} заказов)\n"
        f"📦 Активных заказов: {stats['active_orders']}\n"
        f"💬 Открытых обращений: {stats['open_tickets']}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_menu())
    await callback.answer("✅ Обновлено")


@router.callback_query(F.data == "admin_stats")
@admin_only
async def admin_stats(callback: CallbackQuery):
    """Show detailed statistics"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "📊 <b>Детальная статистика</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽\n"
        f"   📦 Оплаченных заказов: {stats['paid_orders']}\n"
        f"   ⏳ Активных заказов: {stats['active_orders']}\n\n"
        f"💬 Открытых обращений: {stats['open_tickets']}\n\n"
        "Используйте другие команды для более детального просмотра."
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_back())
    await callback.answer()


@router.callback_query(F.data == "admin_support")
@admin_only
async def admin_support_tickets(callback: CallbackQuery):
    """Show support tickets"""
    db = get_db()
    async with db.get_session() as session:
        tickets = await get_open_tickets(session)

    if not tickets:
        text = "💬 <b>Обращения в поддержку</b>\n\n❌ Нет открытых обращений"
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_back())
        await callback.answer()
        return

    text = "💬 <b>Обращения в поддержку</b>\n\n"

    for ticket in tickets[:10]:  # Show first 10
        text += (
            f"📝 #{ticket.id} | {ticket.status}\n"
            f"👤 User ID: {ticket.user.telegram_id}\n"
            f"💬 {ticket.message[:100]}...\n"
            f"🕐 {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        )

    text += "\nИспользуйте /ticket <ID> для ответа"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_back())
    await callback.answer()


@router.message(Command("ticket"))
@admin_only
async def view_ticket(message: Message):
    """View specific ticket"""
    try:
        ticket_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /ticket <ID>")
        return

    db = get_db()
    async with db.get_session() as session:
        from app.database.models import SupportTicket
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await session.execute(
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .options(selectinload(SupportTicket.user))
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            await message.answer("❌ Обращение не найдено")
            return

        text = (
            f"📝 <b>Обращение #{ticket.id}</b>\n\n"
            f"👤 От: @{ticket.user.username or 'Unknown'} ({ticket.user.telegram_id})\n"
            f"📅 Создано: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📊 Статус: {ticket.status}\n\n"
            f"💬 <b>Сообщение:</b>\n{ticket.message}"
        )

        if ticket.admin_response:
            text += f"\n\n✅ <b>Ваш ответ:</b>\n{ticket.admin_response}"

        await message.answer(text, parse_mode="HTML", reply_markup=get_ticket_actions(ticket.id))


@router.callback_query(F.data.startswith("admin_reply_ticket:"))
@admin_only
async def admin_reply_ticket(callback: CallbackQuery, state: FSMContext):
    """Start replying to ticket"""
    ticket_id = int(callback.data.split(":")[1])

    await state.update_data(ticket_id=ticket_id)
    await state.set_state(AdminStates.waiting_for_ticket_reply)

    await callback.message.edit_text(
        f"✉️ Ответ на обращение #{ticket_id}\n\n"
        "Напишите ваш ответ пользователю:",
        reply_markup=get_admin_cancel()
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_ticket_reply, F.text)
@admin_only
async def process_ticket_reply(message: Message, state: FSMContext):
    """Process ticket reply"""
    data = await state.get_data()
    ticket_id = data.get('ticket_id')

    if not ticket_id:
        await message.answer("❌ Ошибка: ID обращения не найден")
        return

    db = get_db()
    async with db.get_session() as session:
        ticket = await get_ticket_by_id(session, ticket_id)

        if not ticket:
            await message.answer("❌ Обращение не найдено")
            return

        # Add message to conversation
        await add_support_message(
            session,
            ticket_id=ticket_id,
            sender_telegram_id=message.from_user.id,
            message=message.text,
            is_admin=True
        )

        # Also update the admin_response field and resolve
        await resolve_ticket(session, ticket_id, message.from_user.id, message.text)

        # Send notification to user using NotificationService
        await NotificationService.notify_user_support_reply(
            bot=message.bot,
            telegram_id=ticket.user.telegram_id,
            ticket_id=ticket_id,
            admin_username=message.from_user.username,
            message=message.text
        )

        await message.answer(f"✅ Ответ отправлен пользователю (ID: {ticket.user.telegram_id})")

    await state.clear()


@router.message(Command("support_reply"))
@admin_only
async def support_reply_command(message: Message):
    """Reply to support ticket using command: /support_reply <ticket_id> <message>"""
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(
                "❌ <b>Использование:</b>\n"
                "/support_reply &lt;ticket_id&gt; &lt;message&gt;\n\n"
                "<b>Пример:</b>\n"
                "/support_reply 123 Ваш вопрос принят, мы работаем над решением",
                parse_mode="HTML"
            )
            return

        ticket_id = int(parts[1])
        reply_message = parts[2]

    except (IndexError, ValueError):
        await message.answer(
            "❌ <b>Ошибка формата</b>\n\n"
            "Используйте: /support_reply &lt;ticket_id&gt; &lt;message&gt;",
            parse_mode="HTML"
        )
        return

    db = get_db()
    async with db.get_session() as session:
        ticket = await get_ticket_by_id(session, ticket_id)

        if not ticket:
            await message.answer(f"❌ Обращение #{ticket_id} не найдено")
            return

        # Add message to conversation
        await add_support_message(
            session,
            ticket_id=ticket_id,
            sender_telegram_id=message.from_user.id,
            message=reply_message,
            is_admin=True
        )

        # Also update the admin_response field
        await resolve_ticket(session, ticket_id, message.from_user.id, reply_message)

        # Send notification to user
        await NotificationService.notify_user_support_reply(
            bot=message.bot,
            telegram_id=ticket.user.telegram_id,
            ticket_id=ticket_id,
            admin_username=message.from_user.username,
            message=reply_message
        )

        await message.answer(
            f"✅ Ответ отправлен!\n\n"
            f"📝 Тикет: #{ticket_id}\n"
            f"👤 Пользователь: {ticket.user.telegram_id}\n"
            f"💬 Ваш ответ: {reply_message[:100]}{'...' if len(reply_message) > 100 else ''}",
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("admin_close_ticket:"))
@admin_only
async def admin_close_ticket(callback: CallbackQuery):
    """Close ticket without reply"""
    ticket_id = int(callback.data.split(":")[1])

    db = get_db()
    async with db.get_session() as session:
        await resolve_ticket(session, ticket_id, callback.from_user.id, "Закрыто администратором")

    await callback.message.edit_text(
        f"✅ Обращение #{ticket_id} закрыто",
        reply_markup=get_admin_back()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_images")
@admin_only
async def admin_add_images_start(callback: CallbackQuery, state: FSMContext):
    """Start adding images to user"""
    await state.set_state(AdminStates.waiting_for_user_id)

    await callback.message.edit_text(
        "➕ <b>Добавить изображения пользователю</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
        reply_markup=get_admin_cancel()
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id, F.text)
@admin_only
async def admin_add_images_user_id(message: Message, state: FSMContext):
    """Process user ID for adding images"""
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите числовое значение.")
        return

    # Check if user exists
    db = get_db()
    async with db.get_session() as session:
        user = await get_or_create_user(session, user_id)

    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.waiting_for_images_count)

    await message.answer(
        f"👤 Пользователь: {user.telegram_id}\n\n"
        "Введите количество изображений для добавления:"
    )


@router.message(AdminStates.waiting_for_images_count, F.text)
@admin_only
async def admin_add_images_count(message: Message, state: FSMContext):
    """Process images count for adding"""
    try:
        count = int(message.text)
        if count <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Неверное количество. Введите положительное число.")
        return

    data = await state.get_data()
    target_user_id = data.get('target_user_id')

    # Add images by creating a manual order
    db = get_db()
    async with db.get_session() as session:
        from app.database.models import Package, Order, User
        from sqlalchemy import select

        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == target_user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        # Create manual package entry
        manual_package = Package(
            name=f"Manual {count} images",
            images_count=count,
            price_rub=0,
            is_active=False
        )
        session.add(manual_package)
        await session.flush()

        # Create paid order
        order = Order(
            user_id=user.id,
            package_id=manual_package.id,
            amount=0,
            status="paid",
            invoice_id=f"manual_{user.id}_{int(__import__('time').time())}"
        )
        session.add(order)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Добавлено {count} изображений пользователю {target_user_id}"
    )


@router.callback_query(F.data == "admin_cancel_action")
@admin_only
async def admin_cancel_action(callback: CallbackQuery, state: FSMContext):
    """Cancel admin action"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено",
        reply_markup=get_admin_back()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_menu")
@admin_only
async def admin_menu_callback(callback: CallbackQuery):
    """Return to admin menu"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "🔐 <b>Админ-панель</b>\n\n"
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽ ({stats['paid_orders']} заказов)\n"
        f"📦 Активных заказов: {stats['active_orders']}\n"
        f"💬 Открытых обращений: {stats['open_tickets']}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_menu())
    await callback.answer()



@router.callback_query(F.data == "admin_utm_menu")
@admin_only
async def admin_utm_menu_callback(callback: CallbackQuery):
    """Show UTM statistics menu"""
    text = "📊 <b>UTM Статистика</b>\n\nВыберите раздел для просмотра:"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_utm_menu())
    await callback.answer()


@router.callback_query(F.data == "admin_utm_stats")
@admin_only
async def admin_utm_stats_callback(callback: CallbackQuery):
    """Show UTM stats"""
    await utm_stats_handler(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin_utm_funnel")
@admin_only
async def admin_utm_funnel_callback(callback: CallbackQuery):
    """Show UTM funnel"""
    await utm_funnel_handler(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin_utm_events")
@admin_only
async def admin_utm_events_callback(callback: CallbackQuery):
    """Show UTM events"""
    await utm_events_handler(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin_utm_sync_status")
@admin_only
async def admin_utm_sync_status_callback(callback: CallbackQuery):
    """Show UTM sync status"""
    await utm_sync_status_handler(callback.message)
    await callback.answer()


# ==================== UTM TRACKING STATISTICS ====================

@router.message(Command("utm_stats"))
@admin_only
async def utm_stats_handler(message: Message):
    """
    Show UTM tracking statistics (only for admins).

    Usage: /utm_stats
    """
    db = get_db()
    async with db.get_session() as session:
        stats = await get_utm_statistics(session)

    if not stats:
        await message.answer(
            "📊 <b>UTM Статистика</b>\n\n"
            "ℹ️ Пока нет данных по UTM-меткам.\n\n"
            "Пользователи без UTM-меток не учитываются в этой статистике. "
            "Создайте ссылку с UTM-метками для отслеживания источников трафика.",
            parse_mode="HTML"
        )
        return

    text = "📊 <b>Статистика по UTM-меткам</b>\n\n"

    for stat in stats[:10]:  # Show top 10 sources
        source = stat['utm_source']
        medium = stat['utm_medium']
        campaign = stat['utm_campaign']
        total_users = stat['total_users']
        paying_users = stat['paying_users']
        conversion_rate = stat['conversion_rate']
        revenue = stat['revenue']
        arpu = stat['arpu']

        text += (
            f"🔹 <b>{source} / {medium} / {campaign}</b>\n"
            f"   👥 Пользователей: {total_users}\n"
            f"   💰 Купили: {paying_users} ({conversion_rate}%)\n"
            f"   💵 Выручка: {revenue:.2f}₽\n"
            f"   📈 ARPU: {arpu:.2f}₽\n\n"
        )

    if len(stats) > 10:
        text += f"<i>...и еще {len(stats) - 10} источников</i>\n\n"

    text += (
        "📌 <b>Команды:</b>\n"
        "• /utm_funnel — воронка конверсии\n"
        "• /utm_events — последние события"
    )

    await message.answer(text, parse_mode="HTML")


@router.message(Command("utm_funnel"))
@admin_only
async def utm_funnel_handler(message: Message):
    """
    Show UTM conversion funnel (only for admins).

    Usage: /utm_funnel
    """
    db = get_db()
    async with db.get_session() as session:
        funnel = await get_conversion_funnel(session)

    starts = funnel['starts']
    first_images = funnel['first_images']
    purchases = funnel['purchases']
    start_to_first_image_rate = funnel['start_to_first_image_rate']
    first_image_to_purchase_rate = funnel['first_image_to_purchase_rate']
    overall_conversion_rate = funnel['overall_conversion_rate']

    text = (
        "📊 <b>Воронка конверсии (UTM пользователи)</b>\n\n"
        f"1️⃣ <b>Запуск бота</b>: {starts} чел.\n"
        f"   ⬇️ {start_to_first_image_rate}%\n\n"
        f"2️⃣ <b>Первое фото</b>: {first_images} чел.\n"
        f"   ⬇️ {first_image_to_purchase_rate}%\n\n"
        f"3️⃣ <b>Покупка</b>: {purchases} чел.\n\n"
        f"📈 <b>Общая конверсия</b>: {overall_conversion_rate}%\n\n"
        "<i>Учитываются только пользователи из UTM-источников</i>"
    )

    await message.answer(text, parse_mode="HTML")


@router.message(Command("utm_events"))
@admin_only
async def utm_events_handler(message: Message):
    """
    Show recent UTM events (only for admins).

    Usage: /utm_events [limit]
    Example: /utm_events 20
    """
    # Parse limit from command
    limit = 20
    if message.text and len(message.text.split()) > 1:
        try:
            limit = int(message.text.split()[1])
            limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
        except ValueError:
            pass

    db = get_db()
    async with db.get_session() as session:
        events = await get_utm_events_summary(session, limit=limit)

    if not events:
        await message.answer(
            "📊 <b>События UTM</b>\n\n"
            "ℹ️ Нет событий для отображения.",
            parse_mode="HTML"
        )
        return

    text = f"📊 <b>Последние {len(events)} событий UTM</b>\n\n"

    for event in events[:20]:  # Show max 20 in message
        event_type = event['event_type']
        user_id = event['user_id']
        username = event['username'] or 'N/A'
        utm_source = event['utm_source'] or '-'
        utm_campaign = event['utm_campaign'] or '-'
        event_value = event['event_value']
        sent = "✅" if event['sent_to_metrika'] else "⏳"

        # Event emoji
        event_emoji = {
            'start': '🚀',
            'first_image': '📸',
            'purchase': '💰'
        }.get(event_type, '📌')

        text += f"{event_emoji} <code>{event_type}</code>"

        if event_value:
            text += f" ({event_value}₽)"

        text += f"\n   👤 @{username} ({user_id})\n"
        text += f"   🏷 {utm_source}/{utm_campaign} {sent}\n\n"

    if len(events) > 20:
        text += f"<i>...и еще {len(events) - 20} событий</i>\n\n"

    text += "\n<i>✅ отправлено в Метрику, ⏳ в очереди</i>"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("utm_sync_status"))
@admin_only
async def utm_sync_status_handler(message: Message):
    """
    Show Yandex Metrika synchronization status (only for admins).

    Usage: /utm_sync_status
    """
    db = get_db()
    async with db.get_session() as session:
        status = await get_utm_sync_status(session)

    total = status['total_events']
    sent = status['sent_events']
    pending = status['pending_events']
    sync_rate = status['sync_rate']
    last_sent = status['last_sent_at']
    last_pending = status['last_pending_at']
    pending_breakdown = status['pending_breakdown']

    # Format last sent time
    if last_sent:
        from datetime import datetime
        try:
            last_sent_dt = datetime.fromisoformat(last_sent)
            last_sent_str = last_sent_dt.strftime("%d.%m.%Y %H:%M:%S")
        except:
            last_sent_str = last_sent
    else:
        last_sent_str = "Никогда"

    # Build text
    text = (
        "📊 <b>Статус синхронизации с Яндекс.Метрикой</b>\n\n"
        f"📈 <b>Общая статистика:</b>\n"
        f"   Всего событий: {total}\n"
        f"   ✅ Отправлено: {sent} ({sync_rate}%)\n"
        f"   ⏳ В очереди: {pending}\n\n"
    )

    if pending > 0:
        text += "📋 <b>В очереди по типам:</b>\n"
        event_names = {
            'start': '🚀 Запуски бота',
            'first_image': '📸 Первые фото',
            'purchase': '💰 Покупки'
        }
        for event_type, count in pending_breakdown.items():
            event_name = event_names.get(event_type, event_type)
            text += f"   {event_name}: {count}\n"
        text += "\n"

    text += (
        f"🕐 <b>Последняя отправка:</b> {last_sent_str}\n\n"
        f"⚙️ <b>Интервал загрузки:</b> {metrika_service.is_enabled and 'каждый час' or 'Метрика отключена'}\n\n"
    )

    if not metrika_service.is_enabled:
        text += (
            "⚠️ <b>Яндекс.Метрика отключена</b>\n"
            "События сохраняются в БД, но не отправляются в Метрику.\n"
            "Для включения установите YANDEX_METRIKA_COUNTER_ID и YANDEX_METRIKA_TOKEN в .env\n\n"
        )
    elif pending > 0:
        text += (
            "💡 <b>Команды:</b>\n"
            "• /utm_upload — загрузить события сейчас\n"
            "• /utm_events — посмотреть последние события"
        )
    else:
        text += "✅ Все события отправлены в Метрику!"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("utm_upload"))
@admin_only
async def utm_upload_handler(message: Message):
    """
    Manually upload pending events to Yandex Metrika (only for admins).

    Usage: /utm_upload
    """
    if not metrika_service.is_enabled:
        await message.answer(
            "⚠️ <b>Яндекс.Метрика отключена</b>\n\n"
            "События не могут быть отправлены, так как Метрика не настроена.\n"
            "Для включения установите YANDEX_METRIKA_COUNTER_ID и YANDEX_METRIKA_TOKEN в .env",
            parse_mode="HTML"
        )
        return

    # Get pending count first
    db = get_db()
    async with db.get_session() as session:
        status = await get_utm_sync_status(session)
        pending = status['pending_events']

    if pending == 0:
        await message.answer(
            "✅ <b>Нет событий для отправки</b>\n\n"
            "Все события уже отправлены в Яндекс.Метрику.",
            parse_mode="HTML"
        )
        return

    # Send status message
    status_msg = await message.answer(
        f"⏳ Отправляю {pending} событий в Яндекс.Метрику...",
        parse_mode="HTML"
    )

    # Upload events
    async with db.get_session() as session:
        success = await metrika_service.upload_pending_events(session)

    if success:
        # Get updated status
        async with db.get_session() as session:
            new_status = await get_utm_sync_status(session)
            new_pending = new_status['pending_events']

        uploaded = pending - new_pending

        await status_msg.edit_text(
            f"✅ <b>Успешно отправлено!</b>\n\n"
            f"Отправлено событий: {uploaded}\n"
            f"Осталось в очереди: {new_pending}\n\n"
            f"Используйте /utm_sync_status для проверки статуса",
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(
            "❌ <b>Ошибка при отправке</b>\n\n"
            "Не удалось отправить события в Яндекс.Метрику.\n"
            "Проверьте логи для подробностей.\n\n"
            "Возможные причины:\n"
            "• Неверный токен или счетчик\n"
            "• Офлайн-конверсии не включены в Метрике\n"
            "• Проблемы с сетью",
            parse_mode="HTML"
        )
