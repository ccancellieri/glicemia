"""Food photo analysis — structured carb estimation + own bolus calculation.

Combines AI vision analysis with the estimator engine to provide
both AI-suggested carbs and GliceMia's own bolus calculation.
Always shows final predicted glucose values.
"""

import base64
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.llm import chat_with_vision
from app.ai.system_prompt import build_system_prompt
from app.ai.context import build_context
from app.analytics.estimator import estimate_bolus, get_current_state, get_insulin_settings
from app.config import settings
from app.models import Meal

log = logging.getLogger(__name__)

# Structured food analysis prompt — asks AI to return JSON with carb estimate
FOOD_ANALYSIS_PROMPT = {
    "it": (
        "Analizza questa foto di cibo. Rispondi PRIMA con un blocco JSON così:\n"
        "```json\n"
        '{{"foods": [{{"name": "nome", "portion": "porzione stimata", "carbs_g": numero}}], '
        '"total_carbs_g": numero, "confidence": "high/medium/low", '
        '"notes": "note su incertezze"}}\n'
        "```\n\n"
        "Poi sotto il JSON, scrivi un messaggio amichevole per {name} con:\n"
        "1. Cosa vedi nel piatto\n"
        "2. Stima carboidrati totali\n"
        "3. Il tuo suggerimento per il bolo\n"
        "4. Previsione glicemia finale\n"
    ),
    "en": (
        "Analyze this food photo. Reply FIRST with a JSON block like this:\n"
        "```json\n"
        '{{"foods": [{{"name": "name", "portion": "estimated portion", "carbs_g": number}}], '
        '"total_carbs_g": number, "confidence": "high/medium/low", '
        '"notes": "notes on uncertainties"}}\n'
        "```\n\n"
        "Then below the JSON, write a friendly message for {name} with:\n"
        "1. What you see on the plate\n"
        "2. Total carb estimate\n"
        "3. Your bolus suggestion\n"
        "4. Final glucose prediction\n"
    ),
    "es": (
        "Analiza esta foto de comida. Responde PRIMERO con un bloque JSON así:\n"
        "```json\n"
        '{{"foods": [{{"name": "nombre", "portion": "porción estimada", "carbs_g": número}}], '
        '"total_carbs_g": número, "confidence": "high/medium/low", '
        '"notes": "notas sobre incertidumbres"}}\n'
        "```\n\n"
        "Luego debajo del JSON, escribe un mensaje amigable para {name} con:\n"
        "1. Qué ves en el plato\n"
        "2. Estimación total de carbohidratos\n"
        "3. Tu sugerencia de bolo\n"
        "4. Predicción final de glucosa\n"
    ),
    "fr": (
        "Analyse cette photo de repas. Réponds D'ABORD avec un bloc JSON comme ceci :\n"
        "```json\n"
        '{{"foods": [{{"name": "nom", "portion": "portion estimée", "carbs_g": nombre}}], '
        '"total_carbs_g": nombre, "confidence": "high/medium/low", '
        '"notes": "notes sur les incertitudes"}}\n'
        "```\n\n"
        "Puis sous le JSON, écris un message amical pour {name} avec :\n"
        "1. Ce que tu vois dans l'assiette\n"
        "2. Estimation totale des glucides\n"
        "3. Ta suggestion de bolus\n"
        "4. Prédiction de glycémie finale\n"
    ),
}


async def analyze_food_photo(
    photo_b64: str,
    caption: str,
    session: Session,
    patient_name: str,
    lang: str = "it",
    patient_id: int = None,
    user=None,
) -> tuple[str, Optional[dict]]:
    """Analyze a food photo and return formatted response + structured data.

    Returns:
        (formatted_message, estimation_dict or None)
    """
    ctx = build_context(session, patient_id=patient_id)
    system_prompt = build_system_prompt(patient_name, lang, ctx)

    prompt_template = FOOD_ANALYSIS_PROMPT.get(lang, FOOD_ANALYSIS_PROMPT["it"])
    user_msg = prompt_template.format(name=patient_name)
    if caption:
        user_msg += f"\nNote: {caption}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    # Get AI analysis with vision
    ai_response = await chat_with_vision(messages, image_base64=photo_b64, user=user)

    # Try to extract JSON from response for structured data
    carbs_estimate = _extract_carbs_from_response(ai_response)

    # Calculate OWN bolus estimation using the estimator
    own_estimation = None
    if carbs_estimate is not None and carbs_estimate > 0:
        own_estimation = estimate_bolus(session, carbs_g=carbs_estimate)

        # Save meal to DB
        session.add(Meal(
            patient_id=patient_id,
            timestamp=datetime.utcnow(),
            carbs_g=carbs_estimate,
            description=caption or "Photo analysis",
            ai_estimation=json.dumps(own_estimation, default=str),
            source="photo",
        ))
        session.commit()

    # Append own estimation to the AI response
    result = ai_response
    if own_estimation and "error" not in own_estimation:
        result += _format_own_estimation(own_estimation, lang)

    return result, own_estimation


