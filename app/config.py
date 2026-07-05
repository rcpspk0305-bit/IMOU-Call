import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

try:
    import streamlit as st
except ImportError:
    st = None

def get_secret(section: str, key: str, default: str = "") -> str:
    """
    Retrieves secret from streamlit st.secrets (supporting nested [section] key structures)
    or falls back to environment variables.
    """
    if st is not None:
        try:
            # 1. Try nested structure: st.secrets["section"]["key"]
            if section in st.secrets and key in st.secrets[section]:
                return st.secrets[section][key]
        except Exception:
            pass

        try:
            # 2. Try flat uppercase: st.secrets["SECTION_KEY"]
            flat_key_upper = f"{section.upper()}_{key.upper()}"
            if flat_key_upper in st.secrets:
                return st.secrets[flat_key_upper]
        except Exception:
            pass

        try:
            # 3. Try flat key or flat uppercase key: st.secrets["key"] or st.secrets["KEY"]
            if key in st.secrets:
                return st.secrets[key]
            if key.upper() in st.secrets:
                return st.secrets[key.upper()]
        except Exception:
            pass

    # 4. Fallback to environment variables
    env_key = f"{section.upper()}_{key.upper()}"
    val = os.getenv(env_key)
    if val is not None:
        return val

    val_direct = os.getenv(key.upper())
    if val_direct is not None:
        return val_direct

    return default

class Config:
    """
    Application Configuration loaded from st.secrets (Streamlit toml) or Environment variables.
    Embedded constants for Exotel, Imou, and Telegram Integrations.
    """
    EXOTEL_SUBDOMAIN = get_secret("exotel", "subdomain", "api.in.exotel.com")
    EXOTEL_SID = get_secret("exotel", "sid", "YOUR_EXOTEL_ACCOUNT_SID")
    EXOTEL_KEY = get_secret("exotel", "key", "YOUR_EXOTEL_API_KEY")
    EXOTEL_TOKEN = get_secret("exotel", "token", "YOUR_EXOTEL_API_TOKEN")
    FROM_NUMBER = get_secret("exotel", "from_number", "YOUR_PERSONAL_VERIFIED_MOBILE")
    CALLER_ID = get_secret("exotel", "caller_id", "YOUR_EXOPHONE_VIRTUAL_NUMBER")
    APP_ID = get_secret("exotel", "app_id", "YOUR_EXOTEL_APP_ID")

    # Agent Lockout Setting (default: 1800 seconds / 30 minutes)
    EXOTEL_CALL_LOCKOUT_SECONDS = int(get_secret("exotel", "call_lockout_seconds", "1800"))

    # Imou OpenAPI Settings (Optimized default polling interval: 600s / 10 mins to protect quota)
    IMOU_APP_ID = get_secret("imou", "app_id", "YOUR_IMOU_APP_ID")
    IMOU_APP_SECRET = get_secret("imou", "app_secret", "YOUR_IMOU_APP_SECRET")
    IMOU_DEVICE_ID = get_secret("imou", "device_id", "YOUR_IMOU_DEVICE_ID")
    IMOU_POLL_INTERVAL_SECONDS = int(get_secret("imou", "poll_interval_seconds", "600"))
    IMOU_API_BASE_URL = get_secret("imou", "api_base_url", "https://openapi-sg.easy4ip.com/openapi")

    # Telegram Bot Control Plane Credentials
    TELEGRAM_BOT_TOKEN = get_secret("telegram", "bot_token", "YOUR_TELEGRAM_BOT_TOKEN")
    TELEGRAM_ALLOWED_CHAT_ID = get_secret("telegram", "allowed_chat_id", "YOUR_TELEGRAM_ALLOWED_CHAT_ID")

    # Safety buffer delay in seconds (default: 180 seconds / 3 minutes)
    BUFFER_DELAY_SECONDS = int(get_secret("general", "buffer_delay_seconds", "180"))

    # Flask settings (no longer running server, but kept as boolean flag)
    DEBUG = get_secret("flask", "env", "") == "development"

    # Supabase Configuration
    SUPABASE_URL = get_secret("supabase", "url", "YOUR_SUPABASE_URL")
    SUPABASE_KEY = get_secret("supabase", "key", "YOUR_SUPABASE_SERVICE_ROLE_KEY")

