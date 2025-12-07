from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db
from app.database.crud import create_support_ticket
from app.keyboards.user_kb import get_support_menu, get_cancel_keyboard, get_back_keyboard
from app.config import settings
from app.services.notification_service import NotificationService

router = Router()


class SupportStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_ticket_type = State()


@router.message(F.text == "💬 Поддержка")
async def support_handler(message: Message):
    """Handle support request"""
    text = (
        "💬 <b>Обратная связь</b>\n\n"
        "Выберите тип обращения:"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_support_menu())


@router.callback_query(F.data.startswith("support_"))
async def support_type_handler(callback: CallbackQuery, state: FSMContext):
    """Handle support type selection"""
    support_type = callback.data.replace("support_", "")

    type_names = {
        "general": "❓ Вопрос по работе",
        "bug": "🐛 Сообщение о проблеме",
        "payment": "💸 Вопрос по оплате",
        "refund": "📦 Запрос возврата"
    }

    if support_type not in type_names:
        await callback.answer("❌ Неизвестный тип обращения", show_alert=True)
        return

    await state.update_data(support_type=support_type)
    await state.set_state(SupportStates.waiting_for_message)

    text = (
        f"<b>{type_names[support_type]}</b>\n\n"
        "Опишите вашу проблему или вопрос подробно.\n\n"
        "Администратор ответит вам в ближайшее время."
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cancel_support_handler(callback: CallbackQuery, state: FSMContext):
    """Handle support cancellation"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Создание обращения отменено.",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()


@router.message(SupportStates.waiting_for_message, F.document)
async def support_document_rejected(message: Message, state: FSMContext):
    """Inform user that documents are not supported in support messages"""
    await message.answer(
        "⚠️ Прикрепление файлов в обращениях пока не поддерживается.\n\n"
        "Пожалуйста, опишите вашу проблему текстом.\n"
        "Если нужно отправить изображение на обработку, отмените создание обращения.",
        reply_markup=get_cancel_keyboard()
    )


@router.message(SupportStates.waiting_for_message, F.text)
async def process_support_message(message: Message, state: FSMContext):
    """Process support message"""
    data = await state.get_data()
    support_type = data.get('support_type', 'general')

    # Validate message
    if len(message.text) < 10:
        await message.answer(
            "❌ Сообщение слишком короткое.\n\n"
            "Пожалуйста, опишите вашу проблему подробнее (минимум 10 символов)."
        )
        return

    if len(message.text) > 1000:
        await message.answer(
            "❌ Сообщение слишком длинное.\n\n"
            "Пожалуйста, сократите ваше сообщение до 1000 символов."
        )
        return

    # Create support ticket
    db = get_db()
    async with db.get_session() as session:
        ticket = await create_support_ticket(
            session,
            telegram_id=message.from_user.id,
            message=message.text
        )

        # Notify admins using NotificationService
        await NotificationService.notify_admins_new_support_request(
            bot=message.bot,
            ticket_id=ticket.id,
            user_telegram_id=message.from_user.id,
            username=message.from_user.username,
            message=message.text
        )

    await state.clear()

    await message.answer(
        "✅ Ваше обращение принято!\n\n"
        f"📝 Номер обращения: #{ticket.id}\n\n"
        "Администратор ответит вам в ближайшее время."
    )
