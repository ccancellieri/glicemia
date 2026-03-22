"""FHIR client — connect to FHIR/SMART on FHIR servers for health data exchange."""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Condition, Observation, HealthRecord

log = logging.getLogger(__name__)


class FHIRClient:
    """Minimal FHIR client for reading/writing patient data."""

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    async def fetch_conditions(self, session: Session) -> dict:
        """Fetch Condition resources and store in DB."""
        stats = {"imported": 0, "skipped": 0}

        try:
            import httpx

            headers = {"Accept": "application/fhir+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/Condition",
                    headers=headers,
                )
                resp.raise_for_status()
                bundle = resp.json()

            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                if resource.get("resourceType") != "Condition":
                    continue

                code = resource.get("code", {})
                codings = code.get("coding", [])

                snomed = None
                icd = None
                display = code.get("text", "Unknown")

                for coding in codings:
                    system = coding.get("system", "")
                    if "snomed" in system.lower():
                        snomed = coding.get("code")
                        display = coding.get("display", display)
                    elif "icd" in system.lower():
                        icd = coding.get("code")

                clinical_status = (
                    resource.get("clinicalStatus", {})
                    .get("coding", [{}])[0]
                    .get("code", "active")
                )

                existing = session.query(Condition).filter_by(
                    snomed_code=snomed, display_name=display
                ).first()

                if existing:
                    existing.clinical_status = clinical_status
                    stats["skipped"] += 1
                else:
                    session.add(Condition(
                        snomed_code=snomed,
                        icd_code=icd,
                        display_name=display,
                        clinical_status=clinical_status,
                    ))
                    stats["imported"] += 1

            session.commit()
        except ImportError:
            stats["error"] = "httpx not installed"
        except Exception as e:
            stats["error"] = str(e)
            log.error("FHIR fetch conditions failed: %s", e)

        return stats

    async def fetch_observations(
        self,
        session: Session,
        category: str = "laboratory",
    ) -> dict:
        """Fetch Observation resources (lab results, vitals)."""
        stats = {"imported": 0, "skipped": 0}

        try:
            import httpx

            headers = {"Accept": "application/fhir+json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/Observation",
                    params={"category": category, "_count": "100"},
                    headers=headers,
                )
                resp.raise_for_status()
                bundle = resp.json()

            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                if resource.get("resourceType") != "Observation":
                    continue

                code = resource.get("code", {})
                codings = code.get("coding", [])
                loinc = None
                display = code.get("text", "Unknown")

                for coding in codings:
                    if "loinc" in coding.get("system", "").lower():
                        loinc = coding.get("code")
                        display = coding.get("display", display)

                value_quantity = resource.get("valueQuantity", {})
                value = value_quantity.get("value")
                unit = value_quantity.get("unit", "")

                effective = resource.get("effectiveDateTime")
                effective_dt = _parse_fhir_date(effective) if effective else datetime.utcnow()

                ref_range = resource.get("referenceRange", [{}])[0]
                ref_low = ref_range.get("low", {}).get("value")
                ref_high = ref_range.get("high", {}).get("value")

                interpretation_coding = (
                    resource.get("interpretation", [{}])[0]
                    .get("coding", [{}])[0]
                )
                interpretation = interpretation_coding.get("code", "")

                existing = session.query(Observation).filter_by(
                    loinc_code=loinc, effective_date=effective_dt, source="fhir"
                ).first()

                if existing:
                    stats["skipped"] += 1
                else:
                    session.add(Observation(
                        loinc_code=loinc,
                        display_name=display,
                        value=value,
                        unit=unit,
                        reference_range_low=ref_low,
                        reference_range_high=ref_high,
                        interpretation=interpretation,
                        effective_date=effective_dt,
                        source="fhir",
                    ))
                    stats["imported"] += 1

            session.commit()
        except ImportError:
            stats["error"] = "httpx not installed"
        except Exception as e:
            stats["error"] = str(e)
            log.error("FHIR fetch observations failed: %s", e)

        return stats

    def export_observations_bundle(self, session: Session) -> dict:
        """Export local observations as a FHIR Bundle for sharing."""
        observations = session.query(Observation).all()

        entries = []
        for obs in observations:
            resource = {
                "resourceType": "Observation",
                "status": "final",
                "code": {
                    "coding": [],
                    "text": obs.display_name,
                },
                "effectiveDateTime": obs.effective_date.isoformat() if obs.effective_date else None,
            }
            if obs.loinc_code:
                resource["code"]["coding"].append({
                    "system": "http://loinc.org",
                    "code": obs.loinc_code,
                    "display": obs.display_name,
                })
            if obs.value is not None:
                resource["valueQuantity"] = {
                    "value": obs.value,
                    "unit": obs.unit or "",
                }
            entries.append({"resource": resource})

        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": entries,
        }


def _parse_fhir_date(date_str: str) -> Optional[datetime]:
    """Parse FHIR datetime strings."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.split("+")[0].split("Z")[0], fmt.replace("%z", ""))
            return dt
        except ValueError:
            continue
    return None
