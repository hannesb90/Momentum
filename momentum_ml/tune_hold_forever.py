"""
tune_hold_forever.py – Håller modellens köpsignaler som LÅNGSIKTIGA innehav?

Bakgrund (2026-07-22): portföljdisciplinen har gått från kvartalsrotation till
köp-och-behåll (säljvakten är enda säljregeln), men backtesten mäter fortfarande
rotationsstrategin (REBALANCE_WEEKS=13: köp på signal, sälj efter ett kvartal om
signalen släpper). Frågan "vad händer om man köper modellens val och BARA
BEHÅLLER" är obesvarad – och det är den strategi som faktiskt praktiseras.

MEDVETET INTE en 156v-omträning (tune_horizon.py-stil): med data från 2010 finns
~5 oberoende 3-årsfönster (underpowered), de senaste 3 årens signaler kan aldrig
utvärderas på 3-årsutfall, och en lång-horisont-modell vore ändå fel verktyg
(long-term reversal-regimen täcks bättre av value-/quality-screenrarna med riktig
fundamentadata). Här utvärderas i stället den BEFINTLIGA modellens historiska
signaler predict-only: varje NY köpsignal (pred_signal 0→1 för en ticker, dvs
inträdet i ett signal-avsnitt, inte varje vecka signalen ligger kvar – annars
dominerar långlivade innehav med överlappande fönster) mäts som framåtavkastning
över 13/26/52/104/156v, absolut och relativt likaviktat universum-index över
SAMMA fönster (samma survivorship-förbehåll som benchmark.py:s equal_weight_index
– indexet delar universum/data med strategin).

Kohorter per inträdesår, eftersom regimberoendet är själva riskfrågan: en
utvärdering som bara ser 2010-talets bull svarar inte på om köpen håller i andra
regimer. Sista kohorten saknar strukturellt de långa horisonterna (för färsk för
att ha realiserat utfall) – kolumnerna blir "–", väntat.

Kör (Pi:n, prisdata + results/signals.csv räcker – ingen MFN-cache, lätt jobb):
    /opt/momentum/venv/bin/python tune_hold_forever.py
"""
import sys

sys.path.insert(0, ".")
import numpy as np
import pandas as pd

import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)

HORIZONS = (13, 26, 52, 104, 156)   # kvartal, halvår, 1 år, 2 år, 3 år
COHORTS = ((2011, 2014), (2015, 2018), (2019, 2022), (2023, 2099))


def _load_entries() -> pd.DataFrame:
    """results/signals.csv → EN rad per NY köpsignal (pred_signal 0→1)."""
    seg = config.SEGMENTS["large"]
    p = f"{config.anchor(seg['results_dir'])}/signals.csv"
    sig = pd.read_csv(p, usecols=["Date", "ticker", "pred_signal"], parse_dates=["Date"])
    sig = sig.sort_values(["ticker", "Date"])
    prev = sig.groupby("ticker")["pred_signal"].shift(1)
    entries = sig[(sig["pred_signal"] == 1) & (prev.fillna(0) == 0)]
    return entries[["Date", "ticker"]].reset_index(drop=True)


def main():
    seg = config.SEGMENTS["large"]
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()

    # Likaviktat universum-index för relativjämförelsen (survivorship-delat
    # med strategin, se docstring). Kumulativ nivåserie → indexavkastning
    # över godtyckligt fönster = idx[p1]/idx[p0] - 1.
    idx_level = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()

    entries = _load_entries()
    weeks = px.index
    entries["week_pos"] = weeks.searchsorted(entries["Date"], side="left")
    entries = entries[entries["week_pos"] < len(weeks)]
    print(f"{len(entries)} nya köpsignaler (signal-inträden), "
          f"{entries['ticker'].nunique()} bolag, {entries['Date'].min().date()} – "
          f"{entries['Date'].max().date()}.")

    def _stats(sub: pd.DataFrame, h: int):
        """(medel abs, medel excess vs index, andel som slog index, n)"""
        rets, excs = [], []
        for _, row in sub.iterrows():
            p0i, p1i = int(row["week_pos"]), int(row["week_pos"]) + h
            if p1i >= len(weeks):
                continue
            t = row["ticker"]
            if t not in px.columns:
                continue
            p0, p1 = px[t].iloc[p0i], px[t].iloc[p1i]
            if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                continue
            r = p1 / p0 - 1
            b = idx_level.iloc[p1i] / idx_level.iloc[p0i] - 1
            rets.append(r)
            excs.append(r - b)
        if not rets:
            return None
        # MEDIAN-excess, inte medel: aktieavkastning är kraftigt högerskev och
        # medlen domineras helt av enstaka extremvinnare på långa horisonter
        # (första körningen: 156v-medel +1379% vid bara 37% win rate). Medianen
        # svarar på "hur går det TYPISKA köpet", win% på "hur ofta slår man index".
        return (float(np.median(rets)), float(np.median(excs)),
                float(np.mean([e > 0 for e in excs])), len(rets))

    header = (f"  {'kohort':<12}{'n':>6}"
              + "".join(f"{f'{h}v abs':>10}{f'{h}v exc':>10}{f'{h}v win%':>10}" for h in HORIZONS))
    print("\n" + "=" * len(header))
    print("  Köp på NY signal, behåll rakt av – median per horisont, excess vs likaviktat index")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    rows = [("alla", entries)]
    rows += [(f"{a}–{b if b < 2099 else 'idag'}",
              entries[(entries["Date"].dt.year >= a) & (entries["Date"].dt.year <= b)])
             for a, b in COHORTS]
    for label, sub in rows:
        cells = f"  {label:<12}{len(sub):>6}"
        for h in HORIZONS:
            st = _stats(sub, h)
            if st is None:
                cells += f"{'–':>10}{'–':>10}{'–':>10}"
            else:
                m, e, w, n = st
                cells += f"{m:>10.1%}{e:>+10.1%}{w:>9.0%} "
        print(cells)
    print("-" * len(header))
    print("  exc = mot likaviktat universum-index över SAMMA fönster (survivorship-delat).")
    print("  win% = andel köp som slog index. Kohort = inträdesår; sena kohorter saknar")
    print("  strukturellt de långa horisonterna (för färska för realiserat utfall).")


if __name__ == "__main__":
    main()
