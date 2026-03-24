"""LiteLLM wrapper — pluggable AI backend with per-user model selection,
API key overrides, and token usage tracking.

Supports configurable timeout and automatic fallback to a secondary model
when the primary is slow or unavailable (e.g., local Ollama -> remote Gemini).
"""

import asyncio
import logging
from typing import Optional

import litellm

from app.config import settings

log = logging.getLogger(__name__)

litellm.suppress_debug_info = True


async def _call_model(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    timeout: Optional[float] = None,
    api_key: Optional[str] = None,
) -> tuple[str, int]:
    """Call a single model with optional timeout. Returns (response_text, token_count)."""
    kwargs = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if api_key:
        kwargs["api_key"] = api_key

    coro = litellm.acompletion(**kwargs)
    if timeout:
        response = await asyncio.wait_for(coro, timeout=timeout)
    else:
        response = await coro

    content = response.choices[0].message.content
    # Count tokens from response usage (prompt + completion)
    usage = getattr(response, "usage", None)
    total_tokens = usage.total_tokens if usage else 0
    return content, total_tokens


async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    user=None,
) -> str:
    """Send messages to AI and return the response text.

    If a UserAccount is provided via `user`, uses per-user model preference,
    API key overrides, and tracks token usage against limits.

    Args:
        messages: List of {"role": ..., "content": ...}
        model: Override model (default: user preference or server setting)
        temperature: Creativity (0.0-1.0)
        max_tokens: Max response length
        user: Optional UserAccount for per-user settings and token tracking

    Returns:
        Response text string.
    """
    # Resolve model: explicit param > user preference > server default
    if not model:
        if user and user.ai_model:
            model = user.ai_model
        else:
            model = settings.AI_MODEL

    # Check per-user token limits
    if user:
        from app.users import check_token_limit, is_model_allowed
        if not is_model_allowed(user, model):
            return f"[Model {model} is not in your allowed models list]"
        allowed, reason = check_token_limit(user)
        if not allowed:
            return f"[Token limit reached ({reason}). Please wait for reset or contact admin.]"

    # Resolve API key: user-specific > server-wide
    api_key = None
    if user:
        from app.users import get_user_api_key_for_model
        api_key = get_user_api_key_for_model(user, model)
    if not api_key and "gemini" in model:
        api_key = settings.GEMINI_API_KEY or None

    use_fallback = settings.AI_FALLBACK_ENABLED and settings.AI_FALLBACK_MODEL
    timeout = float(settings.AI_TIMEOUT_SECONDS) if use_fallback else None

    try:
        content, tokens = await _call_model(
            model, messages, temperature, max_tokens, timeout, api_key
        )
        log.debug("AI response (%s): %d chars, %d tokens", model, len(content), tokens)

        # Track token usage
        if user and tokens > 0:
            _track_tokens(user, tokens)

        return content
    except Exception as e:
        if not use_fallback:
            log.error("AI call failed (model=%s): %s", model, e, exc_info=True)
            return "[AI temporarily unavailable. Please try again.]"

        fallback = settings.AI_FALLBACK_MODEL
        reason = "timeout" if isinstance(e, asyncio.TimeoutError) else str(e)
        log.warning(
            "AI primary (%s) failed (%s) — falling back to %s",
            model, reason, fallback,
        )

        # Resolve fallback API key
        fallback_key = None
        if user:
            from app.users import get_user_api_key_for_model
            fallback_key = get_user_api_key_for_model(user, fallback)
        if not fallback_key and "gemini" in fallback:
            fallback_key = settings.GEMINI_API_KEY or None

        try:
            content, tokens = await _call_model(
                fallback, messages, temperature, max_tokens, api_key=fallback_key
            )
            log.info("Fallback AI response (%s): %d chars, %d tokens", fallback, len(content), tokens)

            if user and tokens > 0:
                _track_tokens(user, tokens)

            return content
        except Exception as e2:
            log.error("Fallback AI also failed (%s): %s", fallback, e2, exc_info=True)
            return "[AI temporarily unavailable. Please try again later.]"


async def chat_with_vision(
    messages: list[dict],
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    model: Optional[str] = None,
    user=None,
) -> str:
    """Send a multimodal (text + image) message to the AI."""
    model = model or (user.ai_model if user and user.ai_model else settings.AI_MODEL)

    if image_base64:
        for m in reversed(messages):
            if m["role"] == "user":
                m["content"] = [
                    {"type": "text", "text": m["content"]},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ]
                break
    elif image_url:
        for m in reversed(messages):
            if m["role"] == "user":
                m["content"] = [
                    {"type": "text", "text": m["content"]},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]
                break

    return await chat(messages, model=model, max_tokens=3000, user=user)


def _track_tokens(user, tokens: int) -> None:
    """Record token usage in a new session (handlers may have closed theirs)."""
    from app.database import get_session
    from app.users import record_token_usage
    session = get_session()
    try:
        # Re-fetch user in this session to avoid detached instance
        from app.models import UserAccount
        u = session.get(UserAccount, user.telegram_user_id)
        if u:
            record_token_usage(session, u, tokens)
    finally:
        session.close()