def _extract_carbs_from_response(response: str) -> Optional[float]:
    """Try to extract total_carbs_g from AI response JSON block."""
    try:
        # Look for JSON block
        start = response.find("```json")
        if start == -1:
            start = response.find("{")
            if start == -1:
                return None
            end = response.find("}", start) + 1
        else:
            start = response.find("{", start)
            end = response.find("```", start)
            if end == -1:
                end = response.rfind("}") + 1
            else:
                end = response.rfind("}", start, end) + 1

        if start == -1 or end <= start:
            return None

        json_str = response[start:end]
        data = json.loads(json_str)
        return float(data.get("total_carbs_g", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _format_own_estimation(est: dict, lang: str) -> str:
    """Format GliceMia's own bolus estimation as an appendix."""
    templates = {
        "it": (
            "\n\n---\n"
            "🔢 *Calcolo GliceMia:*\n"
            "• Glicemia attuale: {current_sg} mg/dL\n"
            "• I:C ratio: 1:{ic_ratio:.0f} | ISF: {isf:.0f}\n"
            "• IOB: {iob_current} U\n"
            "• Bolo cibo: {carb_bolus} U\n"
            "• Bolo correzione: {correction_bolus} U\n"
            "• *Bolo totale suggerito: {total_suggested_bolus} U*\n"
            "• 📈 Stima glicemia a 2h: *{predicted_sg_2h}* mg/dL ({predicted_range})\n"
        ),
        "en": (
            "\n\n---\n"
            "🔢 *GliceMia calculation:*\n"
            "• Current SG: {current_sg} mg/dL\n"
            "• I:C ratio: 1:{ic_ratio:.0f} | ISF: {isf:.0f}\n"
            "• IOB: {iob_current} U\n"
            "• Food bolus: {carb_bolus} U\n"
            "• Correction bolus: {correction_bolus} U\n"
            "• *Total suggested bolus: {total_suggested_bolus} U*\n"
            "• 📈 Predicted SG at 2h: *{predicted_sg_2h}* mg/dL ({predicted_range})\n"
        ),
        "es": (
            "\n\n---\n"
            "🔢 *Cálculo GliceMia:*\n"
            "• Glucosa actual: {current_sg} mg/dL\n"
            "• I:C ratio: 1:{ic_ratio:.0f} | ISF: {isf:.0f}\n"
            "• IOB: {iob_current} U\n"
            "• Bolo comida: {carb_bolus} U\n"
            "• Bolo corrección: {correction_bolus} U\n"
            "• *Bolo total sugerido: {total_suggested_bolus} U*\n"
            "• 📈 Glucosa estimada a 2h: *{predicted_sg_2h}* mg/dL ({predicted_range})\n"
        ),
        "fr": (
            "\n\n---\n"
            "🔢 *Calcul GliceMia :*\n"
            "• Glycémie actuelle : {current_sg} mg/dL\n"
            "• I:C ratio : 1:{ic_ratio:.0f} | ISF : {isf:.0f}\n"
            "• IOB : {iob_current} U\n"
            "• Bolus repas : {carb_bolus} U\n"
            "• Bolus correction : {correction_bolus} U\n"
            "• *Bolus total suggéré : {total_suggested_bolus} U*\n"
            "• 📈 Glycémie estimée à 2h : *{predicted_sg_2h}* mg/dL ({predicted_range})\n"
        ),
    }

    template = templates.get(lang, templates["it"])
    note = est.get("auto_mode_note", "")
    result = template.format(**est)
    if note:
        result += f"_{note}_\n"
    return result
