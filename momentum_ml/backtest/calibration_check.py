"""
backtest/calibration_check.py – mäter kalibreringskvalitet, inte bara att
den är gjord.

Kodgranskning 2026-07-23: isotonic calibration (LGBM per walk-forward-split,
LSTM per valideringsfönster) är korrekt implementerad – anpassad på
validering, aldrig på träningsdata (se models/lgbm_model.py:s docstring om
_fit_calibrator). Men KVALITETEN mäts ingenstans i repot: ingen Brier score,
ingen Expected Calibration Error (ECE), inget reliability-diagram. En
kalibrerare kan vara "gjord" men ändå dålig – det syns inte bara för att
sannolikheterna "ser rimliga ut". Kelly-sizingen (models/ensemble.py) är
direkt beroende av att kalibreringen faktiskt håller, så det här är inte
en kosmetisk siffra.

De rena funktionerna (brier_score, expected_calibration_error,
reliability_bins, calibration_report) tar bara numpy-arrayer och testas
utan att ladda en riktig tränad modell. CLI-delen (__main__) återanvänder
samma data-/feature-uppbyggnad som tune_ablation.py och kräver en redan
tränad + sparad modell (results/lgbm_model.pkl).

    python backtest/calibration_check.py large
"""
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402


def brier_score(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Brier score = mean((p - y)^2). Lägre är bättre (0 = perfekt, 0.25 =
    en modell som alltid gissar 50%). sklearn.metrics.brier_score_loss finns,
    men beräkningen är trivial nog att inte dra in ett sklearn-beroende bara
    för det – samma formel."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    if not mask.any():
        return float("nan")
    return float(np.mean((p[mask] - y[mask]) ** 2))


def reliability_bins(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """
    Underlaget för ett reliability-diagram: delar [0,1] i n_bins lika breda
    hinkar, och visar per hink (medel-predikterad sannolikhet, faktisk
    andel positiva utfall, antal observationer). En perfekt kalibrerad
    modell ligger på diagonalen (mean_predicted == actual_frequency i varje
    hink).
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    p, y = p[mask], y[mask]

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # högsta hinken ska inkludera p==1.0 (annars faller den rätt utanför sista högra kanten)
    bin_idx = np.clip(np.digitize(p, edges[1:-1], right=True), 0, n_bins - 1)

    rows = []
    for b in range(n_bins):
        in_bin = bin_idx == b
        n = int(in_bin.sum())
        rows.append({
            "bin_low": edges[b], "bin_high": edges[b + 1], "n": n,
            "mean_predicted": float(p[in_bin].mean()) if n else float("nan"),
            "actual_frequency": float(y[in_bin].mean()) if n else float("nan"),
        })
    return pd.DataFrame(rows)


def expected_calibration_error(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    """
    ECE = viktat medel av |mean_predicted - actual_frequency| per hink,
    viktat på andel observationer i hinken. 0 = perfekt kalibrerad. Tomma
    hinkar bidrar inte (ingen data att döma av).
    """
    bins = reliability_bins(probs, outcomes, n_bins=n_bins)
    total = bins["n"].sum()
    if total == 0:
        return float("nan")
    err = (bins["mean_predicted"] - bins["actual_frequency"]).abs()
    weight = bins["n"] / total
    return float((err.fillna(0.0) * weight).sum())


def prob_resolution_stats(prob_up: np.ndarray, decimals: int = 4) -> dict:
    """
    Mäter om isotonic-kalibreringen har tappat UPPLÖSNING – oavsett hur bra
    Brier/ECE ser ut kan en trappstegsfunktion kollapsa till en bred platå
    (se lgbm_model.py:s prob_raw-kommentar: "vid svag signal kollapsar den
    till en bred platå på basfrekvensen"), där nästan alla bolag får exakt
    samma prob_up och rankningen inom platån blir en godtycklig tie-break.

    n_unique: antal DISTINKTA prob_up-värden (avrundade till `decimals` för
    att inte räkna flyttalsbrus som olika värden).
    largest_plateau_frac: hur stor andel av observationerna som sitter i den
    ENSKILT största platån – hög andel (t.ex. >50%) betyder att merparten av
    urvalet avgörs av tie-break (prob_raw), inte den kalibrerade sannolikheten.
    """
    p = np.asarray(prob_up, dtype=float)
    p = p[np.isfinite(p)]
    if len(p) == 0:
        return {"n": 0, "n_unique": 0, "largest_plateau_frac": float("nan")}
    rounded = np.round(p, decimals)
    _, counts = np.unique(rounded, return_counts=True)
    return {
        "n": int(len(p)),
        "n_unique": int(len(counts)),
        "largest_plateau_frac": float(counts.max() / len(p)),
    }


def calibration_report(
    cls_models: list, calibrators: list, split_starts: list,
    df: pd.DataFrame, val_windows: list, n_bins: int = 10,
) -> pd.DataFrame:
    """
    Brier/ECE FÖRE (rå LGBM-sannolikhet) och EFTER (isotonic-kalibrerad),
    per walk-forward-split OCH aggregerat över alla splits – exakt den
    jämförelsen som avgör om kalibreringen faktiskt tillför något, inte
    bara "sannolikheter som ser rimliga ut".

    cls_models/calibrators/split_starts: samma ordning som
    MomentumLGBM.cls_models/.calibrators/.split_starts (en modell/
    kalibrerare/startdatum per split).
    val_windows: en pd.DatetimeIndex per split, MOTSVARANDE VALIDERINGS-
    fönstret modellen kalibrerades på (samma fönster fit_walk_forward
    använde – reproduceras av CLI-delen via walk_forward_splits, se
    __main__). Kalibreringen anpassades på just detta fönster, så det är
    här "före/efter" är en rättvis jämförelse – ett annat fönster (t.ex.
    test) skulle blanda in modellens generaliseringsförmåga i måttet.
    """
    from features.feature_engineering import FEATURE_COLS

    rows = []
    all_raw, all_cal, all_y = [], [], []
    for cls_model, calibrator, split_start, val_d in zip(cls_models, calibrators, split_starts, val_windows):
        mask = df.index.isin(val_d)
        sub = df[mask]
        if sub.empty:
            continue
        X = sub[FEATURE_COLS].fillna(0).values
        y = sub["target_signal"].values
        raw = cls_model.predict(X)
        cal = calibrator.transform(raw)

        rows.append({
            "split_start": split_start, "n": len(y),
            "brier_before": brier_score(raw, y), "brier_after": brier_score(cal, y),
            "ece_before": expected_calibration_error(raw, y, n_bins), "ece_after": expected_calibration_error(cal, y, n_bins),
        })
        all_raw.append(raw); all_cal.append(cal); all_y.append(y)

    report = pd.DataFrame(rows)
    if all_raw:
        raw_all, cal_all, y_all = np.concatenate(all_raw), np.concatenate(all_cal), np.concatenate(all_y)
        agg = pd.DataFrame([{
            "split_start": "TOTALT", "n": len(y_all),
            "brier_before": brier_score(raw_all, y_all), "brier_after": brier_score(cal_all, y_all),
            "ece_before": expected_calibration_error(raw_all, y_all, n_bins),
            "ece_after": expected_calibration_error(cal_all, y_all, n_bins),
        }])
        report = pd.concat([report, agg], ignore_index=True)
    return report


def print_calibration_report(report: pd.DataFrame) -> None:
    print(f"\n{'='*78}\nKalibrering: Brier score + ECE, före/efter isotonic\n{'='*78}")
    print(f"  {'split':>12} {'n':>7} {'Brier före':>11} {'Brier efter':>12} "
          f"{'ECE före':>9} {'ECE efter':>10}")
    for _, r in report.iterrows():
        label = r["split_start"] if isinstance(r["split_start"], str) else str(pd.Timestamp(r["split_start"]).date())
        print(f"  {label:>12} {r['n']:>7} {r['brier_before']:>11.4f} {r['brier_after']:>12.4f} "
              f"{r['ece_before']:>9.4f} {r['ece_after']:>10.4f}")
    print("\n  Lägre är bättre för alla fyra mått. 'Efter' bör vara <= 'före' "
          "(kalibreringen ska aldrig FÖRSÄMRA). Om inte: undersök varför.")


def plot_reliability_diagram(probs: np.ndarray, outcomes: np.ndarray, save_path: str,
                              n_bins: int = 10, label: Optional[str] = None) -> None:
    """Sparar ett reliability-diagram (predikterat vs faktiskt, med diagonalen
    som referens) – samma matplotlib-mönster som backtester.plot()."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bins = reliability_bins(probs, outcomes, n_bins=n_bins)
    bins = bins.dropna(subset=["mean_predicted", "actual_frequency"])

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfekt kalibrerad")
    ax.plot(bins["mean_predicted"], bins["actual_frequency"], "o-", label=label or "Modell")
    ax.set_xlabel("Predikterad sannolikhet")
    ax.set_ylabel("Faktisk andel positiva utfall")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_title("Reliability-diagram")
    fig.tight_layout()
    fig.savefig(save_path, dpi=120)
    plt.close(fig)
    print(f"  Reliability-diagram sparat: {save_path}")


if __name__ == "__main__":
    import argparse
    from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe
    from features.feature_engineering import build_all_features, attach_categorical_features, to_model_df
    from models.lgbm_model import MomentumLGBM, walk_forward_splits

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("segment", choices=list(config.SEGMENTS.keys()), nargs="?", default=config.DEFAULT_SEGMENT)
    p.add_argument("--n-bins", type=int, default=10)
    p.add_argument("--plot", action="store_true", help="Spara ett reliability-diagram (results/calibration.png)")
    args = p.parse_args()

    seg = config.SEGMENTS[args.segment]
    model_path = f"{seg['results_dir']}/lgbm_model.pkl"
    print(f"[calibration_check] Laddar modell: {model_path}")
    lgbm = MomentumLGBM.load(model_path)

    print("[calibration_check] Bygger features (återanvänder cache om den finns)...")
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    model_df = to_model_df(feats)

    dates = model_df.index.unique().sort_values()
    dev_df = model_df[model_df.index < dates[-config.HOLDOUT_WEEKS]] if len(dates) > config.HOLDOUT_WEEKS else model_df

    splits = walk_forward_splits(dev_df.index)
    val_windows = [val_d for _, val_d, _ in splits][:len(lgbm.cls_models)]

    report = calibration_report(lgbm.cls_models, lgbm.calibrators, lgbm.split_starts, dev_df, val_windows, n_bins=args.n_bins)
    print_calibration_report(report)

    if lgbm.cls_models and lgbm.calibrators:
        from features.feature_engineering import FEATURE_COLS as _FC
        last_val = val_windows[-1] if val_windows else dev_df.index
        last_sub = dev_df[dev_df.index.isin(last_val)]
        if not last_sub.empty:
            last_raw = lgbm.cls_models[-1].predict(last_sub[_FC].fillna(0).values)
            last_cal = lgbm.calibrators[-1].transform(last_raw)
            res = prob_resolution_stats(last_cal)
            print(f"\n  Upplösning (senaste splitten): {res['n_unique']} unika prob_up-värden "
                  f"av {res['n']} observationer, största platå = {res['largest_plateau_frac']:.1%}.")

    if args.plot:
        from features.feature_engineering import FEATURE_COLS
        all_raw, all_y = [], []
        for cls_model, val_d in zip(lgbm.cls_models, val_windows):
            sub = dev_df[dev_df.index.isin(val_d)]
            if sub.empty:
                continue
            all_raw.append(cls_model.predict(sub[FEATURE_COLS].fillna(0).values))
            all_y.append(sub["target_signal"].values)
        raw_all, y_all = np.concatenate(all_raw), np.concatenate(all_y)
        cal_all = np.concatenate([
            calib.transform(cls_model.predict(dev_df[dev_df.index.isin(val_d)][FEATURE_COLS].fillna(0).values))
            for cls_model, calib, val_d in zip(lgbm.cls_models, lgbm.calibrators, val_windows)
            if not dev_df[dev_df.index.isin(val_d)].empty
        ])
        plot_reliability_diagram(raw_all, y_all, f"{seg['results_dir']}/calibration_before.png", label="Före (rå)")
        plot_reliability_diagram(cal_all, y_all, f"{seg['results_dir']}/calibration_after.png", label="Efter (kalibrerad)")
