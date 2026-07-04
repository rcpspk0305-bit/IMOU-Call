import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

class Config:
    """
    Application Configuration loaded from Environment variables.
    Embedded constants for Exotel, Imou, and Telegram Integrations.
    """
    EXOTEL_SUBDOMAIN = os.getenv("EXOTEL_SUBDOMAIN", "api.in.exotel.com")
    EXOTEL_SID = os.getenv("EXOTEL_SID", "YOUR_EXOTEL_ACCOUNT_SID")
    EXOTEL_KEY = os.getenv("EXOTEL_KEY", "YOUR_EXOTEL_API_KEY")
    EXOTEL_TOKEN = os.getenv("EXOTEL_TOKEN", "YOUR_EXOTEL_API_TOKEN")
    FROM_NUMBER = os.getenv("FROM_NUMBER", "YOUR_PERSONAL_VERIFIED_MOBILE")
    CALLER_ID = os.getenv("CALLER_ID", "YOUR_EXOPHONE_VIRTUAL_NUMBER")
    APP_ID = os.getenv("APP_ID", "YOUR_EXOTEL_APP_ID")

    # Agent Lockout Setting (default: 1800 seconds / 30 minutes)
    EXOTEL_CALL_LOCKOUT_SECONDS = int(os.getenv("EXOTEL_CALL_LOCKOUT_SECONDS", "1800"))

    # Imou OpenAPI Settings (Optimized default polling interval: 600s / 10 mins to protect quota)
    IMOU_APP_ID = os.getenv("IMOU_APP_ID", "YOUR_IMOU_APP_ID")
    IMOU_APP_SECRET = os.getenv("IMOU_APP_SECRET", "YOUR_IMOU_APP_SECRET")
    IMOU_DEVICE_ID = os.getenv("IMOU_DEVICE_ID", "YOUR_IMOU_DEVICE_ID")
    IMOU_POLL_INTERVAL_SECONDS = int(os.getenv("IMOU_POLL_INTERVAL_SECONDS", "600"))
    IMOU_API_BASE_URL = os.getenv("IMOU_API_BASE_URL", "https://openapi.easy4ip.com/openapi")

    # Telegram Bot Control Plane Credentials
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
    TELEGRAM_ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "YOUR_TELEGRAM_ALLOWED_CHAT_ID")

    # Safety buffer delay in seconds (default: 180 seconds / 3 minutes)
    BUFFER_DELAY_SECONDS = int(os.getenv("BUFFER_DELAY_SECONDS", "180"))

    # Flask settings
    DEBUG = os.getenv("FLASK_ENV") == "development"

    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "YOUR_SUPABASE_SERVICE_ROLE_KEY")
