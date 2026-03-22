"""
Genera due PDF:
1) report_proiezioni.pdf  — Proiezioni dei miglioramenti attesi
2) report_istruzioni.pdf  — Istruzioni operative passo-passo
"""

import os, io, math
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

BASE = os.path.dirname(os.path.abspath(__file__))

# ── Colors ──────────────────────────────────────────────────────────
C_BLUE    = HexColor("#2563EB")
C_GREEN   = HexColor("#16A34A")
C_RED     = HexColor("#DC2626")
C_ORANGE  = HexColor("#EA580C")
C_YELLOW  = HexColor("#CA8A04")
C_GRAY    = HexColor("#6B7280")
C_LIGHT   = HexColor("#F3F4F6")
C_WHITE   = white
C_DARK    = HexColor("#1F2937")

# TIR color scheme
C_VERY_LOW  = HexColor("#991B1B")
C_LOW       = HexColor("#DC2626")
C_IN_RANGE  = HexColor("#16A34A")
C_HIGH      = HexColor("#F59E0B")
C_VERY_HIGH = HexColor("#EA580C")

# ── Data from analyze.py ────────────────────────────────────────────
# Actual measured data per period
PERIODS = [
    {"label": "Feb-Mag 2025", "days": 97, "tir": 52.5, "titr": 25.8,
     "tar1": 36.2, "tar2": 10.8, "tbr1": 0.6, "tbr2": 0.0,
     "mean_sg": 178, "sd": 54, "cv": 30.5, "gmi": 7.6},
    {"label": "Set 2025", "days": 32, "tir": 53.0, "titr": 22.0,
     "tar1": 34.5, "tar2": 11.8, "tbr1": 0.3, "tbr2": 0.2,
     "mean_sg": 181, "sd": 51, "cv": 28.3, "gmi": 7.6},
    {"label": "Nov25-Gen26", "days": 96, "tir": 56.6, "titr": 23.7,
     "tar1": 35.0, "tar2": 8.3, "tbr1": 0.1, "tbr2": 0.0,
     "mean_sg": 177, "sd": 50, "cv": 28.1, "gmi": 7.5},
    {"label": "Feb-Mar 2026", "days": 64, "tir": 53.7, "titr": 25.9,
     "tar1": 36.7, "tar2": 9.4, "tbr1": 0.2, "tbr2": 0.0,
     "mean_sg": 177, "sd": 52, "cv": 29.4, "gmi": 7.6},
]

# Projected improvements — CONSERVATIVE estimates
# Revised: account for existing hypo risk (ALERT ON LOW ~0.5/day,
# morning lows 55-69 mg/dL on Feb 20/22/24, evening lows 73-79 on Mar 2/26)
PROJECTIONS = [
    {"label": "Attuale\n(Mar 2026)", "tir": 53.7, "tar1": 36.7, "tar2": 9.4,
     "tbr1": 0.2, "tbr2": 0.0, "mean_sg": 177, "gmi": 7.6, "cv": 29.4},
    {"label": "Dopo Passo 1\n(Dieta+Pre-bolo)", "tir": 58, "tar1": 33, "tar2": 7,
     "tbr1": 0.3, "tbr2": 0.0, "mean_sg": 170, "gmi": 7.4, "cv": 28},
    {"label": "Dopo Passo 2\n(Protocollo sport)", "tir": 62, "tar1": 30, "tar2": 6,
     "tbr1": 0.2, "tbr2": 0.0, "mean_sg": 165, "gmi": 7.3, "cv": 27.5},
    {"label": "Dopo Passo 3\n(AIT 2h15)", "tir": 64, "tar1": 28, "tar2": 5.5,
     "tbr1": 0.3, "tbr2": 0.0, "mean_sg": 162, "gmi": 7.2, "cv": 27},
    {"label": "Dopo Passo 4\n(ICR cena 9)", "tir": 66, "tar1": 26.5, "tar2": 5,
     "tbr1": 0.5, "tbr2": 0.0, "mean_sg": 159, "gmi": 7.1, "cv": 27},
    {"label": "Dopo Passo 5\n(Rivalutazione ISF)", "tir": 68, "tar1": 25, "tar2": 4,
     "tbr1": 0.8, "tbr2": 0.0, "mean_sg": 155, "gmi": 7.0, "cv": 26.5},
]

# Per-meal-block data
MEAL_DATA = {
    "Colazione\n(6-10)":  {"icr_now": "11-14", "sg": 148, "pct_high": 12, "icr_new": "Invariato", "note": "No bolo (5g CHO)"},
    "Pranzo\n(10-15)":    {"icr_now": "8.8-9", "sg": 177, "pct_high": 40, "icr_new": "Invariato", "note": "Pre-bolo+CHO lenti"},
    "Merenda\n(15-18)":   {"icr_now": "9.2-9.4", "sg": 228, "pct_high": 68, "icr_new": "NO bolo", "note": "Snack sport"},
    "Cena\n(18-23)":      {"icr_now": "9.7-10", "sg": 200, "pct_high": 61, "icr_new": "9", "note": "-10% post-sport"},
    "Notte\n(23-6)":      {"icr_now": "11.5-13", "sg": 240, "pct_high": 87, "icr_new": "Invariato", "note": "Rari ipo (3/mese)"},
}


