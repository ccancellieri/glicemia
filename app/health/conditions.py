"""Medical condition management — SNOMED CT / ICD coded conditions.

Tracks active conditions, updates severity from lab results,
and provides condition context for AI interactions.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Condition, Observation

log = logging.getLogger(__name__)

# Common T1D-related conditions with SNOMED CT codes
CONDITION_CATALOG = {
    "t1d": {
        "snomed": "46635009",
        "icd": "E10",
        "display": "Type 1 diabetes mellitus",
    },
    "osteoporosis": {
        "snomed": "64859006",
        "icd": "M81",
        "display": "Osteoporosis",
    },
    "hypothyroidism": {
        "snomed": "40930008",
        "icd": "E03.9",
        "display": "Hypothyroidism",
    },
    "celiac": {
        "snomed": "396331005",
        "icd": "K90.0",
        "display": "Celiac disease",
    },
    "retinopathy": {
        "snomed": "4855003",
        "icd": "H36.0",
        "display": "Diabetic retinopathy",
    },
    "neuropathy": {
        "snomed": "230572002",
        "icd": "G63.2",
        "display": "Diabetic neuropathy",
    },
    "nephropathy": {
        "snomed": "127013003",
        "icd": "N08.3",
        "display": "Diabetic nephropathy",
    },
    "early_menopause": {
        "snomed": "373717006",
        "icd": "E28.3",
        "display": "Premature menopause",
    },
}


def add_condition(
    session: Session,
    condition_key: str = "",
    snomed_code: str = "",
    display_name: str = "",
    severity: str = "moderate",
    onset_date=None,
    notes: str = "",
) -> Optional[Condition]:
    """Add a condition from catalog or custom SNOMED code."""
    catalog = CONDITION_CATALOG.get(condition_key)

    if catalog:
        snomed_code = catalog["snomed"]
        icd_code = catalog["icd"]
        display_name = display_name or catalog["display"]
    else:
        icd_code = ""

    # Check if already exists
    existing = session.query(Condition).filter_by(snomed_code=snomed_code).first()
    if existing:
        existing.clinical_status = "active"
        existing.severity = severity
        existing.last_updated = datetime.utcnow()
        if notes:
            existing.notes = notes
        session.commit()
        return existing

    condition = Condition(
        snomed_code=snomed_code,
        icd_code=icd_code,
        display_name=display_name,
        clinical_status="active",
        severity=severity,
        onset_date=onset_date,
        notes=notes,
    )
    session.add(condition)
    session.commit()
    return condition


def update_conditions_from_labs(session: Session):
    """Auto-update condition severity based on latest lab results.

    e.g., HbA1c changes → update T1D severity
          DEXA T-score → update osteoporosis severity
          TSH → update hypothyroidism status
    """
    # HbA1c → T1D severity
    hba1c = (
        session.query(Observation)
        .filter(Observation.loinc_code == "4548-4")
        .order_by(Observation.effective_date.desc())
        .first()
    )
    if hba1c and hba1c.value:
        t1d = session.query(Condition).filter_by(snomed_code="46635009").first()
        if t1d:
            if hba1c.value > 9:
                t1d.severity = "severe"
            elif hba1c.value > 7.5:
                t1d.severity = "moderate"
            else:
                t1d.severity = "mild"
            t1d.last_updated = datetime.utcnow()

    # DEXA T-score → osteoporosis severity
    dexa = (
        session.query(Observation)
        .filter(Observation.loinc_code == "80948-3")
        .order_by(Observation.effective_date.desc())
        .first()
    )
    if dexa and dexa.value:
        osteo = session.query(Condition).filter_by(snomed_code="64859006").first()
        if osteo:
            if dexa.value < -2.5:
                osteo.severity = "severe"
                osteo.clinical_status = "active"
            elif dexa.value < -1.0:
                osteo.severity = "moderate"
                osteo.clinical_status = "active"
            else:
                osteo.clinical_status = "resolved"
            osteo.last_updated = datetime.utcnow()

    # TSH → hypothyroidism
    tsh = (
        session.query(Observation)
        .filter(Observation.loinc_code == "3016-3")
        .order_by(Observation.effective_date.desc())
        .first()
    )
    if tsh and tsh.value:
        thyroid = session.query(Condition).filter_by(snomed_code="40930008").first()
        if thyroid:
            if tsh.value > 10:
                thyroid.severity = "severe"
                thyroid.clinical_status = "active"
            elif tsh.value > 4.0:
                thyroid.severity = "mild"
                thyroid.clinical_status = "active"
            elif 0.4 <= tsh.value <= 4.0:
                thyroid.clinical_status = "inactive"

    session.commit()
    log.info("Conditions updated from latest lab results")


def get_active_conditions_summary(session: Session) -> str:
    """Get a text summary of active conditions for AI context."""
    conditions = (
        session.query(Condition)
        .filter(Condition.clinical_status.in_(["active", "recurrence"]))
        .all()
    )
    if not conditions:
        return ""

    parts = []
    for c in conditions:
        entry = c.display_name
        if c.severity:
            entry += f" ({c.severity})"
        if c.snomed_code:
            entry += f" [SNOMED:{c.snomed_code}]"
        parts.append(entry)

    return "; ".join(parts)
