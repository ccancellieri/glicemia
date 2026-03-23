"""
PDF: Piano Alimentare e Gestione Completa
T1D + MiniMed 780G
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
C_TEAL    = HexColor("#0D9488")


def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Title2", parent=styles["Title"], fontSize=18, textColor=C_BLUE,
                               spaceAfter=4*mm))
    styles.add(ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=11, textColor=C_GRAY,
                               spaceAfter=3*mm, alignment=TA_CENTER))
    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=13, textColor=C_BLUE,
                               spaceBefore=5*mm, spaceAfter=2*mm))
    styles.add(ParagraphStyle("SubHead", parent=styles["Heading3"], fontSize=11, textColor=C_PURPLE,
                               spaceBefore=3*mm, spaceAfter=2*mm))
    styles.add(ParagraphStyle("SubHead2", parent=styles["Heading3"], fontSize=11, textColor=C_TEAL,
                               spaceBefore=3*mm, spaceAfter=2*mm))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, textColor=C_DARK,
                               leading=13))
    styles.add(ParagraphStyle("BodyBold", parent=styles["Normal"], fontSize=9, textColor=C_DARK,
                               leading=13, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("Warning", parent=styles["Normal"], fontSize=9, textColor=C_RED,
                               leading=13, fontName="Helvetica-Bold", spaceBefore=2*mm))
    styles.add(ParagraphStyle("Tip", parent=styles["Normal"], fontSize=9, textColor=C_GREEN,
                               leading=13, fontName="Helvetica-Bold", spaceBefore=1*mm))
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=C_GRAY,
                               leading=10))
    styles.add(ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8, textColor=C_GRAY,
                               leading=10, alignment=TA_CENTER, spaceBefore=6*mm))
    return styles


def make_table(data, col_widths=None, header=True, header_color=C_BLUE):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def make_timeline_chart(filename):
    """Two-row timeline: Tue/Thu vs Other days."""
    fig, axes = plt.subplots(2, 1, figsize=(11, 4.5), sharex=True)

    for ax, (title, wake, bike_am, school_start) in zip(axes, [
        ("Martedi' / Giovedi' (sveglia 6:30)", 6.5, True, 8.0),
        ("Altri giorni (sveglia ~9:00)", 9.0, False, None),
    ]):
        ax.set_xlim(6, 23)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.set_title(title, fontsize=10, fontweight="bold", loc="left", pad=8)

        # Color blocks
        blocks = []
        if bike_am:
            blocks += [
                (wake, wake+0.25, "#F3F4F6", "Colaz."),
                (wake+0.25, wake+0.75, "#7C3AED", "Bici"),
                (school_start, 13.5, "#93C5FD", "Lavoro/Scuola"),
            ]
        else:
            blocks += [
                (wake, wake+0.5, "#F3F4F6", "Colazione"),
                (wake+0.5, 13.5, "#93C5FD", "Mattina libera"),
            ]

        blocks += [
            (13.5, 14.0, "#2563EB", "Pranzo"),
            (14.0, 15.0, "#DBEAFE", "Riposo"),
            (15.0, 15.5, "#16A34A", "Temp\nTarget ON"),
            (16.5, 17.0, "#EA580C", "Snack"),
            (17.0, 19.0, "#7C3AED", "Bici+Sport"),
            (19.0, 19.5, "#16A34A", "Riconnetti"),
            (19.5, 20.5, "#2563EB", "Cena"),
            (21.0, 22.0, "#F3F4F6", "Spuntino?"),
        ]

        for start, end, color, label in blocks:
            ax.barh(0.5, end-start, left=start, height=0.6, color=color, alpha=0.7, edgecolor="white")
            cx = (start + end) / 2
            fontsize = 6.5 if len(label) < 10 else 5.5
            ax.text(cx, 0.5, label, ha="center", va="center", fontsize=fontsize, fontweight="bold", color="white" if color not in ("#F3F4F6", "#DBEAFE", "#93C5FD") else "#1F2937")

        ax.set_xticks(range(6, 24))
        ax.set_xticklabels([f"{h}:00" for h in range(6, 24)], fontsize=7, rotation=45)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)

    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_crash_mechanism_chart(filename):
    """Show the IOB + exercise crash mechanism with real data."""
    fig, ax = plt.subplots(figsize=(10, 3.2))

    times = [13.5, 13.75, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5, 17.0, 17.5, 18.0, 18.5]
    sg = [130, 124, 136, 207, 284, 332, 358, 313, 264, 214, 150, 86]

    ax.plot(times, sg, "o-", color="#DC2626", linewidth=2.5, markersize=5)
    ax.fill_between(times, sg, 70, alpha=0.05, color="#DC2626")
    ax.axhspan(70, 180, alpha=0.08, color="#16A34A")
    ax.axhline(180, color="#F59E0B", linestyle="--", alpha=0.4)
    ax.axhline(70, color="#DC2626", linestyle="--", alpha=0.4)

    ax.annotate("Pre-bolo\n+ 25g CHO", xy=(13.5, 130), xytext=(13.2, 60),
                fontsize=7, fontweight="bold", color="#2563EB", ha="center",
                arrowprops=dict(arrowstyle="->", color="#2563EB"))
    ax.annotate("Picco 358!\nCHO veloci\nassorbiti", xy=(16.15, 358), xytext=(15.5, 390),
                fontsize=7, fontweight="bold", color="#EA580C", ha="center",
                arrowprops=dict(arrowstyle="->", color="#EA580C"))
    ax.annotate("POMPA OFF\n+ Sport", xy=(17.0, 264), xytext=(17.5, 380),
                fontsize=8, fontweight="bold", color="#DC2626", ha="center",
                arrowprops=dict(arrowstyle="->", color="#DC2626", lw=2))
    ax.annotate("CROLLO\n86 mg/dL!", xy=(18.5, 86), xytext=(18.5, 45),
                fontsize=8, fontweight="bold", color="#DC2626", ha="center",
                arrowprops=dict(arrowstyle="->", color="#DC2626"))

    ax.axvspan(17, 19, alpha=0.1, color="#7C3AED")
    ax.text(18, 395, "SPORT (pompa off)", fontsize=8, ha="center", color="#7C3AED", fontweight="bold")

    ax.set_xlim(13.2, 19)
    ax.set_ylim(30, 420)
    ax.set_xticks([13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5, 18, 18.5])
    ax.set_xticklabels(["13:30","14:00","14:30","15:00","15:30","16:00","16:30","17:00","17:30","18:00","18:30"], fontsize=7, rotation=45)
    ax.set_ylabel("SG (mg/dL)", fontsize=9)
    ax.set_title("Dati Reali 19 Marzo 2026: Il Meccanismo del Crollo Pomeridiano", fontsize=10, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def make_solution_chart(filename):
    """Show the same afternoon with optimized strategy."""
    fig, ax = plt.subplots(figsize=(10, 3.2))

    # CURRENT (bad)
    times_bad = [13.2, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5, 17.0, 17.5, 18.0, 18.5]
    sg_bad =    [135,  130,  136,  207,  284,  332,  358,  313,  264,  214,  150,  86]

    # OPTIMIZED: pre-bolus 15min before + low GI carbs + Temp Target + snack no bolus
    times_good = [13.2, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5, 17.0, 17.5, 18.0, 18.5]
    sg_good =    [135,  125,  118,  155,  185,  195,  190,  180,  175,  155,  140,  125]

    ax.plot(times_bad, sg_bad, "o-", color="#DC2626", linewidth=2, markersize=4, alpha=0.5, label="Attuale (CHO rapidi, no pre-bolo)")
    ax.plot(times_good, sg_good, "o-", color="#16A34A", linewidth=2.5, markersize=5, label="Con strategia (CHO lenti + pre-bolo)")

    ax.axhspan(70, 180, alpha=0.08, color="#16A34A")
    ax.axhline(180, color="#F59E0B", linestyle="--", alpha=0.4)
    ax.axhline(70, color="#DC2626", linestyle="--", alpha=0.4)
    ax.axvspan(17, 19, alpha=0.08, color="#7C3AED")

    ax.annotate("Pre-bolo\n15 min prima\n+ CHO lenti", xy=(13.2, 135), xytext=(13.0, 60),
                fontsize=7, fontweight="bold", color="#16A34A", ha="center",
                arrowprops=dict(arrowstyle="->", color="#16A34A"))
    ax.annotate("Temp Target\nON h15", xy=(15, 195), xytext=(15.2, 250),
                fontsize=7, fontweight="bold", color="#16A34A", ha="center",
                arrowprops=dict(arrowstyle="->", color="#16A34A"))
    ax.annotate("Snack\nno bolo", xy=(16.5, 180), xytext=(16.3, 245),
                fontsize=7, fontweight="bold", color="#EA580C", ha="center",
                arrowprops=dict(arrowstyle="->", color="#EA580C"))

    ax.set_xlim(13, 19)
    ax.set_ylim(30, 300)
    ax.set_xticks([13, 13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5, 18, 18.5])
    ax.set_xticklabels(["13:00","13:30","14:00","14:30","15:00","15:30","16:00","16:30","17:00","17:30","18:00","18:30"], fontsize=7, rotation=45)
    ax.set_ylabel("SG (mg/dL)", fontsize=9)
    ax.set_title("Confronto: Pomeriggio Attuale vs. Con Strategia Alimentare", fontsize=10, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    path = os.path.join(BASE, filename)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_diet_pdf():
    path = os.path.join(BASE, "report_piano_completo.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=12*mm, bottomMargin=12*mm)
    styles = get_styles()
    story = []
    W = 180*mm  # usable width

    # ═══════════════════════════════════════════
    # PAGE 1: PROFILO + COSA SUCCEDE
    # ═══════════════════════════════════════════
    story.append(Paragraph("Piano Alimentare e Gestione Completa", styles["Title2"]))
    story.append(Paragraph("T1D Patient — MiniMed 780G", styles["Subtitle"]))

    # Profile
    story.append(Paragraph("Profilo", styles["SectionHead"]))
    profile = [
        ["Dato", "Valore"],
        ["Eta' / Peso", "—"],
        ["Diagnosi", "T1D"],
        ["Altre condizioni", "—"],
        ["Alimentazione", "—"],
        ["Microinfusore", "MiniMed 780G + Guardian 4 Sensor"],
        ["Attivita' fisica", "—"],
        ["Sveglia", "—"],
    ]
    story.append(make_table(profile, col_widths=[35*mm, W-35*mm]))

    story.append(Spacer(1, 4*mm))

    # ── SECTION 1: COSA SUCCEDE ──
    story.append(Paragraph("1. Cosa Succede Oggi e Cosa Cambiera'", styles["SectionHead"]))
    story.append(Paragraph("Analisi dei dati del microinfusore (3 periodi a confronto):", styles["BodyBold"]))

    current = [
        ["Indicatore", "Gen-Feb 2025\n(Target 100)", "Lug-Ago 2025\n(Target 120)", "Feb-Mar 2026\n(Target 120)", "Obiettivo"],
        ["TIR (70-180)", "51%", "59%", "53.7%", ">70%"],
        ["TAR (>180)", "48%", "35%", "46.1%", "<25%"],
        ["TBR (<70)", "1%", "1%", "0.2%", "<4%"],
        ["Media SG", "180±49", "172±47", "177", "<155"],
        ["GMI / ICG", "7.6%", "7.4%", "7.5%", "<7.0%"],
        ["CV", "27.3%", "27.0%", "35%", "<36%"],
        ["Insulina tot./giorno", "15.6U", "12.8U", "-", "-"],
        ["Autocorrezioni", "63%", "43%", "-", "-"],
    ]
    story.append(make_table(current, col_widths=[28*mm, 28*mm, 28*mm, 28*mm, 18*mm]))

    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Dato chiave:</b> con Target 100 (gen-feb 2025) il TIR era PEGGIORE (51%) rispetto "
        "al Target 120 (59% in lug-ago). Abbassare il target non serve — SmartGuard diventa "
        "piu' aggressivo con le correzioni e poi arrivano i crolli. Il target a 120 e' corretto.", styles["Body"]))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "<b>Insulina totale: 12.8-15.6 U/giorno = 0.24-0.29 U/kg</b> — molto bassa per una T1D. "
        "Conferma una sensibilita' insulinica altissima dovuta a sport quotidiano "
        "e 20 anni di T1D con buon controllo. Piccole dosi di IOB hanno effetti importanti.", styles["Body"]))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "<b>Pattern iperglicemici dal CareLink:</b> il picco piu' frequente e' alle 16:00-16:59 "
        "(12 casi/mese) — esattamente prima dello stacco per lo sport. "
        "I secondi picchi sono alle 11:00-12:59 (18 casi) — probabilmente assorbimento tardivo "
        "della colazione o snack mattutino.", styles["Body"]))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("Il problema principale: il pomeriggio", styles["SubHead"]))
    img_crash = make_crash_mechanism_chart("_chart_crash2.png")
    story.append(Image(img_crash, width=170*mm, height=53*mm))
    story.append(Spacer(1, 2*mm))

    story.append(Paragraph(
        "<b>Il meccanismo:</b> A pranzo mangi ~25g CHO (pasta, ceci) e fai il bolo corretto. "
        "Ma i carboidrati si assorbono in 20-30 minuti mentre l'insulina agisce in 60-90 minuti. "
        "Risultato: picco a 280-360, poi alle 17 disconnetti la pompa per sport con ancora "
        "insulina attiva (IOB). L'esercizio raddoppia la sensibilita' insulinica → "
        "<b>crollo a 70-86 mg/dL</b>.", styles["Body"]))
    story.append(Spacer(1, 2*mm))

    story.append(Paragraph("La soluzione: cambiare TIPO e TIMING, non la quantita'", styles["SubHead"]))
    img_solution = make_solution_chart("_chart_solution.png")
    story.append(Image(img_solution, width=170*mm, height=53*mm))
    story.append(Spacer(1, 2*mm))

    story.append(Paragraph(
        "<b>Cosa cambiera':</b> Con carboidrati a basso indice glicemico (IG), pre-bolo 15 min "
        "prima di mangiare, Temp Target alle 15:00, e snack pre-sport senza bolo, "
        "il picco post-pranzo scende da 360 a ~195 mg/dL e il crollo durante lo sport "
        "non avviene piu'. TIR atteso: <b>65-70%</b> (da 54%).", styles["Body"]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # PAGE 2-3: DIETA SETTIMANALE
    # ═══════════════════════════════════════════
    story.append(Paragraph("2. Piano Alimentare Settimanale", styles["SectionHead"]))

    story.append(Paragraph(
        "<b>Principi guida:</b> T1D. "
        "I carboidrati NON vanno eliminati (indicazione medica anti-chetosi). "
        "Privilegiare CHO a basso IG, proteine ricche di calcio, "
        "alimenti con vitamina D.", styles["Body"]))
    story.append(Spacer(1, 2*mm))

    # Nutrient targets
    story.append(Paragraph("Obiettivi nutrizionali giornalieri", styles["SubHead2"]))
    targets = [
        ["Nutriente", "Obiettivo/giorno", "Perche'"],
        ["Carboidrati", "100-130g totali", "Anti-chetosi + energia sport"],
        ["Proteine", "55-65g (1.0-1.2 g/kg)", "Ossa + muscoli + recupero sport"],
        ["Calcio", "1200 mg", "Salute ossea"],
        ["Vitamina D", "800-1000 UI", "Assorbimento calcio + ossa"],
        ["Ferro", "18 mg", "Sport + depositi da mantenere"],
        ["Magnesio", "320 mg", "Sensibilita' insulinica + ossa + muscoli"],
        ["Omega-3 (ALA)", "1.5-2g", "Infiammazione + cardiovascolare"],
    ]
    story.append(make_table(targets, col_widths=[25*mm, 30*mm, W-55*mm], header_color=C_TEAL))
    story.append(Spacer(1, 3*mm))

    # ── FOOD REFERENCE TABLE ──
    story.append(Paragraph("Tabella di riferimento: CHO, calcio e IG degli alimenti chiave", styles["SubHead2"]))
    food_ref = [
        ["Alimento", "Porzione", "CHO (g)", "Calcio (mg)", "IG", "Note"],
        ["Pasta integrale", "80g cruda", "56", "20", "40-45", "Basso IG, ottimo pranzo"],
        ["Ceci cotti", "150g", "27", "60", "28-35", "Basso IG + proteine + ferro"],
        ["Lenticchie cotte", "150g", "25", "25", "25-30", "IG piu' basso dei legumi"],
        ["Fagioli cannellini", "150g", "25", "50", "30", "Proteine + fibra"],
        ["Riso basmati integr.", "70g crudo", "54", "15", "50", "IG medio, meglio della pasta bianca"],
        ["Pane ai cereali", "30g", "14", "10", "45", "OK per cena"],
        ["Pane ai cereali", "60g", "28", "20", "45", "Porzione piena"],
        ["Taralli", "30g (~4-5)", "21", "8", "65-70", "IG alto! Solo emergenza pre-sport"],
        ["Tofu", "100g", "2", "350", "-", "Eccellente per calcio!"],
        ["Tempeh", "100g", "9", "110", "-", "Proteine + calcio + probiotici"],
        ["Latte di soia fort.", "250ml", "5", "300", "-", "Gia' nella colazione"],
        ["Yogurt soia fort.", "125g", "8", "150", "-", "Spuntino con calcio"],
        ["Semi di sesamo", "15g", "2", "140", "-", "Da aggiungere su tutto!"],
        ["Semi di lino", "10g", "1", "25", "-", "Omega-3 + fitoestrogenici"],
        ["Mandorle", "30g", "5", "75", "-", "Calcio + magnesio"],
        ["Fichi secchi", "30g (3 pz)", "16", "50", "55", "Calcio + ferro"],
        ["Broccoli", "200g cotti", "6", "90", "-", "Calcio + vit K + anti-cancro"],
        ["Cavolo kale", "100g cotto", "4", "150", "-", "Super-calcio vegetale"],
        ["Banana", "1 media", "23", "5", "52", "Pre-sport, CHO veloci"],
        ["Arancia", "1 media", "12", "50", "42", "Vitamina C aiuta assorbimento ferro"],
    ]
    story.append(make_table(food_ref, col_widths=[28*mm, 20*mm, 14*mm, 16*mm, 12*mm, W-90*mm]))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "IG = Indice Glicemico (basso <55, medio 55-69, alto >70). "
        "Per il calcio: la soia fortificata e il tofu sono le fonti vegetali migliori.", styles["Small"]))

    story.append(PageBreak())

    # ── WEEKLY MEAL PLAN ──
    story.append(Paragraph("Piano Pasti: Martedi' e Giovedi' (sveglia 6:30, bici al mattino)", styles["SubHead"]))

    tue_thu = [
        ["Pasto", "Ora", "Cosa mangiare", "CHO (g)", "Bolo?", "Calcio (mg)"],
        ["Colazione", "6:30-6:45",
         "Latte di soia fortif. (250ml)\n"
         "Caffe' senza zucchero\n"
         "1 frutto piccolo (mela/pera)\n"
         "10g mandorle + 5g semi sesamo",
         "~18", "No\n(come ora)", "~375+75\n=450"],
        ["Meta' mattina\n(se serve)", "10:30",
         "Solo se SG <120:\nYogurt soia (125g)",
         "~8", "No", "~150"],
        ["PRE-BOLO", "13:30",
         "Dare il bolo 15 min\nPRIMA di mangiare",
         "-", "SI'", "-"],
        ["Pranzo", "13:45",
         "Opzione A: Ceci (150g) + verdure\n"
         "Opzione B: Pasta integrale (60g)\n"
         "   + legumi o tofu (100g)\n"
         "Opzione C: Lenticchie (150g)\n"
         "   + pane cereali (30g)\n"
         "Condire con olio EVO + sesamo\n"
         "+ verdure a foglia verde",
         "25-35", "SI'\n(ICR 8-9)", "60-350\n(varia)"],
        ["Snack\npre-sport", "16:30",
         "1 banana piccola\nOPPURE 3 fichi secchi\nOPPURE barretta cereali (25g)\nNO taralli (IG troppo alto)",
         "15-20", "NO!", "5-50"],
        ["Cena", "19:30-20:00",
         "Tofu/tempeh (100-150g)\n"
         "Verdure cotte (broccoli, kale)\n"
         "Pane ai cereali (30-60g)\n"
         "Olio EVO + semi lino (10g)",
         "20-30", "SI'\n(ICR 9)", "350-500"],
        ["Spuntino\nnotte", "21:30-22:00",
         "Solo se SG <120:\n5-10g CHO (cracker, frutta)",
         "0-10", "No", "-"],
    ]
    story.append(make_table(tue_thu, col_widths=[20*mm, 18*mm, 52*mm, 14*mm, 14*mm, 18*mm], header_color=C_PURPLE))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "<b>Totale giornata:</b> ~90-120g CHO — <b>Calcio:</b> ~1000-1400 mg — "
        "<b>OK per anti-chetosi</b>", styles["Tip"]))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("Piano Pasti: Altri Giorni (sveglia ~9:00, no bici al mattino)", styles["SubHead"]))
    other = [
        ["Pasto", "Ora", "Cosa mangiare", "CHO (g)", "Bolo?", "Calcio (mg)"],
        ["Colazione", "9:00-9:30",
         "Latte di soia fortif. (250ml)\n"
         "Caffe' senza zucchero\n"
         "Porridge di avena (30g) con\n"
         "  frutta fresca + semi sesamo\n"
         "  + 10g mandorle",
         "~30", "SI'\n(ICR 11-14)", "~450+75\n=525"],
        ["Pranzo", "13:30-14:00",
         "(uguale Ma/Gi)\n"
         "Pre-bolo 15 min prima\n"
         "Ceci/lenticchie/pasta int.\n"
         "  + tofu/verdure + sesamo",
         "25-35", "SI'\n(ICR 8-9)", "60-350"],
        ["Snack\npre-sport", "16:30",
         "(uguale Ma/Gi)\n"
         "Banana / fichi secchi / barretta\n"
         "NO taralli",
         "15-20", "NO!", "5-50"],
        ["Cena", "19:30-20:00",
         "(uguale Ma/Gi)\n"
         "Tofu/tempeh + verdure\n"
         "Pane cereali + semi lino",
         "20-30", "SI'\n(ICR 9)", "350-500"],
        ["Spuntino\nnotte", "21:30-22:00",
         "Solo se SG <120:\n5-10g CHO",
         "0-10", "No", "-"],
    ]
    story.append(make_table(other, col_widths=[20*mm, 18*mm, 52*mm, 14*mm, 14*mm, 18*mm], header_color=C_TEAL))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "<b>Differenza principale:</b> nei giorni non-bici la colazione puo' essere piu' "
        "sostanziosa (porridge di avena), con bolo, perche' c'e' piu' tempo e non c'e' "
        "il rischio di ipo da bici subito dopo.", styles["Body"]))

    story.append(PageBreak())

    # ── MEAL ROTATION ──
    story.append(Paragraph("Rotazione Pranzo Settimanale (suggerimento)", styles["SubHead2"]))
    rotation = [
        ["Giorno", "Pranzo", "CHO (g)", "Proteine (g)", "Calcio (mg)"],
        ["Lunedi'", "Lenticchie (150g) + verdure grigliate\n+ pane cereali (30g) + sesamo", "~39", "~16", "~85"],
        ["Martedi'", "Pasta integrale (60g) + sugo di ceci\n+ broccoli + parmigiano veg", "~40", "~18", "~100"],
        ["Mercoledi'", "Ceci (150g) in insalata tiepida\n+ pomodori + cetrioli + olio EVO", "~27", "~12", "~60"],
        ["Giovedi'", "Riso basmati int. (50g) + tofu (100g)\nsaltato con verdure + sesamo", "~37", "~16", "~370"],
        ["Venerdi'", "Fagioli cannellini (150g)\n+ verdure + pane cereali (30g)", "~39", "~14", "~70"],
        ["Sabato", "Pasta integrale (60g) + pesto\ndi mandorle + tempeh (80g)", "~42", "~22", "~150"],
        ["Domenica", "Zuppa di legumi misti (200g)\n+ crostini integrali (30g)", "~35", "~16", "~80"],
    ]
    story.append(make_table(rotation, col_widths=[20*mm, 60*mm, 16*mm, 20*mm, 18*mm]))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "Questi sono suggerimenti flessibili. L'importante e': CHO a basso IG, "
        "sempre una fonte proteica, verdure a foglia verde quando possibile, "
        "e semi di sesamo/mandorle come condimento per il calcio.", styles["Small"]))

    story.append(Spacer(1, 4*mm))

    # ── SPECIAL FOODS FOR OSTEOPOROSIS ──
    story.append(Paragraph("Focus Osteoporosi: I 5 Alimenti da Non Dimenticare", styles["SubHead2"]))
    osteo = [
        ["Alimento", "Frequenza", "Porzione", "Calcio", "Perche' e' importante"],
        ["Tofu (con calcio)", "3-4 volte/sett.", "100-150g", "350-525 mg", "La fonte vegetale piu' ricca\ndi calcio + proteine + isoflavoni"],
        ["Latte soia fortif.", "Ogni giorno", "250 ml", "300 mg", "Isoflavoni benefici\nper la salute ossea"],
        ["Semi di sesamo", "Ogni giorno", "15g (1 cucch.)", "140 mg", "Aggiungi su insalate,\npasta, zuppe — facile!"],
        ["Verdure a foglia\n(broccoli, kale,\ncavolo)", "Ogni giorno", "200g cotti", "90-150 mg", "Calcio + vitamina K\n(essenziale per le ossa)\n+ antiossidanti"],
        ["Mandorle / fichi\nsecchi", "Ogni giorno", "30g", "50-75 mg", "Snack ricco di calcio\nmagnesio e fibra"],
    ]
    story.append(make_table(osteo, col_widths=[25*mm, 22*mm, 20*mm, 18*mm, W-85*mm], header_color=C_TEAL))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        "<b>Vitamina D:</b> difficile da ottenere solo dalla dieta. Chiedi alla dottoressa "
        "di verificare il livello nel sangue (25-OH vitamina D) e prescrivere un integratore "
        "se necessario (obiettivo >30 ng/mL). 15-20 minuti di sole al giorno aiutano.", styles["Body"]))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(
        "<b>Fitoestrogenici:</b> la soia (latte, tofu, tempeh, edamame) contiene isoflavoni "
        "che hanno un effetto benefico per la salute ossea.", styles["Body"]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # PAGE 4: GESTIONE SPORT + POMPA
    # ═══════════════════════════════════════════
    story.append(Paragraph("Gestione Sport Quotidiano", styles["SectionHead"]))

    img_timeline = make_timeline_chart("_chart_timeline2.png")
    story.append(Image(img_timeline, width=170*mm, height=70*mm))
    story.append(Spacer(1, 3*mm))

    sport_protocol = [
        ["Ora", "Azione", "Dettaglio"],
        ["15:00", "Temp Target ON",
         "SmartGuard > Target Temporaneo > Attivare\n"
         "Alza target a 150 → riduce basale e correzioni → meno IOB alle 17"],
        ["16:30", "Snack pre-sport\nSENZA BOLO",
         "SG <100: NON fare sport, 20g CHO, aspettare\n"
         "SG 100-150: 20g CHO (banana)\n"
         "SG 150-250: 10-15g CHO (mezza banana)\n"
         "SG >250: solo acqua"],
        ["16:50", "Controllo SG",
         "Verificare che SG sia >100 prima di staccare la pompa"],
        ["17:00", "Disconnetti pompa\nBici + Sport",
         "Portare SEMPRE: destrosio, succo, glucometro"],
        ["~19:00", "Riconnetti pompa\nTemp Target OFF",
         "Riconnettere SUBITO dopo lo sport\n"
         "Se SG <100: 15g CHO prima di cena"],
    ]
    story.append(make_table(sport_protocol, col_widths=[16*mm, 30*mm, W-46*mm]))
    story.append(Spacer(1, 2*mm))

    story.append(Paragraph(
        "<b>Taralli pre-sport:</b> hanno indice glicemico alto (65-70) e sono ricchi di grassi. "
        "Questo causa un picco rapido seguito da un calo. Meglio sostituirli con "
        "banana, fichi secchi, o barretta di cereali che danno energia piu' costante.", styles["Warning"]))

    story.append(Spacer(1, 4*mm))

    # ═══════════════════════════════════════════
    # SECTION 3: PUMP SETTINGS
    # ═══════════════════════════════════════════
    story.append(Paragraph("3. Impostazioni Microinfusore", styles["SectionHead"]))

    story.append(Paragraph("Modifiche consigliate (una alla volta, una ogni 5-7 giorni)", styles["BodyBold"]))
    story.append(Spacer(1, 2*mm))

    settings = [
        ["#", "Parametro", "Attuale", "Nuovo", "Quando", "Perche'"],
        ["1", "AIT\n(Active Insulin\nTime)", "2h 30 min", "2h 15 min", "Subito", "Riduce IOB calcolato\n"
         "SmartGuard sara' meno\naggressivo con correzioni\n= meno insulina alle 17"],
        ["2", "ICR Cena\n(18-23)", "9.7-10 g/U", "9 g/U", "Dopo 1 sett.\ncon AIT nuovo", "Post-sport la sensibilita'\n"
         "e' alta ma la cena deve\nessere coperta. Testare\ncon attenzione"],
        ["3", "ICR Pranzo\n(10-15)", "8.8-9 g/U", "INVARIATO", "-", "Il bolo pranzo e' corretto!\n"
         "Il problema e' il tipo di CHO\ne il timing, non la dose"],
        ["4", "ICR Colazione\n(6-10)", "11-14 g/U", "INVARIATO", "-", "Colazione leggera senza\n"
         "bolo → funziona bene"],
        ["5", "ISF", "100 mg/dL/U", "INVARIATO\n(per ora)", "Rivalutare\ndopo 4 sett.", "Con sport quotidiano\n"
         "la sensibilita' e' gia' alta.\nPrima implementare la\nstrategia alimentare"],
        ["6", "Target\nSmartGuard", "120 mg/dL", "INVARIATO\n(NON abbassare!)", "-", "Con Target 100 il TIR era\nPEGGIORE (51% vs 59%).\n120 e' il valore giusto.\nUsare Temp Target pre-sport"],
    ]
    story.append(make_table(settings, col_widths=[8*mm, 24*mm, 22*mm, 22*mm, 22*mm, W-98*mm]))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("Cosa osservare dopo ogni modifica", styles["SubHead"]))
    observe = [
        ["Cosa monitorare", "Frequenza", "Segnale positivo", "Segnale di allarme"],
        ["SG post-pranzo\n(14:00-16:00)", "Ogni giorno", "Picco <250 mg/dL\n(era 280-360)", "Picco invariato →\nCHO non abbastanza lenti"],
        ["SG durante sport\n(17:00-19:00)", "Ogni giorno", "SG resta >100\n(era crollo a 70-86)", "SG <80 → aumentare\nsnack pre-sport"],
        ["SG post-cena\n(20:00-23:00)", "Ogni giorno", "SG 100-180", "SG >250 → ICR cena\ntroppo alto (meno insulina)\n"
         "SG <80 → ICR troppo basso"],
        ["ALERT ON LOW", "Settimanale", "<2 a settimana\n(erano ~3.5/sett)", ">4/settimana →\nstop modifiche, rivalutare"],
        ["TIR su 14 giorni", "Ogni 2 settimane", "TIR >60%\n(era 54%)", "TIR <50% →\nqualcosa non funziona"],
        ["Ipo notte\n(00:00-06:00)", "Settimanale", "Nessuna", "Se compaiono dopo\nmodifica ICR cena →\nripristinare ICR vecchio"],
    ]
    story.append(make_table(observe, col_widths=[28*mm, 22*mm, 32*mm, W-82*mm]))

    story.append(PageBreak())

    # ═══════════════════════════════════════════
    # PAGE 5: CONSIDERAZIONI + APPENDICE
    # ═══════════════════════════════════════════
    story.append(Paragraph("4. Considerazioni Importanti", styles["SectionHead"]))

    story.append(Paragraph("Osteoporosi e sport", styles["SubHead2"]))
    story.append(Paragraph(
        "L'attivita' fisica che fai e' <b>eccellente</b> per le ossa. Lo sport con impatto "
        "(corsa, salti) e con carico stimola la formazione ossea. La bicicletta invece "
        "e' a basso impatto — ottima per il cardiovascolare ma meno per le ossa. "
        "Se possibile, includi negli allenamenti esercizi con salti o pesi.", styles["Body"]))
    story.append(Spacer(1, 2*mm))

    story.append(Paragraph("Controlli periodici T1D", styles["SubHead2"]))
    story.append(Paragraph(
        "Punti da verificare periodicamente con il diabetologo:", styles["Body"]))
    checks = [
        "Livello vitamina D nel sangue (25-OH vitamina D, obiettivo >30 ng/mL)",
        "Eventuale integrazione di vitamina D (800-1000 UI/giorno)",
        "Valutare se l'apporto di calcio e' sufficiente dalla dieta",
        "Profilo lipidico annuale",
        "HbA1c ogni 3 mesi (obiettivo <7.0%)",
    ]
    for c in checks:
        story.append(Paragraph(f"  - {c}", styles["Body"]))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("Chetosi e carboidrati minimi", styles["SubHead2"]))
    story.append(Paragraph(
        "Con ~100-130g di CHO al giorno distribuiti su tutti i pasti, il rischio di chetosi "
        "e' <b>minimo</b>. Il piano prevede CHO ad ogni pasto:", styles["Body"]))
    ketosis = [
        ["Pasto", "CHO (g)", "% del totale"],
        ["Colazione", "18-30", "15-25%"],
        ["Pranzo", "25-42", "25-35%"],
        ["Snack pre-sport", "15-20", "15%"],
        ["Cena", "20-30", "20-25%"],
        ["Spuntino (se serve)", "0-10", "0-10%"],
        ["TOTALE", "~100-130", "100%"],
    ]
    story.append(make_table(ketosis, col_widths=[30*mm, 20*mm, 20*mm], header_color=C_TEAL))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("Peso e sensibilita' insulinica", styles["SubHead2"]))
    story.append(Paragraph(
        "Con sport quotidiano e un fabbisogno insulinico basso "
        "la sensibilita' insulinica e' altissima. "
        "Questo spiega perche':", styles["Body"]))
    weight_notes = [
        "Anche piccole dosi di IOB (1-2U) combinate con esercizio causano ipo",
        "L'ISF di 100 mg/dL/U potrebbe essere adeguato (non modificare per ora)",
        "Le correzioni automatiche di SmartGuard possono essere troppo aggressive → l'AIT a 2h15 aiuta",
        "La colazione leggera senza bolo funziona grazie all'alta sensibilita' mattutina",
    ]
    for w in weight_notes:
        story.append(Paragraph(f"  - {w}", styles["Body"]))

    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("Ordine di implementazione", styles["SubHead2"]))
    impl = [
        ["Settimana", "Cosa fare", "Cosa osservare"],
        ["1", "Cambiare TIPO di CHO a pranzo\n(basso IG: ceci, lenticchie, pasta int.)\n"
         "+ pre-bolo 15 min prima\n+ sostituire taralli con banana/fichi",
         "Picco post-pranzo piu' basso?\n"
         "SG durante sport piu' stabile?"],
        ["2", "Aggiungere Temp Target alle 15:00\n+ snack pre-sport senza bolo",
         "SG >100 durante sport?\n"
         "Meno ALERT ON LOW?"],
        ["3", "Cambiare AIT: 2h30 → 2h15", "IOB piu' basso alle 17?\nNessuna ipo in piu'?"],
        ["4-5", "Cambiare ICR cena: 10 → 9", "SG post-cena <180?\nNessuna ipo notturna?"],
        ["6+", "Rivalutare TIR, media SG, GMI\nDecidere se toccare ISF",
         "TIR >65%? → ottimo!\nTIR 60-65% → rivalutare\nTIR <55% → parlare con dottoressa"],
    ]
    story.append(make_table(impl, col_widths=[18*mm, 62*mm, W-80*mm]))

    # ── RESULTS EXPECTED ──
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("Risultati attesi", styles["SubHead2"]))
    expected = [
        ["", "Oggi", "4-6 settimane", "3 mesi"],
        ["TIR (70-180)", "53.7%", "60-65%", "65-70%"],
        ["TAR (>180)", "46.1%", "32-37%", "25-30%"],
        ["TBR (<70)", "0.2%", "<1%", "<2%"],
        ["Media SG", "177 mg/dL", "155-165", "140-155"],
        ["GMI (HbA1c)", "7.5%", "7.0-7.2%", "6.5-7.0%"],
        ["ALERT ON LOW", "~3.5/sett", "<2/sett", "<1/sett"],
    ]
    story.append(make_table(expected, col_widths=[28*mm, 25*mm, 30*mm, 25*mm], header_color=C_GREEN))

    # ── DISCLAIMER ──
    story.append(Paragraph(
        "NOTA: Questo piano e' basato sull'analisi dei dati del microinfusore MiniMed 780G "
        "(feb-mar 2026) e sulla letteratura clinica. Ogni modifica delle impostazioni della pompa "
        "e della dieta va concordata con il diabetologo/endocrinologo e il nutrizionista. "
        "Non sostituisce il parere medico. I risultati attesi sono stime basate sui dati e possono variare. "
        "I valori nutrizionali sono approssimativi e possono variare in base al prodotto specifico.",
        styles["Disclaimer"]))

    doc.build(story)
    print(f"PDF generato: {path}")
    return path


if __name__ == "__main__":
    generate_diet_pdf()
