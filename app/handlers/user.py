from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy import select

from app.database import get_db
from app.database.models import User
from app.database.crud import (
    get_or_create_user, get_user_balance, decrease_balance,
    update_user_stats, save_processed_image, get_all_packages,
    check_and_reserve_balance, rollback_balance, get_user_by_referral_code,
    set_user_referrer, add_referral_reward, get_or_create_referral_code,
    get_referral_stats
)
from app.utils.locks import user_processing_lock
from app.keyboards.user_kb import (
    get_main_menu, get_packages_keyboard, get_info_menu, get_back_keyboard,
    get_support_contact_keyboard, get_buy_package_keyboard,
    get_low_balance_keyboard,
    get_referral_menu
)
from app.services.image_processor import ImageProcessor
from app.services.yandex_metrika import metrika_service
from app.utils.utm_parser import parse_utm_from_start_param
from app.config import settings
from app.utils.decorators import error_handler
import logging

logger = logging.getLogger(__name__)

router = Router()


class DemoUploadStates(StatesGroup):
    waiting_for_demo_video = State()


async def build_welcome_message(first_name: str, balance: dict) -> str:
    """
    Build welcome message with user's balance info
    """
    # Build balance status message
    balance_text = ""
    if balance['free'] > 0 and balance['paid'] > 0:
        balance_text = f"💫 Баланс: <b>{balance['total']}</b> фото (🎁 {balance['free']} + 💎 {balance['paid']})\n"
    elif balance['free'] > 0:
        balance_text = f"🎁 У вас: <b>{balance['free']}</b> бесплатных фото\n"
    elif balance['paid'] > 0:
        balance_text = f"💎 У вас: <b>{balance['paid']}</b> фото\n"
    else:
        # When balance is 0, emphasize affordability
        if settings.FREE_IMAGES_COUNT > 0:
            balance_text = "⚠️ Бесплатные фото закончились!\n"
        else:
            balance_text = ""

    welcome_text = (
        f"👋 Привет, {first_name}!\n\n"
    )

    if balance_text:
        welcome_text += f"{balance_text}\n"

    welcome_text += (
        "🤖 <b>HeadshotPro AI — Бизнес-портрет</b>\n\n"
        "Я превращу твое обычное фото в профессиональный студийный портрет уровня Forbes и LinkedIn.\n\n"
        "<b>Как пользоваться:</b>\n"
        "• Просто отправь свое фото\n"
        "• Я одену тебя в деловой костюм, настрою свет и сделаю идеальный фон\n\n"
    )

    # Add contextual call-to-action based on balance
    if balance['total'] == 0:
        # Get first package info for the CTA
        welcome_text += f"💎 <b>Начните всего за {settings.PACKAGE_1_PRICE}₽!</b>\n"
        welcome_text += f"Получите классный портрет люксери-уровня по цене чашки кофе ☕️"
    else:
        welcome_text += "✨ Отправляйте фото!"

    return welcome_text

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    """Handle /start command with UTM tracking, referral links, and payment deep links"""
    start_param = None
    if message.text and len(message.text.split()) > 1:
        start_param = message.text.split(maxsplit=1)[1]

    if start_param:
        if start_param.lower() in ['payment', 'buy', 'price', 'packages']:
            db = get_db()
            async with db.get_session() as session:
                await get_or_create_user(
                    session,
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    free_images_count=settings.FREE_IMAGES_COUNT
                )
                packages = await get_all_packages(session)
                balance = await get_user_balance(session, message.from_user.id)

            packages_list = [
                {
                    "id": p.id,
                    "name": p.name,
                    "images_count": p.images_count,
                    "price_rub": float(p.price_rub)
                }
                for p in packages
            ]

            # Build welcome text for deep link to packages
            if settings.FREE_IMAGES_COUNT > 0:
                free_info = f"🎁 Бесплатно: {settings.FREE_IMAGES_COUNT} фото (у вас: {balance['free']})\n"
            else:
                free_info = f"💎 <b>Люксери портреты по доступным ценам!</b>\n"

            text = (
                "💎 <b>Добро пожаловать!</b>\n\n"
                f"{free_info}"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "<b>Выберите пакет:</b>"
            )

            await message.answer(text, parse_mode="HTML", reply_markup=get_packages_keyboard(packages_list))
            return

        elif start_param.lower().startswith(('buy_', 'package_')):
            try:
                package_num = int(start_param.split('_')[1])
                if 1 <= package_num <= 4:
                    db = get_db()
                    async with db.get_session() as session:
                        await get_or_create_user(
                            session,
                            telegram_id=message.from_user.id,
                            username=message.from_user.username,
                            first_name=message.from_user.first_name,
                            free_images_count=settings.FREE_IMAGES_COUNT
                        )
                        packages = await get_all_packages(session)
                        if len(packages) >= package_num:
                            target_package = packages[package_num - 1]
                            text = (
                                f"💎 <b>Покупка пакета: {target_package.name}</b>\n\n"
                                f"📦 Фотографий: {target_package.images_count}\n"
                                f"💰 Стоимость: {target_package.price_rub}₽\n\n"
                                "━━━━━━━━━━━━━━━━━━━━\n\n"
                                "Нажмите кнопку ниже, чтобы продолжить оплату."
                            )
                            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                            keyboard = InlineKeyboardMarkup(
                                inline_keyboard=[
                                    [InlineKeyboardButton(
                                        text=f"💳 Купить за {target_package.price_rub}₽",
                                        callback_data=f"buy_package:{target_package.id}"
                                    )],
                                    [InlineKeyboardButton(
                                        text="🔙 Смотреть все пакеты",
                                        callback_data="show_packages"
                                    )]
                                ]
                            )
                            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                            return
            except (ValueError, IndexError):
                pass

    referral_code = None
    if start_param and start_param.startswith('ref_'):
        referral_code = start_param[4:]

    utm_data = parse_utm_from_start_param(start_param)

    db = get_db()
    async with db.get_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            free_images_count=settings.FREE_IMAGES_COUNT,
            utm_source=utm_data.get('utm_source'),
            utm_medium=utm_data.get('utm_medium'),
            utm_campaign=utm_data.get('utm_campaign'),
            utm_content=utm_data.get('utm_content'),
            utm_term=utm_data.get('utm_term')
        )

        from datetime import datetime, timedelta
        is_new_user = (datetime.utcnow() - user.created_at) < timedelta(seconds=5)

        if is_new_user and referral_code:
            referrer = await get_user_by_referral_code(session, referral_code)
            if referrer and referrer.id != user.id:
                referrer_set = await set_user_referrer(session, user.id, referrer.id)
                if referrer_set:
                    await add_referral_reward(
                        session,
                        user_id=referrer.id,
                        referred_user_id=user.id,
                        reward_type='referral_start',
                        images_rewarded=settings.REFERRAL_REWARD_START
                    )
                    try:
                        await message.bot.send_message(
                            referrer.telegram_id,
                            f"🎉 <b>Новый реферал!</b>\n\n"
                            f"Пользователь перешел по вашей ссылке!\n"
                            f"🎁 Вам начислено <b>{settings.REFERRAL_REWARD_START}</b> бесплатных фото!\n\n"
                            f"Продолжайте делиться ссылкой и получайте больше фото! 👥",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

        if is_new_user:
            await metrika_service.track_event(
                session=session,
                user_id=user.id,
                event_type="start"
            )

        balance = await get_user_balance(session, message.from_user.id)

    welcome_text = await build_welcome_message(message.from_user.first_name, balance)
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_menu())


