"""Voice message handling — transcription + AI response with full context."""

import base64
import logging
import os
import tempfile
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.llm import chat as ai_chat
from app.ai.system_prompt import build_system_prompt
from app.ai.context import build_context
from app.config import settings
from app.models import ChatMessage

log = logging.getLogger(__name__)


async def process_voice_message(
    voice_bytes: bytes,
    session: Session,
    patient_id: int,
    patient_name: str,
    lang: str = "it",
    user=None,
) -> str:
    """Transcribe voice message and get AI response with full context.

    Uses LiteLLM's audio transcription or falls back to sending
    the audio description to the AI as text.
    """
    # Transcribe
    transcript = await _transcribe(voice_bytes)

    if not transcript:
        errors = {
            "it": f"{patient_name}, non sono riuscita a capire il messaggio vocale. Puoi riprovare o scrivere?",
            "en": f"{patient_name}, I couldn't understand the voice message. Can you try again or type?",
            "es": f"{patient_name}, no pude entender el mensaje de voz. ¿Puedes intentar de nuevo o escribir?",
            "fr": f"{patient_name}, je n'ai pas pu comprendre le message vocal. Tu peux réessayer ou écrire ?",
        }
        return errors.get(lang, errors["it"])

    # Build context and get AI response
    ctx = build_context(session, patient_id=patient_id)
    system_prompt = build_system_prompt(patient_name, lang, ctx)

    # Get recent chat history — private per user
    recent = (
        session.query(ChatMessage)
        .filter_by(patient_id=patient_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(10)
        .all()
    )
    recent.reverse()

    messages = [{"role": "system", "content": system_prompt}]
    for cm in recent:
        messages.append({"role": cm.role, "content": cm.content})

    voice_prefix = {
        "it": "[Messaggio vocale trascritto] ",
        "en": "[Transcribed voice message] ",
        "es": "[Mensaje de voz transcrito] ",
        "fr": "[Message vocal transcrit] ",
    }
    prefixed = voice_prefix.get(lang, voice_prefix["it"]) + transcript
    messages.append({"role": "user", "content": prefixed})

    response = await ai_chat(messages, user=user)

    # Save conversation — private per user
    session.add(ChatMessage(
        patient_id=patient_id,
        role="user",
        content=prefixed,
        metadata_json='{"type": "voice"}',
    ))
    session.add(ChatMessage(
        patient_id=patient_id,
        role="assistant",
        content=response,
    ))
    session.commit()

    return response


async def _transcribe(audio_bytes: bytes) -> Optional[str]:
    """Transcribe audio using LiteLLM's transcription or Gemini.

    Tries multiple approaches:
    1. LiteLLM atranscription (if model supports it)
    2. Gemini with audio input
    3. Fallback: describe that voice was received but not transcribed
    """
    try:
        import litellm

        # Save to temp file (Whisper/Gemini need a file)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            # Try LiteLLM transcription (works with OpenAI Whisper, Gemini, etc.)
            response = await litellm.atranscription(
                model=settings.AI_MODEL,
                file=open(tmp_path, "rb"),
                language="it",  # Primary language
            )
            if response and hasattr(response, "text"):
                return response.text
        except Exception as e:
            log.debug("LiteLLM transcription failed (expected for some models): %s", e)

        try:
            # Fallback: send audio as base64 to the AI model for transcription
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            response = await litellm.acompletion(
                model=settings.AI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe this audio message exactly. Return ONLY the transcription, nothing else."},
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": audio_b64,
                                    "format": "ogg",
                                },
                            },
                        ],
                    }
                ],
            )
            if response and response.choices:
                return response.choices[0].message.content
        except Exception as e:
            log.debug("Audio-as-content transcription failed: %s", e)

        # Last resort: try Google Speech-to-Text if available
        try:
            return await _google_stt_fallback(tmp_path)
        except Exception:
            pass

        return None

    except Exception as e:
        log.error("Transcription error: %s", e)
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def _google_stt_fallback(audio_path: str) -> Optional[str]:
    """Fallback transcription using Google Cloud Speech-to-Text (if configured)."""
    # Only works if google-cloud-speech is installed and configured
    try:
        from google.cloud import speech_v1

        client = speech_v1.SpeechClient()
        with open(audio_path, "rb") as f:
            content = f.read()

        audio = speech_v1.RecognitionAudio(content=content)
        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.OGG_OPUS,
            language_code="it-IT",
            alternative_language_codes=["en-US", "es-ES", "fr-FR"],
        )

        response = client.recognize(config=config, audio=audio)
        if response.results:
            return response.results[0].alternatives[0].transcript
    except ImportError:
        pass
    except Exception as e:
        log.debug("Google STT fallback failed: %s", e)

    return None
