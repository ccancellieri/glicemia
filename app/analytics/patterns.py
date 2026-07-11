"""GliceMia pattern computation — pre-compute glucose aggregates for fast context.

Runs daily (via scheduler) to populate the glucose_patterns table.
Computes: hourly (24 slots, last 14d), daily (7 weekdays, last 8w),
monthly (12 months, all history), yearly.
"""

import logging
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import GlucoseReading, GlucosePattern, BolusEvent, Meal
from app.timeutils import utcnow

log = logging.getLogger(__name__)

LOW = 70


def compute_all_patterns(session: Session, patient_id: int = None, now: datetime = None):
    """Compute all pattern types for one patient and upsert into glucose_patterns."""
    now = now or utcnow()

    log.info("Computing glucose patterns (patient=%s)...", patient_id)
    _compute_hourly(session, now, patient_id)
    _compute_daily(session, now, patient_id)
    _compute_monthly(session, now, patient_id)
    _compute_yearly(session, now, patient_id)
    session.commit()
    log.info("Pattern computation complete")


def _upsert_pattern(session: Session, patient_id: int, period_type: str, period_key: str, stats: dict):
    """Insert or update a pattern record."""
    existing = (
        session.query(GlucosePattern)
        .filter_by(patient_id=patient_id, period_type=period_type, period_key=period_key)
        .first()
    )
    if existing:
        existing.avg_sg = stats["avg_sg"]
        existing.std_sg = stats["std_sg"]
        existing.tir_pct = stats["tir_pct"]
        existing.hypo_count = stats["hypo_count"]
        existing.avg_iob = stats.get("avg_iob")
        existing.avg_carbs = stats.get("avg_carbs")
        existing.sample_count = stats["sample_count"]
        existing.computed_at = utcnow()
    else:
        session.add(GlucosePattern(
            patient_id=patient_id,
            period_type=period_type,
            period_key=period_key,
            **stats,
        ))


def _calc_stats(values: list[float]) -> dict:
    """Calculate basic stats from a list of glucose values."""
    n = len(values)
    if n == 0:
        return {
            "avg_sg": 0, "std_sg": 0, "tir_pct": 0,
            "hypo_count": 0, "sample_count": 0,
        }

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance ** 0.5
    tir = 100 * sum(1 for v in values if 70 <= v <= 180) / n
    hypo = sum(1 for v in values if v < LOW)

    return {
        "avg_sg": round(mean, 1),
        "std_sg": round(std, 1),
        "tir_pct": round(tir, 1),
        "hypo_count": hypo,
        "sample_count": n,
    }


def _compute_hourly(session: Session, now: datetime, patient_id: int = None):
    """Compute hourly patterns from the last 14 days."""
    start = now - timedelta(days=14)
    q = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.timestamp >= start,
            GlucoseReading.sg.isnot(None),
            GlucoseReading.sg > 0,
        )
    )
    if patient_id is not None:
        q = q.filter(GlucoseReading.patient_id == patient_id)
    readings = q.all()

    by_hour: dict[str, list[float]] = defaultdict(list)
    for r in readings:
        hour_key = r.timestamp.strftime("%H:00")
        by_hour[hour_key].append(r.sg)

    for hour_key, values in by_hour.items():
        stats = _calc_stats(values)
        _upsert_pattern(session, patient_id, "hourly", hour_key, stats)

    log.debug("Hourly patterns: %d hours computed", len(by_hour))


def _compute_daily(session: Session, now: datetime, patient_id: int = None):
    """Compute weekday patterns from the last 8 weeks."""
    start = now - timedelta(weeks=8)
    q = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.timestamp >= start,
            GlucoseReading.sg.isnot(None),
            GlucoseReading.sg > 0,
        )
    )
    if patient_id is not None:
        q = q.filter(GlucoseReading.patient_id == patient_id)
    readings = q.all()

    by_day: dict[str, list[float]] = defaultdict(list)
    for r in readings:
        day_key = r.timestamp.strftime("%A").lower()
        by_day[day_key].append(r.sg)

    for day_key, values in by_day.items():
        stats = _calc_stats(values)
        _upsert_pattern(session, patient_id, "daily", day_key, stats)

    log.debug("Daily patterns: %d weekdays computed", len(by_day))


def _compute_monthly(session: Session, now: datetime, patient_id: int = None):
    """Compute monthly patterns from all history."""
    q = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.sg.isnot(None),
            GlucoseReading.sg > 0,
        )
    )
    if patient_id is not None:
        q = q.filter(GlucoseReading.patient_id == patient_id)
    readings = q.all()

    by_month: dict[str, list[float]] = defaultdict(list)
    for r in readings:
        month_key = r.timestamp.strftime("%B").lower()
        by_month[month_key].append(r.sg)

    for month_key, values in by_month.items():
        stats = _calc_stats(values)
        _upsert_pattern(session, patient_id, "monthly", month_key, stats)

    log.debug("Monthly patterns: %d months computed", len(by_month))


def _compute_yearly(session: Session, now: datetime, patient_id: int = None):
    """Compute yearly patterns."""
    q = (
        session.query(GlucoseReading)
        .filter(
            GlucoseReading.sg.isnot(None),
            GlucoseReading.sg > 0,
        )
    )
    if patient_id is not None:
        q = q.filter(GlucoseReading.patient_id == patient_id)
    readings = q.all()

    by_year: dict[str, list[float]] = defaultdict(list)
    for r in readings:
        year_key = str(r.timestamp.year)
        by_year[year_key].append(r.sg)

    for year_key, values in by_year.items():
        stats = _calc_stats(values)
        _upsert_pattern(session, patient_id, "yearly", year_key, stats)

    log.debug("Yearly patterns: %d years computed", len(by_year))
