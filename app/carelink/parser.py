"""Parse CareLink Cloud JSON into database records."""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import GlucoseReading, PumpStatus, BolusEvent, InsulinSetting

log = logging.getLogger(__name__)

# CareLink trend mappings
TREND_MAP = {
    "UP": "UP",
    "UP_DOUBLE": "UP_FAST",
    "UP_TRIPLE": "UP_RAPID",
    "DOWN": "DOWN",
    "DOWN_DOUBLE": "DOWN_FAST",
    "DOWN_TRIPLE": "DOWN_RAPID",
    "NONE": "FLAT",
}


def parse_realtime(data: dict, session: Session) -> Optional[dict]:
    """Parse CareLink realtime JSON and store in DB. Returns summary dict."""
    if not data:
        return None

    summary = {}

    # --- Current SG ---
    last_sg = data.get("lastSG", {})
    sg_value = last_sg.get("sg")
    sg_ts = _parse_carelink_ts(last_sg.get("datetime"))
    trend_raw = data.get("lastSGTrend", "NONE")
    trend = TREND_MAP.get(trend_raw, trend_raw)

    if sg_value and sg_ts:
        existing = session.query(GlucoseReading).filter_by(
            timestamp=sg_ts, source="carelink"
        ).first()
        if not existing:
            session.add(GlucoseReading(
                timestamp=sg_ts, sg=sg_value, trend=trend, source="carelink"
            ))
        summary["sg"] = sg_value
        summary["trend"] = trend
        summary["sg_ts"] = sg_ts.isoformat()

    # --- SG history (last 24h) ---
    for sg_entry in data.get("sgs", []):
        sg_val = sg_entry.get("sg")
        sg_time = _parse_carelink_ts(sg_entry.get("datetime"))
        if sg_val and sg_time and sg_val > 0:
            existing = session.query(GlucoseReading).filter_by(
                timestamp=sg_time, source="carelink"
            ).first()
            if not existing:
                session.add(GlucoseReading(
                    timestamp=sg_time, sg=sg_val, source="carelink"
                ))

    # --- Active Insulin (IOB) ---
    active_insulin = data.get("activeInsulin", {})
    iob = active_insulin.get("amount")

    # --- Pump Status ---
    basal = data.get("basal", {})
    basal_rate = basal.get("rateValue")
    reservoir = data.get("reservoirRemainingUnits")
    battery = data.get("medicalDeviceBatteryLevelPercent")
    auto_mode_data = data.get("therapyAlgorithmState", {})
    auto_mode = auto_mode_data.get("autoModeShieldState", "UNKNOWN")

    if sg_ts:
        existing_ps = session.query(PumpStatus).filter_by(
            timestamp=sg_ts, source="carelink"
        ).first()
        if not existing_ps:
            session.add(PumpStatus(
                timestamp=sg_ts,
                active_insulin=iob,
                basal_rate=basal_rate,
                reservoir_units=reservoir,
                battery_pct=battery,
                auto_mode=auto_mode,
                source="carelink",
            ))

    summary["iob"] = iob
    summary["basal_rate"] = basal_rate
    summary["reservoir"] = reservoir
    summary["battery"] = battery
    summary["auto_mode"] = auto_mode

    # --- Markers (bolus, meal, etc.) ---
    for marker in data.get("markers", []):
        marker_type = marker.get("type", "")
        marker_ts = _parse_carelink_ts(marker.get("dateTime"))

        if marker_type == "INSULIN" and marker_ts:
            bolus_vol = marker.get("deliveredAmount") or marker.get("programmedAmount")
            if bolus_vol:
                existing_b = session.query(BolusEvent).filter_by(
                    timestamp=marker_ts, source="carelink"
                ).first()
                if not existing_b:
                    session.add(BolusEvent(
                        timestamp=marker_ts,
                        volume_units=bolus_vol,
                        bolus_type=marker.get("bolusType", "normal"),
                        bolus_source=marker.get("bolusSource", ""),
                        bwz_carb_input=marker.get("carbInput"),
                        bwz_bg_input=marker.get("bgInput"),
                        source="carelink",
                    ))

    # --- I:C and ISF from active settings ---
    ratios = data.get("carbRatios", [])
    sensitivities = data.get("sensitivities", [])
    for ratio in ratios:
        time_key = ratio.get("time", "")
        ic_val = ratio.get("amount")
        if time_key and ic_val:
            existing_is = session.query(InsulinSetting).filter_by(
                time_start=time_key, source="carelink"
            ).first()
            if existing_is:
                existing_is.ic_ratio = ic_val
            else:
                session.add(InsulinSetting(
                    time_start=time_key,
                    time_end="",
                    ic_ratio=ic_val,
                    source="carelink",
                ))

    for sens in sensitivities:
        time_key = sens.get("time", "")
        isf_val = sens.get("amount")
        if time_key and isf_val:
            existing_is = session.query(InsulinSetting).filter_by(
                time_start=time_key, source="carelink"
            ).first()
            if existing_is:
                existing_is.isf = isf_val

    session.commit()
    log.info("CareLink data parsed: SG=%s trend=%s IOB=%s",
             summary.get("sg"), summary.get("trend"), summary.get("iob"))
    return summary


def _parse_carelink_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse CareLink datetime strings."""
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None
