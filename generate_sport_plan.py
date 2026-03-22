"""
PDF: Piano Gestione Sport e Diabete per Nuria Perez Diez
MiniMed 780G — Strategia esercizio fisico quotidiano
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

BASE = os.path.dirname(os.path.abspath(__file__))

C_BLUE    = HexColor("#2563EB")
C_GREEN   = HexColor("#16A34A")
C_RED     = HexColor("#DC2626")
C_ORANGE  = HexColor("#EA580C")
C_YELLOW  = HexColor("#CA8A04")
C_GRAY    = HexColor("#6B7280")
C_LIGHT   = HexColor("#F3F4F6")
C_WHITE   = white
C_DARK    = HexColor("#1F2937")
C_PURPLE  = HexColor("#7C3AED")


def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Title2", parent=styles["Title"], fontSize=20, textColor=C_BLUE,
                               spaceAfter=6*mm))
    styles.add(ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12, textColor=C_GRAY,
                               spaceAfter=4*mm, alignment=TA_CENTER))
    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=14, textColor=C_BLUE,
                               spaceBefore=6*mm, spaceAfter=3*mm))
    styles.add(ParagraphStyle("SubHead", parent=styles["Heading3"], fontSize=11, textColor=C_PURPLE,
                               spaceBefore=4*mm, spaceAfter=2*mm))
    styles.add(ParagraphStyle("BodyIt", parent=styles["Normal"], fontSize=10, textColor=C_DARK,
                               leading=14))
    styles.add(ParagraphStyle("BodyBold", parent=styles["Normal"], fontSize=10, textColor=C_DARK,
                               leading=14, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("Warning", parent=styles["Normal"], fontSize=10, textColor=C_RED,
                               leading=14, fontName="Helvetica-Bold", spaceBefore=2*mm))
    styles.add(ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8, textColor=C_GRAY,
                               leading=10, alignment=TA_CENTER, spaceBefore=8*mm))
    return styles


def make_table(data, col_widths=None, header=True):
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
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def make_warning_table(data, col_widths=None):
    t = Table(data, colWidths=col_widths)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_RED),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, HexColor("#FEF2F2")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def make_daily_timeline_chart(filename):
    """Visual timeline of a typical day with exercise."""
    fig, ax = plt.subplots(figsize=(11, 5.5))

    hours = np.arange(6, 24, 0.083)  # 5-min intervals
    # Simulated SG for a typical BAD day (current pattern)
    np.random.seed(42)
    # Morning: bike ride causes slight dip
    sg_bad = []
    t = 140
    for h in hours:
        if 6 <= h < 7: t += np.random.normal(-0.3, 0.5)  # wake up
        elif 7 <= h < 7.5: t += np.random.normal(-1.5, 0.5)  # bike ride, dip
        elif 7.5 <= h < 8: t += np.random.normal(-0.8, 0.3)
        elif 8 <= h < 10: t += np.random.normal(0.3, 0.3)
        elif 10 <= h < 13: t += np.random.normal(0.2, 0.4)
        elif 13 <= h < 13.5: t += np.random.normal(-0.5, 0.3)  # bolus
        elif 13.5 <= h < 14.5: t += np.random.normal(2.5, 0.5)  # carbs spike
        elif 14.5 <= h < 16: t += np.random.normal(1.5, 0.5)  # still rising
        elif 16 <= h < 17: t += np.random.normal(-0.5, 0.5)  # SG correcting
        elif 17 <= h < 17.3: t += np.random.normal(-3, 0.5)  # DISCONNECT + exercise
        elif 17.3 <= h < 18.5: t += np.random.normal(-4, 0.8)  # CRASH
        elif 18.5 <= h < 19.5: t += np.random.normal(1, 0.5)  # recovery + carbs
        elif 19.5 <= h < 21: t += np.random.normal(1.5, 0.4)  # dinner spike
        elif 21 <= h < 24: t += np.random.normal(0.3, 0.3)
        t = max(50, min(400, t))
        sg_bad.append(t)

    # Simulated SG for an OPTIMIZED day
    t = 130
    sg_good = []
    for h in hours:
        if 6 <= h < 7: t += np.random.normal(-0.1, 0.3)
        elif 7 <= h < 7.5: t += np.random.normal(-0.5, 0.3)  # bike, but temp target
        elif 7.5 <= h < 8: t += np.random.normal(0.2, 0.2)
        elif 8 <= h < 10: t += np.random.normal(0.2, 0.2)
        elif 10 <= h < 13: t += np.random.normal(0.1, 0.3)
        elif 13 <= h < 13.5: t += np.random.normal(-0.3, 0.2)
        elif 13.5 <= h < 14.5: t += np.random.normal(1.2, 0.4)  # slower carbs
        elif 14.5 <= h < 15.5: t += np.random.normal(0.5, 0.3)
        elif 15.5 <= h < 17: t += np.random.normal(-0.3, 0.3)  # temp target active
        elif 17 <= h < 17.5: t += np.random.normal(-1.0, 0.3)  # exercise, controlled
        elif 17.5 <= h < 19: t += np.random.normal(-0.5, 0.3)
        elif 19 <= h < 20: t += np.random.normal(0.5, 0.3)
        elif 20 <= h < 21.5: t += np.random.normal(0.8, 0.3)
        elif 21.5 <= h < 24: t += np.random.normal(-0.1, 0.2)
        t = max(60, min(350, t))
        sg_good.append(t)

    ax.plot(hours, sg_bad, color="#DC2626", linewidth=2, alpha=0.7, label="Giornata attuale (senza strategia)")
    ax.plot(hours, sg_good, color="#16A34A", linewidth=2, alpha=0.8, label="Giornata con strategia sport")

    # Target zone
    ax.axhspan(70, 180, alpha=0.08, color="#16A34A")
    ax.axhline(180, color="#F59E0B", linestyle="--", alpha=0.4, linewidth=1)
    ax.axhline(70, color="#DC2626", linestyle="--", alpha=0.4, linewidth=1)
    ax.text(23.5, 182, "180", fontsize=7, color="#F59E0B", va="bottom")
    ax.text(23.5, 68, "70", fontsize=7, color="#DC2626", va="top")

    # Event annotations
    events = [
        (7.0, "Bici\nscuola", "#7C3AED", 40),
        (8.0, "Scuola", "#6B7280", 25),
        (13.8, "Pranzo\n+ bolo", "#2563EB", 40),
        (15.0, "Temp\nTarget", "#16A34A", -45),
        (16.75, "Snack\nno bolo", "#EA580C", -45),
        (17.0, "Sport\n(pompa off)", "#DC2626", 50),
        (19.0, "Riconnetti", "#16A34A", -40),
        (19.5, "Cena", "#2563EB", 35),
    ]
    for x, txt, color, offset in events:
        ax.annotate(txt, xy=(x, 180), xytext=(x, 180 + offset),
                    fontsize=7, fontweight="bold", color=color,
                    ha="center", va="center",
                    arrowprops=dict(arrowstyle="-", color=color, alpha=0.3))

    # Exercise zone shading
    ax.axvspan(17, 19, alpha=0.08, color="#7C3AED")
    ax.text(18, 55, "SPORT", fontsize=9, ha="center", color="#7C3AED", fontweight="bold", alpha=0.6)
    ax.axvspan(7, 7.5, alpha=0.06, color="#7C3AED")

    ax.set_xlim(6, 24)
    ax.set_ylim(40, 380)
    ax.set_xticks(range(6, 24))
    ax.set_xticklabels([f"{h}:00" for h in range(6, 24)], fontsize=7, rotation=45)
    ax.set_ylabel("SG (mg/dL)", fontsize=10)
    ax.set_title("Giornata Tipo: Attuale vs. Con Strategia Sport", fontsize=13, fontweight="bold", pad=15)
    ax.legend(loc="upper left", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.2)

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_problem_diagram(filename):
    """Diagram showing the crash mechanism."""
    fig, ax = plt.subplots(figsize=(10, 3.5))

    # Timeline with SG from actual data (March 19, 2026)
    times = [13.75, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5, 17.0, 17.37, 17.5, 18.0, 18.25, 18.5]
    sg = [124, 136, 207, 284, 332, 358, 313, 264, 229, 214, 150, 99, 86]

    ax.plot(times, sg, "o-", color="#DC2626", linewidth=2.5, markersize=5)
    ax.fill_between(times, sg, 70, alpha=0.05, color="#DC2626")

    ax.axhspan(70, 180, alpha=0.08, color="#16A34A")
    ax.axhline(180, color="#F59E0B", linestyle="--", alpha=0.4)
    ax.axhline(70, color="#DC2626", linestyle="--", alpha=0.4)

    # Annotations
    ax.annotate("Pranzo\n24g CHO\n3.0U bolo", xy=(13.75, 124), xytext=(13.75, 50),
                fontsize=8, fontweight="bold", color="#2563EB", ha="center",
                arrowprops=dict(arrowstyle="->", color="#2563EB"))
    ax.annotate("Picco\n358!", xy=(16.15, 358), xytext=(16.5, 385),
                fontsize=8, fontweight="bold", color="#EA580C", ha="center",
                arrowprops=dict(arrowstyle="->", color="#EA580C"))
    ax.annotate("POMPA OFF\n+ bici casa", xy=(17.0, 264), xytext=(17.3, 390),
                fontsize=9, fontweight="bold", color="#DC2626", ha="center",
                arrowprops=dict(arrowstyle="->", color="#DC2626", lw=2))
    ax.annotate("CROLLO\n-178 mg/dL\nin 70 min!", xy=(18.0, 150), xytext=(18.5, 200),
                fontsize=8, fontweight="bold", color="#DC2626", ha="center",
                arrowprops=dict(arrowstyle="->", color="#DC2626"))
    ax.annotate("ALERT\nON LOW\n86!", xy=(18.5, 86), xytext=(18.8, 50),
                fontsize=8, fontweight="bold", color="#DC2626", ha="center",
                arrowprops=dict(arrowstyle="->", color="#DC2626"))

    # Exercise zone
    ax.axvspan(17, 19, alpha=0.1, color="#7C3AED")

    ax.set_xlim(13.5, 19)
    ax.set_ylim(30, 410)
    ax.set_xticks([14, 15, 16, 17, 18, 19])
    ax.set_xticklabels(["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"], fontsize=9)
    ax.set_ylabel("SG (mg/dL)")
    ax.set_title("Dati Reali 19 Marzo 2026: Il Meccanismo del Crollo", fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_sport_pdf():
    path = os.path.join(BASE, "report_piano_sport.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = get_styles()
    story = []

    # ── TITLE ──
    story.append(Paragraph("Piano Gestione Sport e Diabete", styles["Title2"]))
    story.append(Paragraph("MiniMed 780G - Nuria Perez Diez (46 anni, T1D da 20 anni) - Strategia Quotidiana", styles["Subtitle"]))
    story.append(Spacer(1, 3*mm))

    # ── ROUTINE ──
    # ── PATIENT PROFILE ──
    story.append(Paragraph("Profilo Paziente", styles["SectionHead"]))
    profile = [
        ["Dato", "Valore"],
        ["Nome", "Nuria Perez Diez"],
        ["Eta'", "46 anni"],
        ["Peso", "~54 kg"],
        ["Diagnosi T1D", "Da 20 anni"],
        ["Altre patologie", "Osteoporosi, menopausa precoce (da 4 anni)"],
        ["Microinfusore", "MiniMed 780G (MMT-1886) + Guardian 4"],
        ["Livello attivita'", "Molto sportiva (~2.5 ore/giorno)"],
    ]
    story.append(make_table(profile, col_widths=[35*mm, 115*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Nota su osteoporosi e menopausa precoce:</b> la menopausa precoce (dall'eta' di ~42 anni) "
        "e' un fattore di rischio importante per l'osteoporosi a causa della carenza estrogenica. "
        "L'attivita' fisica regolare e' molto benefica per la densita' ossea. "
        "Esercizi con impatto (corsa, salti) e con carico (pesi) sono i piu' efficaci. "
        "Assicurarsi di mantenere un adeguato apporto di calcio (1200 mg/giorno) e vitamina D.", styles["BodyIt"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Nota sul peso:</b> con 54 kg la sensibilita' insulinica e' generalmente alta, "
        "il che spiega perche' anche piccole dosi di insulina residua (IOB) combinate con "
        "l'esercizio possono causare crolli importanti della glicemia.", styles["BodyIt"]))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph("La Routine Quotidiana di Nuria", styles["SectionHead"]))
    routine = [
        ["Ora", "Attivita'", "Tipo esercizio", "Durata"],
        ["7:00-7:30", "Bici casa-scuola", "Aerobico moderato", "30 min"],
        ["8:00-13:00", "Scuola", "-", "-"],
        ["13:30-14:00", "Pranzo + bolo", "-", "-"],
        ["15:00-17:00", "Scuola / tempo libero", "-", "-"],
        ["17:00-17:30", "Bici scuola-casa", "Aerobico moderato", "30 min"],
        ["17:30-19:00", "Sport pomeridiano", "Intenso", "~90 min"],
        ["19:30", "Cena", "-", "-"],
    ]
    story.append(make_table(routine, col_widths=[25*mm, 42*mm, 38*mm, 22*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Totale esercizio giornaliero: ~2.5 ore</b> (30 min bici mattina + 30 min bici ritorno + "
        "~90 min sport). Questo e' un livello di attivita' fisica molto alto che influenza "
        "fortemente la sensibilita' insulinica per tutto il giorno.", styles["BodyIt"]))

    story.append(Spacer(1, 4*mm))

    # ── THE PROBLEM ──
    story.append(Paragraph("Il Problema: Perche' Succedono le Ipoglicemie", styles["SectionHead"]))

    img_crash = make_problem_diagram("_chart_crash.png")
    story.append(Image(img_crash, width=170*mm, height=60*mm))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("Il meccanismo (dati reali dal microinfusore):", styles["BodyBold"]))
    mechanism = [
        ["Fase", "Cosa succede", "Perche'"],
        ["1. Pranzo\n(13:50)",
         "24-25g CHO + bolo 2.5-3.0U\nICR 8-9 g/U, bolo corretto",
         "Il bolo e' calcolato giusto\nper i CHO ma..."],
        ["2. Post-pranzo\n(14:00-16:00)",
         "SG sale a 280-360 mg/dL\nnonostante il bolo corretto",
         "25g CHO si assorbono in 20-30 min\nL'insulina agisce in 60-90 min\n= sfasamento temporale"],
        ["3. Disconnessione\n(17:00)",
         "Pompa staccata per sport\nSG ancora 250-330",
         "Ci sono ancora 1-2U di insulina\nattiva dal pranzo (IOB)"],
        ["4. Sport\n(17:00-19:00)",
         "SG crolla da 300 a 70-86\nin 60-90 minuti!",
         "Esercizio RADDOPPIA la\nsensibilita' insulinica\n+ IOB residuo\n+ niente basale\n= crollo"],
    ]
    story.append(make_table(mechanism, col_widths=[28*mm, 60*mm, 60*mm]))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "<b>Punto chiave:</b> Il bolo del pranzo E' corretto per i carboidrati. "
        "Il problema non e' il calcolo ma il <b>timing</b>: l'insulina e' ancora attiva quando "
        "inizia lo sport, e l'esercizio ne amplifica l'effetto.", styles["BodyIt"]))

    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Le ipo del mattino (7:00-8:00):", styles["BodyBold"]))
    story.append(Paragraph(
        "Le ipo mattutine sono <b>rare</b>: nei dati di feb-mar 2026 si sono verificate solo "
        "3 volte in un mese (20, 22, 24 febbraio) con valori minimi di 55-66 mg/dL. "
        "SmartGuard gestisce gia' bene la basale notturna. Il Temp Target prima della bici "
        "e' comunque consigliato come precauzione nei giorni in cui SG e' sotto 120 alla sveglia.", styles["BodyIt"]))

    story.append(PageBreak())

    # ── THE SOLUTION ──
    story.append(Paragraph("La Strategia: Piano Giornaliero Completo", styles["SectionHead"]))

    img_timeline = make_daily_timeline_chart("_chart_timeline.png")
    story.append(Image(img_timeline, width=170*mm, height=85*mm))
    story.append(Spacer(1, 4*mm))

    # ── MORNING STRATEGY ──
    story.append(Paragraph("Mattina: Bici per Andare a Scuola", styles["SubHead"]))
    morning = [
        ["Ora", "Azione", "Dettaglio"],
        ["6:30\n(sveglia)",
         "Controllare SG",
         "Se SG <120: mangiare 10-15g CHO rapidi SENZA bolo\n"
         "Se SG 120-180: OK, partire\n"
         "Se SG >180: partire normalmente"],
        ["6:30",
         "Temp Target ON\n(solo se SG <130)",
         "SmartGuard > Target Temporaneo > Attivare\n"
         "Alza il target a 150 mg/dL e riduce la basale\n"
         "Nei giorni con SG >130 non serve"],
        ["6:45-7:00",
         "Colazione",
         "Latte di soia + caffe' (senza zucchero)\n"
         "Poca frutta (~5g CHO)\n"
         "Niente bolo (come gia' fai)"],
        ["7:00-7:30",
         "Bici verso scuola",
         "Colazione leggera = poco rischio ipo\n"
         "Portare comunque destrosio/succo in tasca"],
    ]
    story.append(make_table(morning, col_widths=[18*mm, 35*mm, 97*mm]))

    story.append(Spacer(1, 4*mm))

    # ── LUNCH STRATEGY ──
    story.append(Paragraph("Pranzo: La Chiave per Evitare il Crollo Pomeridiano", styles["SubHead"]))
    story.append(Paragraph(
        "<b>Indicazione medica:</b> la dottoressa richiede l'assunzione di carboidrati "
        "per evitare la chetosi. I CHO NON vanno eliminati ma gestiti nel modo giusto.", styles["Warning"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "Il pranzo e' il momento piu' critico perche' determina quanta insulina sara' attiva "
        "quando inizia lo sport 3 ore dopo. Con 25g CHO attuali, la strategia e' migliorare "
        "il TIPO e il TIMING, non ridurre la quantita'.", styles["BodyIt"]))
    story.append(Spacer(1, 2*mm))

    lunch = [
        ["Strategia", "Come fare", "Perche'"],
        ["1. PRE-BOLO\n15-20 minuti prima",
         "Dare il bolo 15-20 min PRIMA\ndi iniziare a mangiare",
         "L'insulina inizia ad agire prima\n= il picco post-pranzo e' piu' basso\n"
         "= meno insulina residua alle 17"],
        ["2. CHO A BASSO\nINDICE GLICEMICO",
         "Pasta integrale, riso basmati,\nlegumi, pane integrale\nEvitare: pane bianco, riso\nbianco, patate, succhi",
         "CHO lenti si assorbono in 2-3 ore\n"
         "invece di 20-30 minuti\n= picco piu' basso, energia piu' lunga\n"
         "= meno insulina residua alle 17"],
        ["3. DIVIDERE I CHO\n(opzione)",
         "Con 25g totali, opzione:\n"
         "18g a pranzo (basso IG) + 7g pre-sport\n"
         "Oppure: 25g a pranzo + snack\n"
         "extra 10-15g alle 16:30 senza bolo",
         "Meno CHO a pranzo = meno bolo\n= meno IOB alle 17\n"
         "CHO pre-sport = benzina per lo sport"],
        ["4. ICR PRANZO\nINVARIATO",
         "NON ridurre l'ICR del pranzo\nIl bolo e' corretto per i CHO\nmangiati",
         "Il problema non e' il rapporto\nma il timing e il tipo di CHO"],
    ]
    story.append(make_table(lunch, col_widths=[30*mm, 55*mm, 63*mm]))

    story.append(PageBreak())

    # ── PRE-EXERCISE STRATEGY ──
    story.append(Paragraph("Pomeriggio: Preparazione allo Sport", styles["SubHead"]))
    pre_ex = [
        ["Ora", "Azione", "Dettaglio"],
        ["15:00\n(2h prima)",
         "Attivare Temp Target",
         "SmartGuard > Target Temporaneo > Attivare\n"
         "Il sistema alza il target a 150 mg/dL\n"
         "SmartGuard riduce la basale e trattiene le correzioni\n"
         "Questo riduce l'insulina a bordo (IOB) prima dello sport"],
        ["16:30\n(30 min prima)",
         "Snack pre-sport\nSENZA BOLO",
         "15-20g CHO rapidi (succo, banana, barretta)\n"
         "NON dare bolo per questo snack!\n"
         "Se SG <150: dare 20-25g CHO\n"
         "Se SG 150-250: dare 10-15g CHO\n"
         "Se SG >250: non dare CHO, solo acqua"],
        ["16:50",
         "Controllare SG\nprima di staccare",
         "SG <100: NON fare sport, mangiare 20g CHO, aspettare\n"
         "SG 100-150: OK ma portare CHO extra\n"
         "SG 150-250: ideale per iniziare\n"
         "SG >250: OK staccare, lo sport lo abbassera'"],
        ["17:00",
         "Disconnettere pompa\nInizio bici + sport",
         "Portare SEMPRE: destrosio, succo, glucometro\n"
         "Se possibile, tenere il sensore attivo\n"
         "per monitorare SG durante lo sport"],
    ]
    story.append(make_table(pre_ex, col_widths=[22*mm, 35*mm, 93*mm]))

    story.append(Spacer(1, 4*mm))

    # ── DURING EXERCISE ──
    story.append(Paragraph("Durante lo Sport", styles["SubHead"]))
    during = [
        ["Situazione", "Azione"],
        ["SG scende sotto 100 durante sport", "Fermarsi, mangiare 15g CHO rapidi, aspettare 15 min"],
        ["SG scende sotto 70", "Fermarsi SUBITO, 20g CHO rapidi, non riprendere\nfinche' SG >100"],
        ["Sintomi di ipo (tremore, sudore freddo,\nconfusione)", "Fermarsi, 20g CHO, riposare, NON riprendere sport"],
        ["SG stabile 100-180 durante sport", "Perfetto! Continuare"],
        ["SG sale sopra 250 durante sport", "OK, l'esercizio lo abbassera'. Continuare"],
    ]
    story.append(make_table(during, col_widths=[55*mm, 95*mm]))

    story.append(Spacer(1, 4*mm))

    # ── POST-EXERCISE ──
    story.append(Paragraph("Dopo lo Sport: Riconnessione e Cena", styles["SubHead"]))
    post = [
        ["Ora", "Azione", "Dettaglio"],
        ["Fine sport\n(~19:00)",
         "Riconnettere la pompa\nSUBITO",
         "Non restare sconnesso! SmartGuard\ndeve riprendere a gestire la basale"],
        ["",
         "Disattivare Temp Target",
         "Se ancora attivo, disattivarlo\nper tornare al target normale (120)"],
        ["",
         "Controllare SG",
         "Se SG <100: 15g CHO prima di cena\n"
         "Se SG 100-150: cena normale\n"
         "Se SG >180: cena normale con bolo"],
        ["19:30",
         "Cena",
         "ICR cena: 9 g/U (come da piano)\n"
         "Pre-bolo 10-15 min se SG >150\n"
         "Attenzione: la sensibilita' post-sport\nresta alta per 12-24h!"],
    ]
    story.append(make_table(post, col_widths=[22*mm, 35*mm, 93*mm]))

    story.append(PageBreak())

    # ── COMPLETE DAILY PLAN ──
    story.append(Paragraph("Schema Giornata Completa", styles["SectionHead"]))

    full_day = [
        ["Ora", "Azione", "Pompa", "CHO", "Bolo"],
        ["6:30", "Sveglia + SG check\nTemp Target solo se SG<130", "ON", "Se SG<120:\n10-15g senza bolo", "-"],
        ["6:45", "Colazione\nLatte soia + caffe'\npoca frutta", "ON", "~5g\n(no bolo)", "-"],
        ["7:00", "Bici scuola (30 min)", "ON", "-", "-"],
        ["7:30", "Arrivo scuola", "ON\n(Target 120)", "-", "-"],
        ["13:40", "PRE-BOLO pranzo\n(15-20 min prima)", "ON", "-", "Si'\n(ICR 8-9)"],
        ["14:00", "Pranzo", "ON", "25g\nBasso IG!", "-"],
        ["15:00", "Temp Target ON", "ON\n(Target 150)", "-", "-"],
        ["16:30", "Snack pre-sport", "ON", "10-20g\n(vedi tabella SG)", "NO!"],
        ["16:50", "Controllo SG", "ON", "Extra se <150", "-"],
        ["17:00", "Disconnetti + bici\n+ sport", "OFF", "Durante sport\nse SG<100", "-"],
        ["~19:00", "Fine sport\nRiconnetti + Temp OFF", "ON\n(Target 120)", "-", "-"],
        ["19:30", "Cena", "ON", "25-30g\n(min. per no chetosi)", "Si'\n(ICR 9)"],
        ["22:00", "Spuntino notte (se serve)", "ON", "Solo se SG<120\n5-10g", "NO!"],
    ]
    story.append(make_table(full_day, col_widths=[16*mm, 38*mm, 25*mm, 32*mm, 20*mm]))

    story.append(Spacer(1, 4*mm))

    # ── SNACK DECISION TABLE ──
    story.append(Paragraph("Tabella Decisionale: Snack Pre-Sport (ore 16:30)", styles["SubHead"]))
    snack_table = [
        ["SG alle 16:30", "CHO da dare", "Tipo", "Bolo?"],
        ["< 100 mg/dL", "NON FARE SPORT\nMangiare 20g, aspettare", "Destrosio, succo", "NO"],
        ["100-150 mg/dL", "20-25g CHO", "Banana + succo", "NO"],
        ["150-200 mg/dL", "15g CHO", "Mezza banana o barretta", "NO"],
        ["200-250 mg/dL", "10g CHO", "Piccolo snack", "NO"],
        ["> 250 mg/dL", "0g CHO", "Solo acqua", "NO"],
    ]
    story.append(make_warning_table(snack_table, col_widths=[30*mm, 40*mm, 40*mm, 20*mm]))

    story.append(Spacer(1, 4*mm))

    # ── WHAT TO CARRY ──
    story.append(Paragraph("Kit Sport Obbligatorio", styles["SubHead"]))
    kit = [
        "Destrosio o zollette di zucchero (almeno 30g)",
        "Succo di frutta (brick piccolo)",
        "Glucometro portatile (o telefono con app sensore)",
        "Acqua",
        "Pompa pronta per riconnessione rapida",
    ]
    for k in kit:
        story.append(Paragraph(f"  - {k}", styles["BodyIt"]))

    story.append(Spacer(1, 4*mm))

    # ── FOOD GUIDE ──
    story.append(Paragraph("Guida Alimentare: CHO Lenti vs Veloci", styles["SectionHead"]))
    food = [
        ["CHO LENTI (pranzo)", "CHO VELOCI (pre-sport / emergenza)"],
        ["Pasta integrale", "Succo di frutta"],
        ["Riso basmati / integrale", "Banana matura"],
        ["Pane integrale / segale", "Destrosio / zollette zucchero"],
        ["Legumi (lenticchie, ceci, fagioli)", "Miele / marmellata"],
        ["Avena / cereali integrali", "Crackers / fette biscottate"],
        ["Patate dolci", "Pane bianco"],
        ["Verdure + proteine", "Barretta di cereali"],
    ]
    story.append(make_table(food, col_widths=[75*mm, 75*mm]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Per il pranzo usare SEMPRE i CHO lenti</b> (colonna sinistra). "
        "Questi si assorbono in 2-3 ore invece di 20-30 minuti, danno energia piu' lunga "
        "e causano un picco glicemico piu' basso. I CHO veloci sono solo per lo snack "
        "pre-sport e per le emergenze ipo.", styles["BodyIt"]))

    story.append(PageBreak())

    # ── PUMP SETTINGS ──
    story.append(Paragraph("Impostazioni Pompa Raccomandate (con strategia sport)", styles["SectionHead"]))
    settings = [
        ["Parametro", "Valore Attuale", "Raccomandazione", "Note"],
        ["ICR Colazione\n(6-10)", "11-14 g/U", "Invariato", "Funziona bene"],
        ["ICR Pranzo\n(10-15)", "8.8-9 g/U", "Invariato", "Il bolo e' corretto.\nUsare pre-bolo + CHO lenti"],
        ["ICR Merenda\n(15-18)", "9.2-9.4 g/U", "Invariato", "Lo snack pre-sport\nva dato SENZA bolo"],
        ["ICR Cena\n(18-23)", "9.7-10 g/U", "9 g/U (-10%)", "Unica modifica ICR.\nLa cena e' post-sport"],
        ["ISF", "100 mg/dL/U", "100 (invariato)", "Rimandare a dopo\nimplementazione sport"],
        ["AIT", "2h 30m", "2h 15m", "Meno IOB alle 17\n= crollo meno severo"],
        ["Target SmartGuard", "120 mg/dL", "120 (invariato)", "Il Temp Target a 150\nsi usa prima dello sport"],
    ]
    story.append(make_table(settings, col_widths=[28*mm, 28*mm, 28*mm, 52*mm]))

    story.append(Spacer(1, 4*mm))

    # ── EXPECTED RESULTS ──
    story.append(Paragraph("Risultati Attesi con la Strategia Sport", styles["SectionHead"]))
    results = [
        ["Indicatore", "Attuale", "Atteso (4-6 settimane)", "Come"],
        ["TIR (70-180)", "53.7%", "60-65%", "Meno crolli serali\n+ CHO lenti a pranzo"],
        ["TAR (>180)", "46.1%", "32-37%", "Pre-bolo riduce il picco\npost-pranzo"],
        ["TBR (<70)", "0.2%", "<1%", "Temp Target + snack\nprevengono le ipo"],
        ["ALERT ON LOW", "0.5/giorno", "<0.2/giorno", "Meno crolli = meno alert"],
        ["Ipo mattutine", "SG 55-69\n3 episodi/mese", "0-1/mese", "Temp Target se SG<130\n+ CHO se SG<120"],
        ["Ipo serali", "3-4 episodi/mese", "0-1/mese", "Strategia pre-sport\nelimina il meccanismo"],
    ]
    story.append(make_table(results, col_widths=[30*mm, 28*mm, 36*mm, 45*mm]))

    story.append(Spacer(1, 6*mm))

    # ── SAFETY ──
    story.append(Paragraph("Regole di Sicurezza Sport", styles["SectionHead"]))
    safety = [
        "<b>MAI fare sport se SG <100 mg/dL</b>",
        "<b>MAI fare sport senza CHO di emergenza</b> (destrosio, succo)",
        "<b>MAI restare sconnesso dopo lo sport</b> — riconnettere subito",
        "Se durante lo sport SG <70: FERMARSI, 20g CHO, non riprendere",
        "Se dopo lo sport SG <80: 15g CHO prima di cena",
        "Se si sospende la pompa con SG alto (>250), ricordare che l'insulina attiva\n"
        "  fara' scendere comunque il SG — NON e' necessario dare CHO extra",
        "Lo sport aumenta la sensibilita' insulinica per 12-24 ore: il giorno dopo\n"
        "  la glicemia puo' essere piu' bassa del solito",
        "<b>MAI eliminare i carboidrati dalla dieta</b> — indicazione medica per evitare la chetosi.\n"
        "  I CHO vanno distribuiti meglio, non tolti (min. 25-30g/pasto principale)",
    ]
    for s in safety:
        story.append(Paragraph(f"  - {s}", styles["BodyIt"]))

    # ── DISCLAIMER ──
    story.append(Paragraph(
        "NOTA: Questo piano e' basato sull'analisi dei dati del microinfusore e sulla letteratura clinica. "
        "Ogni modifica va concordata con il diabetologo/endocrinologo. Non sostituisce il parere medico. "
        "I risultati attesi sono stime e possono variare.",
        styles["Disclaimer"]))

    doc.build(story)
    print(f"PDF generato: {path}")
    return path


if __name__ == "__main__":
    generate_sport_pdf()
