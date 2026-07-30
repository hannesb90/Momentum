"""
tune_precision_recall_calibration.py – Precision/Recall/F1 för köpsignalen
(pred_signal vs realized_signal) + kalibrering per sannolikhetsintervall
(EDGE_RISK_SCENARIO_TESTKO.md Tier 2 #13, [RISK-1], FKO-diagnostiklista).

Ren mätning: ingen ny träning. Bygger FÄRSKA features (samma beprövade
recept som tune_atr_stop.py/tune_cash_drag_atr.py, redan körda framgångsrikt
idag mot samma results/lgbm_model.pkl) i stället för den cachade
results/abstention_features.pkl. **VIKTIGT, upptäckt under utveckling:**
abstention_features.pkl gav en HELT DEGENERERAD prob_up (konstant 0,500,
std=0.0, även EFTER buggmönster 1-fixen (DROP_FEATURES) - inom en enda dag
med 97-104 tickers var min=max=0,500) när den kombinerades med
results/lgbm_model.pkl. Grundorsaken är INTE fullständigt fastställd (troligen
en inkompatibilitet mellan de två separata träningskörningarnas interna
datum-/split-bokföring - abstention_lgbm.pkl:s EGEN träning från samma cache
användes aldrig här, bara features-cachen ihop med ETT ANNAT modellobjekt),
men resultatet höll INTE att lita på. Färska features (denna version) gav
en frisk, varierande prob_up-fördelning - se UTVECKLINGSLOGG för detaljer.
Lärdom: cachead abstention_features.pkl bör INTE återanvändas som genväg
ihop med results/lgbm_model.pkl utan vidare verifiering.

Skiljer sig från Test 8 (tune_rank_calibration.py, decil-vinstfrekvens för
prob_up mot 13v target_return) genom att mäta den FAKTISKA köpbeslutet
(pred_signal = "i topp-N denna vecka", en binär portföljåtgärd) som en
klassificerare mot realized_signal (target_signal, en binär tröskel-etikett).

    /opt/momentum/venv/bin/python3 tune_precision_recall_calibration.py
"""
import sys
sys.path.insert(0, '.')
import config

seg = config.SEGMENTS["large"]
config.RESULTS_DIR = "results"
config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
if "gate_enabled" in seg: config.MOMENTUM_GATE_ENABLED = seg["gate_enabled"]
if "gate_min" in seg: config.MOMENTUM_GATE_MIN = seg["gate_min"]
if "market_filter_exposure" in seg:
    config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
if "forward_weeks" in seg:
    config.FORWARD_WEEKS   = seg["forward_weeks"]
    config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    config.EMBARGO_WEEKS   = seg["embargo_weeks"]

import numpy as np
import pandas as pd

from data.data_loader import (
    fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, attach_fundamentals_features,
    to_model_df, FEATURE_COLS,
)
if "drop_features" in seg:
    dropped_set = set(seg["drop_features"])
    filtered = [c for c in FEATURE_COLS if c not in dropped_set]
    FEATURE_COLS.clear()
    FEATURE_COLS.extend(filtered)

from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.drift_monitor import attach_realized_outcomes


def main():
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment="large", prices=data)
    model_features = {t: f for t, f in feats.items() if config.CAP_TIER_MAP.get(t, "") != "Fond"}

    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None
    print(f"[precision_recall] {len(model_features)} tickers, holdout_start={holdout_start}")

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in model_features.items() if len(f) > 0}
    ensemble = MomentumEnsemble()
    feature_dfs = {t: f.assign(ticker=t) for t, f in model_features.items()}
    sig = build_full_output(preds, None, feature_dfs, ensemble)
    print(f"[precision_recall] prob_up spridning: min={sig['prob_up'].min():.3f} "
          f"max={sig['prob_up'].max():.3f} n_unique={sig['prob_up'].nunique()}")

    sig = attach_realized_outcomes(sig, model_features)
    sig = sig.dropna(subset=["realized_signal"])
    print(f"[precision_recall] {len(sig)} rader med realiserat utfall (target känt).")

    def _period(df, label, start=None, end=None):
        sub = df
        if start is not None:
            sub = sub[sub.index >= start]
        if end is not None:
            sub = sub[sub.index < end]
        if sub.empty:
            print(f"\n  {label}: inga rader.")
            return
        y_true = sub["realized_signal"].astype(int)
        y_pred = sub["pred_signal"].astype(int)
        tp = int(((y_pred == 1) & (y_true == 1)).sum())
        fp = int(((y_pred == 1) & (y_true == 0)).sum())
        fn = int(((y_pred == 0) & (y_true == 1)).sum())
        tn = int(((y_pred == 0) & (y_true == 0)).sum())
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else float("nan")
        base_rate = y_true.mean()
        print(f"\n  {label} (n={len(sub)}, basfrekvens köpvärd={base_rate:.1%}):")
        print(f"    TP={tp} FP={fp} FN={fn} TN={tn}")
        print(f"    Precision={precision:.1%}  Recall={recall:.1%}  F1={f1:.3f}  "
              f"(precision över basfrekvens: {precision - base_rate:+.1%})")

    print("\n" + "=" * 90)
    print("Precision/Recall/F1: pred_signal (köpt i topp-N) vs realized_signal (target träffad)")
    print("=" * 90)
    _period(sig, "Hela perioden")
    if holdout_start is not None:
        _period(sig, "Dev", end=holdout_start)
        _period(sig, "Holdout", start=holdout_start)

    prob_col = "prob_up_calibrated" if "prob_up_calibrated" in sig.columns else "prob_up"
    print("\n" + "=" * 90)
    print(f"Kalibrering per sannolikhetsintervall ({prob_col} vs realized_signal, deciler)")
    print("=" * 90)
    for label, sub in (("Hela perioden", sig),
                        ("Dev", sig[sig.index < holdout_start] if holdout_start is not None else sig),
                        ("Holdout", sig[sig.index >= holdout_start] if holdout_start is not None else sig.iloc[0:0])):
        if sub.empty:
            continue
        sub = sub.copy()
        sub["decile"] = pd.qcut(sub[prob_col].rank(method="first"), 10, labels=False, duplicates="drop")
        grp = sub.groupby("decile").agg(
            n=("realized_signal", "size"),
            pred_mean=(prob_col, "mean"),
            empirisk_andel=("realized_signal", "mean"),
        )
        grp["fel"] = (grp["pred_mean"] - grp["empirisk_andel"]).abs()
        brier = float(((sub[prob_col] - sub["realized_signal"]) ** 2).mean())
        print(f"\n  {label} (Brier-score={brier:.4f}, lägre=bättre, 0,25=att alltid gissa 50%):")
        print(grp.to_string(float_format=lambda x: f"{x:.3f}"))

    print("\n[precision_recall] Klart.")


if __name__ == "__main__":
    main()
