"""
tune_otto_valuation_band.py – backtestar "OT Analytics"-metoden (Otto,
otanalytics.se, se konversationen) som en SYSTEMATISK regel: ett bolags EGEN
historiska Börsvärde/EBIT(DA)-multipelband (lägsta<->högsta multipel bolaget
någonsin handlats till) som köp-/sälj-gränser, i stället för en generell
bransch-multipel eller den globala jämförelsekorgen (se
tune_global_relative_value.py, en SYSKON-fråga - den jämför mot ANDRA
bolag, den här jämför bolaget mot SIG SJÄLVT över tid).

Metod (årliga ögonblicksbilder):
  1. Per bolag: årlig (kurs x dagens aktier)/EBIT och /EBITDA, bara år med
     positivt resultat (multipeln är meningslös annars).
  2. "Eget band": LÅG = bolagets egen 10:e percentilen, HÖG = 90:e
     percentilen av dess EGEN multipel-historik (kräver >= 3 lönsamma år,
     annars för tunt för ett band).
  3. Ett givet år: "köpvärd" om ÅRETS multipel <= LÅG-percentilen, "över
     riktkurs" om ÅRETS multipel >= HÖG-percentilen.

TVÅ REGLER TESTAS (event-studie, samma metodik som övriga svep denna
session - median-excess/win% mot likaviktat svenskt index):
  A. KÖP vid egen-historisk-lägsta-multipel -> framåtavkastning?
  B. Framåtavkastning EFTER att ha nått egen-historisk-högsta-multipel
     (stöder det "ta hem vinsten"-tanken, eller fortsätter det upp?)

BEGRÄNSNING (viktig): Ottos EGEN metod använder FRAMÅTBLICKANDE guidade/
estimerade EBIT(DA)-nivåer på den övre/rimliga linjen - ingen systematisk
källa för det finns för hela microcap-universumet, så den här backtesten
använder i stället VARJE ÅRS EGET rapporterade resultat mot samma års
kurs - en BESLÄKTAD men enklare "mean-reversion till egen historisk
multipel"-regel, inte exakt Ottos framåtblickande metod.

Kör (nät krävs, separat datauppsättning från tune_global_relative_value.py):
    /opt/momentum/venv/bin/python tune_otto_valuation_band.py
"""
import sys
import pickle
import time
from pathlib import Path

sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

HORIZONS_WEEKS = [13, 26, 52, 104]
MIN_PROFITABLE_YEARS = 3
LOW_PCT, HIGH_PCT = 0.10, 0.90
CACHE_DIR = Path(__file__).parent / "cache" / "otto_band"


