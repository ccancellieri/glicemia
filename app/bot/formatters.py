"""Format data into friendly messages with final predicted values."""

from datetime import datetime
from typing import Optional


TREND_ARROWS = {
    "UP": "↑",
    "UP_FAST": "↑↑",
    "UP_RAPID": "↑↑↑",
    "DOWN": "↓",
    "DOWN_FAST": "↓↓",
    "DOWN_RAPID": "↓↓↓",
    "FLAT": "→",
}

TREND_RATE = {
    "UP": 2.0,        # mg/dL per minute
    "UP_FAST": 3.0,
    "UP_RAPID": 4.0,
    "DOWN": -1.5,
    "DOWN_FAST": -2.5,
    "DOWN_RAPID": -3.5,
    "FLAT": 0.0,
}


def format_status(
    sg: float,
    trend: str,
    iob: Optional[float],
    basal_rate: Optional[float],
    auto_mode: Optional[str],
    reservoir: Optional[float],
    battery: Optional[int],
    patient_name: str,
    lang: str = "it",
) -> str:
    """Format current CGM/pump status into a friendly message."""
    arrow = TREND_ARROWS.get(trend, "?")

    # Range indicator
    if sg < 54:
        range_emoji = "🔴"
        range_label = {"it": "MOLTO BASSA", "en": "VERY LOW", "es": "MUY BAJA", "fr": "TRÈS BASSE"}
    elif sg < 70:
        range_emoji = "🟡"
        range_label = {"it": "BASSA", "en": "LOW", "es": "BAJA", "fr": "BASSE"}
    elif sg <= 180:
        range_emoji = "🟢"
        range_label = {"it": "IN RANGE", "en": "IN RANGE", "es": "EN RANGO", "fr": "EN CIBLE"}
    elif sg <= 250:
        range_emoji = "🟡"
        range_label = {"it": "ALTA", "en": "HIGH", "es": "ALTA", "fr": "HAUTE"}
    else:
        range_emoji = "🔴"
        range_label = {"it": "MOLTO ALTA", "en": "VERY HIGH", "es": "MUY ALTA", "fr": "TRÈS HAUTE"}

    label = range_label.get(lang, range_label["en"])

    # Predict 30 and 60 min values
    rate = TREND_RATE.get(trend, 0.0)
    pred_30 = max(40, sg + rate * 30)
    pred_60 = max(40, sg + rate * 60)

    lines = [
        f"{range_emoji} *{sg:.0f}* mg/dL {arrow} — {label}",
        "",
        f"📈 Stima 30min: *{pred_30:.0f}* mg/dL | 60min: *{pred_60:.0f}* mg/dL",
    ]

    if iob is not None:
        lines.append(f"💉 IOB: {iob:.2f} U")
    if basal_rate is not None:
        lines.append(f"💧 Basale: {basal_rate:.3f} U/h")
    if auto_mode:
        mode_display = auto_mode.replace("_", " ").title()
        lines.append(f"🤖 Modo: {mode_display}")
    if reservoir is not None:
        lines.append(f"🔋 Serbatoio: {reservoir:.0f} U")
    if battery is not None:
        lines.append(f"🔋 Batteria: {battery}%")

    return "\n".join(lines)


def format_csv_import_result(stats: dict, lang: str = "it") -> str:
    """Format CSV import results."""
    from app.i18n.messages import msg

    if "error" in stats:
        return msg("csv_import_error", lang, error=stats["error"])

    return msg(
        "csv_import_success",
        lang,
        glucose=stats.get("glucose", 0),
        bolus=stats.get("bolus", 0),
        skipped=stats.get("skipped", 0),
    )
