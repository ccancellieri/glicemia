"""LiteLLM wrapper — pluggable AI backend (Gemini, Ollama, Claude, etc.)."""

import logging
from typing import Optional

import litellm

from app.config import settings

log = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """Send messages to the configured AI model and return the response text.

    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        model: Override model (default: from settings)
        temperature: Creativity (0.0-1.0)
        max_tokens: Max response length

    Returns:
        Response text string.
    """
    model = model or settings.AI_MODEL

    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        log.debug("AI response (%s): %d chars", model, len(content))
        return content
    except Exception as e:
        log.error("AI call failed (model=%s): %s", model, e)
        return f"[AI error: {e}]"


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
        # Add image to the last user message
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
