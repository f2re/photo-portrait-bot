import logging
from io import BytesIO
from typing import Dict
from PIL import Image
from aiogram import Bot

from app.database.models import User
from app.services.openrouter import OpenRouterService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Service for processing images (Portrait Generation)"""

    def __init__(self):
        self.openrouter_service = OpenRouterService()

    def _convert_webp_to_png(self, image_bytes: bytes) -> bytes:
        """
        Convert WebP image to PNG format in memory (on-the-fly conversion).

        Args:
            image_bytes: WebP image bytes

        Returns:
            PNG image bytes
        """
        try:
            img = Image.open(BytesIO(image_bytes))

            # Convert to RGB if needed (some WebP images have RGBA mode)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Keep alpha channel for transparent images
                if img.mode == 'P' and 'transparency' in img.info:
                    img = img.convert('RGBA')
                elif img.mode != 'RGBA':
                    img = img.convert('RGBA')
            elif img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')

            # Save as PNG to BytesIO (in memory, no disk I/O)
            output = BytesIO()
            img.save(output, format='PNG', optimize=True)
            output.seek(0)

            png_bytes = output.getvalue()
            logger.info(f"Converted WebP to PNG: {len(image_bytes)} bytes → {len(png_bytes)} bytes")
            return png_bytes

        except Exception as e:
            logger.error(f"Error converting WebP to PNG: {str(e)}")
            raise

    async def process_image(
        self,
        image_bytes: bytes,
        bot: Bot,
        user: User,
        use_transparent_bg: bool = False  # Kept for compatibility with handler signature, but ignored or used for quality
    ) -> Dict:
        """
        Process image to generate passport photo

        Args:
            image_bytes: Input image bytes
            bot: Bot instance for sending notifications
            user: User object
            use_transparent_bg: Ignored in this version (Passport photos usually white bg)

        Returns:
            dict with keys: success (bool), image_bytes (bytes), error (str)
        """
        service_name = "OpenRouter"
        try:
            logger.info(f"Processing image for user {user.telegram_id}")

            # Validate input image and convert WebP if needed
            try:
                img = Image.open(BytesIO(image_bytes))
                width, height = img.size
                original_format = img.format
                logger.info(f"Input image: {width}x{height}, format: {original_format}, mode: {img.mode}")

                # Convert WebP to PNG on-the-fly (in memory)
                if original_format and original_format.upper() == 'WEBP':
                    logger.info("WebP format detected, converting to PNG...")
                    image_bytes = self._convert_webp_to_png(image_bytes)
                    logger.info("WebP → PNG conversion completed")

            except Exception as e:
                logger.error(f"Invalid image format for user {user.telegram_id}: {str(e)}")
                return {
                    "success": False,
                    "image_bytes": None,
                    "error": "Неподдерживаемый формат изображения"
                }

            # Use OpenRouter for passport photo generation
            logger.info(f"Using OpenRouter for passport photo generation (user: {user.telegram_id})")
            result = await self.openrouter_service.generate_passport_photo(image_bytes)

            if result["success"]:
                logger.info(f"Image processing completed successfully for user {user.telegram_id}")
            else:
                error_message = result.get("error", "Unknown error")
                logger.error(f"Image processing failed for user {user.telegram_id} with service {service_name}: {error_message}")
                # Notify admins on failure
                await NotificationService.notify_admins_processing_error(
                    bot=bot,
                    user_telegram_id=user.telegram_id,
                    username=user.username,
                    service_name=service_name,
                    error_message=error_message
                )

            return result

        except Exception as e:
            error_message = str(e)
            logger.error(f"Critical error in process_image for user {user.telegram_id} with service {service_name}: {error_message}", exc_info=True)
            # Notify admins on critical failure
            await NotificationService.notify_admins_processing_error(
                bot=bot,
                user_telegram_id=user.telegram_id,
                username=user.username,
                service_name=service_name,
                error_message=error_message
            )
            return {
                "success": False,
                "image_bytes": None,
                "error": "Произошла внутренняя ошибка. Мы уже уведомлены и скоро все исправим."
            }

    async def test_service(self) -> bool:
        """Test if API service is available"""
        return await self.openrouter_service.test_connection()
