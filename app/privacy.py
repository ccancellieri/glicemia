"""GDPR privacy module — consent management, data export, erasure, and retention.

Implements Articles 7, 9, 15-17, 20, 30 of the GDPR for health data processing.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    GDPRConsent, UserAccount, PatientProfile, GlucoseReading,
    PumpStatus, BolusEvent, Meal, Condition, Observation,
    InsulinSetting, Activity, GlucosePattern, HealthRecord,
    TripPlan, ChatMessage, LiabilityWaiver,
)

log = logging.getLogger(__name__)

# GDPR consent purposes
CONSENT_PURPOSES = {
    "health_data": "Processing of health data (glucose, insulin, medical conditions) for diabetes management",
    "ai_processing": "AI analysis of your health data using local models on our server",
    "ai_external": "Sending health data to external AI services (Gemini, Claude) when local AI is unavailable",
}

# Data retention periods (days)
RETENTION_PERIODS = {
    "chat_messages": 365,        # 1 year
    "glucose_patterns": 365 * 3, # 3 years (aggregated, less sensitive)
    "trip_plans": 365,           # 1 year for completed trips
}


def has_consent(session: Session, telegram_user_id: int, purpose: str) -> bool:
    """Check if user has active consent for a purpose."""
    latest = (
        session.query(GDPRConsent)
        .filter_by(telegram_user_id=telegram_user_id, purpose=purpose)
        .order_by(GDPRConsent.timestamp.desc())
        .first()
    )
    return latest.granted if latest else False


def has_all_required_consents(session: Session, telegram_user_id: int) -> bool:
    """Check if user has granted all required consents."""
    return all(
        has_consent(session, telegram_user_id, purpose)
        for purpose in CONSENT_PURPOSES
    )


def record_consent(
    session: Session,
    telegram_user_id: int,
    purpose: str,
    granted: bool,
    language: str = "en",
    policy_version: str = "1.0",
) -> None:
    """Record a consent decision (grant or withdraw)."""
    consent = GDPRConsent(
        telegram_user_id=telegram_user_id,
        purpose=purpose,
        granted=granted,
        timestamp=datetime.utcnow(),
        privacy_policy_version=policy_version,
        language=language,
    )
    session.add(consent)
    session.commit()
    log.info(
        "GDPR consent %s for user %d, purpose=%s",
        "granted" if granted else "withdrawn",
        telegram_user_id,
        purpose,
    )


def get_consent_status(session: Session, telegram_user_id: int) -> dict[str, bool]:
    """Get current consent status for all purposes."""
    return {
        purpose: has_consent(session, telegram_user_id, purpose)
        for purpose in CONSENT_PURPOSES
    }


def export_user_data(session: Session, telegram_user_id: int) -> dict:
    """Export all personal data for a user (Art. 15 access + Art. 20 portability).

    Returns a JSON-serializable dict with all user data.
    """
    user = session.get(UserAccount, telegram_user_id)
    if not user:
        return {"error": "User not found"}

    def _serialize_rows(rows, exclude=None):
        exclude = exclude or set()
        result = []
        for row in rows:
            d = {}
            for col in row.__table__.columns:
                if col.name in exclude:
                    continue
                val = getattr(row, col.name)
                if isinstance(val, datetime):
                    val = val.isoformat()
                elif isinstance(val, (int, float, str, bool, type(None))):
                    pass
                else:
                    val = str(val)
                d[col.name] = val
            result.append(d)
        return result

    # Exclude encrypted credential fields from export
    credential_fields = {
        "carelink_password", "gemini_api_key", "openweather_api_key",
        "allowed_models_json",
    }

    profile = session.query(PatientProfile).filter_by(patient_id=telegram_user_id).first()

    data = {
        "export_date": datetime.utcnow().isoformat(),
        "format_version": "1.0",
        "account": {
            "telegram_user_id": user.telegram_user_id,
            "patient_name": user.patient_name,
            "language": user.language,
            "ai_model": user.ai_model,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "profile": _serialize_rows([profile]) if profile else None,
        "glucose_readings": _serialize_rows(
            session.query(GlucoseReading).filter_by(patient_id=telegram_user_id).all()
        ),
        "pump_statuses": _serialize_rows(
            session.query(PumpStatus).filter_by(patient_id=telegram_user_id).all()
        ),
        "bolus_events": _serialize_rows(
            session.query(BolusEvent).filter_by(patient_id=telegram_user_id).all()
        ),
        "meals": _serialize_rows(
            session.query(Meal).filter_by(patient_id=telegram_user_id).all()
        ),
        "conditions": _serialize_rows(
            session.query(Condition).filter_by(patient_id=telegram_user_id).all()
        ),
        "observations": _serialize_rows(
            session.query(Observation).filter_by(patient_id=telegram_user_id).all()
        ),
        "insulin_settings": _serialize_rows(
            session.query(InsulinSetting).filter_by(patient_id=telegram_user_id).all()
        ),
        "activities": _serialize_rows(
            session.query(Activity).filter_by(patient_id=telegram_user_id).all()
        ),
        "health_records": _serialize_rows(
            session.query(HealthRecord).filter_by(patient_id=telegram_user_id).all()
        ),
        "chat_messages": _serialize_rows(
            session.query(ChatMessage).filter_by(patient_id=telegram_user_id).all()
        ),
        "consents": _serialize_rows(
            session.query(GDPRConsent).filter_by(telegram_user_id=telegram_user_id).all()
        ),
    }

    return data


def delete_user_data(session: Session, telegram_user_id: int) -> dict:
    """Delete all personal data for a user (Art. 17 right to erasure).

    Keeps only the consent audit trail (legal obligation to prove consent history).
    Returns a summary of what was deleted.
    """
    deleted = {}

    tables = [
        ("glucose_readings", GlucoseReading, "patient_id"),
        ("pump_statuses", PumpStatus, "patient_id"),
        ("bolus_events", BolusEvent, "patient_id"),
        ("meals", Meal, "patient_id"),
        ("conditions", Condition, "patient_id"),
        ("observations", Observation, "patient_id"),
        ("insulin_settings", InsulinSetting, "patient_id"),
        ("activities", Activity, "patient_id"),
        ("glucose_patterns", GlucosePattern, "patient_id"),
        ("health_records", HealthRecord, "patient_id"),
        ("trip_plans", TripPlan, "patient_id"),
        ("chat_messages", ChatMessage, "patient_id"),
        ("patient_profile", PatientProfile, "patient_id"),
        ("liability_waivers", LiabilityWaiver, "telegram_user_id"),
    ]

    for name, model, fk_col in tables:
        count = session.query(model).filter(getattr(model, fk_col) == telegram_user_id).delete()
        deleted[name] = count

    # Deactivate user account (keep row for consent audit trail linkage)
    user = session.get(UserAccount, telegram_user_id)
    if user:
        user.is_active = False
        user.patient_name = "[deleted]"
        user.carelink_username = None
        user.carelink_password = None
        user.gemini_api_key = None
        user.openweather_api_key = None
        user.allowed_models_json = None
        user.settings_json = None
        user.ai_model = None
        deleted["account"] = "anonymized"

    session.commit()
    log.info("GDPR erasure completed for user %d: %s", telegram_user_id, deleted)
    return deleted


def apply_retention_policies(session: Session) -> dict:
    """Apply data retention policies — delete expired data.

    Run periodically (e.g., daily via scheduler).
    """
    now = datetime.utcnow()
    cleaned = {}

    # Chat messages older than retention period
    cutoff = now - timedelta(days=RETENTION_PERIODS["chat_messages"])
    count = session.query(ChatMessage).filter(ChatMessage.timestamp < cutoff).delete()
    if count:
        cleaned["chat_messages"] = count

    # Completed trip plans older than retention period
    cutoff = now - timedelta(days=RETENTION_PERIODS["trip_plans"])
    count = (
        session.query(TripPlan)
        .filter(TripPlan.created_at < cutoff, TripPlan.status == "completed")
        .delete()
    )
    if count:
        cleaned["trip_plans"] = count

    if cleaned:
        session.commit()
        log.info("Retention cleanup: %s", cleaned)

    return cleaned


# --- Privacy notice text ---

PRIVACY_NOTICE = {
    "en": (
        "PRIVACY NOTICE — GliceMia\n"
        "\n"
        "Data controller: Self-hosted personal instance.\n"
        "\n"
        "What we collect and why:\n"
        "- Health data (glucose, insulin, meals, conditions): To provide diabetes management insights. Legal basis: explicit consent (Art. 9(2)(a)).\n"
        "- Telegram user ID & name: To identify you in the bot. Legal basis: contract performance.\n"
        "- Chat history: To provide contextual AI responses. Retained for 1 year.\n"
        "- CareLink credentials: To sync pump/sensor data. Encrypted with Fernet + SQLCipher.\n"
        "\n"
        "AI processing:\n"
        "- Primary: Local Ollama model (data stays on server).\n"
        "- Fallback: External AI (Gemini/Claude) — only with your explicit consent.\n"
        "\n"
        "Your rights (GDPR Art. 15-21):\n"
        "- /privacy export — Download all your data (JSON)\n"
        "- /privacy delete — Erase all your data\n"
        "- /privacy consent — Review/change consent\n"
        "- /privacy info — This notice\n"
        "\n"
        "Data retention: Health data kept while account is active. Chat history: 1 year. "
        "You can delete everything at any time.\n"
        "\n"
        "Security: AES-256 database encryption (SQLCipher), field-level Fernet encryption "
        "for credentials, HTTPS in transit, key-only SSH.\n"
        "\n"
        "Contact: Use /privacy in the bot for all data requests."
    ),
    "it": (
        "INFORMATIVA PRIVACY — GliceMia\n"
        "\n"
        "Titolare del trattamento: Istanza personale self-hosted.\n"
        "\n"
        "Dati raccolti e finalita:\n"
        "- Dati sanitari (glicemia, insulina, pasti, condizioni): Per fornire analisi sulla gestione del diabete. Base giuridica: consenso esplicito (Art. 9(2)(a)).\n"
        "- ID e nome Telegram: Per identificarti nel bot. Base giuridica: esecuzione contratto.\n"
        "- Cronologia chat: Per risposte AI contestuali. Conservata per 1 anno.\n"
        "- Credenziali CareLink: Per sincronizzare dati pompa/sensore. Crittografate con Fernet + SQLCipher.\n"
        "\n"
        "Elaborazione AI:\n"
        "- Primaria: Modello Ollama locale (i dati restano sul server).\n"
        "- Fallback: AI esterna (Gemini/Claude) — solo con il tuo consenso esplicito.\n"
        "\n"
        "I tuoi diritti (GDPR Art. 15-21):\n"
        "- /privacy export — Scarica tutti i tuoi dati (JSON)\n"
        "- /privacy delete — Cancella tutti i tuoi dati\n"
        "- /privacy consent — Rivedi/modifica consensi\n"
        "- /privacy info — Questa informativa\n"
        "\n"
        "Conservazione: Dati sanitari conservati finche l'account e attivo. Chat: 1 anno. "
        "Puoi cancellare tutto in qualsiasi momento.\n"
        "\n"
        "Sicurezza: Crittografia AES-256 del database (SQLCipher), crittografia Fernet "
        "per credenziali, HTTPS, SSH solo con chiave.\n"
        "\n"
        "Contatto: Usa /privacy nel bot per tutte le richieste sui dati."
    ),
}
