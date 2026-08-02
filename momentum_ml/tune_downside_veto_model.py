"""
tune_downside_veto_model.py – ALFA_TESTER_2026-07-30.md #2: separat
nedsidesmodell/downside meta-label. FÖRREGISTRERAT innan körning (ändras
INTE efteråt): primär barriär -40% inom 52v (matchar FORWARD_WEEKS),
sekundär -30% rapporteras men styr inget beslut. Samma informationsmängd
som vid köp (FEATURE_COLS, large-segmentet). Utvärderas som PR-AUC +
kalibrering (INTE portfölj-CAGR som primärt mått, per specen) - jämförs
mot en naiv trailing-volatilitet-baslinje. Skiljer sig från #141/#147
(som reagerar EFTER att positionen redan fallit) genom att detta är en
FÖRE-köp-riskbedömning.

Etikett: träffar priset >= -40% (primär) någon gång inom de kommande 52
veckorna från observationsdatumet (oavsett om target_return vid horisontens
slut ser bra ut - en aktie kan rasa 45% och sedan återhämta sig till +5%,
det räknas ändå som en träffad nedsidesbarriär här, konsekvent med
riskhanteringssyftet: veto:t ska skydda mot RESAN, inte bara slutresultatet).

Walk-forward, purged (samma splits/embargo som produktionen), binär
LightGBM-klassificerare (scale_pos_weight för den sällsynta klassen),
PR-AUC + Brier-score per split, jämfört med en enkel logistisk-liknande
baslinje (bara trailing rvol_26w som ensam prediktor).

    /opt/momentum/venv/bin/python3 tune_downside_veto_model.py
"""
import sys
sys.path.insert(0, ".")
import config

segment = "large"
seg = config.SEGMENTS[segment]

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from features.feature_engineering import to_model_df, FEATURE_COLS
if "drop_features" in seg:
    dropped_set = set(seg["drop_features"])
    filtered = [c for c in FEATURE_COLS if c not in dropped_set]
    FEATURE_COLS.clear()
    FEATURE_COLS.extend(filtered)
from models.lgbm_model import walk_forward_splits
from data.data_loader import load_sweden_universe, fetch_weekly_data, filter_active_universe, filter_liquid_universe
from tune_abstention_gate import _load_state
from tune_lambdarank_common import _slice_sorted

PRIMARY_BARRIER = -0.40
SECONDARY_BARRIER = -0.30
HORIZON_WEEKS = 52


