"""
Batch image processing handler for albums and multiple images
"""
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db
from app.database.crud import (
    get_user_balance, check_and_reserve_balance, rollback_balance,
    update_user_stats, save_processed_image, get_or_create_user
)
from app.services.image_processor import ImageProcessor
from app.services.yandex_metrika import metrika_service
from app.keyboards.user_kb import get_support_contact_keyboard, get_buy_package_keyboard
from app.utils.decorators import error_handler

logger = logging.getLogger(__name__)
router = Router()

# Temporary storage for collecting media group images
# Format: {media_group_id: {"images": [...], "timestamp": datetime, "user_id": int}}
media_groups_storage: Dict[str, Dict] = {}

# Shared storage for batch processing data (user_id -> data)
# This is used to pass data from collection phase to confirmation callbacks
batch_data_storage: Dict[int, Dict] = {}

# Lock for media group processing
MEDIA_GROUP_TIMEOUT = 1.0  # seconds to wait for complete album


class BatchProcessingStates(StatesGroup):
    """States for batch processing"""
    waiting_for_confirmation = State()  # Waiting for user to confirm batch processing


class ImageItem:
    """Container for image data"""
    def __init__(self, file_id: str, file_unique_id: str, is_document: bool, mime_type: Optional[str] = None):
        self.file_id = file_id
        self.file_unique_id = file_unique_id
        self.is_document = is_document
        self.mime_type = mime_type


async def cleanup_old_media_groups():
    """Cleanup old media groups from storage"""
    current_time = datetime.now()
    to_delete = []

    for group_id, data in media_groups_storage.items():
        if current_time - data["timestamp"] > timedelta(seconds=10):
            to_delete.append(group_id)

    for group_id in to_delete:
        del media_groups_storage[group_id]
        logger.info(f"Cleaned up old media group: {group_id}")


