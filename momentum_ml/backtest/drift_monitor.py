"""
backtest/drift_monitor.py – Modell-drift-monitoring.

Jämför modellens prediktioner mot realiserade utfall över ett rullande
fönster och flaggar när prestandan glider under DRIFT_AUC_FLOOR.
Realiserade utfall hämtas från samma target_signal/target_return-kolumner
som feature_engineering.py redan beräknar (forward-looking, byggda med
config.FORWARD_WEEKS/RETURN_THRESHOLD), så drift utvärderas mot exakt
samma definition av "rätt svar" som modellen tränades mot.

Tänkt att köras periodiskt vid live-drift (när nästa periods pris blivit
kända), men fungerar lika gärna retroaktivt på en redan körd backtest för
att se om edge:n håller över tid.
"""

from typing import Dict

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def attach_realized_outcomes(
    signals_df: pd.DataFrame,
    feature_dfs: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Slår ihop signals_df (Date-index, kolumn 'ticker') med
    target_signal/target_return från feature_dfs (per ticker).
    Rader utan target (t.ex. de senaste FORWARD_WEEKS veckorna, där
    framtiden ännu inte är känd) får NaN.
    """
    df = signals_df.copy()
    df["realized_return"] = np.nan
    df["realized_signal"] = np.nan

    for ticker, feat_df in feature_dfs.items():
        mask = df["ticker"] == ticker
        sub_idx = df.index[mask]
        df.loc[mask, "realized_return"] = feat_df["target_return"].reindex(sub_idx).values
        df.loc[mask, "realized_signal"] = feat_df["target_signal"].reindex(sub_idx).values

    return df


def rolling_drift_report(
    signals_with_outcomes: pd.DataFrame,
    window_weeks: int = config.DRIFT_WINDOW_WEEKS,
    min_samples: int = config.DRIFT_MIN_SAMPLES,
) -> pd.DataFrame:
    """
    Rullande AUC och hit-rate (pred_signal vs realized_signal) per
    unikt datum. Returnerar en tidsserie med en `flag`-kolumn som är
    True när AUC < DRIFT_AUC_FLOOR.
    """
    df = signals_with_outcomes.dropna(subset=["realized_signal"]).sort_index()
    dates = df.index.unique().sort_values()

    rows = []
    for i, date in enumerate(dates):
        window_dates = dates[max(0, i - window_weeks + 1): i + 1]
        window = df.loc[df.index.isin(window_dates)]

        if len(window) < min_samples or window["realized_signal"].nunique() < 2:
            rows.append({"Date": date, "auc": np.nan, "hit_rate": np.nan, "n": len(window)})
            continue

        auc = roc_auc_score(window["realized_signal"], window["prob_up"])
        hit_rate = (window["pred_signal"] == window["realized_signal"]).mean()
        rows.append({"Date": date, "auc": auc, "hit_rate": hit_rate, "n": len(window)})

    report = pd.DataFrame(rows).set_index("Date")
    report["flag"] = report["auc"] < config.DRIFT_AUC_FLOOR
    return report


def print_drift_summary(report: pd.DataFrame):
    valid = report.dropna(subset=["auc"])
    if valid.empty:
        print("\n[Drift] Inte nog data (eller för få realiserade utfall) för en drift-rapport.")
        return

    latest = valid.iloc[-1]
    n_flagged = int(valid["flag"].sum())

    print("\n" + "=" * 50)
    print(f"  MODELL-DRIFT (rullande {config.DRIFT_WINDOW_WEEKS}v)")
    print("=" * 50)
    print(f"  Senaste AUC       {latest['auc']:.3f}  (golv: {config.DRIFT_AUC_FLOOR:.2f})")
    print(f"  Senaste hit-rate  {latest['hit_rate']:.1%}")
    print(f"  Perioder flaggade {n_flagged}/{len(valid)}")
    if latest["flag"]:
        print("  [VARNING] AUC under golvet just nu – modellen kan ha tappat edge.")
    print("=" * 50)
