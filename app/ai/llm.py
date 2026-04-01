"""LiteLLM wrapper — pluggable AI backend with per-user model selection,
API key overrides, token usage tracking, and smart medical routing.

Supports:
- Multi-provider fallback chain (Ollama -> Groq -> OpenRouter -> Gemini)
- Medical query routing: diabetes/health queries → local Diabetica-7B (sovereign)
- General queries → cloud GPU APIs (Groq free tier, OpenRouter free models)
- GDPR consent gating for external AI providers
"""

import asyncio
import logging
from typing import Optional

import litellm

from app.config import settings

log = logging.getLogger(__name__)

litellm.suppress_debug_info = True

# Parse medical keywords once at import
_MEDICAL_KEYWORDS: set[str] = set()
if settings.AI_MEDICAL_KEYWORDS:
    _MEDICAL_KEYWORDS = {
        kw.strip().lower()
        for kw in settings.AI_MEDICAL_KEYWORDS.split(",")
        if kw.strip()
    }


def _is_medical_query(messages: list[dict]) -> bool:
    """Check if the latest user message contains medical/diabetes keywords."""
    if not _MEDICAL_KEYWORDS:
        return False
    for msg in reversed(messages):
        if msg.get("role") == "user":
            text = msg.get("content", "")
            if isinstance(text, list):
                text = " ".join(
                    part.get("text", "") for part in text
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            text_lower = text.lower()
            return any(kw in text_lower for kw in _MEDICAL_KEYWORDS)
    return False


def _is_local_model(model: str) -> bool:
    """Check if a model runs locally (Ollama) — no GDPR consent needed."""
    return "ollama" in model


def _resolve_api_key(model: str, user=None) -> Optional[str]:
    """Resolve the API key for a model: user-specific > server-wide."""
    if user:
        from app.users import get_user_api_key_for_model
        key = get_user_api_key_for_model(user, model)
        if key:
            return key
    if "gemini" in model:
        return settings.GEMINI_API_KEY or None
    if "groq" in model:
        return settings.GROQ_API_KEY or None
    if "openrouter" in model:
        return settings.OPENROUTER_API_KEY or None
    return None


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


def _build_fallback_chain(primary_model: str) -> list[str]:
    """Build ordered fallback chain from configured providers.

    Returns a list of models to try in order after the primary fails.
    Skips the primary model and any unconfigured providers.
    """
    candidates = []

    # Add configured fallback model if set
    if settings.AI_FALLBACK_MODEL:
        candidates.append(settings.AI_FALLBACK_MODEL)

    # Add cloud providers if API keys are configured
    if settings.GROQ_API_KEY:
        candidates.append("groq/llama-3.3-70b-versatile")
    if settings.OPENROUTER_API_KEY:
        candidates.append("openrouter/deepseek/deepseek-chat-v3-0324:free")
    if settings.GEMINI_API_KEY:
        candidates.append("gemini/gemini-2.5-flash")

    # Deduplicate while preserving order, skip the primary
    seen = {primary_model}
    chain = []
    for m in candidates:
        if m not in seen:
            seen.add(m)
            chain.append(m)
    return chain


async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    user=None,
) -> str:
    """Send messages to AI and return the response text.

    Smart routing:
    - Medical/diabetes queries → AI_MEDICAL_MODEL (local Diabetica-7B, sovereign)
    - General queries → AI_MODEL with multi-provider fallback chain

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
    # Resolve model: explicit param > user preference > medical routing > server default
    if not model:
        if user and user.ai_model:
            model = user.ai_model
        elif settings.AI_MEDICAL_MODEL and _is_medical_query(messages):
            model = settings.AI_MEDICAL_MODEL
            log.info("Medical query detected — routing to %s", model)
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

    api_key = _resolve_api_key(model, user)
    fallback_chain = _build_fallback_chain(model)
    timeout = float(settings.AI_TIMEOUT_SECONDS) if fallback_chain else None

    try:
        content, tokens = await _call_model(
            model, messages, temperature, max_tokens, timeout, api_key
        )
        log.debug("AI response (%s): %d chars, %d tokens", model, len(content), tokens)

        if user and tokens > 0:
            _track_tokens(user, tokens)

        return content
    except Exception as e:
        if not fallback_chain:
            log.error("AI call failed (model=%s): %s", model, e, exc_info=True)
            return "[AI temporarily unavailable. Please try again.]"

        reason = "timeout" if isinstance(e, asyncio.TimeoutError) else str(e)
        log.warning("AI primary (%s) failed (%s) — trying fallback chain", model, reason)

        # Try each fallback in order
        for fallback in fallback_chain:
            # GDPR: check consent before sending data to external AI
            if user and not _is_local_model(fallback):
                from app.privacy import has_consent
                from app.database import get_session as _get_session
                _s = _get_session()
                try:
                    if not has_consent(_s, user.telegram_user_id, "ai_external"):
                        log.info(
                            "External fallback %s blocked — no GDPR consent (user %d)",
                            fallback, user.telegram_user_id,
                        )
                        continue
                finally:
                    _s.close()

            fallback_key = _resolve_api_key(fallback, user)
            try:
                content, tokens = await _call_model(
                    fallback, messages, temperature, max_tokens, api_key=fallback_key
                )
                log.info("Fallback AI response (%s): %d chars, %d tokens", fallback, len(content), tokens)

                if user and tokens > 0:
                    _track_tokens(user, tokens)

                return content
            except Exception as e2:
                log.warning("Fallback %s failed: %s", fallback, e2)
                continue

        log.error("All AI providers exhausted after primary (%s) + %d fallbacks", model, len(fallback_chain))
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
