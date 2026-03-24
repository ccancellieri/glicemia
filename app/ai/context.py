"""12-layer context builder — injects real-time per-patient data into every AI call."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    GlucoseReading, PumpStatus, BolusEvent, Meal,
    Activity, Condition, GlucosePattern, InsulinSetting,
    PatientProfile, HealthRecord,
)

log = logging.getLogger(__name__)


def build_context(session: Session, patient_id: int = None, now: datetime = None) -> str:
    """Build the full 12-layer context string for AI system prompt injection.
    All queries are scoped to the given patient_id."""
    now = now or datetime.utcnow()
    pid = patient_id
    layers = [
        _layer_current_cgm(session, now, pid),
        _layer_recent_3h(session, now, pid),
        _layer_today_metrics(session, now, pid),
        _layer_hourly_pattern(session, now, pid),
        _layer_weekday_pattern(session, now, pid),
        _layer_monthly_pattern(session, now, pid),
        _layer_recent_activities(session, now, pid),
        _layer_conditions(session, pid),
        _layer_insulin_settings(session, now, pid),
        _layer_patient_profile(session, pid),
        _layer_recent_meals(session, now, pid),
        _layer_health_data(session, now, pid),
    ]
    return "\n\n".join(layer for layer in layers if layer)


def _pid_filter(query, model, pid):
    """Apply patient_id filter if pid is not None."""
    if pid is not None:
        return query.filter(model.patient_id == pid)
    return query


def _layer_current_cgm(session: Session, now: datetime, pid) -> str:
    q = session.query(GlucoseReading).filter(
        GlucoseReading.timestamp >= now - timedelta(minutes=15)
    )
    q = _pid_filter(q, GlucoseReading, pid)
    reading = q.order_by(GlucoseReading.timestamp.desc()).first()

    pq = session.query(PumpStatus).filter(
        PumpStatus.timestamp >= now - timedelta(minutes=15)
    )
    pq = _pid_filter(pq, PumpStatus, pid)
    pump = pq.order_by(PumpStatus.timestamp.desc()).first()

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


def _layer_recent_3h(session: Session, now: datetime, pid) -> str:
    q = session.query(GlucoseReading).filter(
        GlucoseReading.timestamp >= now - timedelta(hours=3)
    )
    q = _pid_filter(q, GlucoseReading, pid)
    readings = q.order_by(GlucoseReading.timestamp.asc()).all()
    if not readings:
        return ""

    points = []
    for r in readings[-36:]:
        time_str = r.timestamp.strftime("%H:%M")
        points.append(f"{time_str}={r.sg:.0f}")

    return f"LAST 3H: {', '.join(points)}"


def _layer_today_metrics(session: Session, now: datetime, pid) -> str:
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    q = session.query(GlucoseReading.sg).filter(
        GlucoseReading.timestamp >= today_start,
        GlucoseReading.sg.isnot(None),
    )
    q = _pid_filter(q, GlucoseReading, pid)
    readings = q.all()
    if not readings:
        return ""

    values = [r.sg for r in readings]
    n = len(values)
    mean = sum(values) / n
    tir = 100 * sum(1 for v in values if 70 <= v <= 180) / n
    below = 100 * sum(1 for v in values if v < 70) / n
    above = 100 * sum(1 for v in values if v > 180) / n

    bq = session.query(func.sum(BolusEvent.volume_units)).filter(
        BolusEvent.timestamp >= today_start
    )
    bq = _pid_filter(bq, BolusEvent, pid)
    boluses = bq.scalar() or 0

    mq = session.query(func.sum(Meal.carbs_g)).filter(
        Meal.timestamp >= today_start
    )
    mq = _pid_filter(mq, Meal, pid)
    carbs = mq.scalar() or 0

    return (
        f"TODAY: mean={mean:.0f} mg/dL, TIR={tir:.0f}%, "
        f"below70={below:.0f}%, above180={above:.0f}%, "
        f"total_insulin={boluses:.1f}U, total_carbs={carbs:.0f}g, "
        f"readings={n}"
    )


def _layer_hourly_pattern(session: Session, now: datetime, pid) -> str:
    hour_key = now.strftime("%H:00")
    q = session.query(GlucosePattern).filter_by(period_type="hourly", period_key=hour_key)
    q = _pid_filter(q, GlucosePattern, pid)
    pattern = q.first()
    if not pattern:
        return ""

    return (
        f"PATTERN THIS HOUR (14d): avg={pattern.avg_sg:.0f}\u00b1{pattern.std_sg:.0f}, "
        f"TIR={pattern.tir_pct:.0f}%, hypos={pattern.hypo_count}, "
        f"samples={pattern.sample_count}"
    )


def _layer_weekday_pattern(session: Session, now: datetime, pid) -> str:
    day_name = now.strftime("%A").lower()
    q = session.query(GlucosePattern).filter_by(period_type="daily", period_key=day_name)
    q = _pid_filter(q, GlucosePattern, pid)
    pattern = q.first()
    if not pattern:
        return ""

    return (
        f"PATTERN {day_name.upper()} (8w): avg={pattern.avg_sg:.0f}\u00b1{pattern.std_sg:.0f}, "
        f"TIR={pattern.tir_pct:.0f}%, hypos={pattern.hypo_count}"
    )


def _layer_monthly_pattern(session: Session, now: datetime, pid) -> str:
    month_key = now.strftime("%B").lower()
    q = session.query(GlucosePattern).filter_by(period_type="monthly", period_key=month_key)
    q = _pid_filter(q, GlucosePattern, pid)
    pattern = q.first()
    if not pattern:
        return ""

    return (
        f"PATTERN {month_key.upper()} (historical): avg={pattern.avg_sg:.0f}, "
        f"TIR={pattern.tir_pct:.0f}%"
    )


def _layer_recent_activities(session: Session, now: datetime, pid) -> str:
    q = session.query(Activity).filter(
        Activity.timestamp_start >= now - timedelta(days=7)
    )
    q = _pid_filter(q, Activity, pid)
    activities = q.order_by(Activity.timestamp_start.desc()).limit(10).all()
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


def _layer_conditions(session: Session, pid) -> str:
    q = session.query(Condition).filter(
        Condition.clinical_status.in_(["active", "recurrence"])
    )
    q = _pid_filter(q, Condition, pid)
    conditions = q.all()
    if not conditions:
        return ""

    items = []
    for c in conditions:
        item = c.display_name
        if c.severity:
            item += f" ({c.severity})"
        items.append(item)

    return f"ACTIVE CONDITIONS: {', '.join(items)}"


def _layer_insulin_settings(session: Session, now: datetime, pid) -> str:
    hour = now.strftime("%H:00")
    q = session.query(InsulinSetting).filter(InsulinSetting.time_start <= hour)
    q = _pid_filter(q, InsulinSetting, pid)
    setting = q.order_by(InsulinSetting.time_start.desc()).first()
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


def _layer_patient_profile(session: Session, pid) -> str:
    q = session.query(PatientProfile)
    if pid is not None:
        q = q.filter_by(patient_id=pid)
    profile = q.first()
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


def _layer_recent_meals(session: Session, now: datetime, pid) -> str:
    q = session.query(Meal).filter(Meal.timestamp >= now - timedelta(hours=24))
    q = _pid_filter(q, Meal, pid)
    meals = q.order_by(Meal.timestamp.desc()).limit(5).all()
    if not meals:
        return ""

    lines = ["RECENT MEALS (24h):"]
    for m in meals:
        parts = [f"  {m.timestamp.strftime('%H:%M')}"]
        if m.carbs_g:
            parts.append(f"{m.carbs_g:.0f}g CHO")
        if m.description:
            parts.append(m.description[:60])
        lines.append(" \u2014 ".join(parts))

    return "\n".join(lines)


def _layer_health_data(session: Session, now: datetime, pid) -> str:
    q = session.query(HealthRecord).filter(
        HealthRecord.timestamp >= now - timedelta(hours=24)
    )
    q = _pid_filter(q, HealthRecord, pid)
    records = q.order_by(HealthRecord.timestamp.desc()).limit(10).all()
    if not records:
        return ""

    lines = ["HEALTH DATA (24h):"]
    for r in records:
        lines.append(f"  {r.timestamp.strftime('%H:%M')} {r.record_type}: {r.value} {r.unit or ''}")

    return "\n".join(lines)
