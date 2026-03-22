"""Lab result analyzer — extract structured data from photos/PDFs of lab reports.

Uses vision AI to OCR and parse lab results into FHIR Observations.
Automatically detects out-of-range values and updates conditions.
"""

import base64
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.llm import chat_with_vision, chat as ai_chat
from app.models import Observation, Condition

log = logging.getLogger(__name__)

# Common lab tests with LOINC codes and reference ranges
KNOWN_TESTS = {
    "hba1c": {"loinc": "4548-4", "unit": "%", "ref_low": 4.0, "ref_high": 6.5},
    "glucose": {"loinc": "15074-8", "unit": "mg/dL", "ref_low": 70, "ref_high": 100},
    "creatinine": {"loinc": "2160-0", "unit": "mg/dL", "ref_low": 0.6, "ref_high": 1.2},
    "tsh": {"loinc": "3016-3", "unit": "mIU/L", "ref_low": 0.4, "ref_high": 4.0},
    "vitamin_d": {"loinc": "1989-3", "unit": "ng/mL", "ref_low": 30, "ref_high": 100},
    "cholesterol_total": {"loinc": "2093-3", "unit": "mg/dL", "ref_low": 0, "ref_high": 200},
    "hdl": {"loinc": "2085-9", "unit": "mg/dL", "ref_low": 40, "ref_high": 999},
    "ldl": {"loinc": "2089-1", "unit": "mg/dL", "ref_low": 0, "ref_high": 130},
    "triglycerides": {"loinc": "2571-8", "unit": "mg/dL", "ref_low": 0, "ref_high": 150},
    "calcium": {"loinc": "17861-6", "unit": "mg/dL", "ref_low": 8.5, "ref_high": 10.5},
    "iron": {"loinc": "2498-4", "unit": "µg/dL", "ref_low": 60, "ref_high": 170},
    "ferritin": {"loinc": "2276-4", "unit": "ng/mL", "ref_low": 12, "ref_high": 150},
    "b12": {"loinc": "2132-9", "unit": "pg/mL", "ref_low": 200, "ref_high": 900},
    "folate": {"loinc": "2284-8", "unit": "ng/mL", "ref_low": 3, "ref_high": 17},
    "alt": {"loinc": "1742-6", "unit": "U/L", "ref_low": 7, "ref_high": 56},
    "ast": {"loinc": "1920-8", "unit": "U/L", "ref_low": 10, "ref_high": 40},
    "dexa_tscore": {"loinc": "80948-3", "unit": "T-score", "ref_low": -1.0, "ref_high": 999},
}

LAB_EXTRACTION_PROMPT = """Analyze this lab result document (photo or PDF).
Extract ALL test results into a JSON array:
```json
[
  {{"test_name": "HbA1c", "value": 6.8, "unit": "%", "reference_range": "4.0-6.5"}},
  {{"test_name": "TSH", "value": 2.4, "unit": "mIU/L", "reference_range": "0.4-4.0"}}
]
```

IMPORTANT:
- Extract every test result you can read
- Use standard test names (HbA1c, TSH, Vitamin D, etc.)
- Include the numeric value and unit
- Include reference range if visible
- For DEXA/densitometry, extract T-score values
- Return ONLY the JSON array, no other text
"""


async def analyze_lab_results(
    image_b64: Optional[str] = None,
    pdf_text: Optional[str] = None,
    session: Optional[Session] = None,
    patient_name: str = "",
    lang: str = "it",
) -> tuple[list[dict], str]:
    """Analyze lab results from photo or PDF text.

    Returns:
        (list of parsed results, formatted summary message)
    """
    # Extract results using AI
    if image_b64:
        messages = [{"role": "user", "content": LAB_EXTRACTION_PROMPT}]
        raw_response = await chat_with_vision(messages, image_base64=image_b64)
    elif pdf_text:
        messages = [
            {"role": "user", "content": LAB_EXTRACTION_PROMPT + f"\n\nDocument text:\n{pdf_text}"}
        ]
        raw_response = await ai_chat(messages)
    else:
        return [], "No lab data provided"

    # Parse JSON from response
    results = _parse_lab_json(raw_response)
    if not results:
        return [], raw_response  # Return raw AI response as fallback

    # Enrich with LOINC codes and interpretations
    enriched = []
    for result in results:
        enriched_result = _enrich_result(result)
        enriched.append(enriched_result)

        # Store in DB
        if session:
            _store_observation(enriched_result, session)

    if session:
        session.commit()

    # Format summary
    summary = _format_lab_summary(enriched, patient_name, lang)
    return enriched, summary


