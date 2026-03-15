import datetime
import calendar
import math
import io
import base64
import os
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

# ════════════════════════════════════════════════════════════════
# PDF EXPORT – reportlab
# ════════════════════════════════════════════════════════════════
from reportlab.lib.pagesizes import A4, landscape as rl_landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, PageBreak,
    Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

# ── Registrácia fontu s podporou diakritiky ──
_FONT_NAME = "DejaVuSans"
_FONT_NAME_BOLD = "DejaVuSans-Bold"
try:
    pdfmetrics.registerFont(TTFont(_FONT_NAME, "DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont(_FONT_NAME_BOLD, "DejaVuSans-Bold.ttf"))
except Exception:
    try:
        pdfmetrics.registerFont(TTFont(_FONT_NAME, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont(_FONT_NAME_BOLD, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    except Exception as _font_err:
        st.error(f"❌ Nepodarilo sa načítať font DejaVuSans: {_font_err}\n\nUisti sa, že DejaVuSans.ttf je dostupný.")
        st.stop()

# ════════════════════════════════════════════════════════════════
# LOGO – načítanie a base64 pre HTML
# ════════════════════════════════════════════════════════════════
LOGO_PATH = "logo.jpg"   # ← uisti sa, že logo.jpg je v rovnakom adresári ako skript

def _get_logo_base64() -> str:
    """Vráti base64 reťazec loga pre vkladanie do HTML."""
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""

# ════════════════════════════════════════════════════════════════
# NASTAVENIE STRÁNKY A DIZAJNU (Skrytie menu a pätky)
# ════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Generátor reportov", page_icon="🏭", layout="centered")

hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# KONFIGURÁCIA GOOGLE SHEETS
# IDs sú načítavané zo Streamlit Secrets alebo z env. premenných.
# Šablóna: .streamlit/secrets.toml.example
# ════════════════════════════════════════════════════════════════
def _secret(key: str) -> str:
    """Načíta hodnotu zo st.secrets alebo z env. premennej. Ak chýba, vyhodí chybu."""
    try:
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    val = os.environ.get(key)
    if val:
        return val
    st.error(f"❌ Chýba povinná konfigurácia: `{key}`\n\n"
             f"Nastav ju v `.streamlit/secrets.toml` alebo ako env. premennú.\n"
             f"Šablóna: `.streamlit/secrets.toml.example`")
    st.stop()

DODAVKY_SHEET_ID = _secret("DODAVKY_SHEET_ID")

DODAVKY_GIDS = {
    1:  "2041175941", 2:  "996148749", 3:  "1052948469", 4:  "1742234642",
    5:  "1522704266", 6:  "318756165", 7:  "174620779",  8:  "1714534272",
    9:  "2141494448", 10: "953926717", 11: "1911464342", 12: "33776211",
}

COL_BODOS      = 1
COL_HBP_DREVO  = 2
COL_RECYKLACIA = 3
COL_JANKULA    = 4
COL_PC_STAV    = 1
RIADOK_PC_STAV_IDX = 36

PREVADZKA_SHEETS = {
    2: {
        "sheet_id":   _secret("PREVADZKA_2_SHEET_ID"),
        "mesiac_gid": "1425398749",
        "denny_gid":  "759527346",
    },
    3: {
        "sheet_id":   _secret("PREVADZKA_3_SHEET_ID"),
        "mesiac_gid": "1081996655",
        "denny_gid":  "737601644",
    },
    4: {
        "sheet_id":   _secret("PREVADZKA_4_SHEET_ID"),
        "mesiac_gid": "737601644",
        "denny_gid":  None,
    },
}

MC_VYROBA = 17; MC_STIEPKA = 9; MC_T_VYSTUP = 10; MC_T_VRATNA = 11
MC_T_K6 = 4; MC_T_K7 = 23; MC_PRIETOK = 13
DZ_K6 = 13; DZ_K7 = 30

# ════════════════════════════════════════════════════════════════
# POMOCNÉ FUNKCIE (Dáta a výpočty)
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=600)
def nacitaj_gs(sheet_id: str, gid: str) -> pd.DataFrame | None:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        return pd.read_csv(url, header=None, dtype=str)
    except Exception as e:
        st.error(f"Chyba pri načítaní dát z Google Sheets (GID: {gid}): {e}")
        return None

def safe_float(df: pd.DataFrame, row_idx: int, col_idx: int) -> float | None:
    try:
        if row_idx >= len(df) or col_idx >= len(df.columns): return None
        val = df.iloc[row_idx, col_idx]
        if pd.isna(val) or str(val).strip() in ("", "-", "—"): return None
        return float(str(val).replace(",", ".").replace("\xa0", "").strip())
    except Exception:
        return None

def sum_column_do_dna(df: pd.DataFrame, col_idx: int, den: int) -> float:
    total = 0.0
    for row_idx in range(1, den + 1):
        val = safe_float(df, row_idx, col_idx)
        if val is not None and val > 0: total += val
    return total

def nacitaj_dodavky_stiepky(mesiac: int, den: int) -> dict:
    vysledok = {"bodos": 0.0, "hbp_drevo": 0.0, "recyklacia": 0.0, "jankula": 0.0, "pociatocny_stav": 800.0}
    gid = DODAVKY_GIDS.get(mesiac)
    if not gid:
        st.warning(f"⚠️ Dodávky štiepky: mesiac {mesiac} nie je nakonfigurovaný. Používajú sa predvolené hodnoty.")
        return vysledok
    df = nacitaj_gs(DODAVKY_SHEET_ID, gid)
    if df is None:
        st.warning("⚠️ Dodávky štiepky: dáta sa nepodarilo načítať z Google Sheets. Zobrazené hodnoty môžu byť nepresné.")
        return vysledok

    pc_stav = safe_float(df, RIADOK_PC_STAV_IDX, COL_PC_STAV)
    if pc_stav is not None: vysledok["pociatocny_stav"] = pc_stav

    vysledok["bodos"]      = sum_column_do_dna(df, COL_BODOS, den)
    vysledok["hbp_drevo"]  = sum_column_do_dna(df, COL_HBP_DREVO, den)
    vysledok["recyklacia"] = sum_column_do_dna(df, COL_RECYKLACIA, den)
    vysledok["jankula"]    = sum_column_do_dna(df, COL_JANKULA, den)
    return vysledok

def nacitaj_prevadzkove_udaje(mesiac: int, den: int) -> dict | None:
    cfg = PREVADZKA_SHEETS.get(mesiac)
    if cfg is None: return None

    df_m = nacitaj_gs(cfg["sheet_id"], cfg["mesiac_gid"])
    if df_m is None: return None

    ci = den + 4
    udaje = {}
    
    def get_m(col_idx):
        v = safe_float(df_m, ci, col_idx)
        return v if v is not None else 0.0

    udaje["vyroba_val"] = get_m(MC_VYROBA)
    udaje["priem_teplota_val"] = get_m(MC_T_VYSTUP)
    udaje["vratna_teplota_val"] = get_m(MC_T_VRATNA)
    udaje["teplota_k6_val"] = max(0.0, get_m(MC_T_K6))
    udaje["teplota_k7_val"] = max(0.0, get_m(MC_T_K7))
    udaje["priem_prietok_val"] = get_m(MC_PRIETOK)

    monthly_sum, stiepka_monthly_sum = 0.0, 0.0
    for row_idx in range(5, ci + 1):
        v_vyr = safe_float(df_m, row_idx, MC_VYROBA)
        if v_vyr and v_vyr > 0: monthly_sum += v_vyr
        v_st = safe_float(df_m, row_idx, MC_STIEPKA)
        if v_st and v_st > 0: stiepka_monthly_sum += v_st

    udaje["monthly_sum"] = monthly_sum
    udaje["stiepka_monthly_sum"] = stiepka_monthly_sum

    aktualna = safe_float(df_m, ci, MC_STIEPKA)
    if not aktualna or aktualna <= 0:
        aktualna = 0.0
        for prev_day in range(1, 5):
            if ci - prev_day >= 5:
                prev_val = safe_float(df_m, ci - prev_day, MC_STIEPKA)
                if prev_val and prev_val > 0:
                    aktualna = prev_val
                    break
        if aktualna == 0.0 and (ci - 4) > 0:
            aktualna = stiepka_monthly_sum / (ci - 4)
    udaje["aktualna_denna_spotreba"] = aktualna

    hours_data_k6, hours_data_k7 = [0.0] * 24, [0.0] * 24
    if cfg.get("denny_gid"):
        df_d = nacitaj_gs(cfg["sheet_id"], cfg["denny_gid"])
        if df_d is not None:
            start_idx = 5 + (den - 1) * 35
            end_idx = start_idx + 24
            def process_hourly(col_idx):
                vals = [safe_float(df_d, ri, col_idx) or 0.0 for ri in range(start_idx, end_idx)]
                return (vals + [0.0] * 24)[:24]
            hours_data_k6 = process_hourly(DZ_K6)
            hours_data_k7 = process_hourly(DZ_K7)

    udaje["hours_data_k6"] = hours_data_k6
    udaje["hours_data_k7"] = hours_data_k7
    return udaje

def fmt(val, jednotka=""):
    return str(round(val, 2)).replace('.', ',') + (f" {jednotka}" if jednotka else "")

def vypocitaj_vydrz_zasoby(pociatocny_stav, spotreba_doteraz, aktualna_denna_spotreba, aktualny_datum):
    zostatok = pociatocny_stav - spotreba_doteraz
    if aktualna_denna_spotreba <= 0: return aktualny_datum + datetime.timedelta(days=9999), 9999
    dni = math.floor(zostatok / aktualna_denna_spotreba)
    return aktualny_datum + datetime.timedelta(days=dni), dni

# ════════════════════════════════════════════════════════════════
# POMOCNÉ FUNKCIE PRE GRAFY A STIAHNUTIE
# ════════════════════════════════════════════════════════════════
def graf_do_pamate(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    buf.seek(0)
    return buf

def create_bar_chart(vyroba: float, priem_teplota: float, teplota_k6: float, teplota_k7: float):
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(['Výroba\n(MWh)', 'Priem. teplota\n(°C)', 'Teplota K6\n(°C)', 'Teplota K7\n(°C)'],
                  [vyroba, priem_teplota, teplota_k6, teplota_k7],
                  color=['#8CC63F', '#2B2B2B', '#5A5A5A', '#7A7A7A'])
    
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(), f'{bar.get_height():.1f}', 
                ha='center', va='bottom')
    ax.grid(True, linestyle='--', alpha=0.3, axis='y')
    ax.set_title('Prevádzkové hodnoty', pad=20, fontsize=12, fontweight='bold')
    
    fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.20)
    return fig

def create_line_chart(values, chart_title, line_color):
    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(1, 25)
    ax.plot(x, values, marker='o', color=line_color, linewidth=1.5)
    ax.axhline(y=3.0, color='red', linestyle='--', linewidth=2)
    
    ax.text(24, 3.85, 'MAX výkon (3 MW)', color='red', fontweight='bold', va='top', ha='right', fontsize=10)
    
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.set_title(chart_title, pad=20, fontsize=12, fontweight='bold')
    ax.set_xlabel("Hodina")
    ax.set_ylabel("Výkon (MW)")
    ax.set_xlim(1, 24)
    ax.set_ylim(0, 4)
    ax.set_xticks(range(1, 25))
    
    for i, val in enumerate(values):
        if val is not None and val > 0:
            ax.text(x[i], val, f"{val:.1f}", ha='center', va='bottom', fontsize=8)
            
    fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.20)
    return fig

# ════════════════════════════════════════════════════════════════
# PDF GENEROVANIE
# ════════════════════════════════════════════════════════════════
def _fig_to_rl_image(fig, width_mm=170, max_height_mm=None):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    orig_w, orig_h = fig.get_size_inches()
    ratio = orig_h / orig_w
    target_w = width_mm * mm
    target_h = target_w * ratio
    if max_height_mm and target_h > max_height_mm * mm:
        target_h = max_height_mm * mm
    return RLImage(buf, width=target_w, height=target_h)

def _get_pdf_styles():
    styles = getSampleStyleSheet()
    s = {}
    s['title'] = ParagraphStyle(
        'ReportTitle', parent=styles['Title'],
        fontName=_FONT_NAME_BOLD,
        fontSize=16, spaceAfter=4 * mm, textColor=colors.HexColor("#2B2B2B"),
    )
    s['subtitle'] = ParagraphStyle(
        'ReportSubtitle', parent=styles['Normal'],
        fontName=_FONT_NAME,
        fontSize=10, spaceAfter=6 * mm, textColor=colors.HexColor("#666666"),
    )
    s['section'] = ParagraphStyle(
        'SectionHeader', parent=styles['Heading2'],
        fontName=_FONT_NAME_BOLD,
        fontSize=12, spaceBefore=6 * mm, spaceAfter=3 * mm,
        textColor=colors.white, backColor=colors.HexColor("#8CC63F"),
        borderPadding=(4, 6, 4, 6),
    )
    s['section_dark'] = ParagraphStyle(
        'SectionHeaderDark', parent=s['section'],
        backColor=colors.HexColor("#5A5A5A"),
    )
    s['note'] = ParagraphStyle(
        'NoteStyle', parent=styles['Normal'],
        fontName=_FONT_NAME_BOLD,
        fontSize=9, textColor=colors.red, spaceBefore=4 * mm,
    )
    s['podpis'] = ParagraphStyle(
        'Podpis', parent=styles['Normal'],
        fontName=_FONT_NAME,
        fontSize=9, textColor=colors.HexColor("#333333"), spaceBefore=6 * mm,
    )
    return s

def _build_portrait_pdf(vybrany_datum, prev, dodavky, celkove_dodavky, zostatok_stiepky,
                         prev_aktualna_denna_spotreba, pocet_zostavajucich_dni, datum_vycerpania,
                         priem_vykon_k6, priem_vykon_k7, priem_vykon_spolu,
                         pocet_h_k6, pocet_h_k7, fmt):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    s = _get_pdf_styles()
    GREEN = colors.HexColor("#8CC63F")
    GREY = colors.HexColor("#5A5A5A")
    LIGHT_BG = colors.HexColor("#f8f9fa")

    story = []

    # ── LOGO HLAVIČKA ──
    try:
        logo_img = RLImage(LOGO_PATH, width=40*mm, height=16*mm)
        # Hlavička s logom vľavo a názvom vpravo
        header_data = [[
            logo_img,
            Paragraph(
                "Prevádzkový report – Cigeľ<br/>"
                f"<font size='9' color='#666666'>"
                f"Prevádzkový záznam – hodnoty za {vybrany_datum.strftime('%d.%m.%Y')}"
                f"</font>",
                ParagraphStyle(
                    'HeaderText',
                    fontName=_FONT_NAME_BOLD,
                    fontSize=14,
                    textColor=colors.HexColor("#2B2B2B"),
                    alignment=TA_RIGHT,
                )
            )
        ]]
        header_table = Table(header_data, colWidths=[45*mm, 125*mm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, GREEN),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4*mm),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 4*mm))
    except Exception:
        # Fallback – bez loga
        story.append(Paragraph("Prevádzkový report – Cigeľ", s['title']))
        story.append(Paragraph(
            f"Prevádzkový záznam – hodnoty za {vybrany_datum.strftime('%d.%m.%Y')}", s['subtitle']))

    # ── Tabuľka prevádzkových údajov ──
    story.append(Paragraph("Prevádzkové údaje", s['section']))
    prev_data = [
        ["Parameter", "Hodnota"],
        ["Výroba", fmt(prev["vyroba_val"], "MWh")],
        ["Kumulatívna výroba", fmt(prev["monthly_sum"], "MWh")],
        ["Priem. hod. výkon K6", fmt(priem_vykon_k6, f"MW ({pocet_h_k6}h)")],
        ["Priem. hod. výkon K7", fmt(priem_vykon_k7, f"MW ({pocet_h_k7}h)")],
        ["Priem. hod. výkon spolu", fmt(priem_vykon_spolu, "MW")],
        ["Priem. výstupná teplota", fmt(prev["priem_teplota_val"], "°C")],
        ["Priem. vratná teplota", fmt(prev["vratna_teplota_val"], "°C")],
        ["Teplota spaľ. komory K6", fmt(prev["teplota_k6_val"], "°C")],
        ["Teplota spaľ. komory K7", fmt(prev["teplota_k7_val"], "°C")],
        ["Priemerný prietok", fmt(prev["priem_prietok_val"], "m³")],
    ]
    col_widths = [100*mm, 70*mm]
    t1 = Table(prev_data, colWidths=col_widths)
    t1s = [
        ('BACKGROUND', (0,0), (-1,0), GREEN), ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), _FONT_NAME_BOLD),
        ('FONTNAME', (0,1), (0,-1), _FONT_NAME), ('FONTNAME', (1,1), (1,-1), _FONT_NAME_BOLD),
        ('FONTSIZE', (0,0), (-1,-1), 9), ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#dddddd")),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6), ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]
    for i in range(1, len(prev_data)):
        if i % 2 == 0: t1s.append(('BACKGROUND', (0,i), (-1,i), LIGHT_BG))
        t1s.append(('LINEBEFORESTROKEWIDTH', (0,i), (0,i), 3))
        t1s.append(('LINEBEFORECOLOR', (0,i), (0,i), GREEN))
    t1.setStyle(TableStyle(t1s))
    story.append(t1)
    story.append(Spacer(1, 4*mm))

    # ── Tabuľka štiepky ──
    story.append(Paragraph("Informácie o zásobe štiepky", s['section_dark']))
    stiepka_data = [
        ["Parameter", "Hodnota"],
        ["Počiatočný stav skladu", fmt(dodavky["pociatocny_stav"], "t")],
        ["Dodávka – Bodos", fmt(dodavky["bodos"], "t")],
        ["Dodávka – z dreva HBP", fmt(dodavky["hbp_drevo"], "t")],
        ["Dodávka – Recyklácia", fmt(dodavky["recyklacia"], "t")],
        ["Dodávka – Jankula", fmt(dodavky["jankula"], "t")],
        ["Spotreba od začiatku mesiaca", fmt(prev["stiepka_monthly_sum"], "t")],
        [f"Zostatok na skládke k {vybrany_datum.strftime('%d.%m.%Y')}", fmt(zostatok_stiepky, "t")],
        ["Aktuálna denná spotreba", fmt(prev["aktualna_denna_spotreba"], "t")],
        ["Predpokladaná výdrž zásoby", "0 dní" if pocet_zostavajucich_dni <= 0 else f"{pocet_zostavajucich_dni} dní"],
        ["Predpokladaný dátum vyčerpania", "Dnes" if pocet_zostavajucich_dni <= 0 else datum_vycerpania.strftime('%d.%m.%Y')],
    ]
    t2 = Table(stiepka_data, colWidths=col_widths)
    t2s = [
        ('BACKGROUND', (0,0), (-1,0), GREY), ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), _FONT_NAME_BOLD),
        ('FONTNAME', (0,1), (0,-1), _FONT_NAME), ('FONTNAME', (1,1), (1,-1), _FONT_NAME_BOLD),
        ('FONTSIZE', (0,0), (-1,-1), 9), ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#dddddd")),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6), ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]
    for i in range(1, len(stiepka_data)):
        if i % 2 == 0: t2s.append(('BACKGROUND', (0,i), (-1,i), LIGHT_BG))
        t2s.append(('LINEBEFORESTROKEWIDTH', (0,i), (0,i), 3))
        t2s.append(('LINEBEFORECOLOR', (0,i), (0,i), GREY))
    t2.setStyle(TableStyle(t2s))
    story.append(t2)

    doc.build(story)
    buf.seek(0)
    return buf

