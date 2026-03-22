"""
MiniMed 780G data analysis for Nuria Perez Diez.
Parses all patient CSV exports and computes per-period metrics.
"""

import csv
import os
import re
from collections import defaultdict
from datetime import datetime

PATIENT_FILES = [
    ("Feb–May 2025",       "report_1y.csv"),
    ("Sep 14–20 2025",     "Nuria Perez Diez 21-09-2025.csv"),
    ("Sep 20–22 2025",     "Nuria Perez Diez 22-09-2025.csv"),
    ("Nov 2025–Jan 2026",  "jan2026.csv"),
    ("Feb–Mar 2026",       "march2026.csv"),
]

BASE = os.path.dirname(os.path.abspath(__file__))

# Glucose thresholds (mg/dL)
VERY_LOW   = 54
LOW        = 70
HIGH       = 180
VERY_HIGH  = 250


def parse_file(path):
    """Return (header_info, data_rows) from a MiniMed 780G CSV export."""
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()

    # Find the data section separator line
    lines = raw.splitlines()
    data_start = None
    for i, line in enumerate(lines):
        if line.startswith("Index;Date;Time;"):
            data_start = i
            break

    if data_start is None:
        return {}, []

    header_line = lines[1]  # "Last Name;First Name;...;Start Date;End Date;..."
    meta = {}
    parts = lines[0].split(";") + lines[1].split(";")
    for j, p in enumerate(parts):
        p = p.strip().strip('"')
        if p in ("Start Date", "End Date") and j + 1 < len(parts):
            meta[p] = parts[j + 1].strip()

    col_names = lines[data_start].split(";")
    col_idx = {name.strip(): i for i, name in enumerate(col_names)}

    rows = []
    for line in lines[data_start + 1:]:
        if not line.strip():
            continue
        cells = line.split(";")
        rows.append(cells)

    return meta, col_names, col_idx, rows


def safe_float(s):
    if not s or not s.strip():
        return None
    try:
        return float(s.strip().replace(",", "."))
    except ValueError:
        return None


