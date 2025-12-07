from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    BOT_USERNAME: str  # Bot username without @ (e.g., "mybot")
    ADMIN_IDS: str

    # Database - can use either DATABASE_URL or individual DB_* variables
    DATABASE_URL: Optional[str] = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "bg_removal_bot"
    DB_USER: str = "bgremove_user"
    DB_PASSWORD: str = ""

    # Bria API (for transparent backgrounds)
    BRIA_API_KEY: str
    BRIA_API_URL: str = "https://engine.prod.bria-api.com/v2"

    # OpenRouter API (for white backgrounds)
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: Optional[str] = "google/gemini-2.5-flash-image-preview"

    # YooKassa (ЮКасса)
    YOOKASSA_SHOP_ID: str
    YOOKASSA_SECRET_KEY: str
    # IMPORTANT: Replace 'your_bot' with your actual bot username (e.g., https://t.me/bg_remove_bot)
    # This URL is shown to users after payment. For Telegram bots, use your bot's t.me link
    YOOKASSA_RETURN_URL: str = "https://t.me/your_bot"

    # Package 1 Configuration
    PACKAGE_1_NAME: str = "Стартовый"
    PACKAGE_1_IMAGES: int = 5
    PACKAGE_1_PRICE: int = 100

    # Package 2 Configuration
    PACKAGE_2_NAME: str = "Базовый"
    PACKAGE_2_IMAGES: int = 10
    PACKAGE_2_PRICE: int = 180

    # Package 3 Configuration
    PACKAGE_3_NAME: str = "Продвинутый"
    PACKAGE_3_IMAGES: int = 25
    PACKAGE_3_PRICE: int = 400

    # Package 4 Configuration
    PACKAGE_4_NAME: str = "Профессиональный"
    PACKAGE_4_IMAGES: int = 50
    PACKAGE_4_PRICE: int = 750

    # Free images for new users
    FREE_IMAGES_COUNT: int = 3

    # Demo video file_id (upload video to bot to get file_id)
    DEMO_VIDEO_FILE_ID: Optional[str] = None

    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # Yandex Metrika (optional - analytics works without it)
    YANDEX_METRIKA_COUNTER_ID: Optional[str] = None  # Counter ID (e.g., "12345678")
    YANDEX_METRIKA_TOKEN: Optional[str] = None  # OAuth token for API access
    METRIKA_GOAL_START: str = "start_bot"  # Goal name for /start command
    METRIKA_GOAL_FIRST_IMAGE: str = "first_image"  # Goal name for first processed image
    METRIKA_GOAL_PURCHASE: str = "purchase"  # Goal name for package purchase
    METRIKA_UPLOAD_INTERVAL: int = 3600  # Interval in seconds for uploading events (default: 1 hour)

    # Referral Program
    REFERRAL_REWARD_START: int = 5  # Images rewarded when referral clicks /start
    REFERRAL_REWARD_PURCHASE_PERCENT: int = 10  # Percentage of images from referral's purchase (10 = 10%)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def database_url(self) -> str:
        """Get async database URL for PostgreSQL"""
        # If DATABASE_URL is set, use it directly
        if self.DATABASE_URL:
            return self.DATABASE_URL
        # Otherwise, construct from individual components
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def admin_ids_list(self) -> List[int]:
        """Get list of admin telegram IDs"""
        return [int(id.strip()) for id in self.ADMIN_IDS.split(",") if id.strip()]

    @property
    def packages_config(self) -> List[dict]:
        """
        Get list of package configurations from environment variables

        Returns:
            List of dicts with keys: name, images_count, price_rub
        """
        packages = []

        # Package 1
        packages.append({
            "name": self.PACKAGE_1_NAME,
            "images_count": self.PACKAGE_1_IMAGES,
            "price_rub": self.PACKAGE_1_PRICE
        })

        # Package 2
        packages.append({
            "name": self.PACKAGE_2_NAME,
            "images_count": self.PACKAGE_2_IMAGES,
            "price_rub": self.PACKAGE_2_PRICE
        })

        # Package 3
        packages.append({
            "name": self.PACKAGE_3_NAME,
            "images_count": self.PACKAGE_3_IMAGES,
            "price_rub": self.PACKAGE_3_PRICE
        })

        # Package 4
        packages.append({
            "name": self.PACKAGE_4_NAME,
            "images_count": self.PACKAGE_4_IMAGES,
            "price_rub": self.PACKAGE_4_PRICE
        })

        return packages

    @property
    def is_metrika_enabled(self) -> bool:
        """Check if Yandex Metrika is properly configured"""
        return bool(self.YANDEX_METRIKA_COUNTER_ID and self.YANDEX_METRIKA_TOKEN)


# Global settings instance
settings = Settings()