def _build_landscape_pdf(vybrany_datum, fig_prevadzka, fig_k6, fig_k7):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=rl_landscape(A4),
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    s = _get_pdf_styles()
    IMG_W = 255
    IMG_MAX_H = 140

    story = []

    story.append(Paragraph("Prevádzkové hodnoty", s['section']))
    story.append(_fig_to_rl_image(fig_prevadzka, width_mm=IMG_W, max_height_mm=IMG_MAX_H))

    story.append(PageBreak())
    story.append(Paragraph("Výkon kotla K6", s['section']))
    story.append(_fig_to_rl_image(fig_k6, width_mm=IMG_W, max_height_mm=IMG_MAX_H))

    story.append(PageBreak())
    story.append(Paragraph("Výkon kotla K7", s['section']))
    story.append(_fig_to_rl_image(fig_k7, width_mm=IMG_W, max_height_mm=IMG_MAX_H))
    story.append(Paragraph(
        "<b>Dodávka štiepky od p. Ing. Jankulu je stanovená len odhadom. "
        "Skutočné dodané množstvo bude uvedené na faktúre.</b>",
        s['note'],
    ))

    doc.build(story)
    buf.seek(0)
    return buf

def generuj_pdf(vybrany_datum, prev, dodavky, celkove_dodavky, zostatok_stiepky,
                prev_aktualna_denna_spotreba, pocet_zostavajucich_dni, datum_vycerpania,
                priem_vykon_k6, priem_vykon_k7, priem_vykon_spolu,
                pocet_h_k6, pocet_h_k7,
                fig_prevadzka, fig_k6, fig_k7, fmt):
    portrait_buf = _build_portrait_pdf(
        vybrany_datum, prev, dodavky, celkove_dodavky, zostatok_stiepky,
        prev_aktualna_denna_spotreba, pocet_zostavajucich_dni, datum_vycerpania,
        priem_vykon_k6, priem_vykon_k7, priem_vykon_spolu,
        pocet_h_k6, pocet_h_k7, fmt,
    )
    landscape_buf = _build_landscape_pdf(vybrany_datum, fig_prevadzka, fig_k6, fig_k7)

    writer = PdfWriter()
    for page in PdfReader(portrait_buf).pages:
        writer.add_page(page)
    for page in PdfReader(landscape_buf).pages:
        writer.add_page(page)

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf

