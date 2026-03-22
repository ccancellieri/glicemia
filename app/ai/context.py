"""12-layer context builder — injects real-time data into every AI call."""

import logging
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    GlucoseReading, PumpStatus, BolusEvent, Meal,
    Activity, Condition, GlucosePattern, InsulinSetting,
    PatientProfile, HealthRecord,
)

log = logging.getLogger(__name__)


def build_context(session: Session, now: datetime = None) -> str:
    """Build the full 12-layer context string for AI system prompt injection."""
    now = now or datetime.utcnow()
    layers = []

    # 1. Current CGM status
    layers.append(_layer_current_cgm(session, now))

    # 2. Recent 3h readings
    layers.append(_layer_recent_3h(session, now))

    # 3. Today's metrics
    layers.append(_layer_today_metrics(session, now))

    # 4. Hourly pattern (same hour, last 14 days)
    layers.append(_layer_hourly_pattern(session, now))

    # 5. Same weekday pattern (last 8 weeks)
    layers.append(_layer_weekday_pattern(session, now))

    # 6. Same month last year
    layers.append(_layer_monthly_pattern(session, now))

    # 7. Recent activities (7 days)
    layers.append(_layer_recent_activities(session, now))

    # 8. Active conditions
    layers.append(_layer_conditions(session))

    # 9. Current insulin settings
    layers.append(_layer_insulin_settings(session, now))

    # 10. Patient profile
    layers.append(_layer_patient_profile(session))

    # 11. Recent meals (24h)
    layers.append(_layer_recent_meals(session, now))

    # 12. Health data (24h)
    layers.append(_layer_health_data(session, now))

    return "\n\n".join(layer for layer in layers if layer)


def _layer_current_cgm(session: Session, now: datetime) -> str:
    reading = (
        session.query(GlucoseReading)
        .filter(GlucoseReading.timestamp >= now - timedelta(minutes=15))
        .order_by(GlucoseReading.timestamp.desc())
        .first()
    )
    pump = (
        session.query(PumpStatus)
        .filter(PumpStatus.timestamp >= now - timedelta(minutes=15))
        .order_by(PumpStatus.timestamp.desc())
        .first()
    )

    if not reading:
        return "CURRENT STATUS: No recent CGM data available."

    parts = [f"CURRENT STATUS: SG {reading.sg:.0f} mg/dL"]
    if reading.trend:
        parts.append(f"trend={reading.trend}")
    if pump:
        if pump.active_insulin is not None:
            parts.append(f"IOB={pump.active_insulin:.2f}U")
        if pump.basal_rate is not None:
            parts.append(f"basal={pump.basal_rate:.3f}U/h")
        if pump.auto_mode:
            parts.append(f"mode={pump.auto_mode}")
        if pump.reservoir_units is not None:
            parts.append(f"reservoir={pump.reservoir_units:.0f}U")
        if pump.battery_pct is not None:
            parts.append(f"battery={pump.battery_pct}%")

    return ", ".join(parts)


def _layer_recent_3h(session: Session, now: datetime) -> str:
    readings = (
        session.query(GlucoseReading)
        .filter(GlucoseReading.timestamp >= now - timedelta(hours=3))
        .order_by(GlucoseReading.timestamp.asc())
        .all()
    )
    if not readings:
        return ""

    points = []
    for r in readings[-36:]:  # Max 36 points (every 5 min for 3h)
        time_str = r.timestamp.strftime("%H:%M")
        points.append(f"{time_str}={r.sg:.0f}")

    return f"LAST 3H: {', '.join(points)}"


def _layer_today_metrics(session: Session, now: datetime) -> str:
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    readings = (
        session.query(GlucoseReading.sg)
        .filter(
            GlucoseReading.timestamp >= today_start,
            GlucoseReading.sg.isnot(None),
        )
        .all()
    )
    if not readings:
        return ""

    values = [r.sg for r in readings]
    n = len(values)
    mean = sum(values) / n
    tir = 100 * sum(1 for v in values if 70 <= v <= 180) / n
    below = 100 * sum(1 for v in values if v < 70) / n
    above = 100 * sum(1 for v in values if v > 180) / n

    boluses = (
        session.query(func.sum(BolusEvent.volume_units))
        .filter(BolusEvent.timestamp >= today_start)
        .scalar()
    ) or 0

    carbs = (
        session.query(func.sum(Meal.carbs_g))
        .filter(Meal.timestamp >= today_start)
        .scalar()
    ) or 0

    return (
        f"TODAY: mean={mean:.0f} mg/dL, TIR={tir:.0f}%, "
        f"below70={below:.0f}%, above180={above:.0f}%, "
        f"total_insulin={boluses:.1f}U, total_carbs={carbs:.0f}g, "
        f"readings={n}"
    )


