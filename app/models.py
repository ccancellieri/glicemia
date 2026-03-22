"""GliceMia database models — FHIR-based schema for T1D data.

All tables use SQLAlchemy ORM. The database is encrypted with SQLCipher (AES-256).
Geospatial columns (GPS tracks) use SpatiaLite when available.
"""

from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, Float, Text, DateTime, Date, Boolean, String,
    UniqueConstraint, Index, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


# --- Patient Profile ---

class PatientProfile(Base):
    __tablename__ = "patient_profile"

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    date_of_birth = Column(Date)
    weight_kg = Column(Float)
    height_cm = Column(Float)
    sex = Column(String(1))  # M/F
    diabetes_type = Column(Text, default="T1D")
    diagnosis_year = Column(Integer)
    pump_model = Column(Text)
    sensor_model = Column(Text)
    diet = Column(Text)  # vegetarian, vegan, etc.
    language = Column(String(5), default="it")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --- CGM & Pump ---

class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    sg = Column(Float)  # Sensor glucose mg/dL
    bg = Column(Float)  # Blood glucose (fingerstick) mg/dL
    trend = Column(Text)  # UP, DOWN, FLAT, etc.
    source = Column(Text, default="carelink")  # carelink, manual, apple_health

    __table_args__ = (
        UniqueConstraint("timestamp", "source", name="uq_glucose_ts_source"),
    )


class PumpStatus(Base):
    __tablename__ = "pump_status"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    active_insulin = Column(Float)  # IOB in units
    basal_rate = Column(Float)  # U/h
    reservoir_units = Column(Float)
    battery_pct = Column(Integer)
    auto_mode = Column(Text)  # AUTO_BASAL, SAFE_BASAL, MANUAL
    suspend = Column(Boolean, default=False)
    source = Column(Text, default="carelink")


class BolusEvent(Base):
    __tablename__ = "bolus_events"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    volume_units = Column(Float)
    bolus_type = Column(Text)  # normal, extended, combo
    bolus_source = Column(Text)  # CLOSED_LOOP_BG_CORRECTION, BOLUS_WIZARD, etc.
    bwz_carb_input = Column(Float)  # grams entered in wizard
    bwz_bg_input = Column(Float)  # BG entered in wizard
    bwz_correction_est = Column(Float)
    bwz_food_est = Column(Float)
    bwz_active_insulin = Column(Float)
    duration_min = Column(Integer)  # for extended bolus
    source = Column(Text, default="carelink")


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    carbs_g = Column(Float)
    description = Column(Text)
    photo_file_id = Column(Text)  # Telegram file ID
    ai_estimation = Column(Text)  # JSON with AI analysis
    source = Column(Text, default="manual")  # manual, photo, telegram


# --- FHIR-Based Clinical Data ---

class Condition(Base):
    """FHIR Condition resource — medical conditions with SNOMED/ICD codes."""
    __tablename__ = "conditions"

    id = Column(Integer, primary_key=True)
    snomed_code = Column(Text)
    icd_code = Column(Text)
    display_name = Column(Text, nullable=False)
    clinical_status = Column(Text, default="active")  # active, inactive, resolved
    verification_status = Column(Text, default="confirmed")
    severity = Column(Text)  # mild, moderate, severe
    onset_date = Column(Date)
    recorded_date = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    body_site = Column(Text)
    evidence_json = Column(Text)
    notes = Column(Text)


class Observation(Base):
    """FHIR Observation — lab results, vitals, clinical measurements."""
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True)
    loinc_code = Column(Text)
    display_name = Column(Text, nullable=False)
    value = Column(Float)
    unit = Column(Text)
    reference_range_low = Column(Float)
    reference_range_high = Column(Float)
    interpretation = Column(Text)  # normal, high, low, critical
    effective_date = Column(DateTime, nullable=False)
    source = Column(Text, default="manual")
    performer = Column(Text)
    metadata_json = Column(Text)


# --- Insulin Settings (dynamic, learned from data) ---

