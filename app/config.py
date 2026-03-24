"""GliceMia configuration — loads from .env and provides defaults."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # AI — primary model + fallback
    AI_MODEL: str = os.getenv("AI_MODEL", "gemini/gemini-2.5-flash")
    AI_FALLBACK_MODEL: str = os.getenv("AI_FALLBACK_MODEL", "")
    AI_TIMEOUT_SECONDS: int = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
    AI_FALLBACK_ENABLED: bool = os.getenv("AI_FALLBACK_ENABLED", "false").lower() == "true"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ALLOWED_USERS: list[int] = [
        int(uid.strip())
        for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
        if uid.strip()
    ]

    # CareLink
    CARELINK_COUNTRY: str = os.getenv("CARELINK_COUNTRY", "it")
    CARELINK_USERNAME: str = os.getenv("CARELINK_USERNAME", "")
    CARELINK_PASSWORD: str = os.getenv("CARELINK_PASSWORD", "")
    CARELINK_POLL_INTERVAL: int = int(os.getenv("CARELINK_POLL_INTERVAL", "300"))

    # Database
    DB_PASSPHRASE: str = os.getenv("DB_PASSPHRASE", "")
    DB_PATH: Path = Path(os.getenv("DB_PATH", "glicemia.db"))

    # External APIs
    OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
    ORS_API_KEY: str = os.getenv("ORS_API_KEY", "")

    # WebApp
    WEBAPP_PORT: int = int(os.getenv("WEBAPP_PORT", "8443"))
    WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")

    # TTS (Text-to-Speech for voice replies)
    # edge-tts is used by default (free, no key needed)
    # Set TTS_MODEL for LiteLLM TTS fallback (e.g., "openai/tts-1")
    TTS_MODEL: str = os.getenv("TTS_MODEL", "")

    # Language & patient
    LANGUAGE: str = os.getenv("LANGUAGE", "it")
    PATIENT_NAME: str = os.getenv("PATIENT_NAME", "Patient")


settings = Settings()
