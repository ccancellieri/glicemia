"""Apple Health import — parse exported ZIP files from iPhone.

Extracts heart rate, steps, sleep, workouts, and other health records
from Apple Health's XML export format.
"""

import logging
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import HealthRecord, Activity

log = logging.getLogger(__name__)

# Apple Health type → our record_type + LOINC code mapping
TYPE_MAP = {
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate", "8867-4", "bpm"),
    "HKQuantityTypeIdentifierStepCount": ("steps", "55423-8", "steps"),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("distance", "55430-3", "km"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_energy", "55424-6", "kcal"),
    "HKQuantityTypeIdentifierBasalEnergyBurned": ("basal_energy", "55425-3", "kcal"),
    "HKQuantityTypeIdentifierBodyMass": ("weight", "29463-7", "kg"),
    "HKQuantityTypeIdentifierBloodPressureSystolic": ("bp_systolic", "8480-6", "mmHg"),
    "HKQuantityTypeIdentifierBloodPressureDiastolic": ("bp_diastolic", "8462-4", "mmHg"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("spo2", "59408-5", "%"),
    "HKQuantityTypeIdentifierRespiratoryRate": ("respiratory_rate", "9279-1", "breaths/min"),
    "HKQuantityTypeIdentifierBloodGlucose": ("blood_glucose", "15074-8", "mg/dL"),
    "HKCategoryTypeIdentifierSleepAnalysis": ("sleep", None, None),
}

# Workout type mapping
WORKOUT_MAP = {
    "HKWorkoutActivityTypeCycling": "cycling",
    "HKWorkoutActivityTypeRunning": "running",
    "HKWorkoutActivityTypeWalking": "walking",
    "HKWorkoutActivityTypeYoga": "yoga",
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "gym",
    "HKWorkoutActivityTypeFunctionalStrengthTraining": "gym",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "hiit",
    "HKWorkoutActivityTypeSwimming": "swimming",
}


def import_apple_health_zip(zip_bytes: bytes, session: Session) -> dict:
    """Import Apple Health data from an exported ZIP file.

    Args:
        zip_bytes: Raw bytes of the Apple Health export ZIP.
        session: SQLAlchemy session.

    Returns:
        Summary dict with counts per record type.
    """
    stats = {"records": 0, "workouts": 0, "skipped": 0, "errors": 0}

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, "export.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Find the export.xml file
                xml_files = [n for n in zf.namelist() if n.endswith("export.xml")]
                if not xml_files:
                    return {"error": "No export.xml found in ZIP"}

                xml_path = zf.extract(xml_files[0], tmp_dir)
        except zipfile.BadZipFile:
            return {"error": "Invalid ZIP file"}

        # Parse XML incrementally (can be very large)
        try:
            context = ET.iterparse(xml_path, events=("end",))
            for event, elem in context:
                try:
                    if elem.tag == "Record":
                        _process_record(elem, session, stats)
                    elif elem.tag == "Workout":
                        _process_workout(elem, session, stats)
                except Exception as e:
                    stats["errors"] += 1
                    log.debug("Error processing element: %s", e)
                finally:
                    elem.clear()  # Free memory
        except ET.ParseError as e:
            log.error("XML parse error: %s", e)
            stats["error"] = f"XML parse error: {e}"

    session.commit()
    log.info(
        "Apple Health import: %d records, %d workouts, %d skipped, %d errors",
        stats["records"], stats["workouts"], stats["skipped"], stats["errors"],
    )
    return stats


def _process_record(elem, session: Session, stats: dict):
    """Process a single Apple Health Record element."""
    record_type = elem.get("type", "")
    mapping = TYPE_MAP.get(record_type)

    if not mapping:
        stats["skipped"] += 1
        return

    our_type, loinc, unit = mapping
    value_str = elem.get("value", "")
    start_date = _parse_apple_date(elem.get("startDate"))

    if not start_date:
        stats["skipped"] += 1
        return

    # Parse value
    value = None
    if value_str:
        try:
            value = float(value_str)
        except ValueError:
            # Sleep analysis has categorical values
            if our_type == "sleep":
                value = 1.0 if "Asleep" in value_str else 0.0
            else:
                stats["skipped"] += 1
                return

    # Unit conversion
    if unit == "mg/dL" and elem.get("unit") == "mmol<180g>/dL":
        pass  # Already in mg/dL
    elif unit == "km" and elem.get("unit") == "m":
        value = value / 1000 if value else None

    # Deduplicate
    existing = (
        session.query(HealthRecord)
        .filter_by(timestamp=start_date, record_type=our_type, source="apple_health")
        .first()
    )
    if existing:
        stats["skipped"] += 1
        return

    session.add(HealthRecord(
        timestamp=start_date,
        source="apple_health",
        loinc_code=loinc,
        record_type=our_type,
        value=value,
        unit=unit,
    ))
    stats["records"] += 1


def _process_workout(elem, session: Session, stats: dict):
    """Process a single Apple Health Workout element."""
    workout_type = elem.get("workoutActivityType", "")
    activity_type = WORKOUT_MAP.get(workout_type, "other")

    start_date = _parse_apple_date(elem.get("startDate"))
    end_date = _parse_apple_date(elem.get("endDate"))
    duration_str = elem.get("duration", "0")

    if not start_date:
        stats["skipped"] += 1
        return

    try:
        duration_min = round(float(duration_str))
    except ValueError:
        duration_min = 0

    # Check for distance and energy in child elements
    distance_km = None
    calories = None
    for stat in elem.iter("WorkoutStatistics"):
        stat_type = stat.get("type", "")
        if "DistanceWalkingRunning" in stat_type or "DistanceCycling" in stat_type:
            try:
                distance_km = float(stat.get("sum", 0))
                if stat.get("unit") == "m":
                    distance_km /= 1000
            except ValueError:
                pass
        elif "ActiveEnergyBurned" in stat_type:
            try:
                calories = float(stat.get("sum", 0))
            except ValueError:
                pass

    # Deduplicate
    existing = (
        session.query(Activity)
        .filter_by(timestamp_start=start_date, source="apple_health")
        .first()
    )
    if existing:
        stats["skipped"] += 1
        return

    session.add(Activity(
        timestamp_start=start_date,
        timestamp_end=end_date,
        activity_type=activity_type,
        duration_min=duration_min,
        distance_km=distance_km,
        calories_est=calories,
        source="apple_health",
    ))
    stats["workouts"] += 1


def _parse_apple_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse Apple Health date format."""
    if not date_str:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=None)  # Store as naive UTC
        except ValueError:
            continue
    return None
