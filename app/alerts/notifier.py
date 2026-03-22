"""Alert notifier — formats and sends proactive alerts via Telegram."""

import logging
from typing import Optional

from app.alerts.engine import Alert
from app.config import settings
from app.i18n.messages import msg

log = logging.getLogger(__name__)


def format_alert(alert: Alert, patient_name: str, lang: str = "it") -> str:
    """Format an alert into a friendly, contextual Telegram message."""
    formatter = _FORMATTERS.get(alert.alert_type, _format_generic)
    return formatter(alert, patient_name, lang)


def _format_urgent_low(alert: Alert, name: str, lang: str) -> str:
    texts = {
        "it": (
            f"🔴 *{name}, ATTENZIONE!* Glicemia molto bassa: *{alert.sg:.0f}* mg/dL\n\n"
            f"📉 Stima tra 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 *Agisci subito:*\n"
            f"• Prendi 15-20g di zuccheri rapidi (succo, glucosio, miele)\n"
            f"• Ricontrolla tra 15 minuti\n"
            f"• Non fare attività fisica\n"
        ),
        "en": (
            f"🔴 *{name}, ATTENTION!* Very low glucose: *{alert.sg:.0f}* mg/dL\n\n"
            f"📉 Estimate in 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 *Act now:*\n"
            f"• Take 15-20g fast carbs (juice, glucose, honey)\n"
            f"• Recheck in 15 minutes\n"
            f"• Don't exercise\n"
        ),
        "es": (
            f"🔴 *{name}, ¡ATENCIÓN!* Glucosa muy baja: *{alert.sg:.0f}* mg/dL\n\n"
            f"📉 Estimación en 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 *Actúa ahora:*\n"
            f"• Toma 15-20g de carbohidratos rápidos (zumo, glucosa, miel)\n"
            f"• Revisa en 15 minutos\n"
            f"• No hagas ejercicio\n"
        ),
        "fr": (
            f"🔴 *{name}, ATTENTION !* Glycémie très basse : *{alert.sg:.0f}* mg/dL\n\n"
            f"📉 Estimation dans 15 min : *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 *Agis maintenant :*\n"
            f"• Prends 15-20g de sucres rapides (jus, glucose, miel)\n"
            f"• Recontrôle dans 15 minutes\n"
            f"• Pas d'activité physique\n"
        ),
    }
    text = texts.get(lang, texts["it"])
    pattern = alert.details.get("pattern", "")
    if pattern:
        text += f"\n📊 _{pattern}_"
    return text


def _format_low(alert: Alert, name: str, lang: str) -> str:
    texts = {
        "it": (
            f"🟡 *{name}*, glicemia bassa: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Stima tra 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Tieni a portata 15g di CHO rapidi.\n"
            f"Se scendi sotto 60, mangia subito.\n"
        ),
        "en": (
            f"🟡 *{name}*, low glucose: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Estimate in 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Keep 15g fast carbs nearby.\n"
            f"If you drop below 60, eat immediately.\n"
        ),
        "es": (
            f"🟡 *{name}*, glucosa baja: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Estimación en 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Ten 15g de CHO rápidos a mano.\n"
            f"Si bajas de 60, come inmediatamente.\n"
        ),
        "fr": (
            f"🟡 *{name}*, glycémie basse : *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Estimation dans 15 min : *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Garde 15g de glucides rapides à portée.\n"
            f"Si tu descends sous 60, mange immédiatement.\n"
        ),
    }
    text = texts.get(lang, texts["it"])
    pattern = alert.details.get("pattern", "")
    if pattern:
        text += f"\n📊 _{pattern}_"
    return text


