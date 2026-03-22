"""GliceMia metrics — TIR, GMI, CV, hypo analysis, time-slot patterns.

Adapted from the original analyze.py and main.py analysis functions.
Works against the SQLAlchemy database instead of CSV files.
"""

import logging
from datetime import datetime, timedelta, time
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import GlucoseReading, BolusEvent, Meal

log = logging.getLogger(__name__)

# Glucose thresholds (mg/dL) — international consensus
VERY_LOW = 54
LOW = 70
HIGH = 180
VERY_HIGH = 250


def compute_metrics(
    session: Session,
    start: datetime,
    end: datetime,
) -> Optional[dict]:
    """Compute glucose metrics for a date range.

    Returns dict with: mean_sg, std_sg, cv, gmi, tir, titr,
    tbr1, tbr2, tar1, tar2, readings count, days, etc.
    """
    readings = (
        session.query(GlucoseReading.sg)
        .filter(
            GlucoseReading.timestamp >= start,
            GlucoseReading.timestamp <= end,
            GlucoseReading.sg.isnot(None),
            GlucoseReading.sg > 0,
        )
        .all()
    )

    values = [r.sg for r in readings]
    n = len(values)
    if n == 0:
        return None

    mean_sg = sum(values) / n
    variance = sum((v - mean_sg) ** 2 for v in values) / n
    std_sg = variance ** 0.5
    cv = 100 * std_sg / mean_sg if mean_sg > 0 else 0

    # GMI (Glucose Management Indicator) ≈ estimated HbA1c
    gmi = 3.31 + 0.02392 * mean_sg

    def pct(lo, hi):
        return 100 * sum(1 for v in values if lo <= v < hi) / n

    tir = pct(LOW, HIGH + 1)       # 70-180
    titr = pct(LOW, 141)            # 70-140 (tight)
    tbr1 = pct(VERY_LOW, LOW)      # 54-70
    tbr2 = pct(0, VERY_LOW)        # <54
    tar1 = pct(HIGH + 1, VERY_HIGH + 1)  # 181-250
    tar2 = pct(VERY_HIGH + 1, 9999)      # >250

    # Days covered
    dates = set()
    ts_readings = (
        session.query(GlucoseReading.timestamp)
        .filter(
            GlucoseReading.timestamp >= start,
            GlucoseReading.timestamp <= end,
            GlucoseReading.sg.isnot(None),
        )
        .all()
    )
    for r in ts_readings:
        dates.add(r.timestamp.date())
    days = len(dates)

    # Bolus stats
    bolus_data = (
        session.query(
            func.count(BolusEvent.id),
            func.sum(BolusEvent.volume_units),
        )
        .filter(
            BolusEvent.timestamp >= start,
            BolusEvent.timestamp <= end,
        )
        .first()
    )
    bolus_count = bolus_data[0] or 0
    bolus_total = bolus_data[1] or 0

    # Carb stats
    carb_data = (
        session.query(
            func.count(Meal.id),
            func.sum(Meal.carbs_g),
        )
        .filter(
            Meal.timestamp >= start,
            Meal.timestamp <= end,
        )
        .first()
    )

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "readings": n,
        "mean_sg": round(mean_sg, 1),
        "std_sg": round(std_sg, 1),
        "cv": round(cv, 1),
        "gmi": round(gmi, 1),
        "tir": round(tir, 1),
        "titr": round(titr, 1),
        "tbr1": round(tbr1, 1),
        "tbr2": round(tbr2, 1),
        "tar1": round(tar1, 1),
        "tar2": round(tar2, 1),
        "bolus_count": bolus_count,
        "bolus_total_u": round(bolus_total, 1),
        "avg_bolus_per_day": round(bolus_count / max(days, 1), 1),
        "avg_insulin_per_day": round(bolus_total / max(days, 1), 1),
        "carb_entries": carb_data[0] or 0,
        "carb_total_g": round(carb_data[1] or 0, 0),
    }


