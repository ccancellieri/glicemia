"""13-layer context builder — injects real-time per-patient data into every AI call.

Layer 2 (GLUCOSE ANALYSIS) uses Gluco-LLM structured prompt format
(Li et al., 2025) for improved LLM glucose reasoning.
"""

import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    GlucoseReading, PumpStatus, BolusEvent, Meal,
    Activity, Condition, GlucosePattern, InsulinSetting,
    PatientProfile, HealthRecord,
)
from app.memory import build_memory_context

log = logging.getLogger(__name__)


def build_context(
    session: Session, patient_id: int = None, now: datetime = None, query: str = None
) -> str:
    """Build the full 13-layer context string for AI system prompt injection.
    All queries are scoped to the given patient_id.
    Layer 13 injects per-user memories learned from previous conversations."""
    now = now or datetime.utcnow()
    pid = patient_id
    layers = [
        _layer_narrative_summary(session, now, pid),
        _layer_current_cgm(session, now, pid),
        _layer_input_statistics(session, now, pid),
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
        build_memory_context(session, pid, query=query),
    ]
    return "\n\n".join(layer for layer in layers if layer)


def _pid_filter(query, model, pid):
    """Apply patient_id filter if pid is not None."""
    if pid is not None:
        return query.filter(model.patient_id == pid)
    return query


def _layer_narrative_summary(session: Session, now: datetime, pid) -> str:
    """Layer 0: Human-readable situation assessment for LLM grounding.

    Synthesizes current SG, trend, IOB, recent meals, and historical
    pattern into a short narrative the LLM can use as a starting point.
    """
    # Current reading
    q = session.query(GlucoseReading).filter(
        GlucoseReading.timestamp >= now - timedelta(minutes=15)
    )
    q = _pid_filter(q, GlucoseReading, pid)
    reading = q.order_by(GlucoseReading.timestamp.desc()).first()
    if not reading:
        return ""

    sg = reading.sg
    trend = reading.trend or "FLAT"

    # IOB
    pq = session.query(PumpStatus).filter(PumpStatus.timestamp >= now - timedelta(minutes=15))
    pq = _pid_filter(pq, PumpStatus, pid)
    pump = pq.order_by(PumpStatus.timestamp.desc()).first()
    iob = pump.active_insulin if pump and pump.active_insulin is not None else 0

    # Historical pattern for this hour
    hour_key = now.strftime("%H:00")
    pattern = session.query(GlucosePattern).filter_by(
        period_type="hourly", period_key=hour_key
    )
    pattern = _pid_filter(pattern, GlucosePattern, pid).first()
    historical_avg = pattern.avg_sg if pattern else None

    # Last meal
    mq = session.query(Meal).filter(Meal.timestamp >= now - timedelta(hours=4))
    mq = _pid_filter(mq, Meal, pid)
    last_meal = mq.order_by(Meal.timestamp.desc()).first()

    # Last bolus
    bq = session.query(BolusEvent).filter(BolusEvent.timestamp >= now - timedelta(hours=4))
    bq = _pid_filter(bq, BolusEvent, pid)
    last_bolus = bq.order_by(BolusEvent.timestamp.desc()).first()

    # Build narrative
    trend_words = {
        "UP": "RISING", "UP_FAST": "RISING FAST", "UP_RAPID": "RISING RAPIDLY",
        "DOWN": "FALLING", "DOWN_FAST": "FALLING FAST", "DOWN_RAPID": "FALLING RAPIDLY",
        "FLAT": "STABLE",
    }
    trend_word = trend_words.get(trend, "STABLE")

    lines = [f"SITUATION SUMMARY:"]
    lines.append(f"  You are currently at {sg:.0f} mg/dL and {trend_word}.")

    if historical_avg:
        diff = sg - historical_avg
        compare = "higher" if diff > 5 else ("lower" if diff < -5 else "close to")
        lines.append(
            f"  This is {compare} your usual {historical_avg:.0f} mg/dL "
            f"at this hour ({hour_key})."
        )

    if last_meal and last_meal.carbs_g:
        meal_ago = int((now - last_meal.timestamp).total_seconds() / 60)
        lines.append(f"  You had {last_meal.carbs_g:.0f}g carbs {meal_ago} min ago.")

    if last_bolus and last_bolus.volume_units:
        bolus_ago = int((now - last_bolus.timestamp).total_seconds() / 60)
        lines.append(f"  Last bolus: {last_bolus.volume_units:.1f}U, {bolus_ago} min ago. IOB: {iob:.1f}U.")

    # Quick prediction using simple model
    try:
        from app.analytics.estimator import predict_glucose
        pred_30 = predict_glucose(session, minutes_ahead=30)
        pred_60 = predict_glucose(session, minutes_ahead=60)
        if "predicted_sg" in pred_30 and "predicted_sg" in pred_60:
            lines.append(
                f"  Prediction: ~{pred_30['predicted_sg']} in 30min, "
                f"~{pred_60['predicted_sg']} in 60min."
            )
            p60 = pred_60["predicted_sg"]
            if p60 < 70:
                lines.append("  Assessment: HYPO RISK — take preventive action.")
            elif p60 > 250:
                lines.append("  Assessment: HIGH RISK — correction may be needed.")
            elif 70 <= p60 <= 180:
                lines.append("  Assessment: Likely to stay in range.")
            else:
                lines.append("  Assessment: Monitor closely.")
    except Exception:
        pass

    return "\n".join(lines)


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


