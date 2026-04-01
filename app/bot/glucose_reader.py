"""Glucose reading extraction from device photos (pump, glucometer).

Uses AI vision to parse glucose values from photos of:
- Medtronic 780G pump screens (SG + trend + IOB)
- Blood glucometers (blood glucose value)

Returns structured data for user confirmation before saving.
"""

import json
import logging
from typing import Optional

from app.ai.llm import chat_with_vision
from app.config import settings

log = logging.getLogger(__name__)

# Prompt to extract glucose readings from device photos
DEVICE_READING_PROMPT = {
    "it": (
        "Analizza questa foto di un dispositivo medico per il diabete.\n"
        "Identifica il tipo di dispositivo e estrai i valori.\n\n"
        "Rispondi SOLO con un blocco JSON così:\n"
        "```json\n"
        '{{"device_type": "pump_780g" | "glucometer" | "cgm_receiver" | "unknown",\n'
        ' "glucose_value": numero_o_null,\n'
        ' "glucose_unit": "mg/dL" | "mmol/L",\n'
        ' "trend": "UP" | "UP_FAST" | "DOWN" | "DOWN_FAST" | "FLAT" | null,\n'
        ' "iob": numero_o_null,\n'
        ' "basal_rate": numero_o_null,\n'
        ' "auto_mode": stringa_o_null,\n'
        ' "battery_pct": numero_o_null,\n'
        ' "reservoir_units": numero_o_null,\n'
        ' "confidence": "high" | "medium" | "low",\n'
        ' "notes": "note sulla lettura"}}\n'
        "```\n"
    ),
    "en": (
        "Analyze this photo of a diabetes medical device.\n"
        "Identify the device type and extract the values.\n\n"
        "Reply ONLY with a JSON block like this:\n"
        "```json\n"
        '{{"device_type": "pump_780g" | "glucometer" | "cgm_receiver" | "unknown",\n'
        ' "glucose_value": number_or_null,\n'
        ' "glucose_unit": "mg/dL" | "mmol/L",\n'
        ' "trend": "UP" | "UP_FAST" | "DOWN" | "DOWN_FAST" | "FLAT" | null,\n'
        ' "iob": number_or_null,\n'
        ' "basal_rate": number_or_null,\n'
        ' "auto_mode": string_or_null,\n'
        ' "battery_pct": number_or_null,\n'
        ' "reservoir_units": number_or_null,\n'
        ' "confidence": "high" | "medium" | "low",\n'
        ' "notes": "reading notes"}}\n'
        "```\n"
    ),
}


async def extract_glucose_from_photo(
    photo_b64: str,
    lang: str = "it",
    user=None,
) -> Optional[dict]:
    """Extract glucose reading from a device photo using AI vision.

    Returns parsed dict with device_type, glucose_value, trend, etc.
    Returns None if parsing fails.
    """
    prompt_text = DEVICE_READING_PROMPT.get(lang, DEVICE_READING_PROMPT["en"])

    messages = [
        {"role": "user", "content": prompt_text},
    ]

    try:
        response = await chat_with_vision(
            messages=messages,
            image_base64=photo_b64,
            user=user,
        )

        # Extract JSON from response
        json_str = _extract_json(response)
        if not json_str:
            log.warning("No JSON found in device photo analysis response")
            return None

        data = json.loads(json_str)

        # Validate
        if data.get("device_type") == "unknown" or data.get("glucose_value") is None:
            return None

        # Convert mmol/L to mg/dL if needed
        if data.get("glucose_unit") == "mmol/L" and data.get("glucose_value"):
            data["glucose_value"] = round(data["glucose_value"] * 18.0)
            data["glucose_unit"] = "mg/dL"

        return data

    except Exception as e:
        log.error("Failed to extract glucose from photo: %s", e)
        return None


def is_likely_device_photo(caption: str) -> bool:
    """Check if the photo caption suggests a medical device rather than food.

    Keywords in IT/EN that indicate a pump, glucometer, or CGM reading.
    """
    if not caption:
        return False
    caption_lower = caption.lower()
    device_keywords = [
        # English
        "pump", "glucometer", "meter", "glucose", "reading", "sg", "bg",
        "cgm", "sensor", "780g", "minimed", "freestyle", "dexcom",
        "accu-chek", "contour", "onetouch", "blood sugar",
        # Italian
        "pompa", "glucometro", "glicemia", "sensore", "lettura",
        "misuratore", "valore", "sangue", "pungidito",
    ]
    return any(kw in caption_lower for kw in device_keywords)


def _extract_json(text: str) -> Optional[str]:
    """Extract JSON block from AI response."""
    # Try ```json ... ```
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return text[start:end].strip()
    # Try ``` ... ```
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return text[start:end].strip()
    # Try raw JSON
    for i, c in enumerate(text):
        if c == "{":
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[i : j + 1]
            break
    return None
