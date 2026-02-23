import datetime
import calendar
import math
import io
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

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
# ════════════════════════════════════════════════════════════════
DODAVKY_SHEET_ID = "1MB041dTwz-zfGg6u3wM1XpmrS_ynDe1J"

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
        "sheet_id":   "1FXmRJwlRr6N2u_aZzuzjnn0HHgNEBTem64B1phXl_NM",
        "mesiac_gid": "1425398749",
        "denny_gid":  "759527346",
    },
    3: {
        "sheet_id":   "1YSYltBW8uw3whOxNr3w8KLgvMkE-vqAV1cCeIn8Ymp0",
        "mesiac_gid": "737601644",
        "denny_gid":  None,
    },
    4: {
        "sheet_id":   "1E2gxstdMVwj5X__5qrPuRJgkV5GtqLK6BtmmCc3GE00",
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
    if not gid: return vysledok
    df = nacitaj_gs(DODAVKY_SHEET_ID, gid)
    if df is None: return vysledok

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

def vypocitaj_vydrz_zasoby(pociatocny_stav, spotreba_doteraz, aktualna_denna_spotreba, aktualny_datum):
    zostatok = pociatocny_stav - spotreba_doteraz
    if aktualna_denna_spotreba <= 0: return aktualny_datum + datetime.timedelta(days=9999), 9999
    dni = math.floor(zostatok / aktualna_denna_spotreba)
    return aktualny_datum + datetime.
