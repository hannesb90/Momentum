"""
tune_quality_momentum_interact.py – Quality x Momentum-interaktion (QMJ-
mönstret, Asness/Frazzini/Pedersen): är momentum starkare/mer robust bland
högkvalitetsbolag? [EDGE-2] i docs/EDGE_RISK_SCENARIO_TESTKO.md.

BAKGRUND: `f_score` (Piotroski, redan validerad solo i #119, IC 0,10-0,14)
och `mom_12_1` finns båda i FEATURE_COLS, men ingen explicit interaktions-
feature mellan dem – bara `interact_report_reaction` (rev_growth x
report_reaction) finns som prejudikat för mönstret i feature_engineering.py.

METOD (kausal, ingen ny datahämtning): återanvänder samma cachade
`results/abstention_features.pkl` som tune_resid_mom_ic.py (large-segmentet,
175 tickers, 2010-2026, redan verifierad att innehålla f_score/mom_12_1/
target_return per ticker/vecka).

Två delfrågor:
  1. Bär `interact = rank(f_score) * rank(mom_12_1)` (per datum, tvärsnitts-
     rank 0..1 på båda benen innan multiplikation) MER solo-IC mot
     target_return än f_score eller mom_12_1 var för sig?
  2. QMJ-testet i sin klassiska form: är momentums EGEN IC högre bland
     högkvalitetsbolag (f_score i övre tertilen den veckan) än bland
     lågkvalitetsbolag (nedre tertilen)? Detta är den mer direkta
     "kvalitet modulerar momentum"-hypotesen - en multiplikativ interaktions-
     score kan dölja detta mönster om den bara mäter "båda höga samtidigt".

Kör (kräver bara pandas/numpy, inget LightGBM, ingen träning):
    /opt/momentum/venv/bin/python3 tune_quality_momentum_interact.py
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


def _load_panel() -> pd.DataFrame:
    model_features = pd.read_pickle(FEATURES_PKL)
    frames = []
    for ticker, df in model_features.items():
        cols = [c for c in ("f_score", "mom_12_1", TARGET) if c in df.columns]
        if len(cols) < 3:
            continue
        sub = df[cols].copy()
        sub["ticker"] = ticker
        frames.append(sub)
    panel = pd.concat(frames)
    panel.index.name = "Date"
    panel = panel.set_index("ticker", append=True)
    return panel[panel.index.get_level_values("Date").notna()]


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


def _momentum_ic_by_quality_bucket(panel: pd.DataFrame) -> None:
    """Klassiska QMJ-testet: mom_12_1s EGEN IC, uppdelat på om bolaget låg i
    övre/nedre f_score-tertilen DEN VECKAN (kausalt, ingen framåtblick)."""
    rows_hi, rows_lo = [], []
    for date, g in panel.groupby(level=0):
        g = g.dropna(subset=["f_score", "mom_12_1", TARGET])
        if len(g) < MIN_CROSS_SECTION:
            continue
        hi_cut = g["f_score"].quantile(2 / 3)
        lo_cut = g["f_score"].quantile(1 / 3)
        g_hi = g[g["f_score"] >= hi_cut]
        g_lo = g[g["f_score"] <= lo_cut]
        if len(g_hi) >= MIN_CROSS_SECTION // 2:
            rows_hi.append({"date": date,
                             "ic": g_hi["mom_12_1"].rank().corr(g_hi[TARGET].rank()),
                             "n": len(g_hi)})
        if len(g_lo) >= MIN_CROSS_SECTION // 2:
            rows_lo.append({"date": date,
                             "ic": g_lo["mom_12_1"].rank().corr(g_lo[TARGET].rank()),
                             "n": len(g_lo)})
    hi_df = pd.DataFrame(rows_hi).set_index("date").sort_index()
    lo_df = pd.DataFrame(rows_lo).set_index("date").sort_index()
    print("\n  QMJ-test: mom_12_1s EGEN IC, betingat på f_score-tertil DEN VECKAN")
    for df, label in ((hi_df, "Momentum-IC | HÖG kvalitet (f_score, övre tertil)"),
                       (lo_df, "Momentum-IC | LÅG kvalitet (f_score, nedre tertil)")):
        ic = df["ic"].dropna()
        if ic.empty:
            print(f"  {label:<52} (inga giltiga veckor)")
            continue
        se = ic.std(ddof=1) / np.sqrt(len(ic)) if len(ic) > 1 else np.nan
        t = ic.mean() / se if se and np.isfinite(se) and se > 0 else np.nan
        print(f"  {label:<52} veckor={len(ic):>4}  IC={ic.mean():>+7.4f}  t={t:>+6.2f}  "
              f"%positiv={(ic > 0).mean():>6.1%}")


def main() -> None:
    if not FEATURES_PKL.exists():
        print(f"{FEATURES_PKL} saknas - kör 'python3 tune_abstention_gate.py fetch' först.")
        return
    panel = _load_panel()
    all_dates = panel.index.get_level_values("Date").unique().sort_values()
    holdout_start = all_dates[-1] - pd.Timedelta(weeks=HOLDOUT_WEEKS)
    dev_panel = panel[panel.index.get_level_values("Date") < holdout_start]
    hold_panel = panel[panel.index.get_level_values("Date") >= holdout_start]
    print(f"[period] {all_dates[0].date()} -> {all_dates[-1].date()}  "
          f"(holdout fryst från {holdout_start.date()})")

    # Tvärsnitts-rank-produkt (per datum), byggd separat innan poolning.
    panel = panel.copy()
    panel["interact_quality_momentum"] = np.nan
    for date, g in panel.groupby(level=0):
        gm = g.dropna(subset=["f_score", "mom_12_1"])
        if len(gm) < MIN_CROSS_SECTION:
            continue
        rq = gm["f_score"].rank(pct=True)
        rm = gm["mom_12_1"].rank(pct=True)
        panel.loc[gm.index, "interact_quality_momentum"] = (rq * rm).values
    dev_panel = panel[panel.index.get_level_values("Date") < holdout_start]
    hold_panel = panel[panel.index.get_level_values("Date") >= holdout_start]

    print("\n" + "=" * 96)
    print("  SOLO-IC: f_score, mom_12_1, interact_quality_momentum (rank-produkt)")
    print("=" * 96)
    for col in ("f_score", "mom_12_1", "interact_quality_momentum"):
        print(f"\n  -- {col} --")
        _summ(_per_date_ic(panel, col), "Hela perioden")
        _summ(_per_date_ic(dev_panel, col), "DEV (före holdout)")
        _summ(_per_date_ic(hold_panel, col), "HOLDOUT (fryst)")

    _momentum_ic_by_quality_bucket(panel)

    print("""
  Dom (samma bar som #119/#121): |IC| >= 0.05 med samma tecken + positiv
  Q5-Q1 i DEV OCH HOLDOUT = värd att bygga in. QMJ-testet läses separat:
  om momentum-IC är TYDLIGT högre i hög-kvalitetsgruppen än i låg-gruppen
  (i BÅDA DEV/HOLDOUT, inte bara pooled) stöds "kvalitet modulerar
  momentum"-hypotesen specifikt, utöver den enklare rank-produkt-frågan.""")


if __name__ == "__main__":
    main()
