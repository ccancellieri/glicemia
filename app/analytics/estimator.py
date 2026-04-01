"""GliceMia glucose prediction and bolus estimation engine.

Provides OWN estimations — not just deferring to the pump's Bolus Wizard.
Always returns final predicted glucose values, not just deltas.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    GlucoseReading, PumpStatus, InsulinSetting,
    GlucosePattern, Activity,
)

log = logging.getLogger(__name__)

# Insulin action curve (MiniMed 780G uses ~3-4h DIA)
DIA_HOURS = 4.0
# Peak insulin action at ~75 min for rapid-acting
PEAK_MIN = 75

# Literature-calibrated uncertainty (mg/dL) from Gluco-LLM RMSE data (Li et al. 2025)
BASE_UNCERTAINTY = {15: 12, 30: 20, 60: 30, 90: 38, 120: 45}

# Dalla Man 2007 oral glucose model parameters
_CARB_KA = 0.05   # absorption rate constant (1/min)
_CARB_KE = 0.03   # elimination rate constant (1/min)
# Carb-to-glucose sensitivity (mg/dL per gram, average T1D)
_CARB_SENSITIVITY = 3.5


def get_current_state(session: Session) -> Optional[dict]:
    """Get the current glucose/pump state from the DB."""
    reading = (
        session.query(GlucoseReading)
        .filter(GlucoseReading.sg.isnot(None))
        .order_by(GlucoseReading.timestamp.desc())
        .first()
    )
    if not reading:
        return None

    pump = (
        session.query(PumpStatus)
        .order_by(PumpStatus.timestamp.desc())
        .first()
    )

    return {
        "sg": reading.sg,
        "trend": reading.trend or "FLAT",
        "timestamp": reading.timestamp,
        "iob": pump.active_insulin if pump else 0,
        "basal_rate": pump.basal_rate if pump else 0,
        "auto_mode": pump.auto_mode if pump else "UNKNOWN",
    }


def get_insulin_settings(session: Session, now: datetime = None) -> dict:
    """Get the current I:C ratio and ISF for the current time of day."""
    now = now or datetime.utcnow()
    hour = now.strftime("%H:00")

    setting = (
        session.query(InsulinSetting)
        .filter(InsulinSetting.time_start <= hour)
        .order_by(InsulinSetting.time_start.desc())
        .first()
    )

    if setting:
        return {
            "ic_ratio": setting.ic_ratio or 10.0,
            "isf": setting.isf or 50.0,
            "target_sg": setting.target_sg or 120.0,
            "source": setting.source,
        }

    # Fallback defaults
    return {"ic_ratio": 10.0, "isf": 50.0, "target_sg": 120.0, "source": "default"}


def predict_glucose(
    session: Session,
    minutes_ahead: int = 60,
    carbs_g: float = 0,
    bolus_u: float = 0,
    log_prediction: bool = False,
    patient_id: int = None,
) -> dict:
    """Predict glucose at a future time point.

    Takes into account:
    - Current SG and trend
    - IOB (insulin on board)
    - Planned carbs and bolus
    - Historical pattern for this time of day

    Returns:
        Dict with predicted_sg, range_low, range_high, trend_contribution,
        iob_contribution, carb_contribution, bolus_contribution.
    """
    state = get_current_state(session)
    if not state:
        return {"error": "No current glucose data"}

    sg = state["sg"]
    iob = state["iob"] or 0
    settings = get_insulin_settings(session)
    isf = settings["isf"]
    ic_ratio = settings["ic_ratio"]

    # 1. Trend-based prediction with exponential decay
    trend_rates = {
        "UP": 2.0, "UP_FAST": 3.0, "UP_RAPID": 4.0,
        "DOWN": -1.5, "DOWN_FAST": -2.5, "DOWN_RAPID": -3.5,
        "FLAT": 0.0,
    }
    trend_rate = trend_rates.get(state["trend"], 0.0)
    # Exponential trend decay: tau=20 for fast trends, 40 for slow
    tau = 20 if abs(trend_rate) > 2.0 else 40
    trend_delta = trend_rate * tau * (1 - math.exp(-minutes_ahead / tau))

    # 2. IOB effect (remaining insulin will lower glucose)
    # Simplified: IOB acts over remaining DIA with exponential decay
    iob_remaining_fraction = _iob_remaining_fraction(0, minutes_ahead)
    iob_delta = -(iob * iob_remaining_fraction * isf)

    # 3. New bolus effect
    bolus_delta = 0
    if bolus_u > 0:
        bolus_active = _iob_active_fraction(0, minutes_ahead)
        bolus_delta = -(bolus_u * bolus_active * isf)

    # 4. Carb effect (Dalla Man 2007 dual-exponential model)
    carb_delta = 0
    if carbs_g > 0:
        carb_delta = _carb_absorption(minutes_ahead, carbs_g) * _CARB_SENSITIVITY

    # 5. Historical pattern adjustment
    pattern_adj = _pattern_adjustment(session, state["timestamp"], minutes_ahead)

    # Total prediction
    predicted = sg + trend_delta + iob_delta + bolus_delta + carb_delta + pattern_adj
    predicted = max(40, predicted)  # Floor at 40

    # Literature-calibrated uncertainty scaled by current glycemic variability
    cv_3h = _recent_cv(session, state["timestamp"])
    uncertainty = _calibrated_uncertainty(minutes_ahead, cv_3h)
    range_low = max(40, predicted - uncertainty)
    range_high = predicted + uncertainty

    # Optionally log prediction for accuracy tracking
    if log_prediction and patient_id is not None:
        try:
            from app.models import PredictionLog
            session.add(PredictionLog(
                patient_id=patient_id,
                timestamp=state["timestamp"],
                horizon_min=minutes_ahead,
                predicted_sg=round(predicted),
                method="estimator",
            ))
            session.commit()
        except Exception as e:
            log.debug("Failed to log prediction: %s", e)

    return {
        "current_sg": round(sg),
        "predicted_sg": round(predicted),
        "range_low": round(range_low),
        "range_high": round(range_high),
        "minutes_ahead": minutes_ahead,
        "trend_contribution": round(trend_delta, 1),
        "iob_contribution": round(iob_delta, 1),
        "bolus_contribution": round(bolus_delta, 1),
        "carb_contribution": round(carb_delta, 1),
        "pattern_adjustment": round(pattern_adj, 1),
        "iob_current": round(iob, 2),
    }


def estimate_bolus(
    session: Session,
    carbs_g: float,
    target_sg: float = None,
) -> dict:
    """Estimate bolus dose for a meal.

    Provides OWN estimation using I:C, ISF, current SG, IOB.
    Shows final predicted glucose value.
    """
    state = get_current_state(session)
    if not state:
        return {"error": "No current glucose data"}

    settings = get_insulin_settings(session)
    ic_ratio = settings["ic_ratio"]
    isf = settings["isf"]
    target = target_sg or settings["target_sg"]
    sg = state["sg"]
    iob = state["iob"] or 0

    # Carb bolus
    carb_bolus = carbs_g / ic_ratio if ic_ratio > 0 else 0

    # Correction bolus (if above target, accounting for IOB)
    correction_needed = (sg - target) / isf if isf > 0 else 0
    correction_after_iob = max(0, correction_needed - iob)

    # Total suggested bolus
    total_bolus = max(0, carb_bolus + correction_after_iob)

    # Predict glucose after meal + bolus (at 2 hours)
    prediction = predict_glucose(
        session, minutes_ahead=120, carbs_g=carbs_g, bolus_u=total_bolus
    )

    # Also predict what happens with pump's auto-correction
    # (780G in auto mode will micro-bolus for corrections)
    auto_mode_note = ""
    if state.get("auto_mode") in ("AUTO_BASAL", "AUTO_BOLUS"):
        auto_mode_note = (
            "780G in auto mode will also micro-bolus for corrections. "
            "My estimate is for the food bolus only."
        )

    return {
        "current_sg": round(sg),
        "carbs_g": round(carbs_g),
        "ic_ratio": ic_ratio,
        "isf": isf,
        "target_sg": target,
        "iob_current": round(iob, 2),
        "carb_bolus": round(carb_bolus, 2),
        "correction_bolus": round(correction_after_iob, 2),
        "total_suggested_bolus": round(total_bolus, 1),
        "predicted_sg_2h": prediction.get("predicted_sg"),
        "predicted_range": f"{prediction.get('range_low')}-{prediction.get('range_high')}",
        "auto_mode_note": auto_mode_note,
        "settings_source": settings["source"],
    }


def estimate_activity_impact(
    session: Session,
    activity_type: str,
    duration_min: int,
    intensity: str = "moderate",
) -> dict:
    """Estimate glucose impact of a planned activity.

    Uses historical data for similar activities + physiological model.
    """
    state = get_current_state(session)
    if not state:
        return {"error": "No current glucose data"}

    sg = state["sg"]
    iob = state["iob"] or 0

    # Base glucose drop rates by activity type and intensity (mg/dL per 30 min)
    drop_rates = {
        ("cycling", "low"): 15,
        ("cycling", "moderate"): 25,
        ("cycling", "vigorous"): 40,
        ("walking", "low"): 8,
        ("walking", "moderate"): 15,
        ("walking", "vigorous"): 22,
        ("running", "moderate"): 30,
        ("running", "vigorous"): 45,
        ("gym", "moderate"): 20,
        ("gym", "vigorous"): 30,
    }

    base_rate = drop_rates.get((activity_type, intensity), 20)
    total_drop = base_rate * (duration_min / 30)

    # IOB amplifies the drop (~50% more effect during exercise)
    iob_amplification = iob * 15  # rough: each unit IOB adds ~15 mg/dL drop
    total_drop += iob_amplification

    # Historical correction: check similar past activities
    historical_avg = _historical_activity_delta(session, activity_type, duration_min)
    if historical_avg is not None:
        # Blend model with historical (60% historical, 40% model)
        total_drop = 0.6 * abs(historical_avg) + 0.4 * total_drop

    predicted_sg = max(40, sg - total_drop)
    predicted_end = max(40, sg - total_drop)

    # Risk assessment
    risk = "low"
    if predicted_end < 70:
        risk = "high"
    elif predicted_end < 90:
        risk = "moderate"

    # Carb recommendation if at risk
    carbs_needed = 0
    if predicted_end < 90:
        carbs_needed = max(0, (90 - predicted_end) / 3.5)

    return {
        "current_sg": round(sg),
        "activity_type": activity_type,
        "duration_min": duration_min,
        "intensity": intensity,
        "iob_current": round(iob, 2),
        "estimated_drop": round(total_drop),
        "predicted_sg_end": round(predicted_end),
        "predicted_range": f"{round(max(40, predicted_end - 15))}-{round(predicted_end + 15)}",
        "risk_level": risk,
        "carbs_recommended_g": round(carbs_needed),
        "historical_data_used": historical_avg is not None,
    }


def predict_trajectory(
    session: Session,
    carbs_g: float = 0,
    bolus_u: float = 0,
    horizons: tuple = (15, 30, 60, 90, 120),
) -> list[dict]:
    """Predict glucose at multiple future horizons with confidence intervals.

    Returns a list of prediction dicts, one per horizon.
    """
    results = []
    for minutes in horizons:
        pred = predict_glucose(session, minutes_ahead=minutes, carbs_g=carbs_g, bolus_u=bolus_u)
        results.append(pred)
    return results


def _carb_absorption(minutes: float, carbs_g: float) -> float:
    """Dalla Man 2007 dual-exponential oral glucose absorption model.

    Returns the cumulative fraction of carbs absorbed at `minutes`.
    """
    if minutes <= 0:
        return 0.0
    ka, ke = _CARB_KA, _CARB_KE
    t = minutes  # already in minutes (rates adjusted accordingly)
    # Cumulative absorption fraction (integrated rate)
    if abs(ka - ke) < 1e-6:
        # Degenerate case: ka == ke
        frac = 1.0 - (1.0 + ka * t) * math.exp(-ka * t)
    else:
        frac = 1.0 - (ka * math.exp(-ke * t) - ke * math.exp(-ka * t)) / (ka - ke)
    return max(0.0, min(1.0, frac))


def _recent_cv(session: Session, now: datetime) -> float:
    """Compute coefficient of variation (%) of glucose over last 3 hours."""
    cutoff = now - timedelta(hours=3)
    readings = (
        session.query(GlucoseReading.sg)
        .filter(GlucoseReading.timestamp >= cutoff, GlucoseReading.sg.isnot(None))
        .all()
    )
    if len(readings) < 3:
        return 15.0  # default moderate CV
    values = [r.sg for r in readings]
    mean = sum(values) / len(values)
    if mean <= 0:
        return 15.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / mean * 100


def _calibrated_uncertainty(minutes_ahead: int, cv_3h: float) -> float:
    """Literature-calibrated confidence interval scaled by glycemic variability.

    Base values from Gluco-LLM RMSE data (Li et al. 2025).
    Scaled by current CV relative to an average CV of 15%.
    """
    # Interpolate from BASE_UNCERTAINTY
    horizons = sorted(BASE_UNCERTAINTY.keys())
    if minutes_ahead <= horizons[0]:
        base = BASE_UNCERTAINTY[horizons[0]]
    elif minutes_ahead >= horizons[-1]:
        base = BASE_UNCERTAINTY[horizons[-1]]
    else:
        for i in range(len(horizons) - 1):
            if horizons[i] <= minutes_ahead <= horizons[i + 1]:
                t = (minutes_ahead - horizons[i]) / (horizons[i + 1] - horizons[i])
                base = BASE_UNCERTAINTY[horizons[i]] * (1 - t) + BASE_UNCERTAINTY[horizons[i + 1]] * t
                break
        else:
            base = 30.0

    volatility_factor = max(0.7, min(1.5, cv_3h / 15.0))
    return base * volatility_factor


def _iob_remaining_fraction(start_min: int, end_min: int) -> float:
    """Fraction of IOB that acts between start_min and end_min."""
    dia_min = DIA_HOURS * 60
    # Simplified exponential decay
    if end_min >= dia_min:
        return 1.0
    return 1.0 - (1.0 - end_min / dia_min) ** 2


def _iob_active_fraction(start_min: int, end_min: int) -> float:
    """Fraction of a bolus that has acted by end_min."""
    dia_min = DIA_HOURS * 60
    if end_min >= dia_min:
        return 1.0
    # Sigmoid-like: slow start, peak at PEAK_MIN, then tails off
    t = end_min / dia_min
    return min(1.0, 1.0 - (1.0 - t) ** 2.5)


def _pattern_adjustment(session: Session, now: datetime, minutes_ahead: int) -> float:
    """Adjust prediction based on historical hourly pattern."""
    future_hour = (now + timedelta(minutes=minutes_ahead)).strftime("%H:00")
    current_hour = now.strftime("%H:00")

    future_pattern = (
        session.query(GlucosePattern)
        .filter_by(period_type="hourly", period_key=future_hour)
        .first()
    )
    current_pattern = (
        session.query(GlucosePattern)
        .filter_by(period_type="hourly", period_key=current_hour)
        .first()
    )

    if future_pattern and current_pattern and current_pattern.avg_sg > 0:
        # Small nudge toward the historical pattern
        historical_delta = future_pattern.avg_sg - current_pattern.avg_sg
        return historical_delta * 0.2  # 20% weight on historical
    return 0.0


def _historical_activity_delta(
    session: Session,
    activity_type: str,
    duration_min: int,
    lookback_days: int = 90,
) -> Optional[float]:
    """Get average glucose delta from similar past activities."""
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    activities = (
        session.query(Activity)
        .filter(
            Activity.activity_type == activity_type,
            Activity.timestamp_start >= cutoff,
            Activity.sg_delta.isnot(None),
        )
        .all()
    )

    if len(activities) < 3:
        return None

    # Filter for similar duration (±30%)
    similar = [
        a for a in activities
        if a.duration_min and abs(a.duration_min - duration_min) / max(duration_min, 1) < 0.3
    ]

    if len(similar) < 2:
        similar = activities  # Fall back to all activities of this type

    deltas = [a.sg_delta for a in similar if a.sg_delta is not None]
    if not deltas:
        return None

    return sum(deltas) / len(deltas)
