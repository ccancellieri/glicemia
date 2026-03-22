"""Proactive alert engine — detects situations requiring attention.

Checks run after every CareLink poll. Alerts are contextual, friendly,
and always include final predicted glucose values + historical comparison.
Deduplicates so the same alert type isn't spammed within a cooldown window.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import GlucoseReading, PumpStatus, GlucosePattern

log = logging.getLogger(__name__)

# Thresholds
URGENT_LOW = 54
LOW = 70
HIGH = 250
FALLING_FAST_RATE = -2.5  # mg/dL per minute
RISING_FAST_RATE = 3.0

# Cooldowns (prevent repeated alerts of same type)
_alert_cooldowns: dict[str, datetime] = {}
COOLDOWN_MINUTES = {
    "urgent_low": 15,
    "low": 30,
    "predicted_low": 45,
    "high": 60,
    "predicted_high": 60,
    "falling_fast": 20,
    "rising_fast": 30,
    "sensor_gap": 30,
    "reservoir_low": 120,
    "battery_low": 120,
    "prolonged_high": 120,
}

# Trend rate estimates (mg/dL per minute)
TREND_RATES = {
    "UP": 2.0,
    "UP_FAST": 3.0,
    "UP_RAPID": 4.0,
    "DOWN": -1.5,
    "DOWN_FAST": -2.5,
    "DOWN_RAPID": -3.5,
    "FLAT": 0.0,
}


class Alert:
    """Represents a proactive alert to send to the user."""

    def __init__(
        self,
        alert_type: str,
        severity: str,  # urgent, warning, info
        sg: Optional[float] = None,
        predicted_sg: Optional[float] = None,
        minutes_to_event: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        self.alert_type = alert_type
        self.severity = severity
        self.sg = sg
        self.predicted_sg = predicted_sg
        self.minutes_to_event = minutes_to_event
        self.details = details or {}
        self.timestamp = datetime.utcnow()


def check_alerts(session: Session, now: datetime = None) -> list[Alert]:
    """Run all alert checks against current data. Returns list of triggered alerts."""
    now = now or datetime.utcnow()
    alerts = []

    # Get latest reading
    reading = (
        session.query(GlucoseReading)
        .filter(GlucoseReading.sg.isnot(None))
        .order_by(GlucoseReading.timestamp.desc())
        .first()
    )
    if not reading:
        return alerts

    # Get latest pump status
    pump = (
        session.query(PumpStatus)
        .order_by(PumpStatus.timestamp.desc())
        .first()
    )

    sg = reading.sg
    trend = reading.trend or "FLAT"
    rate = TREND_RATES.get(trend, 0.0)
    data_age = (now - reading.timestamp).total_seconds() / 60

    # --- Sensor data gap ---
    if data_age > 15:
        a = _maybe_alert("sensor_gap", now, Alert(
            alert_type="sensor_gap",
            severity="warning",
            sg=sg,
            details={"minutes_since_last": round(data_age)},
        ))
        if a:
            alerts.append(a)
        return alerts  # Stale data — skip other checks

    # --- Urgent low (<54) ---
    if sg < URGENT_LOW:
        a = _maybe_alert("urgent_low", now, Alert(
            alert_type="urgent_low",
            severity="urgent",
            sg=sg,
            predicted_sg=max(40, sg + rate * 15),
            details={"trend": trend},
        ))
        if a:
            alerts.append(a)

    # --- Low (54-70) ---
    elif sg < LOW:
        pred_15 = sg + rate * 15
        a = _maybe_alert("low", now, Alert(
            alert_type="low",
            severity="warning",
            sg=sg,
            predicted_sg=round(max(40, pred_15)),
            details={"trend": trend},
        ))
        if a:
            alerts.append(a)

    # --- Predicted low (currently OK but heading low within 30 min) ---
    elif sg >= LOW and rate < 0:
        pred_30 = sg + rate * 30
        if pred_30 < LOW:
            minutes_to_low = (sg - LOW) / abs(rate) if rate != 0 else 999
            a = _maybe_alert("predicted_low", now, Alert(
                alert_type="predicted_low",
                severity="warning",
                sg=sg,
                predicted_sg=round(max(40, pred_30)),
                minutes_to_event=round(minutes_to_low),
                details={"trend": trend, "pred_15": round(sg + rate * 15)},
            ))
            if a:
                alerts.append(a)

    # --- High (>250) ---
    if sg > HIGH:
        a = _maybe_alert("high", now, Alert(
            alert_type="high",
            severity="warning",
            sg=sg,
            predicted_sg=round(sg + rate * 30),
            details={"trend": trend},
        ))
        if a:
            alerts.append(a)

    # --- Predicted high (heading above 250 within 30 min) ---
    elif sg <= HIGH and rate > 0:
        pred_30 = sg + rate * 30
        if pred_30 > HIGH:
            minutes_to_high = (HIGH - sg) / rate if rate > 0 else 999
            a = _maybe_alert("predicted_high", now, Alert(
                alert_type="predicted_high",
                severity="info",
                sg=sg,
                predicted_sg=round(pred_30),
                minutes_to_event=round(minutes_to_high),
                details={"trend": trend},
            ))
            if a:
                alerts.append(a)

    # --- Falling fast ---
    if rate <= FALLING_FAST_RATE:
        pred_15 = sg + rate * 15
        a = _maybe_alert("falling_fast", now, Alert(
            alert_type="falling_fast",
            severity="warning",
            sg=sg,
            predicted_sg=round(max(40, pred_15)),
            details={"trend": trend, "rate": rate},
        ))
        if a:
            alerts.append(a)

    # --- Rising fast ---
    if rate >= RISING_FAST_RATE:
        pred_15 = sg + rate * 15
        a = _maybe_alert("rising_fast", now, Alert(
            alert_type="rising_fast",
            severity="info",
            sg=sg,
            predicted_sg=round(pred_15),
            details={"trend": trend, "rate": rate},
        ))
        if a:
            alerts.append(a)

    # --- Prolonged high (>180 for 2+ hours) ---
    two_hours_ago = now - timedelta(hours=2)
    high_readings = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.timestamp >= two_hours_ago,
            GlucoseReading.sg > 180,
        )
        .count()
    )
    total_recent = (
        session.query(GlucoseReading)
        .filter(GlucoseReading.timestamp >= two_hours_ago)
        .count()
    )
    if total_recent > 0 and high_readings / total_recent > 0.9:
        a = _maybe_alert("prolonged_high", now, Alert(
            alert_type="prolonged_high",
            severity="warning",
            sg=sg,
            details={"hours_above_180": 2, "trend": trend},
        ))
        if a:
            alerts.append(a)

    # --- Pump alerts ---
    if pump:
        if pump.reservoir_units is not None and pump.reservoir_units < 20:
            a = _maybe_alert("reservoir_low", now, Alert(
                alert_type="reservoir_low",
                severity="info",
                details={"units_remaining": pump.reservoir_units},
            ))
            if a:
                alerts.append(a)

        if pump.battery_pct is not None and pump.battery_pct < 15:
            a = _maybe_alert("battery_low", now, Alert(
                alert_type="battery_low",
                severity="info",
                details={"battery_pct": pump.battery_pct},
            ))
            if a:
                alerts.append(a)

    # Enrich alerts with historical pattern context
    for alert in alerts:
        alert.details["pattern"] = _get_pattern_context(session, now)

    return alerts


def _maybe_alert(alert_type: str, now: datetime, alert: Alert) -> Optional[Alert]:
    """Return alert only if cooldown has expired for this type."""
    last = _alert_cooldowns.get(alert_type)
    cooldown = COOLDOWN_MINUTES.get(alert_type, 30)
    if last and (now - last) < timedelta(minutes=cooldown):
        return None
    _alert_cooldowns[alert_type] = now
    return alert


def _get_pattern_context(session: Session, now: datetime) -> str:
    """Get historical pattern context for enriching alerts."""
    hour_key = now.strftime("%H:00")
    pattern = (
        session.query(GlucosePattern)
        .filter_by(period_type="hourly", period_key=hour_key)
        .first()
    )
    if not pattern:
        return ""
    return (
        f"Historical avg at {hour_key}: {pattern.avg_sg:.0f} mg/dL, "
        f"TIR={pattern.tir_pct:.0f}%, hypos={pattern.hypo_count}"
    )
