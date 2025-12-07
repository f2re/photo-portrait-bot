from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List


def get_main_menu() -> ReplyKeyboardMarkup:
    """Get main menu keyboard"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📸 Обработать изображение")],
            [KeyboardButton(text="💎 Купить пакет"), KeyboardButton(text="📊 Мой баланс")],
            [KeyboardButton(text="👥 Реферальная программа")],
            [KeyboardButton(text="ℹ️ Информация"), KeyboardButton(text="💬 Поддержка")]
        ],
        resize_keyboard=True
    )
    return keyboard


def get_packages_keyboard(packages: List[dict]) -> InlineKeyboardMarkup:
    """
    Get packages selection keyboard

    Args:
        packages: List of package dicts with keys: id, name, images_count, price_rub

    Returns:
        InlineKeyboardMarkup with packages
    """
    buttons = []

    for package in packages:
        # Calculate discount if applicable
        base_price = 20  # Base price per image in rubles
        actual_price_per_image = package['price_rub'] / package['images_count']
        discount = int((1 - actual_price_per_image / base_price) * 100)

        if discount > 0:
            text = f"💰 {package['images_count']} изображений - {package['price_rub']}₽ (скидка {discount}%)"
        else:
            text = f"💰 {package['images_count']} изображений - {package['price_rub']}₽"

        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"buy_package:{package['id']}"
        )])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_info_menu() -> InlineKeyboardMarkup:
    """Get information menu keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Оферта", callback_data="info_offer")],
            [InlineKeyboardButton(text="💸 Условия возврата", callback_data="info_refund")],
            [InlineKeyboardButton(text="🔒 Конфиденциальность", callback_data="info_privacy")],
            [InlineKeyboardButton(text="❓ Как это работает", callback_data="info_how_it_works")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def get_support_menu() -> InlineKeyboardMarkup:
    """Get support menu keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Вопрос по работе", callback_data="support_general")],
            [InlineKeyboardButton(text="🐛 Сообщить о проблеме", callback_data="support_bug")],
            [InlineKeyboardButton(text="💸 Вопрос по оплате", callback_data="support_payment")],
            [InlineKeyboardButton(text="📦 Запрос возврата", callback_data="support_refund")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def get_payment_confirmation(payment_url: str, payment_id: str) -> InlineKeyboardMarkup:
    """Get payment confirmation keyboard with 'I paid' button"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment:{payment_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")]
        ]
    )
    return keyboard


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Get cancel keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ]
    )
    return keyboard


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Get back keyboard"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def get_support_contact_keyboard() -> InlineKeyboardMarkup:
    """Get support contact keyboard (for errors)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Обратиться в поддержку", callback_data="contact_support")],
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="try_again")],
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def get_buy_package_keyboard() -> InlineKeyboardMarkup:
    """Get buy package keyboard (when balance is zero)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить пакет", callback_data="show_packages")],
            [InlineKeyboardButton(text="📊 Проверить баланс", callback_data="check_balance")],
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def get_low_balance_keyboard() -> InlineKeyboardMarkup:
    """Get low balance keyboard (when balance is low but not zero)"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить еще", callback_data="show_packages")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def get_payment_contact_keyboard() -> ReplyKeyboardMarkup:
    """
    Get keyboard for contact sharing during payment
    Offers easy button to share phone contact
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Через СМС на телефон", request_contact=True)],
            [KeyboardButton(text="📧 Через Email")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard


def get_contact_skip_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for contact input (email) with cancel option"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")]
        ]
    )
    return keyboard


def get_referral_menu(bot_username: str, referral_code: str) -> InlineKeyboardMarkup:
    """
    Get referral program menu keyboard
    
    Args:
        bot_username: Bot's username (without @)
        referral_code: User's referral code
    
    Returns:
        InlineKeyboardMarkup with referral options
    """
    referral_link = f"https://t.me/{bot_username}?start=ref_{referral_code}"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📤 Поделиться ссылкой",
                url=f"https://t.me/share/url?url={referral_link}&text=Попробуй этого бота для удаления фона с изображений! Первые 3 обработки бесплатно!"
            )],
            [InlineKeyboardButton(
                text="📋 Скопировать ссылку",
                callback_data=f"copy_referral:{referral_code}"
            )],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard
