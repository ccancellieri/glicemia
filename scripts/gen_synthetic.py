#!/usr/bin/env python3
"""Generate synthetic CGM/bolus/meal data for CI (no real patient data).

Adds ~14 days of 5-minute glucose readings (sinusoid + noise around
120 mg/dL) plus a handful of meal/bolus rows for the demo patient, so
scripts/test_demo.py has data to exercise metrics/patterns/estimator/alerts.

Requires scripts/seed_demo.py to have already created the user account and
patient profile — this script only adds readings/meals/boluses.

Usage: python scripts/gen_synthetic.py
"""

import math
import os
import random
import sys
from datetime import datetime, timedelta

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, get_session
from app.models import GlucoseReading, BolusEvent, Meal, GlucosePattern
from app.analytics.patterns import compute_all_patterns
from app.config import settings
from app.timeutils import utcnow

PATIENT_ID = (
    settings.TELEGRAM_ALLOWED_USERS[0] if settings.TELEGRAM_ALLOWED_USERS else 1
)

DAYS = 14
INTERVAL_MIN = 5
BASE_SG = 120.0       # mg/dL
AMPLITUDE_SG = 40.0   # mg/dL -- plain diurnal sinusoid
NOISE_STDEV = 12.0    # mg/dL
MIN_SG = 45.0
MAX_SG = 320.0
MEAL_STEP_DAYS = 2    # a meal+bolus every ~2 days -> a handful over 14 days

SYNTHETIC_SOURCE = "synthetic"


def _generate_glucose_readings(end: datetime, rng: random.Random) -> list[tuple[datetime, float]]:
    """Plain sinusoid + Gaussian noise around BASE_SG -- clearly synthetic data."""
    total_points = DAYS * 24 * 60 // INTERVAL_MIN
    readings = []
    for i in range(total_points):
        ts = end - timedelta(minutes=INTERVAL_MIN * (total_points - 1 - i))
        hour_of_day = ts.hour + ts.minute / 60
        sg = BASE_SG + AMPLITUDE_SG * math.sin(2 * math.pi * hour_of_day / 24)
        sg += rng.gauss(0, NOISE_STDEV)
        sg = max(MIN_SG, min(MAX_SG, sg))
        readings.append((ts, round(sg, 1)))
    return readings


def _generate_meals_and_boluses(
    end: datetime, rng: random.Random
) -> tuple[list[tuple[datetime, float]], list[tuple[datetime, float, float]]]:
    """A handful of synthetic lunch meals + matching wizard boluses."""
    meals = []
    boluses = []
    for d in range(0, DAYS, MEAL_STEP_DAYS):
        day = (end - timedelta(days=DAYS - 1 - d)).replace(
            hour=13, minute=0, second=0, microsecond=0
        )
        carbs_g = round(rng.uniform(40, 70))
        meals.append((day, carbs_g))
        bolus_u = round(carbs_g / 10.0, 1)  # matches estimator's default I:C fallback
        boluses.append((day + timedelta(minutes=2), bolus_u, carbs_g))
    return meals, boluses


def main():
    print("=== GliceMia -- Generate Synthetic Data (CI) ===\n")

    init_db()
    session = get_session()
    pid = PATIENT_ID

    existing = (
        session.query(GlucoseReading)
        .filter_by(patient_id=pid, source=SYNTHETIC_SOURCE)
        .count()
    )
    if existing > 0:
        print(f"Synthetic glucose data already present ({existing} readings) -- skipping generation")
    else:
        rng = random.Random(42)  # deterministic, reproducible synthetic data
        now = utcnow()

        readings = _generate_glucose_readings(now, rng)
        for ts, sg in readings:
            session.add(GlucoseReading(
                patient_id=pid, timestamp=ts, sg=sg, source=SYNTHETIC_SOURCE,
            ))

        meals, boluses = _generate_meals_and_boluses(now, rng)
        for ts, carbs_g in meals:
            session.add(Meal(
                patient_id=pid, timestamp=ts, carbs_g=carbs_g,
                description="Synthetic meal", source=SYNTHETIC_SOURCE,
            ))
        for ts, bolus_u, carbs_g in boluses:
            session.add(BolusEvent(
                patient_id=pid, timestamp=ts, volume_units=bolus_u,
                bolus_type="normal", bolus_source="BOLUS_WIZARD",
                bwz_carb_input=carbs_g, source=SYNTHETIC_SOURCE,
            ))

        session.commit()
        print(f"Generated {len(readings)} glucose readings, {len(meals)} meals, {len(boluses)} bolus events")

    print("\nComputing glucose patterns...")
    compute_all_patterns(session, patient_id=pid)
    count = session.query(GlucosePattern).filter_by(patient_id=pid).count()
    print(f"  {count} pattern records computed")

    session.close()
    print("\nDone. Run 'python scripts/test_demo.py' to verify.")


if __name__ == "__main__":
    main()