def analyze(label, filename):
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        print(f"  [missing] {filename}")
        return None

    meta, col_names, col_idx, rows = parse_file(path)

    sg_col    = col_idx.get("Sensor Glucose (mg/dL)")
    bg_col    = col_idx.get("BG Reading (mg/dL)")
    alert_col = col_idx.get("Alert")
    suspend_col = col_idx.get("Suspend")
    bolus_src_col = col_idx.get("Bolus Source")
    bolus_del_col = col_idx.get("Bolus Volume Delivered (U)")
    carb_col  = col_idx.get("BWZ Carb Input (grams)")
    bwz_sg_col = col_idx.get("BWZ BG/SG Input (mg/dL)")
    date_col  = col_idx.get("Date")

    sg_values = []
    bg_values = []
    alerts = defaultdict(int)
    suspends = defaultdict(int)
    bolus_sources = defaultdict(int)
    bolus_total_u = 0.0
    bolus_count = 0
    carb_total = 0.0
    carb_entries = 0
    bwz_sg_values = []
    dates_seen = set()

    def get(cells, col):
        if col is None or col >= len(cells):
            return ""
        return cells[col].strip()

    for cells in rows:
        sg = safe_float(get(cells, sg_col))
        if sg is not None and sg > 0:
            sg_values.append(sg)

        bg = safe_float(get(cells, bg_col))
        if bg is not None and bg > 0:
            bg_values.append(bg)

        alert = get(cells, alert_col)
        if alert:
            # Normalize: strip ": alert silence" / ": vibration" suffixes
            key = re.sub(r":\s*(alert silence|vibration)$", "", alert).strip()
            alerts[key] += 1

        suspend = get(cells, suspend_col)
        if suspend:
            suspends[suspend] += 1

        src = get(cells, bolus_src_col)
        if src:
            bolus_sources[src] += 1

        bd = safe_float(get(cells, bolus_del_col))
        if bd is not None and bd > 0:
            bolus_total_u += bd
            bolus_count += 1

        carb = safe_float(get(cells, carb_col))
        if carb is not None and carb > 0:
            carb_total += carb
            carb_entries += 1

        bwz_sg = safe_float(get(cells, bwz_sg_col))
        if bwz_sg is not None and bwz_sg > 0:
            bwz_sg_values.append(bwz_sg)

        d = get(cells, date_col)
        if d:
            dates_seen.add(d)

    n = len(sg_values)
    if n == 0:
        print(f"  [no SG data] {filename}")
        return None

    def pct(vals, lo, hi):
        return 100 * sum(1 for v in vals if lo <= v < hi) / len(vals)

    tir   = pct(sg_values, LOW, HIGH)
    tbr1  = pct(sg_values, VERY_LOW, LOW)    # low 54-70
    tbr2  = pct(sg_values, 0, VERY_LOW)      # very low <54
    tar1  = pct(sg_values, HIGH, VERY_HIGH)  # high 180-250
    tar2  = pct(sg_values, VERY_HIGH, 9999)  # very high >250
    titr  = pct(sg_values, 70, 140)          # tight TIR

    mean_sg = sum(sg_values) / n
    gmi = 3.31 + 0.02392 * mean_sg  # Glucose Management Indicator (mmol/mol approx)
    # Standard deviation
    variance = sum((v - mean_sg) ** 2 for v in sg_values) / n
    sd_sg = variance ** 0.5
    cv = 100 * sd_sg / mean_sg

    days = len(dates_seen)
    avg_bolus_per_day = bolus_count / days if days else 0
    avg_carbs_per_entry = carb_total / carb_entries if carb_entries else 0
    avg_insulin_per_day = bolus_total_u / days if days else 0

    # Closed-loop breakdown
    cl_correction = bolus_sources.get("CLOSED_LOOP_BG_CORRECTION", 0)
    cl_food       = bolus_sources.get("CLOSED_LOOP_BG_CORRECTION_AND_FOOD_BOLUS", 0)
    bwz           = bolus_sources.get("BOLUS_WIZARD", 0)
    cl_pct = 100 * (cl_correction + cl_food) / max(bolus_count, 1)

    return {
        "label": label,
        "days": days,
        "sg_count": n,
        "mean_sg": mean_sg,
        "sd_sg": sd_sg,
        "cv": cv,
        "gmi_pct": gmi,          # % HbA1c equivalent
        "tir": tir,
        "titr": titr,
        "tbr1": tbr1,
        "tbr2": tbr2,
        "tar1": tar1,
        "tar2": tar2,
        "bolus_count": bolus_count,
        "avg_bolus_per_day": avg_bolus_per_day,
        "avg_insulin_per_day": avg_insulin_per_day,
        "avg_carbs_per_entry": avg_carbs_per_entry,
        "cl_pct": cl_pct,
        "cl_correction": cl_correction,
        "cl_food": cl_food,
        "bwz": bwz,
        "alerts": dict(alerts),
        "suspends": dict(suspends),
        "bg_values": bg_values,
        "sg_values": sg_values,
    }


def bar(pct, width=30, fill="█", empty="░"):
    filled = int(round(pct / 100 * width))
    return fill * filled + empty * (width - filled)


