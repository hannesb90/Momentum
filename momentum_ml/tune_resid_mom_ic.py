"""
tune_resid_mom_ic.py – Solo-IC-validering av `resid_mom` (residual-momentum,
Blitz-Huij-Martens), samma disciplin som tune_fundamentals.py/UTVECKLINGSLOGG
#119 tillämpade på Börsdata-featuresen. [EDGE-1] i
docs/EDGE_RISK_SCENARIO_TESTKO.md.

BAKGRUND (kodkommentar, features/feature_engineering.py:250-256): `resid_mom`
byggdes om från en aritmetisk-summa-approximation till korrekt GEOMETRISK
kedjning av 48v residual-avkastning. Kommentaren varnar: "modellen är tränad
på DEN GAMLA (aritmetisk summa) skalan - kräver omträning innan denna variant
faktiskt syns i signalerna". DENNA körning har FÖRST verifierat mtime-kedjan:

    features/feature_engineering.py   2026-07-28 23:20:42  (senaste ändring)
    results/abstention_features.pkl   2026-07-29 11:23:39  (byggd EFTER fixen)
    results/lgbm_model.pkl            2026-07-29 15:39:41  (tränad EFTER fixen)
    results/lgbm_model_serving.pkl    2026-07-30 06:47:37  (tränad EFTER fixen)

Dvs: till skillnad från vad kodkommentaren (skriven vid fix-tillfället) antydde
har den nuvarande produktionsmodellen (Test 10-kombinerade varianten,
29 juli 15:39) FAKTISKT tränats på den korrigerade (geometriska) featuren -
"kräver omträning"-varningen är sannolikt redan inaktuell. Detta scriptet
löser INTE den frågan direkt (ingen jämförelse gammal/ny modellversion görs
här) - det är en separat, egen slutsats loggad i UTVECKLINGSLOGG.md. Detta
scriptets egentliga syfte är den ANDRA halvan av EDGE-1: `resid_mom` har,
till skillnad från Börsdata-featuresen (#119) och gap-familjen (#106 m.fl.),
ALDRIG fått en egen isolerad IC-validering - bara ingått i fullmodellens
FEATURE_COLS utan att någon frågat "bär den egen prediktiv kraft, ensam?".

METOD (kausal, ingen ny datahämtning): återanvänder den redan cachade
`results/abstention_features.pkl` (byggd av `tune_abstention_gate.py fetch`,
large-segmentet, 175 tickers, 2012-2025, redan verifierad att innehålla
BÅDE `resid_mom` och `target_return` per ticker/vecka). Per handelsdatum:
Spearman-rankkorrelation (IC) mellan `resid_mom` och `target_return` över
tvärsnittet (tickers med giltiga värden den veckan, min 10). Rapporteras
poolat (medel av per-datum-IC + t-stat), per årskohort (teckenstabilitet,
samma bar som #119: |IC|>=0.05 med samma tecken), samt separat för DEV
(< HOLDOUT_WEEKS från sista datum) och den frusna HOLDOUT-perioden - samma
ärliga uppdelning som resten av projektet. Kvintilspread (Q5-Q1 medel
target_return) per datum, snittad, som sekundärt mått.

Kör (kräver bara pandas/numpy/scipy, inget LightGBM, ingen träning):
    /opt/momentum/venv/bin/python3 tune_resid_mom_ic.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config

FEATURES_PKL = Path("results/abstention_features.pkl")
FEATURE = "resid_mom"
TARGET = "target_return"
HOLDOUT_WEEKS = int(getattr(config, "HOLDOUT_WEEKS", 104))
MIN_CROSS_SECTION = 10   # min antal tickers med giltiga värden för att räkna en veckas IC


def _per_date_ic_and_spread(panel: pd.DataFrame) -> pd.DataFrame:
    """panel: MultiIndex (Date, ticker) med kolumnerna FEATURE/TARGET.
    Returnerar en per-datum-DataFrame med ic, q5m1, n."""
    rows = []
    for date, g in panel.groupby(level=0):
        g = g.dropna(subset=[FEATURE, TARGET])
        if len(g) < MIN_CROSS_SECTION:
            continue
        ic = g[FEATURE].rank().corr(g[TARGET].rank())
        q5 = g[g[FEATURE] >= g[FEATURE].quantile(0.8)][TARGET].mean()
        q1 = g[g[FEATURE] <= g[FEATURE].quantile(0.2)][TARGET].mean()
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
    avg_n = df["n"].mean()
    print(f"  {label:<28} veckor={n_weeks:>4}  medel-tickers/v={avg_n:>5.0f}  "
          f"IC={mean_ic:>+7.4f}  t={t:>+6.2f}  %positiv={pct_pos:>6.1%}  Q5-Q1={q5m1:>+7.2%}")


def main() -> None:
    if not FEATURES_PKL.exists():
        print(f"{FEATURES_PKL} saknas - kör 'python3 tune_abstention_gate.py fetch' först "
              "(large-segmentet, bygger den delade feature-cachen).")
        return

    model_features = pd.read_pickle(FEATURES_PKL)
    print(f"[data] {len(model_features)} tickers laddade ur {FEATURES_PKL}")

    frames = []
    for ticker, df in model_features.items():
        if FEATURE not in df.columns or TARGET not in df.columns:
            continue
        sub = df[[FEATURE, TARGET]].copy()
        sub["ticker"] = ticker
        frames.append(sub)
    panel = pd.concat(frames)
    panel.index.name = "Date"
    panel = panel.set_index("ticker", append=True)
    panel = panel[panel.index.get_level_values("Date").notna()]

    all_dates = panel.index.get_level_values("Date").unique().sort_values()
    holdout_start = all_dates[-1] - pd.Timedelta(weeks=HOLDOUT_WEEKS)
    dev_panel = panel[panel.index.get_level_values("Date") < holdout_start]
    holdout_panel = panel[panel.index.get_level_values("Date") >= holdout_start]

    print(f"[period] {all_dates[0].date()} -> {all_dates[-1].date()}  "
          f"(holdout fryst från {holdout_start.date()}, HOLDOUT_WEEKS={HOLDOUT_WEEKS})")

    print("\n" + "=" * 96)
    print(f"  {FEATURE.upper()} SOLO-IC (Spearman, tvärsnitt per datum, mot {TARGET})")
    print("=" * 96)
    all_res = _per_date_ic_and_spread(panel)
    dev_res = _per_date_ic_and_spread(dev_panel)
    hold_res = _per_date_ic_and_spread(holdout_panel)
    _summ(all_res, "Hela perioden")
    _summ(dev_res, "DEV (före holdout)")
    _summ(hold_res, "HOLDOUT (fryst)")

    print("\n  Per årskohort (hela perioden, teckenstabilitet):")
    all_res_y = all_res.copy()
    all_res_y["year"] = all_res_y.index.year
    for y, g in all_res_y.groupby("year"):
        if len(g) < 8:   # för få veckor det året för en meningsfull siffra
            continue
        print(f"    {y}: IC={g['ic'].mean():>+7.4f}  (veckor={len(g)}, "
              f"%positiv={(g['ic'] > 0).mean():>5.1%})")

    print("""
  Dom (samma bar som #119/tune_fundamentals.py): |IC| >= 0.05 MED SAMMA TECKEN
  över kohorterna + positiv Q5-Q1 i DEV OCH HOLDOUT = resid_mom bär genuin,
  egen prediktiv kraft. IC ~0 eller tecken-instabilt = featuren tillför inget
  isolerat (kan ändå bära interaktions-/icke-linjärt värde i fullmodellen,
  se samma reservation som #119 gjorde för Börsdata-måtten - detta är en
  UNIVARIAT analys, inte en fullmodells-ablation).""")


if __name__ == "__main__":
    main()
