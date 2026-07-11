#!/usr/bin/env python3
"""Seed the GliceMia database from CareLink CSV files in private/data/.

Creates the demo user account + patient profile if missing, then imports
CSVs and computes patterns for that patient.

Usage: python scripts/seed_demo.py
"""

import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, get_session
from app.models import PatientProfile, Condition, GlucoseReading, UserAccount
from app.carelink.csv_import import import_carelink_csv
from app.analytics.patterns import compute_all_patterns
from app.config import settings

# Demo patient: first bootstrap admin from .env, or a synthetic ID.
DEMO_PATIENT_ID = (
    settings.TELEGRAM_ALLOWED_USERS[0] if settings.TELEGRAM_ALLOWED_USERS else 1
)
DEMO_PATIENT_NAME = os.getenv("PATIENT_NAME", "Demo")
DEMO_LANGUAGE = os.getenv("LANGUAGE", "it")


def main():
    print("=== GliceMia — Seed Demo Data ===\n")

    # 1. Init DB
    init_db()
    session = get_session()
    pid = DEMO_PATIENT_ID

    # 2. Seed user account (skip if exists)
    if not session.get(UserAccount, pid):
        from app.users import create_user
        create_user(
            session, telegram_user_id=pid,
            patient_name=DEMO_PATIENT_NAME, language=DEMO_LANGUAGE, is_admin=True,
        )
        print(f"User account seeded: {DEMO_PATIENT_NAME} (id={pid})")
    else:
        print(f"User account already exists (id={pid})")

    # 3. Seed patient profile (skip if exists)
    if not session.query(PatientProfile).filter_by(patient_id=pid).first():
        session.add(PatientProfile(
            patient_id=pid,
            name=DEMO_PATIENT_NAME,
            diabetes_type="T1D",
            pump_model="MiniMed 780G (MMT-1886)",
            sensor_model="Guardian 4",
            diet="vegetarian",
            language=DEMO_LANGUAGE,
        ))
        session.add(Condition(
            patient_id=pid,
            snomed_code="46635009", icd_code="E10",
            display_name="Diabete tipo 1",
            clinical_status="active", severity="moderate",
        ))
        session.commit()
        print("Patient profile seeded for", DEMO_PATIENT_NAME)
    else:
        print("Patient profile already exists")

    # 4. Import CSVs
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "private", "data")
    if os.path.isdir(data_dir):
        existing = session.query(GlucoseReading).filter_by(patient_id=pid).count()
        if existing > 0:
            print(f"Database already has {existing} glucose readings — skipping CSV import")
        else:
            csv_files = sorted(f for f in os.listdir(data_dir) if f.endswith(".csv"))
            for f in csv_files:
                path = os.path.join(data_dir, f)
                s = get_session()
                try:
                    r = import_carelink_csv(path, s, patient_id=pid)
                    print(f"  {f}: glucose={r['glucose']}, bolus={r['bolus']}")
                except Exception as e:
                    print(f"  {f}: ERROR {e}")
                finally:
                    s.close()
    else:
        print("No private/data/ directory found — skipping CSV import")

    # 5. Compute patterns
    print("\nComputing glucose patterns...")
    s = get_session()
    compute_all_patterns(s, patient_id=pid)
    from app.models import GlucosePattern
    count = s.query(GlucosePattern).filter_by(patient_id=pid).count()
    print(f"  {count} pattern records computed")
    s.close()

    # 6. Summary
    s = get_session()
    from sqlalchemy import func
    from app.models import BolusEvent
    total_glucose = s.query(GlucoseReading).filter_by(patient_id=pid).count()
    total_bolus = s.query(BolusEvent).filter_by(patient_id=pid).count()
    mn = s.query(func.min(GlucoseReading.timestamp)).filter(
        GlucoseReading.patient_id == pid
    ).scalar()
    mx = s.query(func.max(GlucoseReading.timestamp)).filter(
        GlucoseReading.patient_id == pid
    ).scalar()
    s.close()

    print(f"\n=== Database Summary (patient {pid}) ===")
    print(f"  Glucose readings: {total_glucose}")
    print(f"  Bolus events:     {total_bolus}")
    print(f"  Date range:       {mn} → {mx}")
    print(f"\nDone! Run 'python agent.py' to start the bot.")


if __name__ == "__main__":
    main()