# ════════════════════════════════════════════════════════════════
# STREAMLIT APLIKÁCIA
# ════════════════════════════════════════════════════════════════

# ── LOGO v Streamlit hlavičke ──
logo_b64_header = _get_logo_base64()
if logo_b64_header:
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:20px; margin-bottom:10px;">
        <img src="data:image/jpeg;base64,{logo_b64_header}"
             style="height:60px; width:auto; object-fit:contain; flex-shrink:0;" 
             alt="Handlovská Energetika"/>
        <div>
            <div style="font-size:2rem; font-weight:700; line-height:1.2; color:inherit;">
                Prevádzkový report - Cigeľ
            </div>
            <div style="font-size:1rem; color:#888; margin-top:4px;">
                Vyber dátum a vygeneruj report, ktorý si môžeš skopírovať do mailu.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.title("🏭 Prevádzkový report - Cigeľ")
    st.write("Vyber dátum a vygeneruj report, ktorý si môžeš skopírovať do mailu.")

dnes = datetime.datetime.today().date()
vcera = dnes - datetime.timedelta(days=1)

vybrany_datum = st.date_input("Dátum reportu:", value=vcera, max_value=vcera, format="DD/MM/YYYY")

if st.button("🚀 Generuj report", type="primary"):
    with st.spinner('Načítavam a spracúvam dáta z Google Sheets...'):
        mesiac = vybrany_datum.month
        den = vybrany_datum.day

        dodavky = nacitaj_dodavky_stiepky(mesiac, den)
        prev = nacitaj_prevadzkove_udaje(mesiac, den)

        if prev is None:
            st.error(f"❌ Mesiac {mesiac} nie je nakonfigurovaný v `PREVADZKA_SHEETS`. "
                     f"Doplň `sheet_id` a GIDs pre tento mesiac do konfigurácie.")
            st.stop()

        celkove_dodavky = sum([dodavky["bodos"], dodavky["hbp_drevo"], dodavky["recyklacia"], dodavky["jankula"]])
        datum_vycerpania, pocet_zostavajucich_dni = vypocitaj_vydrz_zasoby(
            dodavky["pociatocny_stav"] + celkove_dodavky,
            prev["stiepka_monthly_sum"],
            prev["aktualna_denna_spotreba"],
            vybrany_datum
        )
        zostatok_stiepky = dodavky["pociatocny_stav"] + celkove_dodavky - prev["stiepka_monthly_sum"]

        hours_data_k6, hours_data_k7 = prev["hours_data_k6"], prev["hours_data_k7"]
        for i in range(24):
            if hours_data_k6[i] > 0 and hours_data_k7[i] > 0:
                if hours_data_k6[i] > 3.3: hours_data_k6[i] /= 2
                if hours_data_k7[i] > 3.3: hours_data_k7[i] /= 2

        prev_h_k6 = [v for v in hours_data_k6 if v > 0]
        prev_h_k7 = [v for v in hours_data_k7 if v > 0]
        priem_vykon_k6 = sum(prev_h_k6) / len(prev_h_k6) if prev_h_k6 else 0.0
        priem_vykon_k7 = sum(prev_h_k7) / len(prev_h_k7) if prev_h_k7 else 0.0
        
        pocet_h_k6, pocet_h_k7 = len(prev_h_k6), len(prev_h_k7)
        priem_vykon_spolu = ((priem_vykon_k6 * pocet_h_k6 + priem_vykon_k7 * pocet_h_k7) / (pocet_h_k6 + pocet_h_k7)) if (pocet_h_k6 + pocet_h_k7 > 0) else 0.0

        # ── HTML e-mail s logom ──
        logo_b64 = logo_b64_header
        logo_html = (
            f"<img src='data:image/jpeg;base64,{logo_b64}' "
            f"style='height:40px; margin-bottom:8px;' alt='Handlovská Energetika'/>"
            if logo_b64 else ""
        )

        def td_row(label, value, alt=False):
            bg_color = "#f8f9fa" if alt else "#ffffff"
            return f"<tr style='background: {bg_color};'><td style='padding:10px;border-left:4px solid #8CC63F; color:#2B2B2B;'>{label}</td><td style='padding:10px;text-align:right;font-weight:bold; color:#2B2B2B;'>{value}</td></tr>"
        
        html_table = f"""
        {logo_html}
        <table style='width:100%; border-collapse:collapse; font-family:sans-serif;'>
            <tr style='background:#8CC63F;color:white;'><th style='padding:10px;text-align:left;'>Parameter</th><th style='padding:10px;text-align:right;'>Hodnota</th></tr>
            {td_row("Výroba", fmt(prev["vyroba_val"], "MWh"))}
            {td_row("Kumulatívna výroba", fmt(prev["monthly_sum"], "MWh"), True)}
            {td_row("Priem. hod. výkon K6", fmt(priem_vykon_k6, f"MW ({pocet_h_k6}h)"))}
            {td_row("Priem. hod. výkon K7", fmt(priem_vykon_k7, f"MW ({pocet_h_k7}h)"), True)}
            {td_row("Priem. hod. výkon spolu", fmt(priem_vykon_spolu, "MW"))}
            {td_row("Priem. výstupná teplota", fmt(prev["priem_teplota_val"], "°C"), True)}
            {td_row("Priem. vratná teplota", fmt(prev["vratna_teplota_val"], "°C"))}
            {td_row("Teplota spaľ. komory K6", fmt(prev["teplota_k6_val"], "°C"), True)}
            {td_row("Teplota spaľ. komory K7", fmt(prev["teplota_k7_val"], "°C"))}
            {td_row("Priemerný prietok", fmt(prev["priem_prietok_val"], "m³"), True)}
        </table><br>
        """

        def td_row_stiepka(label, value, alt=False):
            bg_color = "#f8f9fa" if alt else "#ffffff"
            return f"<tr style='background: {bg_color};'><td style='padding:10px;border-left:4px solid #5A5A5A; color:#2B2B2B;'>{label}</td><td style='padding:10px;text-align:right;font-weight:bold; color:#2B2B2B;'>{value}</td></tr>"

        html_stiepka_info = f"""
        <table style='width:100%; border-collapse:collapse; font-family:sans-serif; border:1px solid #ddd;'>
            <tr style='background:#5A5A5A;color:white;'><th colspan='2' style='padding:10px;text-align:left;'>Informácie o zásobe štiepky</th></tr>
            {td_row_stiepka("Počiatočný stav skladu", fmt(dodavky["pociatocny_stav"], "t"))}
            {td_row_stiepka("Dodávka – Bodos", fmt(dodavky["bodos"], "t"), True)}
            {td_row_stiepka("Dodávka – z dreva HBP", fmt(dodavky["hbp_drevo"], "t"))}
            {td_row_stiepka("Dodávka – Recyklácia", fmt(dodavky["recyklacia"], "t"), True)}
            {td_row_stiepka("Dodávka – Jankula", fmt(dodavky["jankula"], "t"))}
            {td_row_stiepka("Spotreba od začiatku mesiaca", fmt(prev["stiepka_monthly_sum"], "t"), True)}
            {td_row_stiepka(f"Zostatok na skládke k {vybrany_datum.strftime('%d.%m.%Y')}", fmt(zostatok_stiepky, "t"))}
            {td_row_stiepka("Aktuálna denná spotreba", fmt(prev["aktualna_denna_spotreba"], "t"), True)}
            {td_row_stiepka("Predpokladaná výdrž zásoby", "0 dní" if pocet_zostavajucich_dni <= 0 else f"{pocet_zostavajucich_dni} dní")}
            {td_row_stiepka("Predpokladaný dátum vyčerpania", "Dnes" if pocet_zostavajucich_dni <= 0 else datum_vycerpania.strftime('%d.%m.%Y'), True)}
        </table><br>
        """

    st.success("Report bol úspešne vygenerovaný! Skopíruj si ho nižšie.")
    st.divider()
    
    st.markdown("**Predmet e-mailu (skopíruj text nižšie):**")
    st.code(f"Prevádzkový záznam - hodnoty za {vybrany_datum.strftime('%d.%m.%Y')}", language="text")
    st.write("")

    st.markdown(f"Dobrý deň,\n\nZasielam Vám hodnoty z prevádzkového záznamu za deň {vybrany_datum.strftime('%d.%m.%Y')}:")
    st.markdown(html_table, unsafe_allow_html=True)
    st.markdown(html_stiepka_info, unsafe_allow_html=True)

    st.markdown("### Prevádzkové hodnoty")
    fig_prevadzka = create_bar_chart(prev["vyroba_val"], prev["priem_teplota_val"],
                                     prev["teplota_k6_val"], prev["teplota_k7_val"])
    st.pyplot(fig_prevadzka, use_container_width=True)
    st.download_button(
        label="💾 Stiahnuť graf prevádzkových hodnôt",
        data=graf_do_pamate(fig_prevadzka),
        file_name=f"Prevadzkove_hodnoty_{vybrany_datum.strftime('%d_%m_%Y')}.png",
        mime="image/png"
    )

    st.markdown("### Výkon kotla K6")
    fig_k6 = create_line_chart(hours_data_k6, "Výkon kotla K6", "#8CC63F")
    st.pyplot(fig_k6, use_container_width=True)
    st.download_button(
        label="💾 Stiahnuť graf K6",
        data=graf_do_pamate(fig_k6),
        file_name=f"Vykon_K6_{vybrany_datum.strftime('%d_%m_%Y')}.png",
        mime="image/png"
    )

    st.markdown("### Výkon kotla K7")
    fig_k7 = create_line_chart(hours_data_k7, "Výkon kotla K7", "#2B2B2B")
    st.pyplot(fig_k7, use_container_width=True)
    st.download_button(
        label="💾 Stiahnuť graf K7",
        data=graf_do_pamate(fig_k7),
        file_name=f"Vykon_K7_{vybrany_datum.strftime('%d_%m_%Y')}.png",
        mime="image/png"
    )

    st.divider()
    pdf_buf = generuj_pdf(
        vybrany_datum=vybrany_datum,
        prev=prev,
        dodavky=dodavky,
        celkove_dodavky=celkove_dodavky,
        zostatok_stiepky=zostatok_stiepky,
        prev_aktualna_denna_spotreba=prev["aktualna_denna_spotreba"],
        pocet_zostavajucich_dni=pocet_zostavajucich_dni,
        datum_vycerpania=datum_vycerpania,
        priem_vykon_k6=priem_vykon_k6,
        priem_vykon_k7=priem_vykon_k7,
        priem_vykon_spolu=priem_vykon_spolu,
        pocet_h_k6=pocet_h_k6,
        pocet_h_k7=pocet_h_k7,
        fig_prevadzka=fig_prevadzka,
        fig_k6=fig_k6,
        fig_k7=fig_k7,
        fmt=fmt,
    )
    st.download_button(
        label="📄 Stiahnuť kompletný report (PDF)",
        data=pdf_buf,
        file_name=f"Report_Cigel_{vybrany_datum.strftime('%d_%m_%Y')}.pdf",
        mime="application/pdf",
        type="primary",
    )

    st.markdown("""
    <br>
    <p style="color:red;"><b>Dodávka štiepky od p. Ing. Jankulu je stanovená len odhadom. 
    Skutočné dodané množstvo bude uvedené na faktúre.</b></p>
    """, unsafe_allow_html=True)