def _layer_hourly_pattern(session: Session, now: datetime) -> str:
    hour_key = now.strftime("%H:00")
    pattern = (
        session.query(GlucosePattern)
        .filter_by(period_type="hourly", period_key=hour_key)
        .first()
    )
    if not pattern:
        return ""

    return (
        f"PATTERN THIS HOUR (14d): avg={pattern.avg_sg:.0f}±{pattern.std_sg:.0f}, "
        f"TIR={pattern.tir_pct:.0f}%, hypos={pattern.hypo_count}, "
        f"samples={pattern.sample_count}"
    )


def _layer_weekday_pattern(session: Session, now: datetime) -> str:
    day_name = now.strftime("%A").lower()
    pattern = (
        session.query(GlucosePattern)
        .filter_by(period_type="daily", period_key=day_name)
        .first()
    )
    if not pattern:
        return ""

    return (
        f"PATTERN {day_name.upper()} (8w): avg={pattern.avg_sg:.0f}±{pattern.std_sg:.0f}, "
        f"TIR={pattern.tir_pct:.0f}%, hypos={pattern.hypo_count}"
    )


def _layer_monthly_pattern(session: Session, now: datetime) -> str:
    month_key = now.strftime("%B").lower()
    pattern = (
        session.query(GlucosePattern)
        .filter_by(period_type="monthly", period_key=month_key)
        .first()
    )
    if not pattern:
        return ""

    return (
        f"PATTERN {month_key.upper()} (historical): avg={pattern.avg_sg:.0f}, "
        f"TIR={pattern.tir_pct:.0f}%"
    )


def _layer_recent_activities(session: Session, now: datetime) -> str:
    activities = (
        session.query(Activity)
        .filter(Activity.timestamp_start >= now - timedelta(days=7))
        .order_by(Activity.timestamp_start.desc())
        .limit(10)
        .all()
    )
    if not activities:
        return ""

    lines = ["RECENT ACTIVITIES (7d):"]
    for a in activities:
        parts = [f"  {a.timestamp_start.strftime('%a %H:%M')} {a.activity_type or '?'}"]
        if a.duration_min:
            parts.append(f"{a.duration_min}min")
        if a.distance_km:
            parts.append(f"{a.distance_km:.1f}km")
        if a.sg_delta is not None:
            parts.append(f"SG delta={a.sg_delta:+.0f}")
        lines.append(", ".join(parts))

    return "\n".join(lines)


def _layer_conditions(session: Session) -> str:
    conditions = (
        session.query(Condition)
        .filter(Condition.clinical_status.in_(["active", "recurrence"]))
        .all()
    )
    if not conditions:
        return ""

    items = []
    for c in conditions:
        item = c.display_name
        if c.severity:
            item += f" ({c.severity})"
        items.append(item)

    return f"ACTIVE CONDITIONS: {', '.join(items)}"


def _layer_insulin_settings(session: Session, now: datetime) -> str:
    hour = now.strftime("%H:00")
    setting = (
        session.query(InsulinSetting)
        .filter(InsulinSetting.time_start <= hour)
        .order_by(InsulinSetting.time_start.desc())
        .first()
    )
    if not setting:
        return ""

    parts = [f"INSULIN SETTINGS (current): period={setting.time_start}"]
    if setting.ic_ratio:
        parts.append(f"I:C=1:{setting.ic_ratio:.0f}")
    if setting.isf:
        parts.append(f"ISF={setting.isf:.0f} mg/dL/U")
    if setting.target_sg:
        parts.append(f"target={setting.target_sg:.0f}")

    return ", ".join(parts)


def _layer_patient_profile(session: Session) -> str:
    profile = session.query(PatientProfile).first()
    if not profile:
        return ""

    parts = [f"PATIENT: {profile.name}"]
    if profile.weight_kg:
        parts.append(f"weight={profile.weight_kg}kg")
    if profile.diabetes_type:
        parts.append(f"type={profile.diabetes_type}")
    if profile.pump_model:
        parts.append(f"pump={profile.pump_model}")
    if profile.diet:
        parts.append(f"diet={profile.diet}")

    return ", ".join(parts)


def _layer_recent_meals(session: Session, now: datetime) -> str:
    meals = (
        session.query(Meal)
        .filter(Meal.timestamp >= now - timedelta(hours=24))
        .order_by(Meal.timestamp.desc())
        .limit(5)
        .all()
    )
    if not meals:
        return ""

    lines = ["RECENT MEALS (24h):"]
    for m in meals:
        parts = [f"  {m.timestamp.strftime('%H:%M')}"]
        if m.carbs_g:
            parts.append(f"{m.carbs_g:.0f}g CHO")
        if m.description:
            parts.append(m.description[:60])
        lines.append(" — ".join(parts))

    return "\n".join(lines)


def _layer_health_data(session: Session, now: datetime) -> str:
    records = (
        session.query(HealthRecord)
        .filter(HealthRecord.timestamp >= now - timedelta(hours=24))
        .order_by(HealthRecord.timestamp.desc())
        .limit(10)
        .all()
    )
    if not records:
        return ""

    lines = ["HEALTH DATA (24h):"]
    for r in records:
        lines.append(f"  {r.timestamp.strftime('%H:%M')} {r.record_type}: {r.value} {r.unit or ''}")

    return "\n".join(lines)
