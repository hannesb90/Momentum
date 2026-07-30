"""
tune_rank_calibration.py – Punkt 8, omskriven för LambdaRank-modellen
(2026-07-29). backtest/calibration_check.py antar fortfarande en binär
klassificerare med isotonic-kalibrering (`.calibrators`) – den finns inte
längre på MomentumLGBM sedan modellen migrerades till ren LambdaRank-
ranking (models/lgbm_model.py). `prob_up` beräknas numera som en
tvärsnittell min-max-normalisering av rank-scoren ("en sorteringsprior"),
INTE en kalibrerad sannolikhet.

Frågan Test 8 skulle svara på gäller fortfarande: är prob_up=0.8
associerat med ~80% vinstfrekvens? För en ranking-modell är rätt mått
inte Brier/ECE mot den naiva prob_up, utan EMPIRISK vinstfrekvens per
rank-decil (samma decil-konstruktion som redan används i träningen,
lgbm_model.py:s y_tr_rel via pd.qcut). Om deciler har en tydlig monoton
relation till faktisk framtida avkastning/vinstfrekvens är rangordningen
i sig meningsfull (bra nyheter för toppN-urval) - men om den naiva
min-max-prob_up avviker mycket från den empiriska vinstfrekvensen per
decil, är det ett kvantitativt mått på hur fel Kelly-sizingen
(models/ensemble.py:s kelly_position_size, som fortfarande tar prob_up
som en riktig sannolikhet) blir.

Körs mot dev-delen (samma HOLDOUT_WEEKS-gräns som huvudpipelinen) över
ALLA walk-forward-splits modellen redan har, återanvänder redan tränad
modell (results/lgbm_model.pkl) - ingen omträning.

    /opt/momentum/venv/bin/python3 tune_rank_calibration.py large
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config

segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
seg     = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
if "drop_features" in seg:
    config.DROP_FEATURES = seg["drop_features"]

from features.feature_engineering import FEATURE_COLS, build_all_features, attach_categorical_features, attach_fundamentals_features, to_model_df
from models.lgbm_model import MomentumLGBM, walk_forward_splits
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

N_DECILES = 10


def decile_calibration_report(cls_models, split_starts, df: pd.DataFrame, val_windows, n_deciles: int = N_DECILES) -> pd.DataFrame:
    all_decile, all_signal, all_return, all_naive_prob = [], [], [], []

    for cls_model, split_start, val_d in zip(cls_models, split_starts, val_windows):
        sub = df[df.index.isin(val_d)]
        if sub.empty:
            continue
        X = sub[FEATURE_COLS].fillna(0).values
        score = cls_model.predict(X, predict_disable_shape_check=True)

        tmp = pd.DataFrame({
            "score": score,
            "target_signal": sub["target_signal"].values,
            "target_return": sub["target_return"].values,
        }, index=sub.index)

        tmp["decile"] = tmp.groupby(level=0)["score"].transform(
            lambda x: pd.qcut(x, n_deciles, labels=False, duplicates="drop") if len(x) >= n_deciles else np.nan
        )
        # Samma formel som lgbm_model.py:s predict() använder för prob_up idag
        tmp["naive_prob_up"] = tmp.groupby(level=0)["score"].transform(
            lambda x: (x - x.min()) / (x.max() - x.min() + 1e-9) if x.max() > x.min() else 0.5
        )

        all_decile.append(tmp["decile"].values)
        all_signal.append(tmp["target_signal"].values)
        all_return.append(tmp["target_return"].values)
        all_naive_prob.append(tmp["naive_prob_up"].values)

    decile = np.concatenate(all_decile)
    signal = np.concatenate(all_signal)
    ret = np.concatenate(all_return)
    naive_prob = np.concatenate(all_naive_prob)

    mask = np.isfinite(decile)
    flat = pd.DataFrame({
        "decile": decile[mask].astype(int),
        "target_signal": signal[mask],
        "target_return": ret[mask],
        "naive_prob_up": naive_prob[mask],
    })

    report = flat.groupby("decile").agg(
        n=("target_signal", "size"),
        empirical_win_rate=("target_signal", "mean"),
        mean_return=("target_return", "mean"),
        mean_naive_prob_up=("naive_prob_up", "mean"),
    ).reset_index()
    report["naive_calibration_error"] = (report["mean_naive_prob_up"] - report["empirical_win_rate"]).abs()
    return report, flat


def print_report(report: pd.DataFrame) -> None:
    print(f"\n{'='*90}\nEmpirisk vinstfrekvens per rank-decil (0=lägst score, {N_DECILES-1}=högst) vs naiv prob_up\n{'='*90}")
    print(f"  {'decile':>6} {'n':>6} {'empirisk vinst%':>16} {'mean_return':>12} {'naiv prob_up':>13} {'|fel|':>8}")
    for _, r in report.iterrows():
        print(f"  {int(r['decile']):>6} {int(r['n']):>6} {r['empirical_win_rate']:>15.1%} "
              f"{r['mean_return']:>11.2%} {r['mean_naive_prob_up']:>13.3f} {r['naive_calibration_error']:>8.3f}")
    spearman = report[["decile", "empirical_win_rate"]].corr(method="spearman").iloc[0, 1]
    print(f"\n  Spearman(decile, empirisk vinstfrekvens) = {spearman:.3f} "
          f"(nära 1.0 = rangordningen bär verklig signal om framtida vinstfrekvens)")
    print(f"  Medel |naiv_prob_up - empirisk_vinstfrekvens| = {report['naive_calibration_error'].mean():.3f} "
          f"-> så mycket är Kelly-sizingens indata fel i snitt, om den tolkas som en sannolikhet.")


if __name__ == "__main__":
    model_path = f"{seg['results_dir']}/lgbm_model.pkl"
    print(f"[rank_calibration] Laddar modell: {model_path}")
    lgbm = MomentumLGBM.load(model_path)

    print("[rank_calibration] Bygger features (återanvänder cache om den finns)...")
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment=segment, prices=data)
    model_df = to_model_df(feats)

    dates = model_df.index.unique().sort_values()
    dev_df = model_df[model_df.index < dates[-config.HOLDOUT_WEEKS]] if len(dates) > config.HOLDOUT_WEEKS else model_df

    splits = walk_forward_splits(dev_df.index)
    val_windows = [val_d for _, val_d, _ in splits][:len(lgbm.cls_models)]

    report, flat = decile_calibration_report(lgbm.cls_models, lgbm.split_starts, dev_df, val_windows)
    print_report(report)

    out_path = f"{seg['results_dir']}/rank_calibration_deciles.csv"
    report.to_csv(out_path, index=False)
    print(f"\n  Sparat: {out_path}")