@router.message(F.text == "📊 Мой баланс")
async def balance_handler(message: Message):
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, message.from_user.id)

    text = (
        "📊 <b>Ваш баланс:</b>\n\n"
        f"🎁 Бесплатных фото: {balance['free']}\n"
        f"💎 Оплаченных фото: {balance['paid']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📸 Всего доступно: {balance['total']}"
    )

    if balance['total'] == 0:
        text += f"\n\n💰 <b>Начните всего за {settings.PACKAGE_1_PRICE}₽!</b>\nПолучите классный портрет люксери-уровня 🎯"
        await message.answer(text, parse_mode="HTML", reply_markup=get_buy_package_keyboard())
    elif balance['total'] <= 3:
        text += "\n\n💡 Рекомендуем пополнить баланс заранее!"
        await message.answer(text, parse_mode="HTML", reply_markup=get_low_balance_keyboard())
    else:
        text += "\n\n✅ У вас достаточно фото!"
        await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💎 Купить пакет")
async def packages_handler(message: Message):
    db = get_db()
    async with db.get_session() as session:
        packages = await get_all_packages(session)
        balance = await get_user_balance(session, message.from_user.id)

    packages_list = [
        {
            "id": p.id,
            "name": p.name,
            "images_count": p.images_count,
            "price_rub": float(p.price_rub)
        }
        for p in packages
    ]

    # Build text with balance info
    if settings.FREE_IMAGES_COUNT > 0:
        balance_info = f"🎁 Бесплатно: {settings.FREE_IMAGES_COUNT} фото (осталось: {balance['free']})\n"
    else:
        balance_info = f"💎 <b>Студийные портреты по цене чашки кофе!</b>\n"

    text = (
        "💎 <b>Доступные пакеты:</b>\n\n"
        f"{balance_info}"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите пакет для покупки:"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_packages_keyboard(packages_list))


@router.message(F.text == "ℹ️ Информация")
async def info_handler(message: Message):
    text = (
        "ℹ️ <b>Информация о боте</b>\n\n"
        "Выберите интересующий раздел:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_info_menu())


@router.message(F.text == "👥 Реферальная программа")
async def referral_program_handler(message: Message):
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one()
        referral_code = await get_or_create_referral_code(session, user.id)
        stats = await get_referral_stats(session, user.id)

    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"🎁 <b>Ваши награды:</b>\n"
        f"• За старт реферала: {settings.REFERRAL_REWARD_START} фото\n"
        f"• За покупку реферала: {settings.REFERRAL_REWARD_PURCHASE_PERCENT}% от пакета\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: {stats['total_referrals']}\n"
        f"• Всего получено: {stats['total_rewards']} фото\n"
        f"  └ За старты: {stats['rewards_from_start']}\n"
        f"  └ За покупки: {stats['rewards_from_purchases']}\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>https://t.me/{settings.BOT_USERNAME}?start=ref_{referral_code}</code>\n\n"
        "💡 Поделитесь ссылкой с друзьями и получайте бонусы!"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_referral_menu(settings.BOT_USERNAME, referral_code)
    )


@router.callback_query(F.data.startswith("copy_referral:"))
async def copy_referral_handler(callback: CallbackQuery):
    referral_code = callback.data.split(":")[1]
    referral_link = f"https://t.me/{settings.BOT_USERNAME}?start=ref_{referral_code}"
    await callback.answer(
        f"✅ Ссылка скопирована!\n{referral_link}",
        show_alert=True
    )


@router.callback_query(F.data == "info_how_it_works")
async def info_how_it_works_handler(callback: CallbackQuery):
    text = (
        "❓ <b>Как это работает?</b>\n\n"
        "📸 <b>Процесс очень прост:</b>\n\n"
        "1️⃣ <b>Сделайте селфи</b> или выберите фото из галереи.\n"
        "   • Лицо должно быть хорошо видно\n"
        "   • Смотрите в камеру\n"
        "   • Можно домашнее фото в любой одежде\n\n"
        "2️⃣ <b>Отправьте боту</b>\n"
        "   • Я сохраню ваши черты лица на 100%\n"
        "   • Одену вас в стильный деловой костюм\n"
        "   • Помещу на профессиональный студийный фон\n\n"
        "3️⃣ <b>Получите результат</b>\n"
        "   • Через 30 секунд вы получите портрет уровня топ-менеджера\n"
        "   • Идеально для LinkedIn, резюме и корпоративных сайтов\n\n"
        "✨ Используется технология Gemini 2.5 Flash Image для фотореалистичного качества!"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "info_offer")
async def info_offer_handler(callback: CallbackQuery):
    text = (
        "📄 <b>Публичная оферта</b>\n\n"
        "Используя данного бота, вы соглашаетесь с условиями предоставления услуг по генерации фото на документы.\n\n"
        "1. Услуга предоставляется 'как есть'.\n"
        "2. Возврат средств возможен при технической ошибке.\n"
        "3. Ваши фото обрабатываются конфиденциально и не сохраняются."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "info_refund")
async def info_refund_handler(callback: CallbackQuery):
    text = (
        "💸 <b>Условия возврата</b>\n\n"
        "Обратитесь в поддержку, если результат обработки вас не устроил по техническим причинам."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "info_privacy")
async def info_privacy_handler(callback: CallbackQuery):
    text = (
        "🔒 <b>Политика конфиденциальности</b>\n\n"
        "Мы не храним ваши фотографии. Они используются только для обработки и сразу удаляются."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery):
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, callback.from_user.id)
    welcome_text = await build_welcome_message(callback.from_user.first_name, balance)
    try:
        await callback.message.edit_text(welcome_text, parse_mode="HTML", reply_markup=None)
    except Exception:
        await callback.message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_menu())
    await callback.answer()


