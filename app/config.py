"""GliceMia configuration — loads from .env and provides defaults."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # AI — server-wide defaults (per-user overrides stored in DB)
    AI_MODEL: str = os.getenv("AI_MODEL", "gemini/gemini-2.5-flash")
    AI_FALLBACK_MODEL: str = os.getenv("AI_FALLBACK_MODEL", "")
    AI_TIMEOUT_SECONDS: int = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
    AI_FALLBACK_ENABLED: bool = os.getenv("AI_FALLBACK_ENABLED", "false").lower() == "true"
    OLLAMA_API_BASE: str = os.getenv("OLLAMA_API_BASE", "")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Comma-separated Telegram user IDs — bootstrap admin(s). After first run,
    # authorization is managed in the DB via UserAccount.is_active.
    TELEGRAM_ALLOWED_USERS: list[int] = [
        int(uid.strip())
        for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
        if uid.strip()
    ]

    # Server-wide API keys (per-user keys in DB take precedence when set)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
    ORS_API_KEY: str = os.getenv("ORS_API_KEY", "")

    # Database
    DB_PASSPHRASE: str = os.getenv("DB_PASSPHRASE", "")
    DB_PATH: Path = Path(os.getenv("DB_PATH", "glicemia.db"))

    # WebApp
    WEBAPP_PORT: int = int(os.getenv("WEBAPP_PORT", "8443"))
    WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")

    # TTS (Text-to-Speech for voice replies)
    TTS_MODEL: str = os.getenv("TTS_MODEL", "")


settings = Settings()
