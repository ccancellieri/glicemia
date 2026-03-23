"""Text-to-Speech — generate voice replies using edge-tts or LiteLLM."""

import io
import logging
import tempfile
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

# Italian voice options for edge-tts (Microsoft Edge, free)
EDGE_VOICES = {
    "it": "it-IT-ElsaNeural",
    "en": "en-US-JennyNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
}


async def text_to_speech(text: str, lang: str = "it") -> Optional[bytes]:
    """Convert text to OGG audio bytes for Telegram voice messages.

    Tries:
    1. edge-tts (free, no API key, great quality)
    2. LiteLLM TTS (if TTS_MODEL is configured — costs money)

    Returns OGG/Opus bytes or None on failure.
    """
    # Strip markdown formatting for cleaner speech
    clean_text = _strip_markdown(text)

    if not clean_text.strip():
        return None

    # Try edge-tts first (free)
    audio = await _edge_tts(clean_text, lang)
    if audio:
        return audio

    # Fallback: LiteLLM TTS (OpenAI tts-1, etc.)
    if settings.TTS_MODEL:
        audio = await _litellm_tts(clean_text, lang)
        if audio:
            return audio

    log.warning("All TTS methods failed")
    return None


async def _edge_tts(text: str, lang: str) -> Optional[bytes]:
    """Generate speech using edge-tts (Microsoft Edge, free)."""
    try:
        import edge_tts

        voice = EDGE_VOICES.get(lang, EDGE_VOICES["it"])
        communicate = edge_tts.Communicate(text, voice)

        # edge-tts outputs MP3, we need to collect it
        mp3_buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buf.write(chunk["data"])

        mp3_bytes = mp3_buf.getvalue()
        if not mp3_bytes:
            return None

        # Convert MP3 to OGG/Opus for Telegram voice messages
        return await _mp3_to_ogg(mp3_bytes)

    except ImportError:
        log.debug("edge-tts not installed, skipping")
        return None
    except Exception as e:
        log.warning("edge-tts failed: %s", e)
        return None


async def _litellm_tts(text: str, lang: str) -> Optional[bytes]:
    """Generate speech using LiteLLM (OpenAI tts-1, etc.)."""
    try:
        import litellm

        voice_map = {"it": "nova", "en": "alloy", "es": "nova", "fr": "nova"}
        voice = voice_map.get(lang, "nova")

        response = await litellm.aspeech(
            model=settings.TTS_MODEL,
            input=text,
            voice=voice,
        )

        # LiteLLM returns audio bytes (MP3 by default)
        if hasattr(response, "read"):
            mp3_bytes = response.read()
        elif isinstance(response, bytes):
            mp3_bytes = response
        else:
            mp3_bytes = response.content if hasattr(response, "content") else None

        if not mp3_bytes:
            return None

        return await _mp3_to_ogg(mp3_bytes)

    except Exception as e:
        log.warning("LiteLLM TTS failed: %s", e)
        return None


async def _mp3_to_ogg(mp3_bytes: bytes) -> Optional[bytes]:
    """Convert MP3 bytes to OGG/Opus for Telegram voice messages.

    Uses ffmpeg if available, otherwise returns MP3 (Telegram can handle both
    but OGG is native for voice messages).
    """
    try:
        import asyncio
        import os

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_f:
            mp3_f.write(mp3_bytes)
            mp3_path = mp3_f.name

        ogg_path = mp3_path.replace(".mp3", ".ogg")

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", mp3_path, "-c:a", "libopus",
            "-b:a", "64k", "-y", ogg_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if proc.returncode == 0:
            with open(ogg_path, "rb") as f:
                ogg_bytes = f.read()

            os.unlink(mp3_path)
            os.unlink(ogg_path)
            return ogg_bytes

    except FileNotFoundError:
        log.debug("ffmpeg not found, returning MP3 as-is")
    except Exception as e:
        log.debug("MP3-to-OGG conversion failed: %s", e)

    # Fallback: return MP3 directly (Telegram can play it, just not as voice)
    return mp3_bytes


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting for cleaner TTS output."""
    import re

    # Remove bold/italic markers
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", text)
    # Remove inline code
    text = re.sub(r"`(.+?)`", r"\1", text)
    # Remove links [text](url) -> text
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # Remove headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bullet points
    text = re.sub(r"^[•\-\*]\s+", "", text, flags=re.MULTILINE)
    return text.strip()