def annual_multiples(ticker: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"{ticker.replace('.', '_')}.pkl"
    if cp.exists():
        return pickle.loads(cp.read_bytes())
    import yfinance as yf
    out = {}
    try:
        tk = yf.Ticker(ticker)
        shares = tk.get_info().get("sharesOutstanding")
        fin = tk.financials
        ebit_by_year, ebitda_by_year = {}, {}
        if fin is not None:
            if "EBIT" in fin.index:
                for c, v in fin.loc["EBIT"].items():
                    if pd.notna(v):
                        ebit_by_year[c.year] = float(v)
            if "EBITDA" in fin.index:
                for c, v in fin.loc["EBITDA"].items():
                    if pd.notna(v):
                        ebitda_by_year[c.year] = float(v)
        d = yf.download(ticker, start="2010-01-01", interval="3mo", auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            close = d["Close"][ticker].dropna()
        else:
            close = d["Close"].dropna()
        close.index = pd.DatetimeIndex(close.index).tz_localize(None)
        yearly_px = close.resample("YE").last().dropna()
        for dt, px in yearly_px.items():
            yr = dt.year
            if shares is None:
                continue
            mcap = float(px) * shares
            ebit, ebitda = ebit_by_year.get(yr), ebitda_by_year.get(yr)
            out[yr] = {
                "date": dt.normalize(), "price": float(px),
                "ebit": ebit, "ebitda": ebitda,
                "mult_ebit": (mcap / ebit) if ebit and ebit > 0 else None,
                "mult_ebitda": (mcap / ebitda) if ebitda and ebitda > 0 else None,
            }
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] {ticker}: {e}")
    df = pd.DataFrame.from_dict(out, orient="index")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(pickle.dumps(df))
    return df


def main():
    tickers, sector_map, cap_map, name_map = load_sweden_universe(
        min_market_cap=["Small Cap", "Micro Cap", "Nano Cap"])
    se_universe = [t for t in tickers if sector_map.get(t) in ("Information Technology", "Health Care")]
    print(f"[tune_otto_valuation_band] {len(se_universe)} svenska IT/Health Care small/micro/nano-bolag - "
          f"bygger multipelhistorik (kan ta lång tid)...")

    per_ticker: dict = {}
    for i, t in enumerate(se_universe, 1):
        df = annual_multiples(t)
        if not df.empty:
            per_ticker[t] = df
        if i % 40 == 0:
            print(f"  ... {i}/{len(se_universe)} klara")
        time.sleep(0.2)
    print(f"  {len(per_ticker)} bolag med giltig data.")

    buy_events, sell_events = [], []
    for t, df in per_ticker.items():
        for col, kind in (("mult_ebit", "EBIT"), ("mult_ebitda", "EBITDA")):
            vals = df[col].dropna()
            if len(vals) < MIN_PROFITABLE_YEARS:
                continue
            low, high = vals.quantile(LOW_PCT), vals.quantile(HIGH_PCT)
            for yr, row in df.iterrows():
                m = row[col]
                if m is None or pd.isna(m):
                    continue
                if m <= low:
                    buy_events.append({"ticker": t, "year": yr, "date": row["date"],
                                       "metric": kind, "mult": m, "low": low, "high": high})
                if m >= high:
                    sell_events.append({"ticker": t, "year": yr, "date": row["date"],
                                        "metric": kind, "mult": m, "low": low, "high": high})
            break  # föredra EBIT om den har nog data, annars EBITDA (redan sorterat i loopen)

    buy_df = pd.DataFrame(buy_events)
    sell_df = pd.DataFrame(sell_events)
    print(f"\n[tune_otto_valuation_band] {len(buy_df)} 'köpvärd' (egen-historisk-lägsta-multipel)-händelser, "
          f"{len(sell_df)} 'över riktkurs' (egen-historisk-högsta-multipel)-händelser.")
    if buy_df.empty and sell_df.empty:
        print("Inga händelser - avbryter.")
        return

    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx_level = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    weeks = px.index

    def _fwd_excess(ticker, date, h):
        pos = weeks.searchsorted(date, side="left")
        p1i = pos + h
        if ticker not in px.columns or pos >= len(weeks) or p1i >= len(weeks):
            return None
        p0, p1 = px[ticker].iloc[pos], px[ticker].iloc[p1i]
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            return None
        r = p1 / p0 - 1
        b = idx_level.iloc[p1i] / idx_level.iloc[pos] - 1
        return r - b

    def _print_table(label, df):
        header = (f"  {'grupp':<18}{'n':>6}"
                  + "".join(f"{f'{h}v exc':>10}{f'{h}v win%':>9}{f'{h}v n':>7}" for h in HORIZONS_WEEKS))
        print("\n" + "=" * len(header))
        print(f"  {label}")
        print("=" * len(header))
        print(header)
        print("-" * len(header))
        cells = f"  {'händelse':<18}{len(df):>6}"
        for h in HORIZONS_WEEKS:
            excs = [_fwd_excess(r["ticker"], r["date"], h) for _, r in df.iterrows()]
            excs = [e for e in excs if e is not None]
            if excs:
                cells += f"{np.median(excs):>+10.1%}{np.mean([e>0 for e in excs]):>8.0%} {len(excs):>7}"
            else:
                cells += f"{'–':>10}{'–':>9}{'–':>7}"
        print(cells)
        print("-" * len(header))

    if not buy_df.empty:
        _print_table("A. KÖP-disciplin: pris vid egen-historisk-LÄGSTA multipel -> framåtavkastning",
                     buy_df)
    if not sell_df.empty:
        _print_table("B. SÄLJ-disciplin: pris vid egen-historisk-HÖGSTA multipel -> framåtavkastning EFTERÅT",
                     sell_df)

    print("\n  Läsning: (A) positiv excess stöder 'köp vid egen-historisk-billigast'.")
    print("  (B) NEGATIV excess efter en högsta-multipel-händelse stöder 'ta hem vinsten' -")
    print("  fortsätter det i stället uppåt (positiv excess) är 'sälj vid riktkurs' fel råd,")
    print("  bolaget kan vara i en genuin omvärdering som INTE återgår till det gamla bandet.")
    print("  OBS bakåtblickande TTM-approximation, se docstring - inte exakt Ottos framåtblickande metod.")


if __name__ == "__main__":
    main()
