"""Import and merge CareLink CSV reports into historical database.

Handles the standard MiniMed 780G CSV export format from CareLink website.
Deduplicates against existing records by timestamp+source.
"""

import io
import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import GlucoseReading, BolusEvent, InsulinSetting

log = logging.getLogger(__name__)


def import_carelink_csv(file_path: str, session: Session) -> dict:
    """Import a CareLink CSV export into the database.

    Args:
        file_path: Path to the CSV file.
        session: SQLAlchemy session.

    Returns:
        Summary dict with counts of imported records.
    """
    log.info("Importing CareLink CSV: %s", os.path.basename(file_path))

    try:
        with open(file_path, "r", encoding="latin1") as f:
            lines = f.readlines()
    except FileNotFoundError:
        log.error("File not found: %s", file_path)
        return {"error": f"File not found: {file_path}"}

    # Find the data header row
    header_idx = _find_header(lines)
    if header_idx is None:
        # Try utf-8-sig encoding
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
            header_idx = _find_header(lines)
        except Exception:
            pass

    if header_idx is None:
        log.error("Could not find data header in CSV")
        return {"error": "Could not find data header in CSV"}

    # Parse column names
    header_line = lines[header_idx].strip()
    sep = ";" if ";" in header_line else ","
    col_names = [c.strip().strip('"') for c in header_line.split(sep)]
    col_idx = {name: i for i, name in enumerate(col_names)}

    stats = {"glucose": 0, "bolus": 0, "skipped": 0, "errors": 0}

    for line in lines[header_idx + 1:]:
        line = line.strip()
        if not line:
            continue

        cells = [c.strip().strip('"') for c in line.split(sep)]

        try:
            ts = _parse_row_timestamp(cells, col_idx)
            if ts is None:
                stats["skipped"] += 1
                continue

            # Sensor glucose
            sg = _safe_float(cells, col_idx.get("Sensor Glucose (mg/dL)"))
            bg = _safe_float(cells, col_idx.get("BG Reading (mg/dL)"))

            if sg is not None and sg > 0:
                existing = session.query(GlucoseReading).filter_by(
                    timestamp=ts, source="carelink_csv"
                ).first()
                if not existing:
                    session.add(GlucoseReading(
                        timestamp=ts, sg=sg, bg=bg, source="carelink_csv"
                    ))
                    stats["glucose"] += 1

            # Bolus
            bolus_vol = _safe_float(cells, col_idx.get("Bolus Volume Delivered (U)"))
            if bolus_vol is not None and bolus_vol > 0:
                existing = session.query(BolusEvent).filter_by(
                    timestamp=ts, source="carelink_csv"
                ).first()
                if not existing:
                    carb_input = _safe_float(cells, col_idx.get("BWZ Carb Input (grams)"))
                    bg_input = _safe_float(cells, col_idx.get("BWZ BG/SG Input (mg/dL)"))
                    bolus_src = _get_cell(cells, col_idx.get("Bolus Source"))
                    isf = _safe_float(cells, col_idx.get("BWZ Insulin Sensitivity (mg/dL/U)"))
                    ic = _safe_float(cells, col_idx.get("BWZ Carb Ratio (g/U)"))

                    session.add(BolusEvent(
                        timestamp=ts,
                        volume_units=bolus_vol,
                        bolus_source=bolus_src or "",
                        bwz_carb_input=carb_input,
                        bwz_bg_input=bg_input,
                        source="carelink_csv",
                    ))
                    stats["bolus"] += 1

                    # Update insulin settings if available
                    if isf or ic:
                        hour = ts.strftime("%H:00")
                        existing_is = session.query(InsulinSetting).filter_by(
                            time_start=hour, source="carelink_csv"
                        ).first()
                        if existing_is:
                            if isf:
                                existing_is.isf = isf
                            if ic:
                                existing_is.ic_ratio = ic
                        elif isf or ic:
                            session.add(InsulinSetting(
                                time_start=hour,
                                time_end="",
                                ic_ratio=ic,
                                isf=isf,
                                source="carelink_csv",
                            ))

        except Exception as e:
            stats["errors"] += 1
            log.debug("Error parsing CSV row: %s", e)

    session.commit()
    log.info(
        "CSV import complete: %d glucose, %d bolus, %d skipped, %d errors",
        stats["glucose"], stats["bolus"], stats["skipped"], stats["errors"],
    )
    return stats


def import_carelink_csv_bytes(data: bytes, filename: str, session: Session) -> dict:
    """Import CareLink CSV from raw bytes (e.g., Telegram file upload)."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        return import_carelink_csv(tmp_path, session)
    finally:
        os.unlink(tmp_path)


def _find_header(lines: list[str]) -> Optional[int]:
    """Find the header row index in a CareLink CSV."""
    keywords = ["Date", "Time", "Sensor Glucose"]
    for i, line in enumerate(lines):
        if all(kw in line for kw in keywords):
            return i
    return None


def _parse_row_timestamp(cells: list[str], col_idx: dict) -> Optional[datetime]:
    """Extract timestamp from a CSV row."""
    date_i = col_idx.get("Date")
    time_i = col_idx.get("Time")
    if date_i is None or time_i is None:
        return None
    date_str = _get_cell(cells, date_i)
    time_str = _get_cell(cells, time_i)
    if not date_str or not time_str:
        return None

    for date_fmt in ("%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        for time_fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(f"{date_str} {time_str}", f"{date_fmt} {time_fmt}")
            except ValueError:
                continue
    return None


def _get_cell(cells: list[str], idx: Optional[int]) -> str:
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx].strip()


def _safe_float(cells: list[str], idx: Optional[int]) -> Optional[float]:
    val = _get_cell(cells, idx)
    if not val:
        return None
    try:
        return float(val.replace(",", "."))
    except ValueError:
        return None
