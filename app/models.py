"""GliceMia database models — FHIR-based schema for T1D data.

All tables use SQLAlchemy ORM. The database is encrypted with SQLCipher (AES-256).
Geospatial columns (GPS tracks) use SpatiaLite when available.
"""

from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, Float, Text, DateTime, Date, Boolean, String,
    ForeignKey, UniqueConstraint, Index, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from app.crypto import EncryptedText


class Base(DeclarativeBase):
    pass


# --- User Account (multi-patient) ---

class UserAccount(Base):
    """Bot user — one row per Telegram user. Holds credentials, API keys,
    preferences, and token-usage counters. Added at runtime via /setup."""
    __tablename__ = "user_accounts"

    telegram_user_id = Column(Integer, primary_key=True)  # Telegram numeric ID
    patient_name = Column(Text, nullable=False)
    language = Column(String(5), default="it")
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    # CareLink credentials (per-patient, field-level encrypted)
    carelink_username = Column(EncryptedText)
    carelink_password = Column(EncryptedText)
    carelink_country = Column(String(5))
    carelink_poll_interval = Column(Integer, default=300)  # seconds

    # Per-user API keys (field-level encrypted, fallback to server-wide keys)
    gemini_api_key = Column(EncryptedText)
    openweather_api_key = Column(EncryptedText)

    # AI model preference (optional override — fallback to server default)
    ai_model = Column(Text)  # preferred model, e.g. "ollama/qwen2.5:14b-instruct-q4_K_M"
    # JSON list of models this user is allowed to use, e.g.:
    # [{"model": "ollama/qwen2.5:14b", "api_key": null},
    #  {"model": "gemini/gemini-2.5-flash", "api_key": "AIza..."}]
    # API keys inside this JSON are also encrypted via EncryptedText
    # null/empty = use all server-available models with server keys
    allowed_models_json = Column(EncryptedText)

    # Per-user settings JSON for extensible preferences
    # e.g. {"timezone": "Europe/Rome", "units": "mg/dL", "voice_reply": true}
    settings_json = Column(Text)

    # Token usage tracking
    tokens_used_today = Column(Integer, default=0)
    tokens_used_month = Column(Integer, default=0)
    daily_token_limit = Column(Integer, default=0)   # 0 = unlimited
    monthly_token_limit = Column(Integer, default=0)  # 0 = unlimited
    token_reset_date = Column(Date)       # last daily reset
    token_reset_month = Column(Date)      # last monthly reset

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    profile = relationship("PatientProfile", back_populates="user", uselist=False)
    glucose_readings = relationship("GlucoseReading", back_populates="user")
    pump_statuses = relationship("PumpStatus", back_populates="user")
    bolus_events = relationship("BolusEvent", back_populates="user")
    meals = relationship("Meal", back_populates="user")
    conditions = relationship("Condition", back_populates="user")
    observations = relationship("Observation", back_populates="user")
    insulin_settings = relationship("InsulinSetting", back_populates="user")
    activities = relationship("Activity", back_populates="user")
    glucose_patterns = relationship("GlucosePattern", back_populates="user")
    health_records = relationship("HealthRecord", back_populates="user")
    trip_plans = relationship("TripPlan", back_populates="user")
    chat_messages = relationship("ChatMessage", back_populates="user")


# --- Patient Profile ---

class PatientProfile(Base):
    __tablename__ = "patient_profile"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, unique=True)
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

    user = relationship("UserAccount", back_populates="profile")


# --- CGM & Pump ---

class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    sg = Column(Float)  # Sensor glucose mg/dL
    bg = Column(Float)  # Blood glucose (fingerstick) mg/dL
    trend = Column(Text)  # UP, DOWN, FLAT, etc.
    source = Column(Text, default="carelink")  # carelink, manual, apple_health

    user = relationship("UserAccount", back_populates="glucose_readings")

    __table_args__ = (
        UniqueConstraint("patient_id", "timestamp", "source", name="uq_glucose_ts_source"),
    )


class PumpStatus(Base):
    __tablename__ = "pump_status"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    active_insulin = Column(Float)  # IOB in units
    basal_rate = Column(Float)  # U/h
    reservoir_units = Column(Float)
    battery_pct = Column(Integer)
    auto_mode = Column(Text)  # AUTO_BASAL, SAFE_BASAL, MANUAL
    suspend = Column(Boolean, default=False)
    source = Column(Text, default="carelink")

    user = relationship("UserAccount", back_populates="pump_statuses")


class BolusEvent(Base):
    __tablename__ = "bolus_events"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
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

    user = relationship("UserAccount", back_populates="bolus_events")


class Meal(Base):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    carbs_g = Column(Float)
    description = Column(Text)
    photo_file_id = Column(Text)  # Telegram file ID
    ai_estimation = Column(Text)  # JSON with AI analysis
    source = Column(Text, default="manual")  # manual, photo, telegram

    user = relationship("UserAccount", back_populates="meals")


# --- FHIR-Based Clinical Data ---

class Condition(Base):
    """FHIR Condition resource — medical conditions with SNOMED/ICD codes."""
    __tablename__ = "conditions"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
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

    user = relationship("UserAccount", back_populates="conditions")


class Observation(Base):
    """FHIR Observation — lab results, vitals, clinical measurements."""
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
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

    user = relationship("UserAccount", back_populates="observations")


# --- Insulin Settings (dynamic, learned from data) ---

class InsulinSetting(Base):
    """Time-of-day insulin parameters — updated from CareLink + learned."""
    __tablename__ = "insulin_settings"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
    time_start = Column(Text, nullable=False)  # "00:00", "06:00", etc.
    time_end = Column(Text, nullable=False)
    ic_ratio = Column(Float)  # I:C ratio (g/U)
    isf = Column(Float)  # Insulin Sensitivity Factor (mg/dL/U)
    target_sg = Column(Float, default=120.0)
    source = Column(Text, default="carelink")  # carelink, learned, manual
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("UserAccount", back_populates="insulin_settings")


# --- Activities ---

class Activity(Base):
    """Activity tracking with GPS, calories, glucose impact."""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
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

    user = relationship("UserAccount", back_populates="activities")


# --- Pre-computed Patterns ---

class GlucosePattern(Base):
    """Pre-computed glucose aggregates for fast context injection."""
    __tablename__ = "glucose_patterns"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
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

    user = relationship("UserAccount", back_populates="glucose_patterns")

    __table_args__ = (
        UniqueConstraint("patient_id", "period_type", "period_key", name="uq_pattern_period"),
    )


# --- Health Records (from connectors) ---

class HealthRecord(Base):
    """Data from Apple Health, FHIR, Health Connect."""
    __tablename__ = "health_records"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    source = Column(Text, nullable=False)
    loinc_code = Column(Text)
    record_type = Column(Text)  # heart_rate, steps, sleep, blood_pressure
    value = Column(Float)
    unit = Column(Text)
    metadata_json = Column(Text)

    user = relationship("UserAccount", back_populates="health_records")


# --- Trip Plans ---

class TripPlan(Base):
    """Planned activities with route, weather, glucose prediction."""
    __tablename__ = "trip_plans"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
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

    user = relationship("UserAccount", back_populates="trip_plans")


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
    """Stores conversation history for context. Per-user — conversations are private."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("user_accounts.telegram_user_id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    platform = Column(Text, default="telegram")
    role = Column(Text, nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    metadata_json = Column(Text)  # file IDs, message type, etc.

    user = relationship("UserAccount", back_populates="chat_messages")
