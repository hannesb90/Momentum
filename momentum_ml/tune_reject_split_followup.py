"""
tune_reject_split_followup.py – Uppföljning på tune_reject_split_diagnosis.py
(som visade att degenererade splits beror på genuint saknad signal, inte
regularisering). Fyra frågor:

  precursors  – vilka driftmått FÖREGÅR en degenererad split (trend i
                feature-drift/targetvarians/AUC + marknadsregim i
                splittarna före)?
  windows     – förbättrar ett kortare (130v) eller recency-viktat
                träningsfönster de degenererade perioderna?
  regime      – global modell (all träningsdata) vs regimanpassad modell
                (bara tränings-veckor i SAMMA regim som slutet av
                träningsfönstret, dvs. utan framåtblick)?
  abstention  – hade modellen bort AVSTÅ från att rangordna (hålla
                jämviktad/benchmark-exponering i stället) i lågt-AUC-
                perioder, baserat på validerings-AUC (känt FÖRE
                testfönstret, ingen framåtblick)?
  abstention_sweep – samma fråga som abstention, men svept över flera
                AUC-trösklar (0,50-0,54) + explicit verifiering att varje
                splits train/val/test-fönster är strikt kronologiskt
                ordnat (ingen framåtblick i beslutsunderlaget). Kräver att
                'abstention' körts minst en gång först (återanvänder
                results/reject_split_abstention.csv, ingen omträning).

Samma datakälla-caveat som tune_reject_split_diagnosis.py: nyaste
TILLGÄNGLIGA feature-cache, inte en bit-identisk reproduktion av en
specifik natts produktionskörning.

    /opt/momentum/venv/bin/python3 tune_reject_split_followup.py precursors
    /opt/momentum/venv/bin/python3 tune_reject_split_followup.py windows
    /opt/momentum/venv/bin/python3 tune_reject_split_followup.py regime
    /opt/momentum/venv/bin/python3 tune_reject_split_followup.py abstention
    /opt/momentum/venv/bin/python3 tune_reject_split_followup.py abstention_sweep
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, ".")
import config
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits
from backtest.calibration_check import prob_resolution_stats
from backtest.regime import classify_regimes
from data.data_loader import fetch_weekly_data
from tune_reject_split_diagnosis import _load_dev_df, _slice, _train_one, BASELINE

COMPARISON_CSV = Path("results/reject_split_comparison.csv")


def _require_comparison() -> pd.DataFrame:
    if not COMPARISON_CSV.exists():
        raise SystemExit(
            f"{COMPARISON_CSV} saknas - kör 'tune_reject_split_diagnosis.py compare' först.")
    return pd.read_csv(COMPARISON_CSV)


def _regime_series() -> pd.Series:
    print(f"[followup] Hämtar {config.INDEX_BENCHMARK_TICKER} för regimklassificering...")
    data = fetch_weekly_data([config.INDEX_BENCHMARK_TICKER], start=config.START_DATE,
                              end=None, use_cache=True)
    return classify_regimes(data)


# ── 1. Driftmått som föregår degenererade splits ─────────────────────────────

def cmd_precursors():
    df = _require_comparison().sort_values("split").reset_index(drop=True)
    lag_cols = ["feature_drift_mean_abs_z", "target_var_median_by_date",
                "val_auc_best", "nan_rate_mean", "val_score_largest_plateau_frac"]
    for col in lag_cols:
        df[f"{col}_lag1"] = df[col].shift(1)
        df[f"{col}_lag2"] = df[col].shift(2)
        df[f"{col}_delta1"] = df[col] - df[f"{col}_lag1"]

    print(f"{'='*100}\nTidsserie runt de degenererade splittarna (± 3)\n{'='*100}")
    degenerate_idx = df.index[df["degenerate"]].tolist()
    window_idx = sorted(set(
        i for d in degenerate_idx for i in range(max(0, d - 3), min(len(df), d + 2))))
    cols_show = ["split", "val_start", "degenerate", "feature_drift_mean_abs_z",
                 "target_var_median_by_date", "val_auc_best", "val_score_largest_plateau_frac"]
    print(df.loc[window_idx, cols_show].to_string(index=False))

    print(f"\n{'='*100}\nKorrelation (lag1/lag2/delta1) mot 'degenerate' - {len(degenerate_idx)} degenererade "
          f"av {len(df)} (litet stickprov, tolka riktning inte p-värden)\n{'='*100}")
    corr_cols = [c for c in df.columns if c.endswith(("_lag1", "_lag2", "_delta1"))]
    corrs = df[corr_cols + ["degenerate"]].corr(numeric_only=True)["degenerate"].drop("degenerate")
    print(corrs.sort_values(key=np.abs, ascending=False).to_string())

    regimes = _regime_series()
    rows = []
    for _, row in df.iterrows():
        val_start = pd.Timestamp(row["val_start"])
        window = regimes[(regimes.index >= val_start - pd.Timedelta(weeks=260))
                          & (regimes.index < val_start)]
        share = window.value_counts(normalize=True).to_dict() if len(window) else {}
        rows.append({
            "split": row["split"], "degenerate": row["degenerate"],
            "train_bear_share": share.get("bear", 0.0),
            "train_bull_share": share.get("bull", 0.0),
            "train_sideways_share": share.get("sideways", 0.0),
        })
    regime_df = pd.DataFrame(rows)
    print(f"\n{'='*100}\nMarknadsregim UNDER TRÄNINGSFÖNSTRET, degenererade vs friska (median)\n{'='*100}")
    print(regime_df.groupby("degenerate")[["train_bear_share", "train_bull_share",
                                            "train_sideways_share"]].median().to_string())
    regime_df.to_csv("results/reject_split_precursors_regime.csv", index=False)
    print("\n[followup] Sparat: results/reject_split_precursors_regime.csv")


# ── 2. Kortare/viktade träningsfönster ────────────────────────────────────────

def _short_window_dates(train_d: pd.DatetimeIndex, weeks: int) -> pd.DatetimeIndex:
    uniq = pd.DatetimeIndex(sorted(set(train_d)))
    keep = set(uniq[-weeks:])
    return pd.DatetimeIndex([d for d in train_d if d in keep])


def _recency_weights(train_sub: pd.DataFrame, half_life_weeks: int = 52) -> np.ndarray:
    dates = train_sub.index
    age_weeks = (dates.max() - dates).days / 7.0
    return np.power(0.5, age_weeks / half_life_weeks).values


def cmd_windows():
    dev_df = _load_dev_df()
    splits = walk_forward_splits(dev_df.index)
    comparison = _require_comparison()
    degenerate_splits = comparison.loc[comparison["degenerate"], "split"].tolist()
    print(f"[followup] Degenererade splits (1-indexerade): {degenerate_splits}\n")

    rows = []
    for split_no in degenerate_splits:
        i = split_no - 1
        train_d, val_d, test_d = splits[i]
        train_sub, X_tr, y_cls_tr, _ = _slice(dev_df, train_d)
        _, X_va, y_cls_va, _ = _slice(dev_df, val_d)
        test_sub, X_te, y_cls_te, y_reg_te = _slice(dev_df, test_d)
        if len(X_te) < 10:
            continue

        def _eval(model, label):
            raw_te = model.predict(X_te)
            auc = None
            if len(set(y_cls_te)) > 1:
                from sklearn.metrics import roc_auc_score
                auc = float(roc_auc_score(y_cls_te, raw_te))
            ic = float(pd.Series(raw_te).corr(pd.Series(y_reg_te), method="spearman"))
            rows.append({"split": split_no, "variant": label, "num_trees": model.num_trees(),
                         "test_auc": auc, "test_rank_ic": ic})
            print(f"  split {split_no} [{label}]: num_trees={model.num_trees()} auc={auc} ic={ic:.4f}")

        model_base, _ = _train_one(X_tr, y_cls_tr, X_va, y_cls_va, BASELINE)
        _eval(model_base, "baseline_260w")

        short_dates = _short_window_dates(train_d, 130)
        train_sub_short, X_tr_s, y_cls_tr_s, _ = _slice(dev_df, short_dates)
        model_short, _ = _train_one(X_tr_s, y_cls_tr_s, X_va, y_cls_va, BASELINE)
        _eval(model_short, "short_130w")

        weights = _recency_weights(train_sub)
        params = {**config.LGBM_PARAMS, "objective": "binary", **BASELINE}
        p = {k: v for k, v in params.items() if k not in ("n_estimators", "early_stopping_rounds")}
        ds_tr = lgb.Dataset(X_tr, label=y_cls_tr, weight=weights)
        ds_va = lgb.Dataset(X_va, label=y_cls_va, reference=ds_tr)
        model_weighted = lgb.train(
            p, ds_tr, num_boost_round=params["n_estimators"], valid_sets=[ds_va],
            callbacks=[lgb.early_stopping(params["early_stopping_rounds"], verbose=False),
                       lgb.log_evaluation(period=-1)])
        _eval(model_weighted, "recency_weighted_260w")

    out = pd.DataFrame(rows)
    out.to_csv("results/reject_split_window_variants.csv", index=False)
    print(f"\n{'='*100}\nMedian per variant (degenererade splits)\n{'='*100}")
    print(out.groupby("variant")[["num_trees", "test_auc", "test_rank_ic"]].median().to_string())


# ── 3. Global modell vs regimanpassad modell ─────────────────────────────────

def cmd_regime():
    dev_df = _load_dev_df()
    splits = walk_forward_splits(dev_df.index)
    comparison = _require_comparison()
    degenerate_splits = comparison.loc[comparison["degenerate"], "split"].tolist()
    regimes = _regime_series()

    rows = []
    for split_no in degenerate_splits:
        i = split_no - 1
        train_d, val_d, test_d = splits[i]
        train_sub, X_tr, y_cls_tr, _ = _slice(dev_df, train_d)
        _, X_va, y_cls_va, _ = _slice(dev_df, val_d)
        test_sub, X_te, y_cls_te, y_reg_te = _slice(dev_df, test_d)
        if len(X_te) < 10:
            continue

        current_regime = regimes.asof(train_d.max())
        matched_dates = pd.DatetimeIndex(
            [d for d in train_d if regimes.get(d, None) == current_regime])
        print(f"  split {split_no}: aktuell regim={current_regime}, "
              f"{len(set(matched_dates))}/{len(set(train_d))} tränings-veckor matchar.")

        def _eval(model, label):
            raw_te = model.predict(X_te)
            auc = None
            if len(set(y_cls_te)) > 1:
                from sklearn.metrics import roc_auc_score
                auc = float(roc_auc_score(y_cls_te, raw_te))
            ic = float(pd.Series(raw_te).corr(pd.Series(y_reg_te), method="spearman"))
            rows.append({"split": split_no, "variant": label, "regime": current_regime,
                         "num_trees": model.num_trees(), "test_auc": auc, "test_rank_ic": ic})
            print(f"    [{label}] num_trees={model.num_trees()} auc={auc} ic={ic:.4f}")

        model_global, _ = _train_one(X_tr, y_cls_tr, X_va, y_cls_va, BASELINE)
        _eval(model_global, "global_all_regimes")

        if len(set(matched_dates)) >= 100 and len(matched_dates) < len(train_d):
            _, X_tr_m, y_cls_tr_m, _ = _slice(dev_df, matched_dates)
            model_regime, _ = _train_one(X_tr_m, y_cls_tr_m, X_va, y_cls_va, BASELINE)
            _eval(model_regime, "regime_matched")
        else:
            print(f"    [regime_matched] hoppar över - för få ({len(set(matched_dates))}) "
                  f"matchande veckor eller matchar hela fönstret.")

    out = pd.DataFrame(rows)
    out.to_csv("results/reject_split_regime_vs_global.csv", index=False)
    print(f"\n{'='*100}\nResultat per split\n{'='*100}")
    print(out.to_string(index=False))


# ── 4. Avstående vid låg signalstyrka ────────────────────────────────────────

def cmd_abstention(threshold: float = 0.52):
    dev_df = _load_dev_df()
    splits = walk_forward_splits(dev_df.index)
    comparison = _require_comparison()

    rows = []
    for _, row in comparison.iterrows():
        i = int(row["split"]) - 1
        train_d, val_d, test_d = splits[i]
        train_sub, X_tr, y_cls_tr, _ = _slice(dev_df, train_d)
        _, X_va, y_cls_va, _ = _slice(dev_df, val_d)
        test_sub, X_te, y_cls_te, y_reg_te = _slice(dev_df, test_d)
        if len(X_te) < 10:
            continue

        model, _ = _train_one(X_tr, y_cls_tr, X_va, y_cls_va, BASELINE)
        raw_te = model.predict(X_te)
        test_sub = test_sub.copy()
        test_sub["_raw"] = raw_te

        equal_weight_ret = float(test_sub["target_return"].mean())
        by_date = []
        for date, g in test_sub.groupby(test_sub.index):
            if len(g) < 10:
                continue
            cutoff = g["_raw"].quantile(0.9)
            top_decile_ret = float(g.loc[g["_raw"] >= cutoff, "target_return"].mean())
            by_date.append(top_decile_ret)
        top_decile_ret = float(np.mean(by_date)) if by_date else None

        rows.append({
            "split": row["split"], "val_auc_best": row["val_auc_best"],
            "would_abstain": bool(row["val_auc_best"] < threshold),
            "test_top_decile_return": top_decile_ret,
            "test_equal_weight_return": equal_weight_ret,
            "picks_beat_equal_weight": (
                (top_decile_ret > equal_weight_ret) if top_decile_ret is not None else None),
        })
        print(f"  split {row['split']}: val_auc_best={row['val_auc_best']:.3f} "
              f"abstain={row['val_auc_best'] < threshold} "
              f"top_decile_ret={top_decile_ret:.4f} equal_weight_ret={equal_weight_ret:.4f}")

    out = pd.DataFrame(rows)
    out.to_csv("results/reject_split_abstention.csv", index=False)

    print(f"\n{'='*100}\nTröskel val_auc_best < {threshold} -> avstå. Resultat:\n{'='*100}")
    for label, sub in (("SKULLE AVSTÅ (låg AUC)", out[out["would_abstain"]]),
                       ("SKULLE HANDLA (normal AUC)", out[~out["would_abstain"]])):
        if sub.empty:
            print(f"{label}: inga splits")
            continue
        beat_rate = sub["picks_beat_equal_weight"].mean()
        print(f"{label} (n={len(sub)}): medel top-decil-avkastning={sub['test_top_decile_return'].mean():.4f}, "
              f"medel jämviktad avkastning={sub['test_equal_weight_return'].mean():.4f}, "
              f"andel splits där modellens urval slog jämvikt={beat_rate:.1%}")


ABSTENTION_CSV = Path("results/reject_split_abstention.csv")
SWEEP_THRESHOLDS = [0.50, 0.51, 0.52, 0.53, 0.54]


def _verify_no_lookahead() -> None:
    """Explicit, programmatisk kontroll (inte bara en kommentar) att varje
    splits train/val/test-fönster är strikt kronologiskt ordnat - dvs att
    val_auc_best (avstående-beslutets underlag) alltid är beräknat på data
    som ligger HELT FÖRE testfönstret, aldrig delvis inom eller efter det."""
    dev_df = _load_dev_df()
    splits = walk_forward_splits(dev_df.index)
    violations = []
    for i, (train_d, val_d, test_d) in enumerate(splits):
        if not (train_d.max() < val_d.min() and val_d.max() < test_d.min()):
            violations.append(i + 1)
    if violations:
        print(f"  [VARNING] {len(violations)} split(ar) med kronologisk överlappning: {violations}")
    else:
        print(f"  OK - samtliga {len(splits)} splits: träning < validering < test, "
              f"strikt kronologiskt, ingen överlappning.")


def cmd_abstention_sweep():
    if not ABSTENTION_CSV.exists():
        raise SystemExit(f"{ABSTENTION_CSV} saknas - kör 'abstention' först.")
    df = pd.read_csv(ABSTENTION_CSV)

    print(f"{'='*100}\nSteg 1: verifiera att beslutsunderlaget (val_auc_best) inte innehåller framåtblick\n{'='*100}")
    _verify_no_lookahead()

    print(f"\n{'='*100}\nSteg 2: svep över AUC-trösklar {SWEEP_THRESHOLDS}\n{'='*100}")
    rows = []
    for t in SWEEP_THRESHOLDS:
        abstain = df[df["val_auc_best"] < t]
        trade = df[df["val_auc_best"] >= t]
        for label, sub in (("abstain", abstain), ("trade", trade)):
            if sub.empty:
                continue
            edge = sub["test_top_decile_return"] - sub["test_equal_weight_return"]
            rows.append({
                "threshold": t, "group": label, "n": len(sub),
                "mean_top_decile_ret": float(sub["test_top_decile_return"].mean()),
                "mean_equal_weight_ret": float(sub["test_equal_weight_return"].mean()),
                "mean_edge": float(edge.mean()),
                "win_rate": float(sub["picks_beat_equal_weight"].mean()),
            })

    sweep = pd.DataFrame(rows)
    print(sweep.to_string(index=False))
    sweep.to_csv("results/reject_split_abstention_sweep.csv", index=False)

    print(f"\n{'='*100}\nRobusthetsbedömning\n{'='*100}")
    abstain_edges = sweep[sweep["group"] == "abstain"].set_index("threshold")["mean_edge"]
    trade_edges = sweep[sweep["group"] == "trade"].set_index("threshold")["mean_edge"]
    for t in SWEEP_THRESHOLDS:
        if t in abstain_edges.index and t in trade_edges.index:
            n_abstain = int(sweep[(sweep["threshold"] == t) & (sweep["group"] == "abstain")]["n"].iloc[0])
            print(f"  tröskel {t:.2f}: abstain-grupp (n={n_abstain}) edge={abstain_edges[t]:+.4f}, "
                  f"trade-grupp edge={trade_edges[t]:+.4f}, "
                  f"skillnad={trade_edges[t]-abstain_edges[t]:+.4f}")
    holds = all(
        abstain_edges.get(t, 0) < trade_edges.get(t, -1) for t in SWEEP_THRESHOLDS
        if t in abstain_edges.index and t in trade_edges.index)
    print(f"\n  Abstain-gruppens edge lägre än trade-gruppens vid ALLA trösklar i svepet: {holds}")
    if any(sweep[sweep["group"] == "abstain"]["n"] < 5):
        print("  OBS: minst en tröskel har <5 splits i abstain-gruppen - litet stickprov, "
              "tolka som riktning/indikation, inte en statistiskt säkerställd effekt.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "precursors"
    {
        "precursors": cmd_precursors,
        "windows": cmd_windows,
        "regime": cmd_regime,
        "abstention": cmd_abstention,
        "abstention_sweep": cmd_abstention_sweep,
    }[cmd]()
