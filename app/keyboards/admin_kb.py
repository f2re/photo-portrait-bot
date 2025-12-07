from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_menu() -> InlineKeyboardMarkup:
    """Get admin menu keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Статистика пользователей", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders")],
            [InlineKeyboardButton(text="💬 Обращения в поддержку", callback_data="admin_support")],
            [InlineKeyboardButton(text="📊 UTM Статистика", callback_data="admin_utm_menu")],
            [InlineKeyboardButton(text="➕ Добавить генерации", callback_data="admin_add_images")],
            [InlineKeyboardButton(text="💵 Оформить возврат", callback_data="admin_refund")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh")]
        ]
    )
    return keyboard


def get_order_actions(order_id: int) -> InlineKeyboardMarkup:
    """Get order actions keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"admin_confirm_order:{order_id}")],
            [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"admin_cancel_order:{order_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_orders")]
        ]
    )
    return keyboard


def get_ticket_actions(ticket_id: int) -> InlineKeyboardMarkup:
    """Get support ticket actions keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Ответить", callback_data=f"admin_reply_ticket:{ticket_id}")],
            [InlineKeyboardButton(text="✅ Закрыть обращение", callback_data=f"admin_close_ticket:{ticket_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_support")]
        ]
    )
    return keyboard


def get_admin_utm_menu() -> InlineKeyboardMarkup:
    """Get admin UTM menu keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_utm_stats")],
            [InlineKeyboardButton(text="🎢 Воронка конверсии", callback_data="admin_utm_funnel")],
            [InlineKeyboardButton(text="📈 События UTM", callback_data="admin_utm_events")],
            [InlineKeyboardButton(text="⚙️ Статус синхронизации", callback_data="admin_utm_sync_status")],
            [InlineKeyboardButton(text="◀️ Назад в админ-панель", callback_data="admin_menu")]
        ]
    )
    return keyboard


def get_admin_back() -> InlineKeyboardMarkup:
    """Get back to admin menu keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в админ-панель", callback_data="admin_menu")]
        ]
    )
    return keyboard


def get_admin_cancel() -> InlineKeyboardMarkup:
    """Get cancel keyboard for admin actions"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_action")]
        ]
    )
    return keyboard
