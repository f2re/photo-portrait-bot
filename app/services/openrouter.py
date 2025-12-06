import aiohttp
import base64
import logging
from io import BytesIO
from typing import Dict
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


# Passport photo generation prompt from plan
PASSPORT_PHOTO_PROMPT = """You are a professional passport photo specialist. Transform this portrait into a perfect
passport/ID photo that meets international biometric passport photo standards.

STRICT REQUIREMENTS:
1. Background: Pure white (#FFFFFF) background - completely uniform, no shadows, no gradients
2. Lighting: Even, diffused lighting on face - no harsh shadows, no glare
3. Composition:
   - Face centered in frame
   - Head and shoulders visible
   - Face occupies 70-80% of photo height
   - Eyes at 2/3 height from bottom
4. Subject Requirements:
   - Neutral facial expression (mouth closed)
   - Eyes open, looking directly at camera
   - No smile (slight natural expression acceptable)
   - Face fully visible, no hair covering eyes or face
   - No glasses glare (if wearing glasses)
5. Technical Quality:
   - High resolution and sharp focus
   - Natural skin tones (no filters, no beauty effects)
   - Proper exposure (not too bright, not too dark)
   - No red-eye effect
   - Professional quality suitable for printing

Output format: High-quality passport photo that would be accepted by any government agency
worldwide (USA, EU, Russia, etc.). This photo must meet ICAO (International Civil Aviation
Organization) biometric passport photo standards."""


class OpenRouterService:
    """Service for generating official passport photos using OpenRouter API"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        # Use Gemini 2.5 Flash Image for image generation capabilities
        self.model = settings.OPENROUTER_MODEL or "google/gemini-2.5-flash-image-preview"
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def generate_passport_photo(self, image_bytes: bytes) -> Dict:
        """
        Generate official passport photo from portrait using OpenRouter API

        Args:
            image_bytes: Original portrait image bytes

        Returns:
            dict with keys: success (bool), image_bytes (bytes), error (str)
        """
        try:
            # Convert image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')

            # Detect image format
            image = Image.open(BytesIO(image_bytes))
            image_format = image.format.lower() if image.format else 'jpeg'
            mime_type = f"image/{image_format}"

            # Prepare request with modalities for image generation
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://photo-portrait-bot.com",  # Bot reference
                "X-Title": "Photo Portrait Bot"  # Bot name
            }

            payload = {
                "model": self.model,
                "modalities": ["text", "image"],  # Enable image output
                "stream": False,  # Explicitly disable streaming for image responses
                "messages": [
                    {
                        "role": "system",
                        "content": PASSPORT_PHOTO_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Transform this portrait into a professional passport photo following all requirements."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.2,
                "top_p": 0.95,
                "max_tokens": 2048,
                "frequency_penalty": 0,
                "presence_penalty": 0,
            }

            logger.info(f"Sending passport photo request to OpenRouter API with model: {self.model}")

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"OpenRouter API response received successfully")
                        logger.debug(f"Response keys: {result.keys()}")

                        # Extract image from response
                        try:
                            choices = result.get('choices', [])
                            if not choices:
                                logger.error("No choices in API response")
                                raise ValueError("No choices in API response")

                            message = choices[0].get('message', {})

                            # Check for images field (primary format for image generation)
                            images = message.get('images', [])

                            if images:
                                # Images are returned as base64 data URLs or URLs
                                image_data = images[0]

                                # Handle dict format
                                if isinstance(image_data, dict):
                                    # Try different possible keys for the image URL
                                    image_url = (image_data.get('url') or
                                                image_data.get('data') or
                                                image_data.get('image_url'))

                                    # If image_url is also a dict, extract the url from it
                                    if isinstance(image_url, dict):
                                        image_url = image_url.get('url') or image_url.get('data')

                                    if image_url:
                                        image_data = image_url
                                    else:
                                        raise ValueError(f"Unexpected dict format: {image_data.keys()}")

                                # Handle data URL format: data:image/png;base64,xxxx
                                if isinstance(image_data, str):
                                    if image_data.startswith('data:'):
                                        # Extract base64 part
                                        base64_part = image_data.split(',', 1)[1] if ',' in image_data else image_data
                                        processed_image_bytes = base64.b64decode(base64_part)
                                    elif image_data.startswith('http'):
                                        # It's a URL - need to download
                                        logger.info(f"Downloading image from URL: {image_data[:50]}...")
                                        async with session.get(image_data) as img_response:
                                            if img_response.status == 200:
                                                processed_image_bytes = await img_response.read()
                                            else:
                                                raise ValueError(f"Failed to download image from URL: {img_response.status}")
                                    else:
                                        # Assume it's raw base64 without prefix
                                        processed_image_bytes = base64.b64decode(image_data)
                                else:
                                    raise ValueError(f"Unexpected image data type: {type(image_data)}")

                                # Validate it's a valid image
                                Image.open(BytesIO(processed_image_bytes))

                                logger.info("Successfully generated passport photo from API response")

                                return {
                                    "success": True,
                                    "image_bytes": processed_image_bytes,
                                    "error": None
                                }
                            else:
                                # Fallback: check content field for base64 images
                                content = message.get('content', '')
                                if 'base64' in content or content.startswith('data:'):
                                    # Try to extract base64 from content
                                    if content.startswith('data:'):
                                        base64_part = content.split(',', 1)[1] if ',' in content else content
                                    else:
                                        base64_part = content

                                    processed_image_bytes = base64.b64decode(base64_part)
                                    Image.open(BytesIO(processed_image_bytes))  # Validate

                                    return {
                                        "success": True,
                                        "image_bytes": processed_image_bytes,
                                        "error": None
                                    }
                                else:
                                    raise ValueError("No image data found in API response")

                        except Exception as extract_error:
                            logger.error(f"Failed to extract image from response: {str(extract_error)}", exc_info=True)

                            return {
                                "success": False,
                                "image_bytes": None,
                                "error": f"Failed to extract image: {str(extract_error)}"
                            }

                    else:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                        return {
                            "success": False,
                            "image_bytes": None,
                            "error": f"API error: {response.status} - {error_text}"
                        }

        except Exception as e:
            logger.error(f"Error in generate_passport_photo: {str(e)}", exc_info=True)
            return {
                "success": False,
                "image_bytes": None,
                "error": str(e)
            }

    async def test_connection(self) -> bool:
        """Test OpenRouter API connection"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": "test"
                    }
                ],
                "max_tokens": 10
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    return response.status == 200

        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False
