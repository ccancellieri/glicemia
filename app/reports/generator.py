"""Report generation — PDF charts and data summaries via Telegram.

Generates glucose charts and metric summaries for today, week, or month.
"""

import io
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import GlucoseReading
from app.analytics.metrics import compute_metrics, time_slot_analysis

log = logging.getLogger(__name__)

# Chart style constants
COLOR_IN_RANGE = "#4CAF50"
COLOR_LOW = "#2196F3"
COLOR_HIGH = "#FFC107"
COLOR_VERY_HIGH = "#F44336"
RANGE_LOW = 70
RANGE_HIGH = 180


def generate_report(
    session: Session,
    period: str = "week",
    patient_name: str = "",
    lang: str = "it",
) -> tuple[str, bytes | None]:
    """Generate a text report + optional chart PNG.

    Args:
        session: DB session.
        period: "today", "week", "month"
        patient_name: For report title.
        lang: Language.

    Returns:
        (text_report, chart_png_bytes or None)
    """
    now = datetime.utcnow()
    period_map = {
        "today": timedelta(days=1),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
    }
    delta = period_map.get(period, timedelta(days=7))
    start = now - delta

    # Compute metrics
    metrics = compute_metrics(session, start, now)
    if not metrics:
        no_data = {
            "it": f"{patient_name}, non ci sono dati sufficienti per il report.",
            "en": f"{patient_name}, not enough data for the report.",
            "es": f"{patient_name}, no hay datos suficientes para el informe.",
            "fr": f"{patient_name}, pas assez de données pour le rapport.",
        }
        return no_data.get(lang, no_data["it"]), None

    # Time slot analysis
    slots = time_slot_analysis(session, start, now)

    # Build text report
    text = _format_report_text(metrics, slots, patient_name, period, lang)

    # Generate chart
    chart = _generate_chart(session, start, now, metrics, patient_name, period)

    return text, chart


def _format_report_text(
    metrics: dict,
    slots: list[dict],
    name: str,
    period: str,
    lang: str,
) -> str:
    """Format metrics into a readable Telegram message."""
    period_labels = {
        "today": {"it": "Oggi", "en": "Today", "es": "Hoy", "fr": "Aujourd'hui"},
        "week": {"it": "Settimana", "en": "Week", "es": "Semana", "fr": "Semaine"},
        "month": {"it": "Mese", "en": "Month", "es": "Mes", "fr": "Mois"},
    }
    period_label = period_labels.get(period, {}).get(lang, period)

    lines = [
        f"📊 *Report {period_label} — {name}*\n",
        f"📅 {metrics['days']} giorni | {metrics['readings']} letture\n",
        f"🎯 *TIR (70-180):* {metrics['tir']}%",
        f"🎯 Tight TIR (70-140): {metrics['titr']}%",
        f"⬇️ Sotto 70: {metrics['tbr1']}% | Sotto 54: {metrics['tbr2']}%",
        f"⬆️ Sopra 180: {metrics['tar1']}% | Sopra 250: {metrics['tar2']}%\n",
        f"📈 Media: *{metrics['mean_sg']}* mg/dL ± {metrics['std_sg']}",
        f"📉 CV: {metrics['cv']}% {'✅' if metrics['cv'] < 36 else '⚠️'} (target <36%)",
        f"🔬 GMI (HbA1c stimata): *{metrics['gmi']}%*\n",
        f"💉 Boli/giorno: {metrics['avg_bolus_per_day']}",
        f"💊 Insulina/giorno: {metrics['avg_insulin_per_day']} U",
    ]

    if metrics.get("carb_entries"):
        lines.append(f"🍞 Carboidrati registrati: {metrics['carb_total_g']:.0f}g in {metrics['carb_entries']} pasti")

    # Slot analysis
    if slots:
        lines.append("\n📋 *Analisi per fascia oraria:*")
        for s in slots:
            issues_text = ""
            for issue in s.get("issues", []):
                if issue["type"] == "recurring_hypo":
                    issues_text += f" ⚠️ Ipo nel {issue['frequency_pct']}% dei giorni"
                elif issue["type"] == "recurring_hyper":
                    issues_text += f" ⚠️ Iper nel {issue['frequency_pct']}% dei giorni"
            lines.append(
                f"  {s['slot']}: media {s['mean_sg']:.0f}, TIR {s['tir_pct']:.0f}%{issues_text}"
            )

    return "\n".join(lines)


def _generate_chart(
    session: Session,
    start: datetime,
    end: datetime,
    metrics: dict,
    name: str,
    period: str,
) -> bytes | None:
    """Generate a glucose chart as PNG bytes."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        log.warning("matplotlib not installed — skipping chart")
        return None

    readings = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.timestamp >= start,
            GlucoseReading.timestamp <= end,
            GlucoseReading.sg.isnot(None),
        )
        .order_by(GlucoseReading.timestamp.asc())
        .all()
    )

    if len(readings) < 2:
        return None

    timestamps = [r.timestamp for r in readings]
    values = [r.sg for r in readings]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(f"GliceMia — {name} — {period.title()}", fontsize=14, fontweight="bold")

    # Top: glucose trace
    ax1.fill_between(timestamps, RANGE_LOW, RANGE_HIGH, alpha=0.1, color=COLOR_IN_RANGE, label="Target range")
    ax1.axhline(y=RANGE_LOW, color=COLOR_LOW, linestyle="--", alpha=0.5)
    ax1.axhline(y=RANGE_HIGH, color=COLOR_HIGH, linestyle="--", alpha=0.5)

    # Color points by range
    colors = []
    for v in values:
        if v < 54:
            colors.append(COLOR_LOW)
        elif v < RANGE_LOW:
            colors.append(COLOR_LOW)
        elif v <= RANGE_HIGH:
            colors.append(COLOR_IN_RANGE)
        elif v <= 250:
            colors.append(COLOR_HIGH)
        else:
            colors.append(COLOR_VERY_HIGH)

    ax1.scatter(timestamps, values, c=colors, s=3, alpha=0.6)
    ax1.plot(timestamps, values, color="gray", alpha=0.2, linewidth=0.5)
    ax1.set_ylabel("Glucose (mg/dL)")
    ax1.set_ylim(40, max(300, max(values) + 20))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    ax1.grid(True, alpha=0.3)

    # Bottom: TIR pie
    tir_values = [metrics["tbr2"], metrics["tbr1"], metrics["tir"], metrics["tar1"], metrics["tar2"]]
    tir_labels = ["<54", "54-70", "70-180", "180-250", ">250"]
    tir_colors = [COLOR_LOW, "#64B5F6", COLOR_IN_RANGE, COLOR_HIGH, COLOR_VERY_HIGH]
    # Filter out zeros
    filtered = [(v, l, c) for v, l, c in zip(tir_values, tir_labels, tir_colors) if v > 0]
    if filtered:
        vals, labs, cols = zip(*filtered)
        ax2.pie(vals, labels=labs, colors=cols, autopct="%1.0f%%", startangle=90)
        ax2.set_title(f"TIR: {metrics['tir']}% | GMI: {metrics['gmi']}% | CV: {metrics['cv']}%")

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