def build_downside_labels(model_features: dict) -> dict:
    """{ticker: pd.Series(index=dates, values=0/1/nan)} - 1 om priset når
    PRIMARY_BARRIER någon gång inom HORIZON_WEEKS veckor framåt, kausalt
    (etiketten är bara känd i efterhand, precis som target_return)."""
    labels = {}
    for t, feat in model_features.items():
        if "Close" not in feat.columns:
            continue
        px = feat["Close"].dropna()
        if len(px) < HORIZON_WEEKS + 5:
            continue
        arr = px.values
        n = len(arr)
        lab = np.full(n, np.nan)
        for i in range(n - HORIZON_WEEKS):
            window = arr[i + 1: i + 1 + HORIZON_WEEKS]
            min_ret = window.min() / arr[i] - 1.0
            lab[i] = 1.0 if min_ret <= PRIMARY_BARRIER else 0.0
        labels[t] = pd.Series(lab, index=px.index)
    return labels


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    # "Close" krävs i model_features för label-byggnaden - hämta separat om saknas.
    for t in list(model_features.keys()):
        if "Close" not in model_features[t].columns and t in data:
            model_features[t] = model_features[t].assign(Close=data[t]["Close"].reindex(model_features[t].index))

    print("[downside_veto] Bygger nedsidesetiketter (-40% inom 52v, kausalt)...")
    labels = build_downside_labels(model_features)

    model_df = to_model_df(model_features)
    lab_rows = []
    for t, s in labels.items():
        d = s.dropna()
        for date, v in d.items():
            lab_rows.append({"ticker": t, "Date": date, "downside_hit": v})
    lab_df = pd.DataFrame(lab_rows).set_index("Date")

    merged = model_df.reset_index().merge(
        lab_df.reset_index(), on=["Date", "ticker"], how="inner"
    ).set_index("Date")
    print(f"[downside_veto] {len(merged)} observationer med etikett. "
          f"Basfrekvens (andel som träffar -40%): {merged['downside_hit'].mean():.1%}")

    all_dates = merged.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = merged[merged.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    print(f"[downside_veto] {len(splits)} splits.\n")

    rows = []
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        val_sub = _slice_sorted(dev_df, val_d)
        test_sub = _slice_sorted(dev_df, test_d)
        if len(test_sub) < 50 or train_sub["downside_hit"].nunique() < 2:
            continue

        X_tr, y_tr = train_sub[FEATURE_COLS].values, train_sub["downside_hit"].values
        X_va, y_va = val_sub[FEATURE_COLS].values, val_sub["downside_hit"].values
        X_te, y_te = test_sub[FEATURE_COLS].values, test_sub["downside_hit"].values
        if y_te.sum() == 0 or y_te.sum() == len(y_te):
            continue   # PR-AUC odefinierad utan båda klasserna i test

        pos_frac = max(y_tr.mean(), 1e-6)
        params = {
            "objective": "binary", "metric": "average_precision",
            "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 30,
            "reg_alpha": 0.1, "reg_lambda": 1.0, "verbosity": -1,
            "seed": config.RANDOM_SEED, "scale_pos_weight": (1 - pos_frac) / pos_frac,
        }
        ds_tr = lgb.Dataset(X_tr, label=y_tr)
        ds_va = lgb.Dataset(X_va, label=y_va, reference=ds_tr)
        model = lgb.train(params, ds_tr, num_boost_round=300, valid_sets=[ds_va],
                          callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(period=-1)])

        p_model = model.predict(X_te)
        pr_auc_model = average_precision_score(y_te, p_model)
        roc_auc_model = roc_auc_score(y_te, p_model) if len(set(y_te)) > 1 else np.nan
        brier_model = brier_score_loss(y_te, p_model)

        # Naiv baslinje: bara trailing rvol_26w (rank-normaliserad till [0,1] som "risk-score")
        rvol_idx = FEATURE_COLS.index("rvol_26w") if "rvol_26w" in FEATURE_COLS else None
        if rvol_idx is not None:
            rvol_te = X_te[:, rvol_idx]
            rank = pd.Series(rvol_te).rank(pct=True).fillna(0.5).values
            pr_auc_naive = average_precision_score(y_te, rank)
            roc_auc_naive = roc_auc_score(y_te, rank) if len(set(y_te)) > 1 else np.nan
        else:
            pr_auc_naive = roc_auc_naive = np.nan

        rows.append({
            "split": i + 1, "n_test": len(test_sub), "base_rate": y_te.mean(),
            "pr_auc_model": pr_auc_model, "roc_auc_model": roc_auc_model, "brier_model": brier_model,
            "pr_auc_naive_rvol": pr_auc_naive, "roc_auc_naive_rvol": roc_auc_naive,
        })
        print(f"  split {i+1}/{len(splits)}: n={len(test_sub)} basfrekvens={y_te.mean():.1%} "
              f"PR-AUC(modell)={pr_auc_model:.3f} PR-AUC(rvol)={pr_auc_naive:.3f} "
              f"ROC-AUC(modell)={roc_auc_model:.3f} Brier={brier_model:.4f}")

    df = pd.DataFrame(rows)
    print("\n" + "=" * 90)
    print("Sammanfattning (median över splits)")
    print("=" * 90)
    print(df[["pr_auc_model", "roc_auc_model", "brier_model", "pr_auc_naive_rvol", "roc_auc_naive_rvol"]]
          .median().to_string(float_format=lambda x: f"{x:.4f}"))
    print(f"\nModell slår naiv rvol-baslinje på PR-AUC i {int((df['pr_auc_model'] > df['pr_auc_naive_rvol']).sum())} "
          f"av {len(df)} splits ({100*(df['pr_auc_model'] > df['pr_auc_naive_rvol']).mean():.0f}%).")
    print("\n[downside_veto] Klart (dev-diagnostik). Holdouten INTE öppnad i denna körning - "
          "per specen öppnas den bara en gång, efter att dev-resultatet bedömts.")


if __name__ == "__main__":
    main()