def print_report(results):
    print("\n" + "=" * 72)
    print("  MiniMed 780G — Nuria Perez Diez — Multi-Period Analysis")
    print("=" * 72)

    # Table header
    cols = ["Period", "Days", "SG#", "Mean±SD", "CV%", "GMI%", "TIR%", "TITR%", "TAR1%", "TAR2%", "TBR1%", "TBR2%"]
    widths = [18, 4, 5, 12, 5, 5, 5, 6, 5, 5, 5, 5]
    header = "  ".join(f"{c:<{w}}" for c, w in zip(cols, widths))
    print("\n" + header)
    print("-" * len(header))

    for r in results:
        if r is None:
            continue
        row = [
            r["label"],
            str(r["days"]),
            str(r["sg_count"]),
            f"{r['mean_sg']:.0f}±{r['sd_sg']:.0f}",
            f"{r['cv']:.1f}",
            f"{r['gmi_pct']:.1f}",
            f"{r['tir']:.1f}",
            f"{r['titr']:.1f}",
            f"{r['tar1']:.1f}",
            f"{r['tar2']:.1f}",
            f"{r['tbr1']:.1f}",
            f"{r['tbr2']:.1f}",
        ]
        print("  ".join(f"{v:<{w}}" for v, w in zip(row, widths)))

    print()

    # TIR stacked bars per period
    print("\n--- Time-in-Range breakdown (per period) ---\n")
    print(f"  {'Period':<20} {'<54':>4} {'54-70':>5} {'70-180':>6} {'180-250':>7} {'>250':>4}  [visual TIR 70-180]")
    print("  " + "-" * 78)
    for r in results:
        if r is None:
            continue
        print(f"  {r['label']:<20} {r['tbr2']:>4.1f} {r['tbr1']:>5.1f} {r['tir']:>6.1f} {r['tar1']:>7.1f} {r['tar2']:>4.1f}  {bar(r['tir'])}")

    print()

    # Insulin & bolus summary
    print("\n--- Bolus & Insulin Summary ---\n")
    print(f"  {'Period':<20} {'Boluses/day':>11} {'U/day':>6} {'CL%':>5} {'CL-corr':>8} {'CL-food':>8} {'BWZ':>4}")
    print("  " + "-" * 68)
    for r in results:
        if r is None:
            continue
        print(f"  {r['label']:<20} {r['avg_bolus_per_day']:>11.1f} {r['avg_insulin_per_day']:>6.1f} {r['cl_pct']:>5.1f} {r['cl_correction']:>8} {r['cl_food']:>8} {r['bwz']:>4}")

    print()

    # Alert summary
    print("\n--- Alert Frequency (top alerts per period) ---\n")
    for r in results:
        if r is None:
            continue
        print(f"  {r['label']} ({r['days']} days):")
        sorted_alerts = sorted(r["alerts"].items(), key=lambda x: -x[1])
        for alert, count in sorted_alerts[:6]:
            per_day = count / r["days"] if r["days"] else 0
            print(f"    {count:>4}x  ({per_day:.1f}/day)  {alert}")
        if r["suspends"]:
            print(f"    Suspends: {dict(list(r['suspends'].items()))}")
        print()

    # Trend summary
    print("\n--- Trend Summary ---\n")
    valid = [r for r in results if r is not None]
    if len(valid) >= 2:
        first, last = valid[0], valid[-1]
        dtir  = last["tir"] - first["tir"]
        dmean = last["mean_sg"] - first["mean_sg"]
        dgmi  = last["gmi_pct"] - first["gmi_pct"]
        dcv   = last["cv"] - first["cv"]
        print(f"  TIR change    {first['label']} → {last['label']}: {dtir:+.1f}%  ({'improved' if dtir > 0 else 'worsened'})")
        print(f"  Mean SG       {first['mean_sg']:.0f} → {last['mean_sg']:.0f} mg/dL  ({dmean:+.0f})")
        print(f"  GMI           {first['gmi_pct']:.1f}% → {last['gmi_pct']:.1f}%  ({dgmi:+.1f}%)")
        print(f"  CV (variability) {first['cv']:.1f}% → {last['cv']:.1f}%  ({dcv:+.1f}%, target <36%)")

    print()
    print("  NOTE: This analysis is informational only. Consult your diabetes")
    print("  care team for clinical interpretation and therapy adjustments.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    results = []
    for label, filename in PATIENT_FILES:
        print(f"Parsing: {filename}")
        r = analyze(label, filename)
        results.append(r)

    print_report(results)
