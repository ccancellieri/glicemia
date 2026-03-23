"""Telegram WebApp initData validation — HMAC-SHA256 verification."""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qs, unquote

from app.config import settings

log = logging.getLogger(__name__)

MAX_AUTH_AGE = 86400  # 24 hours


def validate_init_data(init_data: str) -> dict | None:
    """Validate Telegram WebApp initData and return user info.

    Returns dict with user_id, first_name, etc. or None if invalid.
    """
    if not init_data or not settings.TELEGRAM_BOT_TOKEN:
        return None

    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        # Build data-check-string (sorted key=value pairs, excluding hash)
        check_pairs = []
        for key in sorted(parsed.keys()):
            if key == "hash":
                continue
            check_pairs.append(f"{key}={parsed[key][0]}")
        data_check_string = "\n".join(check_pairs)

        # HMAC-SHA256 verification
        secret_key = hmac.new(
            b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            log.warning("WebApp initData hash mismatch")
            return None

        # Check auth_date freshness
        auth_date = int(parsed.get("auth_date", [0])[0])
        if time.time() - auth_date > MAX_AUTH_AGE:
            log.warning("WebApp initData expired (auth_date=%d)", auth_date)
            return None

        # Extract user
        user_str = parsed.get("user", [None])[0]
        if not user_str:
            return None

        user = json.loads(unquote(user_str))
        user_id = user.get("id")

        # Check authorization
        if settings.TELEGRAM_ALLOWED_USERS and user_id not in settings.TELEGRAM_ALLOWED_USERS:
            log.warning("WebApp unauthorized user: %s", user_id)
            return None

        return user

    except Exception as e:
        log.error("WebApp initData validation error: %s", e)
        return None
