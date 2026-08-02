"""
tune_accrual_anomaly.py – [EDGE-11] Accrual-anomalin (Sloan 1996):
(CFO−NI)/tillgångar. Komplement till redan validerade f_score/roa/fcf_margin
(#119) - inte samma mått. Sloans tes: höga periodiseringar (NI >> CFO,
dvs "pappersvinster" utan kassaflödesstöd) förutsäger SVAGARE framtida
avkastning; höga CFO relativt NI ("kassaflödestäckt vinst") förutsäger
STARKARE. `fscore()` (altdata/fundamentals.py) har redan en BINÄR
accruals-komponent (`operating_cash_flow > net_income`) som en av nio
F-score-signaler - detta testar den KONTINUERLIGA versionen isolerat,
samma IC-metodik som #119 (tune_fundamentals.py).

Accrual-ratio = (net_income - operating_cash_flow) / total_assets. LÄGRE
(mer negativt, dvs CFO > NI) = tesen förutsäger BÄTTRE framåtavkastning,
så IC förväntas NEGATIVT om anomalin håller (till skillnad från f_score/
roa/rev_growth m.fl. där HÖGRE = bättre).

Kör på Pi:n (samma förutsättning som #119 - kräver att fundamenta-
rapporterna redan finns cachade via altdata/fundamentals.py::load_reports):

    /opt/momentum/venv/bin/python3 tune_accrual_anomaly.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config
from data.data_loader import fetch_weekly_data
from altdata.fundamentals import load_reports

HORIZONS = [26, 52]


def build_accrual_rows(reports: dict) -> list:
    rows = []
    for tk, years in reports.items():
        ys = sorted(years)
        for y in ys:
            cur = years[y]
            ni = cur.get("net_income")
            cfo = cur.get("operating_cash_flow")
            assets = cur.get("total_assets")
            if ni is None or cfo is None or not assets:
                continue
            rows.append({"ticker": tk, "year": y, "accrual_ratio": (ni - cfo) / assets})
    return rows


def main():
    reports = load_reports()
    rows = build_accrual_rows(reports)
    fund = pd.DataFrame(rows)
    tickers = sorted(fund["ticker"].unique())
    print(f"[accrual] {len(fund)} bolagsår · {len(tickers)} bolag med accrual_ratio beräkningsbar.")

    data = fetch_weekly_data(tickers, start="2015-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if d is not None and "Close" in d}).sort_index()
    px.index = pd.to_datetime(px.index)
    print(f"prisdata: {px.shape[1]} tickers")

    out = []
    for _, r in fund.iterrows():
        tk = r["ticker"]
        if tk not in px.columns:
            continue
        t0 = pd.Timestamp(int(r["year"]) + 1, 5, 1)
        s = px[tk].dropna()
        idx0 = s.index.searchsorted(t0)
        if idx0 >= len(s):
            continue
        row = dict(r)
        row["t0"] = s.index[idx0]
        for h in HORIZONS:
            if idx0 + h < len(s):
                row[f"fwd_{h}"] = s.iloc[idx0 + h] / s.iloc[idx0] - 1
        out.append(row)
    ev = pd.DataFrame(out).dropna(subset=["fwd_26"], how="all")
    if ev.empty:
        print("Inga matchande pris-fönster.")
        return

    for h in HORIZONS:
        col = f"fwd_{h}"
        if col in ev:
            ev[f"x_{h}"] = ev[col] - ev.groupby("year")[col].transform("mean")

    print(f"\n{len(ev)} observationer med pris-matchning, {ev['year'].nunique()} år "
          f"({ev['year'].min()}-{ev['year'].max()}).\n")
    print("=" * 74)
    print("  ACCRUAL-RATIO IC (excess mot årskohort · Spearman) – FÖRVÄNTAT NEGATIVT tecken")
    print("=" * 74)
    for h in HORIZONS:
        xs = ev.dropna(subset=["accrual_ratio", f"x_{h}"])
        if len(xs) < 20:
            print(f"  {h}v: för få observationer (n={len(xs)}).")
            continue
        ic = xs["accrual_ratio"].rank().corr(xs[f"x_{h}"].rank())
        q1 = xs[xs["accrual_ratio"] <= xs["accrual_ratio"].quantile(0.2)][f"x_{h}"].mean()
        q5 = xs[xs["accrual_ratio"] >= xs["accrual_ratio"].quantile(0.8)][f"x_{h}"].mean()
        print(f"  {h:>3}v: n={len(xs):<5} IC={ic:+.3f}  Q1(låg accrual)={q1:+.2%}  "
              f"Q5(hög accrual)={q5:+.2%}  spread(Q1-Q5)={q1-q5:+.2%}")
        per_year = xs.groupby("year").apply(
            lambda g: g["accrual_ratio"].rank().corr(g[f"x_{h}"].rank()) if len(g) >= 10 else None
        ).dropna()
        print(f"        per-år-IC: " + ", ".join(f"{y}:{v:+.2f}" for y, v in per_year.items()))

    print("\n[accrual] Tolkning: tesen håller om IC är NEGATIVT (låg accrual/hög CFO-täckning "
          "-> bättre framåtavkastning) OCH Q1 > Q5 (spread positiv i tabellen ovan) konsekvent "
          "över horisonter/år. |IC| >= 0.05 med rätt tecken = värd att komplettera f_score med.")
    print("[accrual] Klart.")


if __name__ == "__main__":
    main()