def make_tir_stacked_bar_chart(periods, filename, title, figsize=(10, 5)):
    """Stacked horizontal bar chart of TIR breakdown."""
    fig, ax = plt.subplots(figsize=figsize)

    labels = [p["label"] for p in periods]
    y_pos = np.arange(len(labels))

    tbr2  = [p["tbr2"] for p in periods]
    tbr1  = [p["tbr1"] for p in periods]
    tir   = [p["tir"] for p in periods]
    tar1  = [p["tar1"] for p in periods]
    tar2  = [p["tar2"] for p in periods]

    left = np.zeros(len(labels))

    colors = ["#991B1B", "#DC2626", "#16A34A", "#F59E0B", "#EA580C"]
    data   = [tbr2, tbr1, tir, tar1, tar2]
    names  = ["<54 mg/dL", "54-70", "70-180 (Target)", "180-250", ">250"]

    for d, c, n in zip(data, colors, names):
        bars = ax.barh(y_pos, d, left=left, color=c, label=n, height=0.6, edgecolor="white", linewidth=0.5)
        # Add percentage text
        for i, (v, l) in enumerate(zip(d, left)):
            if v > 4:
                ax.text(l + v/2, i, f"{v:.1f}%", ha="center", va="center",
                        fontsize=8, fontweight="bold", color="white")
        left += np.array(d)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("% del tempo", fontsize=10)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=15)
    ax.set_xlim(0, 100)
    ax.axvline(70, color="#16A34A", linestyle="--", alpha=0.5, linewidth=1.5)
    ax.text(71, len(labels) - 0.5, "Obiettivo\nTIR >70%", fontsize=7, color="#16A34A", va="top")

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=5, fontsize=8,
              frameon=False)
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_tir_trend_line(periods_actual, projections, filename):
    """Line chart: actual TIR + projected TIR."""
    fig, ax = plt.subplots(figsize=(10, 4.5))

    # Actual
    x_act = list(range(len(periods_actual)))
    y_act = [p["tir"] for p in periods_actual]
    ax.plot(x_act, y_act, "o-", color="#2563EB", linewidth=2.5, markersize=8,
            label="TIR Misurato", zorder=5)
    for i, (x, y) in enumerate(zip(x_act, y_act)):
        ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points",
                    xytext=(0, 12), ha="center", fontsize=9, fontweight="bold", color="#2563EB")

    # Projected
    x_proj = list(range(len(periods_actual) - 1, len(periods_actual) - 1 + len(projections)))
    y_proj = [p["tir"] for p in projections]
    ax.plot(x_proj, y_proj, "s--", color="#16A34A", linewidth=2, markersize=7,
            label="TIR Proiettato", zorder=4)
    for i, (x, y) in enumerate(zip(x_proj, y_proj)):
        if i > 0:
            ax.annotate(f"{y:.0f}%", (x, y), textcoords="offset points",
                        xytext=(0, 12), ha="center", fontsize=9, fontweight="bold", color="#16A34A")

    # Target line
    ax.axhline(70, color="#16A34A", linestyle=":", alpha=0.4, linewidth=2)
    ax.text(x_proj[-1] + 0.2, 70.5, "Obiettivo 70%", fontsize=8, color="#16A34A", alpha=0.7)

    all_labels = [p["label"] for p in periods_actual] + [p["label"] for p in projections[1:]]
    ax.set_xticks(range(len(all_labels)))
    ax.set_xticklabels(all_labels, fontsize=7, rotation=25, ha="right")
    ax.set_ylabel("TIR %", fontsize=10)
    ax.set_title("Andamento TIR: Dati Reali + Proiezioni con Ottimizzazione", fontsize=12, fontweight="bold", pad=15)
    ax.set_ylim(40, 80)
    ax.legend(loc="upper left", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)

    # Shade projection area
    ax.axvspan(x_proj[0], x_proj[-1], alpha=0.07, color="#16A34A")
    ax.text((x_proj[0] + x_proj[-1]) / 2, 42, "AREA PROIEZIONE",
            ha="center", fontsize=8, color="#16A34A", alpha=0.6, fontweight="bold")

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_meal_block_chart(filename):
    """Bar chart of pre-bolus SG by meal block."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    blocks = list(MEAL_DATA.keys())
    sg = [MEAL_DATA[b]["sg"] for b in blocks]
    pct = [MEAL_DATA[b]["pct_high"] for b in blocks]

    colors_sg = ["#16A34A" if v < 180 else "#F59E0B" if v < 220 else "#EA580C" for v in sg]
    colors_pct = ["#16A34A" if v < 30 else "#F59E0B" if v < 50 else "#EA580C" for v in pct]

    bars1 = ax1.bar(blocks, sg, color=colors_sg, edgecolor="white", width=0.6)
    ax1.axhline(180, color="#DC2626", linestyle="--", alpha=0.5, linewidth=1.5)
    ax1.text(4.3, 182, "180", fontsize=8, color="#DC2626")
    ax1.axhline(70, color="#DC2626", linestyle="--", alpha=0.3, linewidth=1)
    ax1.set_ylabel("mg/dL")
    ax1.set_title("SG Medio Pre-Bolo per Fascia", fontsize=11, fontweight="bold")
    for bar, v in zip(bars1, sg):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 3,
                 f"{v}", ha="center", fontsize=9, fontweight="bold")
    ax1.set_ylim(0, 280)
    ax1.tick_params(axis='x', labelsize=7)

    bars2 = ax2.bar(blocks, pct, color=colors_pct, edgecolor="white", width=0.6)
    ax2.axhline(30, color="#16A34A", linestyle="--", alpha=0.5, linewidth=1.5)
    ax2.text(4.3, 31, "30%", fontsize=8, color="#16A34A")
    ax2.set_ylabel("% del tempo")
    ax2.set_title("% Tempo Sopra 180 mg/dL per Fascia", fontsize=11, fontweight="bold")
    for bar, v in zip(bars2, pct):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                 f"{v}%", ha="center", fontsize=9, fontweight="bold")
    ax2.set_ylim(0, 100)
    ax2.tick_params(axis='x', labelsize=7)

    for ax in (ax1, ax2):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_gmi_projection_chart(filename):
    """GMI projection chart."""
    fig, ax = plt.subplots(figsize=(10, 4))
    labels = [p["label"] for p in PROJECTIONS]
    gmi = [p["gmi"] for p in PROJECTIONS]
    mean_sg = [p["mean_sg"] for p in PROJECTIONS]

    colors = ["#2563EB"] + ["#16A34A"] * (len(PROJECTIONS) - 1)
    bars = ax.bar(range(len(labels)), gmi, color=colors, edgecolor="white", width=0.55)
    ax.axhline(7.0, color="#16A34A", linestyle="--", alpha=0.5, linewidth=2)
    ax.text(len(labels) - 0.5, 7.02, "Obiettivo GMI <7%", fontsize=8, color="#16A34A")

    for i, (bar, g, sg) in enumerate(zip(bars, gmi, mean_sg)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.03,
                f"{g}%\n({sg} mg/dL)", ha="center", fontsize=8, fontweight="bold")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7, rotation=20, ha="right")
    ax.set_ylabel("GMI (%)", fontsize=10)
    ax.set_title("Proiezione GMI (equiv. HbA1c) e SG Medio", fontsize=12, fontweight="bold", pad=15)
    ax.set_ylim(6.2, 8.0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_settings_impact_chart(filename):
    """Waterfall chart showing incremental TIR improvement per setting change."""
    fig, ax = plt.subplots(figsize=(10, 4.5))

    steps = [
        ("Attuale", 53.7, 0),
        ("Dieta\n+Pre-bolo", 0, 4.3),
        ("Protocollo\nSport", 0, 4.0),
        ("AIT\n2h30→2h15", 0, 2.0),
        ("ICR Cena\n10→9", 0, 2.0),
        ("Rivalut.\nISF", 0, 2.0),
        ("Obiettivo", 68, 0),
    ]

    cumulative = 53.7
    bottoms = []
    heights = []
    colors = []

    for i, (name, base, inc) in enumerate(steps):
        if i == 0:
            bottoms.append(0)
            heights.append(base)
            colors.append("#2563EB")
        elif i == len(steps) - 1:
            bottoms.append(0)
            heights.append(cumulative)
            colors.append("#16A34A")
        else:
            bottoms.append(cumulative)
            heights.append(inc)
            cumulative += inc
            colors.append("#34D399")

    x = range(len(steps))
    bars = ax.bar(x, heights, bottom=bottoms, color=colors, edgecolor="white", width=0.55)

    # Add connector lines
    for i in range(len(steps) - 1):
        top = bottoms[i] + heights[i]
        ax.plot([i + 0.3, i + 0.7], [top, top], color="#9CA3AF", linewidth=1, linestyle="-")

    # Labels
    for i, (bar, (name, base, inc)) in enumerate(zip(bars, steps)):
        top = bottoms[i] + heights[i]
        if i == 0:
            ax.text(i, top + 0.8, f"{base:.1f}%", ha="center", fontsize=9, fontweight="bold", color="#2563EB")
        elif i == len(steps) - 1:
            ax.text(i, top + 0.8, f"{cumulative:.0f}%", ha="center", fontsize=9, fontweight="bold", color="#16A34A")
        else:
            ax.text(i, top + 0.8, f"+{inc:.1f}%", ha="center", fontsize=9, fontweight="bold", color="#059669")

    ax.set_xticks(x)
    ax.set_xticklabels([s[0] for s in steps], fontsize=8)
    ax.set_ylabel("TIR %", fontsize=10)
    ax.set_title("Impatto Incrementale di Ogni Modifica sul TIR", fontsize=12, fontweight="bold", pad=15)
    ax.axhline(70, color="#16A34A", linestyle=":", alpha=0.4, linewidth=2)
    ax.set_ylim(0, 80)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.2)

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


# ── PDF Generation ──────────────────────────────────────────────────

def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Title2", parent=styles["Title"], fontSize=20, textColor=C_BLUE,
                               spaceAfter=6*mm))
    styles.add(ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12, textColor=C_GRAY,
                               spaceAfter=4*mm, alignment=TA_CENTER))
    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=14, textColor=C_BLUE,
                               spaceBefore=6*mm, spaceAfter=3*mm, borderWidth=0,
                               borderColor=C_BLUE, borderPadding=2))
    styles.add(ParagraphStyle("BodyIt", parent=styles["Normal"], fontSize=10, textColor=C_DARK,
                               leading=14))
    styles.add(ParagraphStyle("SmallGray", parent=styles["Normal"], fontSize=8, textColor=C_GRAY,
                               leading=10))
    styles.add(ParagraphStyle("CellStyle", parent=styles["Normal"], fontSize=9, textColor=C_DARK,
                               leading=11))
    styles.add(ParagraphStyle("CellBold", parent=styles["Normal"], fontSize=9, textColor=C_DARK,
                               leading=11, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8, textColor=C_GRAY,
                               leading=10, alignment=TA_CENTER, spaceBefore=8*mm))
    styles.add(ParagraphStyle("BigNumber", parent=styles["Normal"], fontSize=28, textColor=C_BLUE,
                               alignment=TA_CENTER, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("BigLabel", parent=styles["Normal"], fontSize=9, textColor=C_GRAY,
                               alignment=TA_CENTER))
    return styles


def make_table(data, col_widths=None, header=True):
    """Helper to make styled tables."""
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def generate_projections_pdf():
    """PDF 1: Proiezioni dei miglioramenti attesi."""
    path = os.path.join(BASE, "report_proiezioni.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_styles()
    story = []

    # ── Title ──
    story.append(Paragraph("Proiezioni di Miglioramento", styles["Title2"]))
    story.append(Paragraph("MiniMed 780G - Nuria Perez Diez (46 anni, 54 kg, T1D da 20 anni) - Marzo 2026", styles["Subtitle"]))
    story.append(Spacer(1, 4*mm))

    # ── Key numbers ──
    kpi_data = [
        ["TIR Attuale", "TIR Obiettivo", "GMI Attuale", "GMI Obiettivo"],
        ["53.7%", "68%", "7.6%", "7.0%"],
        ["(sotto obiettivo)", "(raggiungibile)", "(equiv. HbA1c)", "(equiv. HbA1c)"],
    ]
    kpi_t = Table(kpi_data, colWidths=[42*mm]*4)
    kpi_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_GRAY),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 22),
        ("TEXTCOLOR", (0, 1), (0, 1), C_RED),
        ("TEXTCOLOR", (1, 1), (1, 1), C_GREEN),
        ("TEXTCOLOR", (2, 1), (2, 1), C_ORANGE),
        ("TEXTCOLOR", (3, 1), (3, 1), C_GREEN),
        ("FONTSIZE", (0, 2), (-1, 2), 7),
        ("TEXTCOLOR", (0, 2), (-1, 2), C_GRAY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BOX", (0, 0), (-1, -1), 1, HexColor("#E5E7EB")),
        ("LINEAFTER", (0, 0), (2, -1), 0.5, HexColor("#E5E7EB")),
    ]))
    story.append(kpi_t)
    story.append(Spacer(1, 6*mm))

    # ── Situation chart ──
    story.append(Paragraph("1. Situazione Attuale - Distribuzione del Tempo per Fascia Oraria", styles["SectionHead"]))
    story.append(Paragraph(
        "L'analisi di 12 mesi di dati mostra un TIR consistentemente tra 52-57%. "
        "Il problema principale e' l'iperglicemia: il 43-47% del tempo sopra 180 mg/dL. "
        "Tuttavia, esistono <b>ipoglicemie ricorrenti</b> che limitano la possibilita' di "
        "rendere le impostazioni piu' aggressive (vedi sezione dedicata).", styles["BodyIt"]))
    story.append(Spacer(1, 3*mm))

    img_path = make_tir_stacked_bar_chart(PERIODS, "_chart_tir_actual.png",
                                           "Distribuzione TIR per Periodo (Dati Reali)")
    story.append(Image(img_path, width=170*mm, height=85*mm))
    story.append(Spacer(1, 3*mm))

    # ── Meal block analysis ──
    story.append(Paragraph("2. Analisi per Fascia Oraria - Dove si Perde il Controllo", styles["SectionHead"]))
    img_meal = make_meal_block_chart("_chart_meals.png")
    story.append(Image(img_meal, width=170*mm, height=68*mm))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Evidenza chiave:</b> La merenda (68% sopra 180) e la notte (87% sopra 180) sono le fasce critiche. "
        "Il picco ore 16:00-17:00 (confermato dal report CareLink: 12 casi/mese) e' causato dallo "
        "sfasamento tra assorbimento CHO (20-30 min) e azione insulina (60-90 min) del pranzo. "
        "Il problema NON e' la dose del bolo (che e' corretta) ma il TIPO di CHO e il TIMING.", styles["BodyIt"]))

    story.append(Spacer(1, 4*mm))

    # ── HYPO WARNING SECTION ──
    story.append(Paragraph("ATTENZIONE: Ipoglicemie Esistenti", styles["SectionHead"]))
    story.append(Paragraph(
        "<b>I dati recenti (Feb-Mar 2026) mostrano ipoglicemie ricorrenti che condizionano "
        "ogni modifica alle impostazioni:</b>", styles["BodyIt"]))
    story.append(Spacer(1, 2*mm))

    hypo_table = [
        ["Fascia", "Episodi", "Dettaglio", "Impatto sulle modifiche"],
        ["Mattina\n(6-10)",
         "Rari: 3 episodi\nin 30 giorni",
         "20/02: SG 55 mg/dL\n22/02: SG 57\n24/02: SG 66\n(Solo fine febbraio)",
         "Rischio basso.\nTemp Target solo se\nSG <130 alla sveglia"],
        ["Sera\n(17-19)",
         "ALERT ON LOW\ncausati da SPORT",
         "Crollo 300→86 in 70 min\nPompa OFF + IOB + esercizio\nNon e' un problema di ICR!",
         "Risolvere con strategia\nsport (dieta+Temp Target)\nnon con la pompa"],
        ["Notte\n(23-6)",
         "MINIMUM DELIVERY\nsporadico",
         "SmartGuard riduce basale\nautonomamente",
         "Basale notturna gestita\nda SmartGuard. OK"],
    ]
    story.append(make_table(hypo_table, col_widths=[25*mm, 32*mm, 45*mm, 45*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Conclusione:</b> Le ipo serali NON sono un problema di impostazioni pompa ma di "
        "gestione sport (IOB dal pranzo + esercizio + pompa disconnessa). La soluzione e' "
        "cambiare il tipo di CHO a pranzo (basso IG), fare pre-bolo, e usare il protocollo "
        "Temp Target + snack pre-sport. Le ipo mattutine sono rare (3/mese).",
        styles["BodyIt"]))

    story.append(PageBreak())

    # ── Projections ──
    story.append(Paragraph("3. Proiezione dei Miglioramenti con Ottimizzazione (Versione Conservativa)", styles["SectionHead"]))
    story.append(Paragraph(
        "Le proiezioni seguenti sono stime <b>conservative</b> che tengono conto delle ipoglicemie "
        "esistenti. Basate sulla letteratura clinica del MiniMed 780G "
        "(Passanisi 2024, CO-PILOT 2026) e sull'analisi dei pattern specifici di Nuria. "
        "Ogni passo si aggiunge al precedente. L'ISF viene rivalutato solo come ultimo passo, "
        "una volta verificato che le ipo non siano peggiorate.", styles["BodyIt"]))
    story.append(Spacer(1, 3*mm))

    # Waterfall chart
    img_waterfall = make_settings_impact_chart("_chart_waterfall.png")
    story.append(Image(img_waterfall, width=170*mm, height=75*mm))
    story.append(Spacer(1, 4*mm))

    # Projection table
    proj_header = ["Fase", "TIR %", "TAR\n>180%", "TAR\n>250%", "TBR\n<70%", "SG\nMedio", "GMI %"]
    proj_rows = [proj_header]
    for p in PROJECTIONS:
        proj_rows.append([
            p["label"].replace("\n", " "),
            f"{p['tir']:.1f}%", f"{p['tar1']+p['tar2']:.1f}%",
            f"{p['tar2']:.1f}%", f"{p['tbr1']:.1f}%",
            f"{p['mean_sg']}", f"{p['gmi']}%"
        ])
    story.append(make_table(proj_rows, col_widths=[36*mm, 18*mm, 18*mm, 18*mm, 18*mm, 18*mm, 18*mm]))
    story.append(Spacer(1, 4*mm))

    # ── TIR trend line ──
    story.append(Paragraph("4. Andamento TIR: Storico + Proiezione", styles["SectionHead"]))
    img_trend = make_tir_trend_line(PERIODS, PROJECTIONS, "_chart_trend.png")
    story.append(Image(img_trend, width=170*mm, height=75*mm))
    story.append(Spacer(1, 3*mm))

    # ── Stacked bar projections ──
    story.append(Paragraph("5. Distribuzione TIR Proiettata dopo Ogni Fase", styles["SectionHead"]))
    img_proj = make_tir_stacked_bar_chart(PROJECTIONS, "_chart_tir_projected.png",
                                            "Distribuzione TIR Proiettata per Fase di Ottimizzazione")
    story.append(Image(img_proj, width=170*mm, height=85*mm))
    story.append(Spacer(1, 3*mm))

    # ── GMI projection ──
    story.append(PageBreak())
    story.append(Paragraph("6. Proiezione GMI (Equivalente HbA1c)", styles["SectionHead"]))
    img_gmi = make_gmi_projection_chart("_chart_gmi.png")
    story.append(Image(img_gmi, width=170*mm, height=68*mm))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "Il GMI (Glucose Management Indicator) e' una stima dell'HbA1c basata sulla glicemia media del sensore. "
        "Con l'ottimizzazione conservativa, si prevede un passaggio da <b>7.6% a 7.0%</b>, al target di 7%. "
        "L'approccio prudente e' necessario per rispettare il rischio ipoglicemico esistente.",
        styles["BodyIt"]))

    # ── Assumptions ──
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Ipotesi e Limitazioni delle Proiezioni", styles["SectionHead"]))
    assumptions = [
        "Le proiezioni sono stime conservative basate su studi clinici pubblicati (PubMed)",
        "Si assume che ogni modifica sia applicata per almeno 5-7 giorni prima della successiva",
        "Le stime di TBR (<70) includono un margine di sicurezza prudenziale",
        "I risultati reali possono variare in base a fattori individuali (attivita', malattia, stress)",
        "Le proiezioni per la dieta sono le piu' incerte e dipendono dall'aderenza",
    ]
    for a in assumptions:
        story.append(Paragraph(f"  - {a}", styles["BodyIt"]))

    # Disclaimer
    story.append(Paragraph(
        "NOTA: Questa analisi e' basata sui dati del microinfusore ed e' solo informativa. "
        "Ogni modifica alle impostazioni va concordata con il diabetologo/endocrinologo. "
        "Le proiezioni non sono garanzie di risultato.",
        styles["Disclaimer"]))

    doc.build(story)
    print(f"PDF generato: {path}")
    return path


def generate_instructions_pdf():
    """PDF 2: Istruzioni operative passo-passo."""
    path = os.path.join(BASE, "report_istruzioni.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_styles()
    story = []

    # ── Title ──
    story.append(Paragraph("Istruzioni per l'Ottimizzazione", styles["Title2"]))
    story.append(Paragraph("MiniMed 780G - Nuria Perez Diez (46 anni, 54 kg, T1D da 20 anni)", styles["Subtitle"]))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph(
        "Piano operativo: prima la dieta e la gestione sport, poi le impostazioni pompa. "
        "Vegetariana, osteoporosi, menopausa precoce. Insulina totale 12.8 U/giorno (0.24 U/kg). "
        "Da discutere e validare con il diabetologo.",
        styles["BodyIt"]))
    story.append(Spacer(1, 2*mm))

    story.append(Paragraph(
        "<b>Dato CareLink importante:</b> Con Target 100 (gen-feb 2025) il TIR era PEGGIORE (51%) "
        "rispetto al Target 120 (59% in lug-ago 2025). Il target a 120 e' corretto, NON abbassarlo.",
        styles["BodyIt"]))
    story.append(Spacer(1, 4*mm))

    # ── STEP 1: DIET ──
    story.append(Paragraph("PASSO 1: Cambiare Tipo di CHO + Pre-Bolo (Subito)", styles["SectionHead"]))
    step1 = [
        ["Cosa cambiare", "Attuale", "Nuovo"],
        ["Tipo CHO pranzo", "Variabile", "Basso IG: ceci, lenticchie,\npasta integrale, fagioli"],
        ["Timing bolo pranzo", "Insieme al pasto", "Pre-bolo 15-20 min\nPRIMA di mangiare"],
        ["Snack pre-sport", "Taralli (IG 65-70)", "Banana, fichi secchi,\nbarretta cereali (IG <55)"],
        ["Quantita' CHO pranzo", "~25g", "25g (invariata)\nIndicazione medica anti-chetosi"],
    ]
    story.append(make_table(step1, col_widths=[35*mm, 45*mm, 65*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Perche' e' il primo passo:</b> I dati mostrano picchi a 280-360 mg/dL dopo pranzo "
        "(16:00-16:59 = fascia iperglicemica piu' frequente: 12 casi/mese dal CareLink). "
        "I CHO a basso IG si assorbono in 2-3 ore invece di 20-30 minuti → picco piu' basso "
        "→ meno IOB alle 17 → meno crolli durante sport.", styles["BodyIt"]))
    story.append(Paragraph("<b>Effetto atteso:</b> TIR da 53.7% a ~58% (+4.3%). "
        "Questo passo da solo ha l'impatto piu' grande.", styles["BodyIt"]))

    story.append(Spacer(1, 6*mm))

    # ── STEP 2: SPORT PROTOCOL ──
    story.append(Paragraph("PASSO 2: Protocollo Sport (dopo 1 settimana col Passo 1)", styles["SectionHead"]))
    step2 = [
        ["Ora", "Azione", "Dettaglio"],
        ["15:00", "Temp Target ON", "SmartGuard > Target Temp. > Attivare\n"
         "Alza target a 150 → riduce basale e correzioni"],
        ["16:30", "Snack SENZA bolo", "SG<150: 20g CHO (banana)\n"
         "SG 150-250: 10-15g CHO\nSG>250: solo acqua"],
        ["16:50", "Controllo SG", "SG <100: NON fare sport, 20g CHO\nSG >100: OK staccare"],
        ["17:00", "Pompa OFF + sport", "Portare destrosio e succo"],
        ["~19:00", "Riconnetti + Temp OFF", "Se SG<100: 15g CHO prima di cena"],
    ]
    story.append(make_table(step2, col_widths=[18*mm, 35*mm, 95*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Perche':</b> Le ipo serali (ALERT ON LOW) sono causate da IOB + esercizio + pompa off, "
        "NON dalle impostazioni della pompa. Il Temp Target riduce l'insulina a bordo 2 ore prima "
        "dello sport. Lo snack senza bolo fornisce glucosio di sicurezza.", styles["BodyIt"]))
    story.append(Paragraph(
        "<b>Mattina Ma/Gi (sveglia 6:30, bici):</b> Temp Target ON solo se SG <130 alla sveglia. "
        "Colazione leggera (latte soia + caffe' + frutta, ~5g CHO, senza bolo) come gia' fai.", styles["BodyIt"]))
    story.append(Paragraph("<b>Effetto atteso:</b> TIR da ~58% a ~62% (+4%)", styles["BodyIt"]))

    story.append(Spacer(1, 6*mm))

    # ── STEP 3: AIT ──
    story.append(Paragraph("PASSO 3: Ridurre AIT (dopo 7 giorni dal Passo 2)", styles["SectionHead"]))
    step3 = [
        ["Parametro", "Valore Attuale", "Valore Suggerito", "Quando"],
        ["Tempo Insulina Attiva", "2h 30m", "2h 15m", "Settimana 3"],
    ]
    story.append(make_table(step3, col_widths=[40*mm, 35*mm, 35*mm, 35*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("<b>Perche':</b> Con AIT piu' corto, SmartGuard calcola meno IOB → "
        "puo' correggere piu' liberamente. Con il protocollo sport gia' in atto, "
        "il rischio di ipo da AIT ridotto e' minore.", styles["BodyIt"]))
    story.append(Paragraph("<b>Come:</b> Menu > Impostazioni Bolo > Tempo Insulina Attiva > 2:15", styles["BodyIt"]))
    story.append(Paragraph("<b>Effetto atteso:</b> TIR da ~62% a ~64% (+2%)", styles["BodyIt"]))

    story.append(PageBreak())

    # ── STEP 4: ICR CENA ──
    story.append(Paragraph("PASSO 4: ICR Cena (dopo 7 giorni dal Passo 3)", styles["SectionHead"]))
    step4 = [
        ["Parametro", "Valore Attuale", "Valore Suggerito", "Quando"],
        ["ICR Cena (18-23)", "9.7-10 g/U", "9 g/U", "Settimana 4"],
    ]
    story.append(make_table(step4, col_widths=[40*mm, 35*mm, 35*mm, 35*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Perche' ora e non prima:</b> Col protocollo sport gia' attivo, le ipo serali "
        "saranno ridotte. Quindi e' sicuro aumentare leggermente la copertura insulinica "
        "della cena (-10%). Cena vegetariana con 25-30g CHO (pane cereali + tofu/tempeh + verdure).", styles["BodyIt"]))
    story.append(Paragraph("<b>Come:</b> Menu > Impostazioni Bolo > Rapporto I/CHO > 18:00-23:00 > 9 g/U", styles["BodyIt"]))
    story.append(Paragraph("<b>Effetto atteso:</b> TIR da ~64% a ~66% (+2%)", styles["BodyIt"]))

    story.append(Spacer(1, 6*mm))

    # ── STEP 5 ──
    story.append(Paragraph("PASSO 5: Rivalutare ISF (SOLO dopo 4 settimane)", styles["SectionHead"]))
    step5 = [
        ["Parametro", "Valore Attuale", "Valore Suggerito", "Quando"],
        ["Sensibilita' Insulinica", "100 mg/dL/U", "90 mg/dL/U", "Settimana 5-6"],
    ]
    story.append(make_table(step5, col_widths=[40*mm, 35*mm, 35*mm, 35*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("<b>Prerequisiti:</b> Applicare SOLO se: (1) TBR <70 sotto 2%, "
        "(2) nessun episodio <54 mg/dL, (3) ALERT ON LOW <2/settimana.", styles["BodyIt"]))
    story.append(Paragraph("<b>Come:</b> Menu > Impostazioni Bolo > Sensibilita' > 90 mg/dL/U", styles["BodyIt"]))
    story.append(Paragraph("<b>Effetto atteso:</b> TIR da ~66% a ~68% (+2%)", styles["BodyIt"]))

    story.append(Spacer(1, 6*mm))

    # ── Summary table ──
    story.append(Paragraph("Riepilogo Completo (Dieta → Sport → Pompa)", styles["SectionHead"]))
    summary = [
        ["Passo", "Tipo", "Modifica", "Settimana", "TIR Atteso"],
        ["1", "DIETA", "CHO basso IG + pre-bolo 15 min", "1", "~58%"],
        ["2", "SPORT", "Temp Target + snack no bolo", "2", "~62%"],
        ["3", "POMPA", "AIT 2h30 → 2h15", "3", "~64%"],
        ["4", "POMPA", "ICR Cena 10 → 9", "4", "~66%"],
        ["5", "POMPA", "ISF 100 → 90 (se sicuro)", "5-6", "~68%"],
    ]
    story.append(make_table(summary, col_widths=[16*mm, 18*mm, 52*mm, 20*mm, 22*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>ICR Pranzo INVARIATO</b> (8.8-9 g/U): il bolo e' corretto per 25g CHO. "
        "Il problema e' il tipo di CHO e il timing, non la dose insulinica.", styles["BodyIt"]))

    story.append(Spacer(1, 6*mm))

    # ── Safety section ──
    story.append(Paragraph("Regole di Sicurezza", styles["SectionHead"]))
    safety = [
        "<b>FERMARSI</b> se TBR (<70 mg/dL) supera il 4% del tempo",
        "<b>FERMARSI</b> se gli ALERT ON LOW superano 3 al giorno",
        "<b>FERMARSI</b> se si verificano episodi di ipoglicemia severa (<54 mg/dL)",
        "<b>TORNARE INDIETRO</b> all'impostazione precedente se i limiti sopra vengono superati",
        "<b>NON</b> applicare piu' di una modifica pompa alla volta",
        "<b>NON</b> abbassare il Target SmartGuard sotto 120 (con 100 era peggiore)",
        "<b>NON</b> eliminare i carboidrati (indicazione medica anti-chetosi)",
        "<b>MAI</b> fare sport con SG <100 o senza CHO di emergenza",
    ]
    for s in safety:
        story.append(Paragraph(f"  - {s}", styles["BodyIt"]))

    story.append(Spacer(1, 6*mm))

    # ── Diet summary ──
    story.append(Paragraph("Riepilogo Alimentare (Vegetariana)", styles["SectionHead"]))
    diet_table = [
        ["Fascia", "CHO", "Consiglio"],
        ["Colazione", "~5g (no bolo)", "Latte soia + caffe' + poca frutta\nGia' OK come fai"],
        ["Pranzo", "25g (basso IG!)", "Pre-bolo 15 min! Ceci, lenticchie,\npasta integrale. NO pane bianco"],
        ["Snack sport", "15-20g (NO bolo!)", "Banana o fichi secchi\nNO taralli (IG troppo alto)"],
        ["Cena", "25-30g", "Tofu/tempeh + verdure + pane cereali\nFonte calcio per osteoporosi"],
        ["Notte", "0-10g solo se SG<120", "Solo se necessario per ipo"],
    ]
    story.append(make_table(diet_table, col_widths=[25*mm, 32*mm, 90*mm]))

    # Disclaimer
    story.append(Paragraph(
        "NOTA: Questo documento e' solo informativo. Ogni modifica alle impostazioni del microinfusore "
        "deve essere concordata con il diabetologo/endocrinologo. Non sostituisce il parere medico.",
        styles["Disclaimer"]))

    doc.build(story)
    print(f"PDF generato: {path}")
    return path


if __name__ == "__main__":
    print("Generazione grafici...")
    generate_projections_pdf()
    generate_instructions_pdf()
    print("Fatto!")
