"""
tune_riskadj_momentum_ic.py – Riskjusterad ("Sharpe-liknande") momentum som
RANKNINGSFEATURE, inte bara positionsstorlek. [EDGE-4] i
docs/EDGE_RISK_SCENARIO_TESTKO.md.

BAKGRUND: MODELLANALYS.md §5 noterar att volatilitetsskalning idag bara
finns på POSITIONS-/PORTFÖLJNIVÅ (inverse_vol sizing, vol-target-overlay),
aldrig vid URVALET. Kandidatfeature: `mom_12_1 / rvol_26w` (riskjusterad
12-1-momentum) och `roc_13w / rvol_13w` (riskjusterad kortsiktig momentum),
jämförda mot sina råa (icke-riskjusterade) motsvarigheter.

METOD: samma cachade panel/mönster som #121 (resid_mom) och #122
(quality x momentum) - `results/abstention_features.pkl`, large-segmentet,
per-datum tvärsnitts-Spearman-IC mot `target_return`, DEV/HOLDOUT-uppdelning.

Kör:
    /opt/momentum/venv/bin/python3 tune_riskadj_momentum_ic.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config

FEATURES_PKL = Path("results/abstention_features.pkl")
TARGET = "target_return"
HOLDOUT_WEEKS = int(getattr(config, "HOLDOUT_WEEKS", 104))
MIN_CROSS_SECTION = 10

RAW_COLS = ["mom_12_1", "roc_13w", "rvol_13w", "rvol_26w", TARGET]


def _load_panel() -> pd.DataFrame:
    model_features = pd.read_pickle(FEATURES_PKL)
    frames = []
    for ticker, df in model_features.items():
        cols = [c for c in RAW_COLS if c in df.columns]
        if len(cols) < len(RAW_COLS):
            continue
        sub = df[cols].copy()
        sub["ticker"] = ticker
        frames.append(sub)
    panel = pd.concat(frames)
    panel.index.name = "Date"
    panel = panel.set_index("ticker", append=True)
    panel = panel[panel.index.get_level_values("Date").notna()]
    # Riskjusterade varianter. Vol-golv (1e-4 ~ 1bp/vecka) undviker division
    # med nära-noll-vol som annars ger extremvärden.
    panel["mom_12_1_riskadj"] = panel["mom_12_1"] / panel["rvol_26w"].clip(lower=1e-4)
    panel["roc_13w_riskadj"] = panel["roc_13w"] / panel["rvol_13w"].clip(lower=1e-4)
    return panel


def _per_date_ic(panel: pd.DataFrame, feature_col: str) -> pd.DataFrame:
    rows = []
    for date, g in panel.groupby(level=0):
        g = g.dropna(subset=[feature_col, TARGET])
        if len(g) < MIN_CROSS_SECTION:
            continue
        ic = g[feature_col].rank().corr(g[TARGET].rank())
        q5 = g[g[feature_col] >= g[feature_col].quantile(0.8)][TARGET].mean()
        q1 = g[g[feature_col] <= g[feature_col].quantile(0.2)][TARGET].mean()
        rows.append({"date": date, "ic": ic, "q5m1": q5 - q1, "n": len(g)})
    return pd.DataFrame(rows).set_index("date").sort_index()


def _summ(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        print(f"  {label:<28} (inga giltiga veckor)")
        return
    ic = df["ic"].dropna()
    n_weeks = len(ic)
    mean_ic = ic.mean()
    se = ic.std(ddof=1) / np.sqrt(n_weeks) if n_weeks > 1 else np.nan
    t = mean_ic / se if se and np.isfinite(se) and se > 0 else np.nan
    pct_pos = (ic > 0).mean()
    q5m1 = df["q5m1"].mean()
    print(f"  {label:<28} veckor={n_weeks:>4}  IC={mean_ic:>+7.4f}  t={t:>+6.2f}  "
          f"%positiv={pct_pos:>6.1%}  Q5-Q1={q5m1:>+7.2%}")


def main() -> None:
    if not FEATURES_PKL.exists():
        print(f"{FEATURES_PKL} saknas.")
        return
    panel = _load_panel()
    all_dates = panel.index.get_level_values("Date").unique().sort_values()
    holdout_start = all_dates[-1] - pd.Timedelta(weeks=HOLDOUT_WEEKS)
    dev_panel = panel[panel.index.get_level_values("Date") < holdout_start]
    hold_panel = panel[panel.index.get_level_values("Date") >= holdout_start]
    print(f"[period] {all_dates[0].date()} -> {all_dates[-1].date()}  "
          f"(holdout fryst från {holdout_start.date()})")

    pairs = [("mom_12_1", "mom_12_1_riskadj", "12-1-momentum"),
             ("roc_13w", "roc_13w_riskadj", "13v-momentum (kort)")]
    for raw, adj, label in pairs:
        print("\n" + "=" * 96)
        print(f"  {label}: RÅ vs RISKJUSTERAD (/rvol)")
        print("=" * 96)
        for col, sub in ((raw, "RÅ"), (adj, "RISKJUSTERAD")):
            print(f"\n  -- {col} ({sub}) --")
            _summ(_per_date_ic(panel, col), "Hela perioden")
            _summ(_per_date_ic(dev_panel, col), "DEV (före holdout)")
            _summ(_per_date_ic(hold_panel, col), "HOLDOUT (fryst)")

    print("""
  Dom: |IC| >= 0.05 med samma tecken + positiv Q5-Q1 i DEV OCH HOLDOUT.
  Riskjustering "vinner" om dess IC/Q5-Q1 är TYDLIGT och KONSEKVENT bättre
  än den råa varianten i BÅDA DEV och HOLDOUT - inte bara pooled (samma
  disciplin som #119/#121/#122).""")


if __name__ == "__main__":
    main()