class InsulinSetting(Base):
    """Time-of-day insulin parameters — updated from CareLink + learned."""
    __tablename__ = "insulin_settings"

    id = Column(Integer, primary_key=True)
    time_start = Column(Text, nullable=False)  # "00:00", "06:00", etc.
    time_end = Column(Text, nullable=False)
    ic_ratio = Column(Float)  # I:C ratio (g/U)
    isf = Column(Float)  # Insulin Sensitivity Factor (mg/dL/U)
    target_sg = Column(Float, default=120.0)
    source = Column(Text, default="carelink")  # carelink, learned, manual
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --- Activities ---

class Activity(Base):
    """Activity tracking with GPS, calories, glucose impact."""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    timestamp_start = Column(DateTime, nullable=False, index=True)
    timestamp_end = Column(DateTime)
    activity_type = Column(Text)  # cycling, walking, running, gym
    intensity = Column(Text)  # low, moderate, vigorous
    duration_min = Column(Integer)
    distance_km = Column(Float)
    elevation_gain_m = Column(Float)
    elevation_loss_m = Column(Float)
    calories_est = Column(Float)
    avg_heart_rate = Column(Integer)
    max_heart_rate = Column(Integer)
    start_sg = Column(Float)
    end_sg = Column(Float)
    sg_delta = Column(Float)
    avg_iob = Column(Float)
    location_name = Column(Text)
    weather_temp_c = Column(Float)
    weather_conditions = Column(Text)
    gps_track_json = Column(Text)  # GeoJSON LineString (SpatiaLite upgrade later)
    source = Column(Text, default="manual")
    notes = Column(Text)


# --- Pre-computed Patterns ---

class GlucosePattern(Base):
    """Pre-computed glucose aggregates for fast context injection."""
    __tablename__ = "glucose_patterns"

    id = Column(Integer, primary_key=True)
    period_type = Column(Text, nullable=False)  # hourly, daily, weekly, monthly, yearly
    period_key = Column(Text, nullable=False)  # "14:00", "monday", "march", "2025-W12"
    avg_sg = Column(Float)
    std_sg = Column(Float)
    tir_pct = Column(Float)
    hypo_count = Column(Integer)
    avg_iob = Column(Float)
    avg_carbs = Column(Float)
    sample_count = Column(Integer)
    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("period_type", "period_key", name="uq_pattern_period"),
    )


# --- Health Records (from connectors) ---

class HealthRecord(Base):
    """Data from Apple Health, FHIR, Health Connect."""
    __tablename__ = "health_records"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    source = Column(Text, nullable=False)
    loinc_code = Column(Text)
    record_type = Column(Text)  # heart_rate, steps, sleep, blood_pressure
    value = Column(Float)
    unit = Column(Text)
    metadata_json = Column(Text)


# --- Trip Plans ---

class TripPlan(Base):
    """Planned activities with route, weather, glucose prediction."""
    __tablename__ = "trip_plans"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    description = Column(Text)
    route_json = Column(Text)  # GeoJSON
    distance_km = Column(Float)
    elevation_profile_json = Column(Text)
    weather_json = Column(Text)
    activity_type = Column(Text)
    estimated_duration_min = Column(Integer)
    estimated_calories = Column(Float)
    glucose_prediction_json = Column(Text)
    suggestions_json = Column(Text)
    status = Column(Text, default="planned")  # planned, active, completed


# --- Liability Waiver ---

class LiabilityWaiver(Base):
    """Tracks user acceptance of the liability waiver."""
    __tablename__ = "liability_waivers"

    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, nullable=False, unique=True)
    accepted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    language = Column(String(5))
    version = Column(Text, default="1.0")


# --- Conversation History ---

class ChatMessage(Base):
    """Stores conversation history for context."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    platform = Column(Text, default="telegram")
    user_id = Column(Text)
    role = Column(Text, nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    metadata_json = Column(Text)  # file IDs, message type, etc.
