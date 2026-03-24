"""LiteLLM wrapper — pluggable AI backend (Gemini, Ollama, Claude, etc.).

Supports configurable timeout and automatic fallback to a secondary model
when the primary is slow or unavailable (e.g., local Ollama → remote Gemini).
"""

import asyncio
import logging
from typing import Optional

import litellm

from app.config import settings

log = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


async def _call_model(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    timeout: Optional[float] = None,
) -> str:
    """Call a single model with optional timeout. Returns response text."""
    coro = litellm.acompletion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if timeout:
        response = await asyncio.wait_for(coro, timeout=timeout)
    else:
        response = await coro
    return response.choices[0].message.content


async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """Send messages to the configured AI model and return the response text.

    If AI_FALLBACK_ENABLED is true and the primary model times out or fails,
    automatically retries with AI_FALLBACK_MODEL.

    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        model: Override model (default: from settings)
        temperature: Creativity (0.0-1.0)
        max_tokens: Max response length

    Returns:
        Response text string.
    """
    model = model or settings.AI_MODEL
    use_fallback = settings.AI_FALLBACK_ENABLED and settings.AI_FALLBACK_MODEL
    timeout = float(settings.AI_TIMEOUT_SECONDS) if use_fallback else None

    try:
        content = await _call_model(model, messages, temperature, max_tokens, timeout)
        log.debug("AI response (%s): %d chars", model, len(content))
        return content
    except Exception as e:
        if not use_fallback:
            log.error("AI call failed (model=%s): %s", model, e)
            return f"[AI error: {e}]"

        fallback = settings.AI_FALLBACK_MODEL
        reason = "timeout" if isinstance(e, asyncio.TimeoutError) else str(e)
        log.warning(
            "AI primary (%s) failed (%s) — falling back to %s",
            model, reason, fallback,
        )
        try:
            content = await _call_model(fallback, messages, temperature, max_tokens)
            log.info("Fallback AI response (%s): %d chars", fallback, len(content))
            return content
        except Exception as e2:
            log.error("Fallback AI also failed (%s): %s", fallback, e2)
            return f"[AI error: primary={reason}, fallback={e2}]"


async def chat_with_vision(
    messages: list[dict],
    image_url: Optional[str] = None,
    image_base64: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Send a multimodal (text + image) message to the AI.

    For food photo analysis, lab result photos, etc.
    """
    model = model or settings.AI_MODEL

    if image_base64:
        for msg in reversed(messages):
            if msg["role"] == "user":
                msg["content"] = [
                    {"type": "text", "text": msg["content"]},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ]
                break
    elif image_url:
        for msg in reversed(messages):
            if msg["role"] == "user":
                msg["content"] = [
                    {"type": "text", "text": msg["content"]},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]
                break

    return await chat(messages, model=model, max_tokens=3000)
