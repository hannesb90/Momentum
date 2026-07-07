"""
tune_fundamentals.py – Har fundamenta-features (F-score, fundamental momentum)
prediktiv kraft för svenska aktier? IC-validering INNAN de får påverka köp.

Metod (kausal):
  · Årsrapport för räkenskapsår Y antas känd senast 1 MAJ år Y+1 (konservativt –
    de flesta publiceras feb–mars). Score-datum = första handelsveckan efter.
  · Framåtavkastning 26v/52v från score-datumet, MINUS likaviktade kohortens
    snitt samma fönster (excess = tvärsnittsjämförelse, som modellen jobbar).
  · Spearman-IC per mått + kvintilspread (Q5−Q1), poolat och per årskohort.

Tolkningsguide: |IC| ≥ 0.05 med stabilt tecken över kohorter och positiv
kvintilspread = värd att ta in i kvant-screenern. IC ~0 = axeln ger inget här.

Kör på Pi:n när backfill+build körts:
    /opt/momentum/venv/bin/python -m altdata.fundamentals build
    /opt/momentum/venv/bin/python tune_fundamentals.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config
from data.data_loader import fetch_weekly_data

METRICS = ["f_score", "rev_growth", "rev_accel", "margin_delta", "ni_growth", "roa"]
HORIZONS = [26, 52]


def main():
    fp = Path(config.anchor(config.RESULTS_DIR)) / "fundamentals.csv"
    if not fp.exists():
        print("fundamentals.csv saknas – kör 'python -m altdata.fundamentals build' först.")
        return
    fund = pd.read_csv(fp)
    tickers = sorted(fund["ticker"].unique())
    print(f"{len(fund)} bolagsår · {len(tickers)} bolag · mått: {', '.join(METRICS)}")

    data = fetch_weekly_data(tickers, start="2015-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if d is not None and "Close" in d}).sort_index()
    px.index = pd.to_datetime(px.index)
    print(f"prisdata: {px.shape[1]} tickers")

    rows = []
    for _, r in fund.iterrows():
        tk = r["ticker"]
        if tk not in px.columns:
            continue
        t0 = pd.Timestamp(int(r["year"]) + 1, 5, 1)      # känd senast 1 maj året efter
        s = px[tk].dropna()
        idx0 = s.index.searchsorted(t0)
        if idx0 >= len(s):
            continue
        row = dict(r)
        row["t0"] = s.index[idx0]
        for h in HORIZONS:
            if idx0 + h < len(s):
                row[f"fwd_{h}"] = s.iloc[idx0 + h] / s.iloc[idx0] - 1
        rows.append(row)
    ev = pd.DataFrame(rows).dropna(subset=["fwd_26"], how="all")
    if ev.empty:
        print("Inga matchande pris-fönster än (för färsk data?).")
        return

    # Excess mot årskohortens likaviktade snitt (tvärsnitt, som modellen jobbar).
    for h in HORIZONS:
        col = f"fwd_{h}"
        if col in ev:
            ev[f"x_{h}"] = ev[col] - ev.groupby("year")[col].transform("mean")

    print("\n" + "=" * 74)
    print("  FUNDAMENTA-IC (excess mot årskohort · Spearman)")
    print("=" * 74)
    print(f"  {'mått':<14}{'n':>5} | {'IC 26v':>8} {'Q5−Q1':>8} | {'IC 52v':>8} {'Q5−Q1':>8} | per-år-IC (52v)")
    print("  " + "-" * 72)
    for m in METRICS:
        sub = ev.dropna(subset=[m])
        if len(sub) < 20:
            print(f"  {m:<14}{len(sub):>5} | (för få observationer)")
            continue
        cells = []
        for h in HORIZONS:
            xs = sub.dropna(subset=[f"x_{h}"])
            if len(xs) < 20:
                cells += ["     n/a", "     n/a"]
                continue
            ic = xs[m].rank().corr(xs[f"x_{h}"].rank())
            q5 = xs[xs[m] >= xs[m].quantile(0.8)][f"x_{h}"].mean()
            q1 = xs[xs[m] <= xs[m].quantile(0.2)][f"x_{h}"].mean()
            cells += [f"{ic:>+8.3f}", f"{q5 - q1:>+7.1%}"]
        per_year = []
        for y, g in sub.dropna(subset=["x_52"]).groupby("year"):
            if len(g) >= 15:
                per_year.append(f"{y}:{g[m].rank().corr(g['x_52'].rank()):+.2f}")
        print(f"  {m:<14}{len(sub):>5} | {cells[0]} {cells[1]} | {cells[2]} {cells[3]} | {' '.join(per_year)}")

    print("""
  Dom: |IC| ≥ 0.05 med SAMMA tecken över kohorterna och positiv Q5−Q1 → ta in
  måttet i kvant-screenern (viktad komponent, aldrig ensam köpgrund). IC ~0 →
  axeln tillför inget för svensk huvudlista – då vet vi det, till priset av en
  backfill. OBS: få kohorter (3–4 år) = svag statistik; kräv konsistens, inte
  bara poolad signifikans.""")


if __name__ == "__main__":
    main()
