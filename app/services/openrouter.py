import aiohttp
import base64
import logging
from io import BytesIO
from typing import Dict
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


# Passport photo generation prompt
PASSPORT_PHOTO_PROMPT = """# Role: Professional Portrait Photographer
# Task: Generate an ultra-realistic 8k corporate headshot based on an input reference image.
# Compliance: Ensure subject consent regarding likeness usage (Civil Code of the RF, Art. 152.1).

## 1. Subject & Identity Preservation
- **Action:** Analyze the facial structure, landmarks, and skin tone of the source image.
- **Requirement:** Maintain High Identity Fidelity. The output face must be a recognizable, photorealistic reconstruction of the source subject.
- **Expression:** Project a confident, approachable, and professional demeanor (slight smile, engaged eyes).

## 2. Attire & Styling
- **Suit:** Premium navy blue wool business suit with visible fabric texture. Fit should be tailored and modern.
- **Shirt:** Crisp white spread-collar dress shirt.
- **Texture:** Ensure realistic fabric fold physics; avoid "melted" or "painted" looking clothing.

## 3. Environment & Background
- **Setting:** High-end photography studio.
- **Backdrop:** Clean, solid charcoal gray (#36454F).
- **Effect:** Apply a soft vignette (darker edges) to center focus on the subject.
- **Composition:** Standard head-and-shoulders corporate portrait framing.

## 4. Technical Photography Specs
- **Camera:** Sony A7III simulation.
- **Lens:** 85mm f/1.4 GM (Portrait Telephoto).
- **Depth of Field:** Shallow aperture to create smooth background bokeh, keeping the eyes and face razor-sharp.
- **Lighting Setup:**
  - *Key Light:* Soft, diffused Rembrandt-style lighting from the left.
  - *Rim Light:* Subtle, cool-toned backlighting to separate the navy suit from the dark gray background.
  - *Fill:* Minimal fill to maintain professional contrast and dimension.

## 5. Quality Boosters
- **Skin Details:** Render natural skin porosity, micro-texture, and imperfections. Avoid "airbrushed" or "wax figure" skin.
- **Eyes:** Add realistic corneal reflections (catchlights) from the studio softbox.

## ⛔ Negative Prompt (Exclusions)
[cartoon, illustration, 3d render, painting, drawing, plastic skin, oversaturated, deformed iris, mutated hands, extra limbs, blur, noise, watermark, text, bad anatomy, distorted features, casual clothing, t-shirt, bright background]
"""


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
                                "text": "Keep the facial features of the person in the uploaded image exactly consistent . Dress them in a professional navy blue business suit with a white shirt, similar to the reference image. Background : Place the subject against a clean, solid dark gray studio photography backdrop . The background should have a subtle gradient , slightly lighter behind the subject and darker towards the edges (vignette effect). There should be no other objects. Photography Style : Shot on a Sony A7III with an 85mm f/1.4 lens , creating a flattering portrait compression. Lighting : Use a classic three-point lighting setup . The main key light should create soft, defining shadows on the face. A subtle rim light should separate the subject's shoulders and hair from the dark background. Crucial Details : Render natural skin texture with visible pores , not an airbrushed look. Add natural catchlights to the eyes . The fabric of the suit should show a subtle wool texture.Final image should be an ultra-realistic, 8k professional headshot."
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
                "response_modalities": ["IMAGE"],  # Указываем, что нужно изображение
                "image_config": {
                    "aspect_ratio": "3:4"  # Портретная ориентация
                },
                "temperature": 0.6,
                "top_p": 0.95,
                "max_tokens": 5048,
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
                                    image_url = (image_data.get('url') or
                                                image_data.get('data') or
                                                image_data.get('image_url'))
                                    
                                    if isinstance(image_url, dict):
                                        image_url = image_url.get('url') or image_url.get('data')

                                    if image_url:
                                        image_data = image_url
                                    else:
                                        raise ValueError(f"Unexpected dict format: {image_data.keys()}")

                                # Handle data URL format or URL
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