def _format_predicted_low(alert: Alert, name: str, lang: str) -> str:
    mins = alert.minutes_to_event or "?"
    pred_15 = alert.details.get("pred_15", "?")
    texts = {
        "it": (
            f"🟡 *{name}*, stai scendendo. Ora: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Stima: *{pred_15}* tra 15 min → *{alert.predicted_sg}* tra 30 min\n"
            f"⏱️ Sotto 70 tra circa *{mins} minuti*\n\n"
            f"💡 Considera uno spuntino leggero (10-15g CHO) per prevenire.\n"
        ),
        "en": (
            f"🟡 *{name}*, you're dropping. Now: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Estimate: *{pred_15}* in 15 min → *{alert.predicted_sg}* in 30 min\n"
            f"⏱️ Below 70 in about *{mins} minutes*\n\n"
            f"💡 Consider a light snack (10-15g carbs) to prevent.\n"
        ),
        "es": (
            f"🟡 *{name}*, estás bajando. Ahora: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Estimación: *{pred_15}* en 15 min → *{alert.predicted_sg}* en 30 min\n"
            f"⏱️ Bajo 70 en unos *{mins} minutos*\n\n"
            f"💡 Considera un snack ligero (10-15g CHO) para prevenir.\n"
        ),
        "fr": (
            f"🟡 *{name}*, tu descends. Maintenant : *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📉 Estimation : *{pred_15}* dans 15 min → *{alert.predicted_sg}* dans 30 min\n"
            f"⏱️ Sous 70 dans environ *{mins} minutes*\n\n"
            f"💡 Envisage une collation légère (10-15g glucides) pour prévenir.\n"
        ),
    }
    text = texts.get(lang, texts["it"])
    pattern = alert.details.get("pattern", "")
    if pattern:
        text += f"\n📊 _{pattern}_"
    return text


def _format_high(alert: Alert, name: str, lang: str) -> str:
    texts = {
        "it": (
            f"🟡 *{name}*, glicemia alta: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📈 Stima tra 30 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Verifica se hai carboidrati non coperti.\n"
            f"La pompa in auto-mode dovrebbe correggere.\n"
        ),
        "en": (
            f"🟡 *{name}*, high glucose: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📈 Estimate in 30 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Check for uncovered carbs.\n"
            f"The pump in auto-mode should correct.\n"
        ),
        "es": (
            f"🟡 *{name}*, glucosa alta: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📈 Estimación en 30 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Verifica si tienes carbohidratos sin cubrir.\n"
            f"La bomba en modo auto debería corregir.\n"
        ),
        "fr": (
            f"🟡 *{name}*, glycémie haute : *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"📈 Estimation dans 30 min : *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Vérifie s'il y a des glucides non couverts.\n"
            f"La pompe en mode auto devrait corriger.\n"
        ),
    }
    return texts.get(lang, texts["it"])


def _format_predicted_high(alert: Alert, name: str, lang: str) -> str:
    mins = alert.minutes_to_event or "?"
    texts = {
        "it": (
            f"📈 *{name}*, stai salendo. Ora: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"Stima tra 30 min: *{alert.predicted_sg}* mg/dL\n"
            f"⏱️ Sopra 250 tra circa *{mins} minuti*\n\n"
            f"💡 La pompa in auto-mode dovrebbe intervenire.\n"
        ),
        "en": (
            f"📈 *{name}*, you're rising. Now: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"Estimate in 30 min: *{alert.predicted_sg}* mg/dL\n"
            f"⏱️ Above 250 in about *{mins} minutes*\n\n"
            f"💡 The pump in auto-mode should intervene.\n"
        ),
    }
    return texts.get(lang, texts["it"])


def _format_falling_fast(alert: Alert, name: str, lang: str) -> str:
    rate = alert.details.get("rate", 0)
    texts = {
        "it": (
            f"⬇️ *{name}*, stai scendendo velocemente!\n"
            f"Ora: *{alert.sg:.0f}* mg/dL ({rate:.1f} mg/dL/min)\n\n"
            f"📉 Stima tra 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Prepara CHO rapidi. Se sei sotto 100, mangia 10-15g.\n"
        ),
        "en": (
            f"⬇️ *{name}*, you're dropping fast!\n"
            f"Now: *{alert.sg:.0f}* mg/dL ({rate:.1f} mg/dL/min)\n\n"
            f"📉 Estimate in 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Prepare fast carbs. If below 100, eat 10-15g.\n"
        ),
    }
    return texts.get(lang, texts["it"])