async def process_media_group_after_timeout(media_group_id: str, user_id: int, bot, state_data_storage: Dict):
    """
    Process media group after timeout (when all images are collected)

    Args:
        media_group_id: ID of media group
        user_id: User ID
        bot: Bot instance
        state_data_storage: Shared storage dict to pass data between handlers
    """
    await asyncio.sleep(MEDIA_GROUP_TIMEOUT)

    if media_group_id not in media_groups_storage:
        return

    group_data = media_groups_storage.pop(media_group_id)
    images = group_data["images"]

    logger.info(f"Processing media group {media_group_id} with {len(images)} images for user {user_id}")

    # Filter only images (skip videos, documents that are not images)
    valid_images = []
    for img in images:
        if img.is_document:
            # Check if document is an image
            if img.mime_type and img.mime_type.startswith('image/'):
                valid_images.append(img)
        else:
            # Photo
            valid_images.append(img)

    if not valid_images:
        await bot.send_message(
            user_id,
            "⚠️ <b>В альбоме нет изображений</b>\n\n"
            "Отправьте изображения для обработки.",
            parse_mode="HTML"
        )
        return

    # Get user balance
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, user_id)

    total_images = len(valid_images)
    available_images = balance['total']

    # Check if user has enough balance
    if available_images == 0:
        await bot.send_message(
            user_id,
            f"❌ <b>Недостаточно обработок!</b>\n\n"
            f"📸 Изображений для обработки: <b>{total_images}</b>\n"
            f"💎 Ваш баланс: <b>0</b>\n\n"
            f"Купите пакет для продолжения работы.",
            parse_mode="HTML",
            reply_markup=get_buy_package_keyboard()
        )
        return

    # Prepare confirmation message
    if available_images >= total_images:
        # Can process all images
        message_text = (
            f"📦 <b>Пакетная обработка</b>\n\n"
            f"📸 Изображений для обработки: <b>{total_images}</b>\n"
            f"💎 Ваш баланс: <b>{available_images}</b>\n\n"
            f"✅ Хватит на все изображения!\n\n"
            f"Спишется <b>{total_images}</b> обработок.\n"
            f"После обработки останется: <b>{available_images - total_images}</b>\n\n"
            f"Начать пакетную обработку?"
        )

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Начать", callback_data=f"batch_confirm:{media_group_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="batch_cancel")
            ]
        ])
    else:
        # Not enough for all images
        message_text = (
            f"📦 <b>Пакетная обработка</b>\n\n"
            f"📸 Изображений для обработки: <b>{total_images}</b>\n"
            f"💎 Ваш баланс: <b>{available_images}</b>\n\n"
            f"⚠️ <b>Недостаточно обработок для всех изображений!</b>\n\n"
            f"Варианты:\n"
            f"• Обработать первые <b>{available_images}</b> изображений\n"
            f"• Купить пакет и обработать все\n\n"
            f"Что выбираете?"
        )

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"✅ Обработать {available_images} шт.",
                callback_data=f"batch_partial:{media_group_id}"
            )],
            [InlineKeyboardButton(
                text="💎 Купить пакет",
                callback_data="show_packages"
            )],
            [InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="batch_cancel"
            )]
        ])

    # Store data in shared storage (will be retrieved by callback handlers with FSMContext)
    state_data_storage[user_id] = {
        "batch_images": [
            {
                "file_id": img.file_id,
                "file_unique_id": img.file_unique_id,
                "is_document": img.is_document
            }
            for img in valid_images
        ],
        "batch_total": total_images,
        "batch_available": available_images
    }

    await bot.send_message(
        user_id,
        message_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.message(F.photo & F.media_group_id)
@router.message(F.document & F.media_group_id)
@error_handler
async def collect_media_group_handler(message: Message):
    """Collect images from media group (album)"""
    media_group_id = message.media_group_id
    user_id = message.from_user.id

    # Cleanup old groups
    await cleanup_old_media_groups()

    # Initialize storage for this media group if not exists
    if media_group_id not in media_groups_storage:
        media_groups_storage[media_group_id] = {
            "images": [],
            "timestamp": datetime.now(),
            "user_id": user_id,
            "task": None
        }

        # Schedule processing after timeout
        task = asyncio.create_task(
            process_media_group_after_timeout(media_group_id, user_id, message.bot, batch_data_storage)
        )
        media_groups_storage[media_group_id]["task"] = task

    # Add image to collection
    if message.photo:
        # Photo from album
        photo = message.photo[-1]
        img_item = ImageItem(
            file_id=photo.file_id,
            file_unique_id=photo.file_unique_id,
            is_document=False
        )
        media_groups_storage[media_group_id]["images"].append(img_item)
        logger.info(f"Added photo to media group {media_group_id}")
    elif message.document:
        # Document from album
        img_item = ImageItem(
            file_id=message.document.file_id,
            file_unique_id=message.document.file_unique_id,
            is_document=True,
            mime_type=message.document.mime_type
        )
        media_groups_storage[media_group_id]["images"].append(img_item)
        logger.info(f"Added document to media group {media_group_id}")

    # Update timestamp
    media_groups_storage[media_group_id]["timestamp"] = datetime.now()


@router.callback_query(F.data.startswith("batch_confirm:"))
@error_handler
async def batch_confirm_handler(callback: CallbackQuery, state: FSMContext):
    """Handle batch processing confirmation (process all images)"""
    await callback.answer()

    # Get stored data from shared storage
    user_id = callback.from_user.id
    data = batch_data_storage.get(user_id, {})
    batch_images = data.get("batch_images", [])

    if not batch_images:
        await callback.message.edit_text(
            "❌ Данные пакетной обработки не найдены.\n\n"
            "Попробуйте отправить изображения снова.",
            parse_mode="HTML"
        )
        # Clear storage
        batch_data_storage.pop(user_id, None)
        return

    # Start processing
    await callback.message.edit_text(
        f"🔄 <b>Начинаю пакетную обработку...</b>\n\n"
        f"📸 Обрабатываю {len(batch_images)} изображений\n\n"
        f"⏳ Пожалуйста, подождите...",
        parse_mode="HTML"
    )

    # Process images one by one
    await process_batch_images(
        callback.message,
        user_id,
        batch_images,
        len(batch_images)
    )

    # Clear storage after processing
    batch_data_storage.pop(user_id, None)


@router.callback_query(F.data.startswith("batch_partial:"))
@error_handler
async def batch_partial_handler(callback: CallbackQuery, state: FSMContext):
    """Handle partial batch processing (process only available images)"""
    await callback.answer()

    # Get stored data from shared storage
    user_id = callback.from_user.id
    data = batch_data_storage.get(user_id, {})
    batch_images = data.get("batch_images", [])
    batch_available = data.get("batch_available", 0)

    if not batch_images or batch_available == 0:
        await callback.message.edit_text(
            "❌ Данные пакетной обработки не найдены.\n\n"
            "Попробуйте отправить изображения снова.",
            parse_mode="HTML"
        )
        # Clear storage
        batch_data_storage.pop(user_id, None)
        return

    # Limit to available images
    images_to_process = batch_images[:batch_available]

    # Start processing
    await callback.message.edit_text(
        f"🔄 <b>Начинаю пакетную обработку...</b>\n\n"
        f"📸 Обрабатываю {len(images_to_process)} из {len(batch_images)} изображений\n\n"
        f"⏳ Пожалуйста, подождите...",
        parse_mode="HTML"
    )

    # Process images one by one
    await process_batch_images(
        message,
        user_id,
        images_to_process,
        len(batch_images)
    )

    # Clear storage after processing
    batch_data_storage.pop(user_id, None)


@router.callback_query(F.data == "batch_cancel")
@error_handler
async def batch_cancel_handler(callback: CallbackQuery, state: FSMContext):
    """Handle batch processing cancellation"""
    await callback.answer("Пакетная обработка отменена")
    await callback.message.edit_text(
        "❌ <b>Пакетная обработка отменена</b>\n\n"
        "Отправьте изображения снова, если передумаете.",
        parse_mode="HTML"
    )
    # Clear storage
    batch_data_storage.pop(callback.from_user.id, None)


async def process_batch_images(message: Message, user_id: int, images: List[Dict], total_images: int):
    """
    Process batch of images one by one with delays

    Args:
        message: Message to send updates to
        user_id: User ID
        images: List of image dicts with file_id, file_unique_id, is_document
        total_images: Total number of images in original batch (for reporting)
    """
    db = get_db()
    processor = ImageProcessor()

    processed_count = 0
    failed_count = 0

    # Get full user object once before the loop
    async with db.get_session() as session:
        user = await get_or_create_user(session, user_id)

    for idx, img_data in enumerate(images, 1):
        try:
            # Get current balance
            async with db.get_session() as session:
                balance = await get_user_balance(session, user_id)

            if balance['total'] == 0:
                # No more images available
                await message.answer(
                    f"⚠️ <b>Баланс закончился!</b>\n\n"
                    f"✅ Обработано: {processed_count} из {len(images)}\n"
                    f"❌ Пропущено: {len(images) - processed_count}\n\n"
                    f"💎 Купите пакет для продолжения работы.",
                    parse_mode="HTML",
                    reply_markup=get_buy_package_keyboard()
                )
                break

            # Reserve balance
            async with db.get_session() as session:
                success, is_free_image = await check_and_reserve_balance(session, user_id)

                if not success:
                    await message.answer(
                        f"⚠️ <b>Не удалось зарезервировать баланс!</b>\n\n"
                        f"✅ Обработано: {processed_count} из {len(images)}\n"
                        f"❌ Пропущено: {len(images) - processed_count}",
                        parse_mode="HTML"
                    )
                    break

            # Download image
            file = await message.bot.get_file(img_data["file_id"])
            file_bytes = await message.bot.download_file(file.file_path)
            image_bytes = file_bytes.read()

            # Process image
            use_transparent = img_data["is_document"]
            result = await processor.process_image(
                image_bytes=image_bytes,
                bot=message.bot,
                user=user,
                use_transparent_bg=use_transparent
            )

            if result['success']:
                # Send result
                output_file = BufferedInputFile(
                    result['image_bytes'],
                    filename=f"batch_{idx}_{img_data['file_unique_id']}.png"
                )

                # Save processing record
                async with db.get_session() as session:
                    # Update stats and check if this is first image
                    is_first_image_processed, db_user_id = await update_user_stats(session, user_id)

                    # Track first_image event to Metrika if this is the first generation
                    if is_first_image_processed:
                        await metrika_service.track_event(
                            session=session,
                            user_id=db_user_id,
                            event_type="first_image"
                        )
                        logger.info(f"First image processed for user {user_id}")

                    await save_processed_image(
                        session,
                        user_id,
                        img_data["file_id"],
                        "batch_processed",
                        "Batch processing",
                        is_free_image
                    )

                    # Get updated balance
                    new_balance = await get_user_balance(session, user_id)

                remaining = len(images) - idx
                caption = (
                    f"✅ <b>Изображение {idx}/{len(images)}</b>\n\n"
                    f"{'PNG с прозрачным фоном' if use_transparent else 'На белом фоне'}\n"
                    f"💎 Осталось обработок: <b>{new_balance['total']}</b>\n"
                )

                if remaining > 0:
                    caption += f"⏳ Осталось обработать: <b>{remaining}</b>"

                # Send as document or photo depending on type
                if use_transparent:
                    await message.answer_document(output_file, caption=caption, parse_mode="HTML")
                else:
                    await message.answer_photo(output_file, caption=caption, parse_mode="HTML")

                processed_count += 1

                # Pause between images (2-3 seconds)
                if idx < len(images):
                    await asyncio.sleep(2.5)

            else:
                # Processing failed - rollback balance
                async with db.get_session() as session:
                    await rollback_balance(session, user_id, is_free_image)

                failed_count += 1
                logger.error(f"Failed to process image {idx}/{len(images)}: {result['error']}")

                # Continue with next image
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error processing image {idx}/{len(images)}: {str(e)}", exc_info=True)
            failed_count += 1

            # Try to rollback if balance was reserved
            try:
                if 'is_free_image' in locals():
                    async with db.get_session() as session:
                        await rollback_balance(session, user_id, is_free_image)
            except:
                pass

            await asyncio.sleep(1)

    # Send final summary
    summary_text = f"🎉 <b>Пакетная обработка завершена!</b>\n\n"
    summary_text += f"✅ Успешно обработано: <b>{processed_count}</b>\n"

    if failed_count > 0:
        summary_text += f"❌ Ошибок: <b>{failed_count}</b>\n"

    # Get final balance
    async with db.get_session() as session:
        final_balance = await get_user_balance(session, user_id)

    summary_text += f"\n💎 Осталось обработок: <b>{final_balance['total']}</b>"

    if final_balance['total'] == 0:
        summary_text += "\n\n⚠️ Баланс закончился! Купите пакет для продолжения."
        await message.answer(summary_text, parse_mode="HTML", reply_markup=get_buy_package_keyboard())
    elif final_balance['total'] <= 3:
        summary_text += "\n\n💡 Рекомендуем пополнить баланс!"
        await message.answer(summary_text, parse_mode="HTML")
    else:
        await message.answer(summary_text, parse_mode="HTML")