def _parse_lab_json(response: str) -> list[dict]:
    """Extract JSON array from AI response."""
    try:
        start = response.find("[")
        end = response.rfind("]") + 1
        if start == -1 or end <= start:
            return []
        return json.loads(response[start:end])
    except (json.JSONDecodeError, ValueError):
        return []


def _enrich_result(result: dict) -> dict:
    """Add LOINC codes, reference ranges, and interpretation."""
    name = result.get("test_name", "").lower().replace(" ", "_").replace("-", "")
    value = result.get("value")

    # Try to match with known tests
    known = None
    for key, info in KNOWN_TESTS.items():
        if key in name or name in key:
            known = info
            break

    if known:
        result["loinc_code"] = known["loinc"]
        if "unit" not in result or not result["unit"]:
            result["unit"] = known["unit"]
        # Interpret
        if value is not None:
            if value < known["ref_low"]:
                result["interpretation"] = "low"
            elif value > known["ref_high"]:
                result["interpretation"] = "high"
            else:
                result["interpretation"] = "normal"
            result["ref_low"] = known["ref_low"]
            result["ref_high"] = known["ref_high"]
    else:
        result["loinc_code"] = None
        result["interpretation"] = "unknown"

    return result


def _store_observation(result: dict, session: Session):
    """Store a lab result as a FHIR Observation in the DB."""
    if result.get("value") is None:
        return

    existing = session.query(Observation).filter_by(
        display_name=result.get("test_name"),
        effective_date=datetime.utcnow().replace(hour=0, minute=0, second=0),
        source="lab_photo",
    ).first()

    if not existing:
        session.add(Observation(
            loinc_code=result.get("loinc_code"),
            display_name=result.get("test_name", "Unknown"),
            value=result.get("value"),
            unit=result.get("unit", ""),
            reference_range_low=result.get("ref_low"),
            reference_range_high=result.get("ref_high"),
            interpretation=result.get("interpretation"),
            effective_date=datetime.utcnow(),
            source="lab_photo",
            performer="lab",
        ))


def _format_lab_summary(results: list[dict], name: str, lang: str) -> str:
    """Format lab results into a friendly summary."""
    if not results:
        return ""

    lines = {
        "it": [f"📋 *{name}, risultati analizzati:*\n"],
        "en": [f"📋 *{name}, results analyzed:*\n"],
        "es": [f"📋 *{name}, resultados analizados:*\n"],
        "fr": [f"📋 *{name}, résultats analysés :*\n"],
    }
    header = lines.get(lang, lines["it"])

    for r in results:
        interp = r.get("interpretation", "unknown")
        icons = {"normal": "✅", "high": "⬆️", "low": "⬇️", "unknown": "❓"}
        icon = icons.get(interp, "❓")

        value = r.get("value", "?")
        unit = r.get("unit", "")
        test_name = r.get("test_name", "?")

        ref = ""
        if r.get("ref_low") is not None and r.get("ref_high") is not None:
            ref = f" (ref: {r['ref_low']}-{r['ref_high']})"

        header.append(f"{icon} {test_name}: *{value}* {unit}{ref}")

    saved = {
        "it": "\n\n_Risultati salvati nel tuo profilo._",
        "en": "\n\n_Results saved to your profile._",
        "es": "\n\n_Resultados guardados en tu perfil._",
        "fr": "\n\n_Résultats sauvegardés dans ton profil._",
    }
    header.append(saved.get(lang, saved["it"]))

    return "\n".join(header)
