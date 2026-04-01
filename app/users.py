"""User account management — lookup, token tracking, model access, admin operations."""

import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models import UserAccount

log = logging.getLogger(__name__)


def get_user(session: Session, telegram_user_id: int) -> UserAccount | None:
    """Look up an active user by Telegram ID. Returns None if not found or inactive."""
    user = session.get(UserAccount, telegram_user_id)
    if user and not user.is_active:
        return None
    return user


def get_all_active_users(session: Session) -> list[UserAccount]:
    """Return all active users."""
    return session.query(UserAccount).filter(UserAccount.is_active.is_(True)).all()


def create_user(
    session: Session,
    telegram_user_id: int,
    patient_name: str,
    language: str = "it",
    is_admin: bool = False,
) -> UserAccount:
    """Create a new user account."""
    user = UserAccount(
        telegram_user_id=telegram_user_id,
        patient_name=patient_name,
        language=language,
        is_admin=is_admin,
    )
    session.add(user)
    session.commit()
    log.info("Created user %s (tg_id=%d, admin=%s)", patient_name, telegram_user_id, is_admin)
    return user


# --- Token tracking ---

def check_token_limit(user: UserAccount) -> tuple[bool, str]:
    """Check if user is within their token limits. Returns (allowed, reason).
    A limit of 0 means unlimited."""
    _maybe_reset_counters(user)

    if user.daily_token_limit > 0 and user.tokens_used_today >= user.daily_token_limit:
        return False, "daily"
    if user.monthly_token_limit > 0 and user.tokens_used_month >= user.monthly_token_limit:
        return False, "monthly"
    return True, ""


def record_token_usage(session: Session, user: UserAccount, tokens: int) -> None:
    """Add token usage to user's daily and monthly counters."""
    _maybe_reset_counters(user)
    user.tokens_used_today += tokens
    user.tokens_used_month += tokens
    session.commit()


def _maybe_reset_counters(user: UserAccount) -> None:
    """Reset daily/monthly counters if the period has rolled over."""
    today = date.today()

    if user.token_reset_date is None or user.token_reset_date < today:
        user.tokens_used_today = 0
        user.token_reset_date = today

    first_of_month = today.replace(day=1)
    if user.token_reset_month is None or user.token_reset_month < first_of_month:
        user.tokens_used_month = 0
        user.token_reset_month = first_of_month


# --- Per-user model access ---

def get_allowed_models(user: UserAccount) -> list[dict] | None:
    """Return parsed allowed_models_json, or None if unrestricted.
    Each entry: {"model": "ollama/qwen2.5:14b", "api_key": "..."} """
    if not user.allowed_models_json:
        return None
    try:
        return json.loads(user.allowed_models_json)
    except (json.JSONDecodeError, TypeError):
        return None


def get_user_api_key_for_model(user: UserAccount, model: str) -> str | None:
    """Return the user's API key for a specific model, or None to use server key."""
    models = get_allowed_models(user)
    if models:
        for m in models:
            if m.get("model") == model and m.get("api_key"):
                return m["api_key"]
    # Fallback: check dedicated key fields
    if "gemini" in model and user.gemini_api_key:
        return user.gemini_api_key
    if "groq" in model and user.groq_api_key:
        return user.groq_api_key
    if "openrouter" in model and user.openrouter_api_key:
        return user.openrouter_api_key
    return None


def is_model_allowed(user: UserAccount, model: str) -> bool:
    """Check if user is allowed to use a given model.
    If allowed_models_json is empty/null, all models are allowed."""
    models = get_allowed_models(user)
    if models is None:
        return True
    return any(m.get("model") == model for m in models)


def get_preferred_model(user: UserAccount, default: str) -> str:
    """Return user's preferred AI model, or the server default."""
    return user.ai_model or default


# --- Per-user settings ---

def get_user_settings(user: UserAccount) -> dict:
    """Return parsed settings_json, or empty dict."""
    if not user.settings_json:
        return {}
    try:
        return json.loads(user.settings_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def update_user_settings(session: Session, user: UserAccount, **kwargs) -> None:
    """Merge kwargs into user's settings_json and commit."""
    current = get_user_settings(user)
    current.update(kwargs)
    user.settings_json = json.dumps(current)
    session.commit()