def analyze_hypo_episodes(
    session: Session,
    start: datetime,
    end: datetime,
    gap_min: int = 15,
) -> list[dict]:
    """Detect and analyze hypoglycemia episodes (<70 mg/dL).

    Groups consecutive low readings (within gap_min) into episodes.
    For each episode returns: start, duration, nadir, and preceding bolus context.
    """
    readings = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.timestamp >= start,
            GlucoseReading.timestamp <= end,
            GlucoseReading.sg < LOW,
            GlucoseReading.sg > 0,
        )
        .order_by(GlucoseReading.timestamp.asc())
        .all()
    )

    if not readings:
        return []

    episodes = []
    ep_start = readings[0].timestamp
    ep_values = [readings[0].sg]
    prev_ts = readings[0].timestamp

    for r in readings[1:]:
        if (r.timestamp - prev_ts) <= timedelta(minutes=gap_min):
            ep_values.append(r.sg)
        else:
            # Close current episode
            episodes.append(_build_episode(session, ep_start, prev_ts, ep_values))
            ep_start = r.timestamp
            ep_values = [r.sg]
        prev_ts = r.timestamp

    # Close last episode
    episodes.append(_build_episode(session, ep_start, prev_ts, ep_values))

    return episodes


def _build_episode(
    session: Session,
    ep_start: datetime,
    ep_end: datetime,
    values: list[float],
) -> dict:
    """Build a hypo episode summary with preceding bolus context."""
    duration_min = max(1, int((ep_end - ep_start).total_seconds() / 60))
    nadir = min(values)

    # Look at boluses in the 3 hours before
    context_start = ep_start - timedelta(hours=3)
    boluses = (
        session.query(BolusEvent)
        .filter(
            BolusEvent.timestamp >= context_start,
            BolusEvent.timestamp <= ep_start,
        )
        .all()
    )
    bolus_total = sum(b.volume_units for b in boluses if b.volume_units)
    bolus_context = (
        f"{bolus_total:.1f}U in {len(boluses)} boluses (3h before)"
        if boluses else "No recent boluses"
    )

    return {
        "start": ep_start.isoformat(),
        "end": ep_end.isoformat(),
        "duration_min": duration_min,
        "nadir": round(nadir),
        "severity": "very_low" if nadir < VERY_LOW else "low",
        "readings": len(values),
        "bolus_context": bolus_context,
    }


def time_slot_analysis(
    session: Session,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Analyze glucose patterns by time-of-day slots.

    Returns per-slot analysis: night (22-08), day (08-16), evening (16-22).
    Flags recurring hypo (>30% of days) and hyper (>50% of days) patterns.
    """
    slots = [
        ("Night (22-08)", time(22, 0), time(7, 59)),
        ("Day (08-16)", time(8, 0), time(15, 59)),
        ("Evening (16-22)", time(16, 0), time(21, 59)),
    ]

    readings = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.timestamp >= start,
            GlucoseReading.timestamp <= end,
            GlucoseReading.sg.isnot(None),
            GlucoseReading.sg > 0,
        )
        .all()
    )

    if not readings:
        return []

    total_days = len(set(r.timestamp.date() for r in readings))
    if total_days == 0:
        return []

    results = []
    for name, slot_start, slot_end in slots:
        if slot_start > slot_end:
            # Overnight slot
            slot_readings = [
                r for r in readings
                if r.timestamp.time() >= slot_start or r.timestamp.time() <= slot_end
            ]
        else:
            slot_readings = [
                r for r in readings
                if slot_start <= r.timestamp.time() <= slot_end
            ]

        if not slot_readings:
            continue

        values = [r.sg for r in slot_readings]
        n = len(values)
        mean = sum(values) / n

        hypo_days = len(set(
            r.timestamp.date() for r in slot_readings if r.sg < LOW
        ))
        hyper_days = len(set(
            r.timestamp.date() for r in slot_readings if r.sg > HIGH
        ))

        issues = []
        if hypo_days / total_days > 0.3:
            hypo_mean = sum(v for v in values if v < LOW) / max(sum(1 for v in values if v < LOW), 1)
            issues.append({
                "type": "recurring_hypo",
                "frequency_pct": round(100 * hypo_days / total_days),
                "avg_hypo_sg": round(hypo_mean),
            })
        if hyper_days / total_days > 0.5:
            hyper_mean = sum(v for v in values if v > HIGH) / max(sum(1 for v in values if v > HIGH), 1)
            issues.append({
                "type": "recurring_hyper",
                "frequency_pct": round(100 * hyper_days / total_days),
                "avg_hyper_sg": round(hyper_mean),
            })

        tir = 100 * sum(1 for v in values if LOW <= v <= HIGH) / n

        results.append({
            "slot": name,
            "readings": n,
            "mean_sg": round(mean, 1),
            "tir_pct": round(tir, 1),
            "hypo_days": hypo_days,
            "hyper_days": hyper_days,
            "issues": issues,
        })

    return results