@router.callback_query(F.data == "contact_support")
async def contact_support_handler(callback: CallbackQuery):
    from app.keyboards.user_kb import get_support_menu
    text = "💬 <b>Обратная связь</b>\n\nВыберите тип обращения:"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_support_menu())
    await callback.answer()


@router.callback_query(F.data == "try_again")
async def try_again_handler(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "📸 <b>Отправьте фото для обработки!</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "show_packages")
async def show_packages_handler(callback: CallbackQuery):
    db = get_db()
    async with db.get_session() as session:
        packages = await get_all_packages(session)
        balance = await get_user_balance(session, callback.from_user.id)
    packages_list = [
        {"id": p.id, "name": p.name, "images_count": p.images_count, "price_rub": float(p.price_rub)}
        for p in packages
    ]

    # Build text with balance info
    if settings.FREE_IMAGES_COUNT > 0:
        balance_info = f"🎁 Бесплатно: {settings.FREE_IMAGES_COUNT} фото (осталось: {balance['free']})\n"
    else:
        balance_info = f"💎 <b>Студийные портреты по цене чашки кофе!</b>\n"

    text = (
        "💎 <b>Доступные пакеты:</b>\n\n"
        f"{balance_info}"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите пакет для покупки:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_packages_keyboard(packages_list))
    await callback.answer()


@router.callback_query(F.data == "check_balance")
async def check_balance_handler(callback: CallbackQuery):
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, callback.from_user.id)
    text = (
        "📊 <b>Ваш баланс:</b>\n\n"
        f"🎁 Бесплатных фото: {balance['free']}\n"
        f"💎 Оплаченных фото: {balance['paid']}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📸 Всего доступно: {balance['total']}"
    )
    from aiogram.exceptions import TelegramBadRequest
    try:
        if balance['total'] == 0:
            text += f"\n\n💰 <b>Начните всего за {settings.PACKAGE_1_PRICE}₽!</b>\nПолучите классный портрет люксери-уровня 🎯"
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_buy_package_keyboard())
        elif balance['total'] <= 3:
            text += "\n\n💡 Рекомендуем пополнить баланс!"
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_low_balance_keyboard())
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.message(F.photo)
@error_handler
async def process_image_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    if user_processing_lock.is_processing(message.from_user.id):
        await message.answer("⏳ Пожалуйста, дождитесь завершения предыдущей обработки.")
        return

    db = get_db()
    status_msg = None
    balance_reserved = False
    is_free_image = False

    try:
        async with user_processing_lock.acquire(message.from_user.id):
            async with db.get_session() as session:
                success, is_free_image = await check_and_reserve_balance(session, message.from_user.id)
                if not success:
                    await message.answer(
                        "❌ У вас закончились попытки!\n\n💎 Купите пакет для продолжения.",
                        reply_markup=get_buy_package_keyboard()
                    )
                    return
                balance_reserved = True

            status_msg = await message.answer("⏳ Создаю ваш бизнес-портрет (это займет около 30 сек)...")

            photo = message.photo[-1]
            file = await message.bot.get_file(photo.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            image_bytes = file_bytes.read()

            processor = ImageProcessor()
            async with db.get_session() as session:
                user = await get_or_create_user(session, message.from_user.id)

            result = await processor.process_image(
                image_bytes=image_bytes,
                bot=message.bot,
                user=user
            )

            if result['success']:
                output_file = BufferedInputFile(
                    result['image_bytes'],
                    filename="business_portrait.png"
                )

                async with db.get_session() as session:
                    is_first, user_id = await update_user_stats(session, message.from_user.id)
                    if is_first:
                        await metrika_service.track_event(
                            session=session,
                            user_id=user_id,
                            event_type="first_image"
                        )
                    await save_processed_image(
                        session,
                        message.from_user.id,
                        photo.file_id,
                        "processed",
                        "OpenRouter Business Portrait",
                        is_free_image
                    )
                    new_balance = await get_user_balance(session, message.from_user.id)

                balance_info = f"📊 Осталось: {new_balance['total']}"
                caption = f"✅ Готово! Ваш бизнес-портрет создан.\n\n{balance_info}"

                # 1. Send Preview (Photo)
                preview_file = BufferedInputFile(result['image_bytes'], filename="business_portrait_preview.png")
                await message.answer_photo(preview_file, caption=caption)

                # 2. Send Document (High Quality)
                doc_file = BufferedInputFile(result['image_bytes'], filename="business_portrait.png")
                await message.answer_document(doc_file, caption="📂 Файл без потери качества")

                if new_balance['total'] == 0:
                    await message.answer("💎 Купите пакет для продолжения!", reply_markup=get_buy_package_keyboard())

                if status_msg:
                    await status_msg.delete()
            else:
                if balance_reserved:
                    async with db.get_session() as session:
                        await rollback_balance(session, message.from_user.id, is_free_image)
                if status_msg:
                    await status_msg.edit_text(
                        f"❌ Ошибка: {result.get('error')}\n\nПопробуйте другое фото.",
                        reply_markup=get_support_contact_keyboard()
                    )

    except Exception as e:
        if balance_reserved:
            async with db.get_session() as session:
                await rollback_balance(session, message.from_user.id, is_free_image)
        if status_msg:
            await status_msg.edit_text("❌ Произошла ошибка. Попробуйте позже.")
        print(f"Error: {e}")


@router.message(F.document)
@error_handler
async def process_document_handler(message: Message, state: FSMContext):
    # Redirect to same handler logic but handle document
    current_state = await state.get_state()
    if current_state is not None:
        return

    if not message.document.mime_type or not message.document.mime_type.startswith('image/') :
        await message.answer("⚠️ Пожалуйста, отправьте изображение.")
        return

    # For now, treat document same as photo (generate passport photo)
    # Reusing logic would be better but for brevity in this CLI response I'll copy necessary parts or redirect
    # Since I cannot easily call another message handler with modified message object, I'll duplicate the logic wrapper
    
    if user_processing_lock.is_processing(message.from_user.id):
        await message.answer("⏳ Ждите завершения обработки.")
        return

    db = get_db()
    status_msg = None
    balance_reserved = False
    is_free_image = False

    try:
        async with user_processing_lock.acquire(message.from_user.id):
            async with db.get_session() as session:
                success, is_free_image = await check_and_reserve_balance(session, message.from_user.id)
                if not success:
                    await message.answer(
                        "❌ У вас закончились попытки!\n\n💎 Купите пакет для продолжения.",
                        reply_markup=get_buy_package_keyboard()
                    )
                    return
                balance_reserved = True

            status_msg = await message.answer("⏳ Создаю ваш бизнес-портрет (HQ)...")

            file = await message.bot.get_file(message.document.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            image_bytes = file_bytes.read()

            processor = ImageProcessor()
            async with db.get_session() as session:
                user = await get_or_create_user(session, message.from_user.id)

            result = await processor.process_image(
                image_bytes=image_bytes,
                bot=message.bot,
                user=user
            )

            if result['success']:
                output_file = BufferedInputFile(
                    result['image_bytes'],
                    filename=f"business_portrait_{message.document.file_name or 'photo'}.png"
                )

                async with db.get_session() as session:
                    is_first, user_id = await update_user_stats(session, message.from_user.id)
                    if is_first:
                        await metrika_service.track_event(
                            session=session,
                            user_id=user_id,
                            event_type="first_image"
                        )
                    await save_processed_image(
                        session,
                        message.from_user.id,
                        message.document.file_id,
                        "processed",
                        "OpenRouter Business Portrait HQ",
                        is_free_image
                    )
                    new_balance = await get_user_balance(session, message.from_user.id)

                caption = f"✅ Готово! Бизнес-портрет (HQ).\n\n📊 Осталось: {new_balance['total']}"
                
                # 1. Send Preview
                preview_file = BufferedInputFile(result['image_bytes'], filename="business_portrait_preview.png")
                await message.answer_photo(preview_file, caption=caption)

                # 2. Send Document
                doc_file = BufferedInputFile(
                    result['image_bytes'],
                    filename=f"business_portrait_{message.document.file_name or 'hq'}.png"
                )
                await message.answer_document(doc_file, caption="📂 Файл без потери качества")
                
                if status_msg:
                    await status_msg.delete()
            else:
                if balance_reserved:
                    async with db.get_session() as session:
                        await rollback_balance(session, message.from_user.id, is_free_image)
                if status_msg:
                    await status_msg.edit_text(f"❌ Ошибка: {result.get('error')}")

    except Exception as e:
        if balance_reserved:
            async with db.get_session() as session:
                await rollback_balance(session, message.from_user.id, is_free_image)
        if status_msg:
            await status_msg.edit_text("❌ Произошла ошибка.")
        print(f"Error: {e}")


@router.message(F.text == "📸 Создать бизнес-портрет")
async def process_image_request_handler(message: Message):
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, message.from_user.id)

    if balance['total'] == 0:
        await message.answer(
            "❌ <b>У вас закончились обработки!</b>\n\n💎 Купите пакет.",
            parse_mode="HTML",
            reply_markup=get_buy_package_keyboard()
        )
    else:
        await message.answer(
            "📸 <b>Отправьте фото!</b>\n\n"
            "Я сделаю из него профессиональный бизнес-портрет.\n"
            "Смотрите прямо в камеру, желательно при хорошем освещении.",
            parse_mode="HTML"
        )