def _layer_input_statistics(session: Session, now: datetime, pid) -> str:
    """Gluco-LLM structured analysis layer — statistics over last 3h CGM window.

    Computes min/max/median/mean/std, rate of change, CV%, key lag values,
    and last meal/bolus timing following the prompt format from
    Li et al. 2025 (Gluco-LLM).
    """
    cutoff = now - timedelta(hours=3)

    # --- 3h glucose readings ---
    q = session.query(GlucoseReading).filter(GlucoseReading.timestamp >= cutoff)
    q = _pid_filter(q, GlucoseReading, pid)
    readings = q.order_by(GlucoseReading.timestamp.asc()).all()
    if not readings or len(readings) < 3:
        return ""

    values = [r.sg for r in readings]
    n = len(values)
    mean_sg = sum(values) / n
    sorted_v = sorted(values)
    median_sg = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    min_sg = sorted_v[0]
    max_sg = sorted_v[-1]
    variance = sum((v - mean_sg) ** 2 for v in values) / n
    std_sg = math.sqrt(variance)
    cv_pct = (std_sg / mean_sg * 100) if mean_sg > 0 else 0

    # --- Rate of change (linear regression over last 15min / ~3 readings) ---
    recent = [(r.timestamp, r.sg) for r in readings[-4:]]
    if len(recent) >= 2:
        t0 = recent[0][0]
        xs = [(r[0] - t0).total_seconds() / 60.0 for r in recent]
        ys = [r[1] for r in recent]
        n_r = len(xs)
        x_mean = sum(xs) / n_r
        y_mean = sum(ys) / n_r
        num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n_r))
        den = sum((xs[i] - x_mean) ** 2 for i in range(n_r))
        rate = num / den if den > 0 else 0.0  # mg/dL per minute
    else:
        rate = 0.0

    if rate > 1.0:
        trend_label = "RISING FAST"
    elif rate > 0.3:
        trend_label = "RISING"
    elif rate > -0.3:
        trend_label = "STABLE"
    elif rate > -1.0:
        trend_label = "FALLING"
    else:
        trend_label = "FALLING FAST"

    # --- Key lag values ---
    lag_targets = [15, 30, 45, 60, 90]
    lag_values = {}
    for lag in lag_targets:
        target_time = now - timedelta(minutes=lag)
        closest = min(readings, key=lambda r: abs((r.timestamp - target_time).total_seconds()))
        if abs((closest.timestamp - target_time).total_seconds()) <= 600:  # within 10min
            lag_values[lag] = f"{closest.sg:.0f}"
        else:
            lag_values[lag] = "n/a"

    lags_str = ", ".join(f"t-{lag}: {lag_values[lag]}" for lag in lag_targets)

    # --- Last meal ---
    mq = session.query(Meal).filter(Meal.timestamp >= now - timedelta(hours=6))
    mq = _pid_filter(mq, Meal, pid)
    last_meal = mq.order_by(Meal.timestamp.desc()).first()
    if last_meal and last_meal.carbs_g:
        meal_ago = int((now - last_meal.timestamp).total_seconds() / 60)
        meal_str = f"  Last meal: {last_meal.carbs_g:.0f}g carbs, {meal_ago} min ago"
    else:
        meal_str = "  Last meal: n/a"

    # --- Last bolus + IOB ---
    bq = session.query(BolusEvent).filter(BolusEvent.timestamp >= now - timedelta(hours=6))
    bq = _pid_filter(bq, BolusEvent, pid)
    last_bolus = bq.order_by(BolusEvent.timestamp.desc()).first()
    if last_bolus and last_bolus.volume_units:
        bolus_ago = int((now - last_bolus.timestamp).total_seconds() / 60)
        bolus_str = f"  Last bolus: {last_bolus.volume_units:.1f}U, {bolus_ago} min ago"
    else:
        bolus_str = "  Last bolus: n/a"

    # IOB from most recent PumpStatus
    pq = session.query(PumpStatus).filter(PumpStatus.timestamp >= now - timedelta(minutes=15))
    pq = _pid_filter(pq, PumpStatus, pid)
    pump = pq.order_by(PumpStatus.timestamp.desc()).first()
    iob_str = f" | IOB: {pump.active_insulin:.1f}U" if pump and pump.active_insulin is not None else ""

    cv_label = "stable" if cv_pct < 20 else ("moderate" if cv_pct < 36 else "high")

    return (
        f"GLUCOSE ANALYSIS (last 3h):\n"
        f"  Range: {min_sg:.0f}-{max_sg:.0f} mg/dL | Median: {median_sg:.0f} | "
        f"Mean: {mean_sg:.0f} ±{std_sg:.0f}\n"
        f"  Current trend: {trend_label} ({rate:+.1f} mg/dL/min)\n"
        f"  CV: {cv_pct:.1f}% ({cv_label})\n"
        f"  Key values: {lags_str}\n"
        f"{meal_str}\n"
        f"{bolus_str}{iob_str}"
    )


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
