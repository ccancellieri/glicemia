#!/usr/bin/env python3
"""Seed the GliceMia database from CareLink CSV files in private/data/.

Usage: python scripts/seed_demo.py
"""

import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, get_session
from app.models import PatientProfile, Condition, GlucoseReading
from app.carelink.csv_import import import_carelink_csv
from app.analytics.patterns import compute_all_patterns
from app.config import settings


def main():
    print("=== GliceMia — Seed Demo Data ===\n")

    # 1. Init DB
    init_db()
    session = get_session()

    # 2. Seed patient profile (skip if exists)
    if not session.query(PatientProfile).first():
        session.add(PatientProfile(
            name=settings.PATIENT_NAME,
            diabetes_type="T1D",
            pump_model="MiniMed 780G (MMT-1886)",
            sensor_model="Guardian 4",
            diet="vegetarian",
            language=settings.LANGUAGE,
        ))
        session.add(Condition(
            snomed_code="46635009", icd_code="E10",
            display_name="Diabete tipo 1",
            clinical_status="active", severity="moderate",
        ))
        session.commit()
        print("Patient profile seeded for", settings.PATIENT_NAME)
    else:
        print("Patient profile already exists")

    # 3. Import CSVs
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "private", "data")
    if os.path.isdir(data_dir):
        existing = session.query(GlucoseReading).count()
        if existing > 0:
            print(f"Database already has {existing} glucose readings — skipping CSV import")
        else:
            csv_files = sorted(f for f in os.listdir(data_dir) if f.endswith(".csv"))
            for f in csv_files:
                path = os.path.join(data_dir, f)
                s = get_session()
                try:
                    r = import_carelink_csv(path, s)
                    print(f"  {f}: glucose={r['glucose']}, bolus={r['bolus']}")
                except Exception as e:
                    print(f"  {f}: ERROR {e}")
                finally:
                    s.close()
    else:
        print("No private/data/ directory found — skipping CSV import")

    # 4. Compute patterns
    print("\nComputing glucose patterns...")
    s = get_session()
    compute_all_patterns(s)
    from app.models import GlucosePattern
    count = s.query(GlucosePattern).count()
    print(f"  {count} pattern records computed")
    s.close()

    # 5. Summary
    s = get_session()
    from sqlalchemy import func
    total_glucose = s.query(GlucoseReading).count()
    from app.models import BolusEvent
    total_bolus = s.query(BolusEvent).count()
    mn = s.query(func.min(GlucoseReading.timestamp)).scalar()
    mx = s.query(func.max(GlucoseReading.timestamp)).scalar()
    s.close()

    print(f"\n=== Database Summary ===")
    print(f"  Glucose readings: {total_glucose}")
    print(f"  Bolus events:     {total_bolus}")
    print(f"  Date range:       {mn} → {mx}")
    print(f"\nDone! Run 'python agent.py' to start the bot.")


if __name__ == "__main__":
    main()