def _format_rising_fast(alert: Alert, name: str, lang: str) -> str:
    rate = alert.details.get("rate", 0)
    texts = {
        "it": (
            f"⬆️ *{name}*, stai salendo velocemente.\n"
            f"Ora: *{alert.sg:.0f}* mg/dL (+{rate:.1f} mg/dL/min)\n\n"
            f"📈 Stima tra 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Controlla se hai CHO non coperti o bolo mancante.\n"
        ),
        "en": (
            f"⬆️ *{name}*, you're rising fast.\n"
            f"Now: *{alert.sg:.0f}* mg/dL (+{rate:.1f} mg/dL/min)\n\n"
            f"📈 Estimate in 15 min: *{alert.predicted_sg}* mg/dL\n\n"
            f"💡 Check for uncovered carbs or missed bolus.\n"
        ),
    }
    return texts.get(lang, texts["it"])


def _format_prolonged_high(alert: Alert, name: str, lang: str) -> str:
    texts = {
        "it": (
            f"⚠️ *{name}*, sei sopra 180 da più di 2 ore.\n"
            f"Ora: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"💡 Suggerimenti:\n"
            f"• Verifica che il set infusione funzioni\n"
            f"• Controlla se il serbatoio ha insulina\n"
            f"• Un bolo di correzione manuale potrebbe aiutare\n"
        ),
        "en": (
            f"⚠️ *{name}*, you've been above 180 for over 2 hours.\n"
            f"Now: *{alert.sg:.0f}* mg/dL {_trend_arrow(alert)}\n\n"
            f"💡 Suggestions:\n"
            f"• Check that the infusion set is working\n"
            f"• Verify the reservoir has insulin\n"
            f"• A manual correction bolus might help\n"
        ),
    }
    return texts.get(lang, texts["it"])


def _format_sensor_gap(alert: Alert, name: str, lang: str) -> str:
    mins = alert.details.get("minutes_since_last", "?")
    texts = {
        "it": (
            f"📡 *{name}*, nessun dato dal sensore da *{mins} minuti*.\n"
            f"Ultimo valore: {alert.sg:.0f} mg/dL\n\n"
            f"💡 Controlla la connessione sensore-pompa.\n"
        ),
        "en": (
            f"📡 *{name}*, no sensor data for *{mins} minutes*.\n"
            f"Last value: {alert.sg:.0f} mg/dL\n\n"
            f"💡 Check the sensor-pump connection.\n"
        ),
    }
    return texts.get(lang, texts["it"])


def _format_reservoir_low(alert: Alert, name: str, lang: str) -> str:
    units = alert.details.get("units_remaining", "?")
    texts = {
        "it": f"🔋 *{name}*, serbatoio basso: *{units:.0f} U* rimanenti. Prepara il cambio!",
        "en": f"🔋 *{name}*, low reservoir: *{units:.0f} U* remaining. Prepare a change!",
    }
    return texts.get(lang, texts["it"])


def _format_battery_low(alert: Alert, name: str, lang: str) -> str:
    pct = alert.details.get("battery_pct", "?")
    texts = {
        "it": f"🪫 *{name}*, batteria pompa bassa: *{pct}%*. Ricarica presto!",
        "en": f"🪫 *{name}*, pump battery low: *{pct}%*. Charge soon!",
    }
    return texts.get(lang, texts["it"])


def _format_generic(alert: Alert, name: str, lang: str) -> str:
    return f"ℹ️ *{name}*, alert: {alert.alert_type} — SG: {alert.sg} mg/dL"


def _trend_arrow(alert: Alert) -> str:
    arrows = {
        "UP": "↑", "UP_FAST": "↑↑", "UP_RAPID": "↑↑↑",
        "DOWN": "↓", "DOWN_FAST": "↓↓", "DOWN_RAPID": "↓↓↓",
        "FLAT": "→",
    }
    trend = alert.details.get("trend", "FLAT")
    return arrows.get(trend, "")


_FORMATTERS = {
    "urgent_low": _format_urgent_low,
    "low": _format_low,
    "predicted_low": _format_predicted_low,
    "high": _format_high,
    "predicted_high": _format_predicted_high,
    "falling_fast": _format_falling_fast,
    "rising_fast": _format_rising_fast,
    "prolonged_high": _format_prolonged_high,
    "sensor_gap": _format_sensor_gap,
    "reservoir_low": _format_reservoir_low,
    "battery_low": _format_battery_low,
}
