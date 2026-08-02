"""
tune_dispersion_proxy.py – Uppföljning på abstention-gate-forskningen
(2026-07-26): val_auc_best är en MODELL-signal, bara känd vid
omträningstillfällena (var 13:e vecka). Kan en SAMTIDIG/bakåtblickande
DATA-proxy - beräkningsbar varje vecka, ingen omträning behövd - fånga
samma "är det här en låg-signal-period?"-information tidigare/tätare?

Kandidatproxyer (alla beräknade vid TRÄNINGSFÖNSTRETS SLUT för varje
split - dvs bara information som redan fanns tillgänglig innan
testfönstret, ingen framåtblick):

  dispersion_ret_4w    – tvärsnittsdispersion (std) i 4-veckors avkastning
  dispersion_ret_12w   – samma, 12-veckorsfönster
  dispersion_mom12_1   – tvärsnittsdispersion i mom_12_1-featuren
  dispersion_prob_raw  – tvärsnittsdispersion i splittens EGNA råa modell-
                         score, mätt på valideringsfönstret (känt innan test)
  pct_positive_trend   – andel bolag med roc_13w > 0 (marknadsbredd)
  avg_pairwise_corr     – genomsnittlig parvis korrelation, trailing 26v
                         avkastning (koncentration/breddmått)

Mot två målvariabler per split (testfönstret, aldrig sett av vare sig
träning eller de proxyer som beräknas ovan):

  test_ic            – Spearman-rankkorrelation, rå score vs target_return
  test_top_decile_edge – medel(target_return i topp-decil) - medel(target_return, alla)

Analys: Spearman-korrelation proxy->mål, kvintiluppdelning, samt
leave-one-split-out för varje proxy (droppa en split i taget, se om
korrelationens tecken/styrka håller - samma robusthetskontroll som
avslöjade att abstention-gatets holdout-resultat drevs av en enda split).

Kräver att 'tune_abstention_gate.py fetch' och 'train' redan körts
(återanvänder samma pickles).

    /opt/momentum/venv/bin/python3 tune_dispersion_proxy.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config
# tune_abstention_gate sätter config.DROP_FEATURES (large-segmentet, 48 av 61
# features) INNAN den själv importerar FEATURE_COLS - måste importeras FÖRE
# vårt eget FEATURE_COLS-import nedan, annars byggs FEATURE_COLS med alla 61
# (buggmönster 1: 61 vs 48 feature-mismatch mot abstention_lgbm.pkl).
from tune_abstention_gate import FEATURES_PKL, DATA_PKL, LGBM_PKL, _load_state
from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits


def _cross_sectional_return(data: dict, tickers: list, as_of: pd.Timestamp, weeks: int) -> pd.Series:
    rets = {}
    for t in tickers:
        df = data.get(t)
        if df is None or "Close" not in df:
            continue
        closes = df.loc[:as_of, "Close"].dropna()
        if len(closes) <= weeks:
            continue
        rets[t] = closes.iloc[-1] / closes.iloc[-1 - weeks] - 1
    return pd.Series(rets)


def _pairwise_corr(data: dict, tickers: list, as_of: pd.Timestamp, weeks: int = 26) -> float:
    closes = pd.DataFrame({t: data[t].loc[:as_of, "Close"] for t in tickers if t in data})
    closes = closes.tail(weeks + 1)
    rets = closes.pct_change().dropna(how="all")
    if rets.shape[1] < 5:
        return float("nan")
    corr = rets.corr()
    iu = np.triu_indices_from(corr.values, k=1)
    vals = corr.values[iu]
    vals = vals[~np.isnan(vals)]
    return float(np.mean(vals)) if len(vals) else float("nan")


def _proxies_for_split(data: dict, model_features: dict, tickers: list, train_end: pd.Timestamp,
                        cls_model, val_d: pd.DatetimeIndex, dev_df: pd.DataFrame) -> dict:
    ret4 = _cross_sectional_return(data, tickers, train_end, 4)
    ret12 = _cross_sectional_return(data, tickers, train_end, 12)

    mom_vals = []
    roc_vals = []
    for t in tickers:
        feat = model_features.get(t)
        if feat is None or train_end not in feat.index:
            continue
        row = feat.loc[train_end]
        if "mom_12_1" in feat.columns and pd.notna(row.get("mom_12_1")):
            mom_vals.append(float(row["mom_12_1"]))
        if "roc_13w" in feat.columns and pd.notna(row.get("roc_13w")):
            roc_vals.append(float(row["roc_13w"]))

    val_sub = dev_df[dev_df.index.isin(val_d)]
    raw_disp = float("nan")
    if len(val_sub):
        X_va = val_sub[FEATURE_COLS].fillna(0).values
        raw_va = cls_model.predict(X_va)
        by_date = pd.Series(raw_va, index=val_sub.index)
        per_date_std = by_date.groupby(level=0).std()
        raw_disp = float(per_date_std.mean()) if len(per_date_std) else float("nan")

    return {
        "dispersion_ret_4w": float(ret4.std()) if len(ret4) else float("nan"),
        "dispersion_ret_12w": float(ret12.std()) if len(ret12) else float("nan"),
        "dispersion_mom12_1": float(np.std(mom_vals)) if mom_vals else float("nan"),
        "dispersion_prob_raw": raw_disp,
        "pct_positive_trend": float(np.mean([v > 0 for v in roc_vals])) if roc_vals else float("nan"),
        "avg_pairwise_corr": _pairwise_corr(data, tickers, train_end),
    }


def _targets_for_split(dev_df: pd.DataFrame, test_d: pd.DatetimeIndex, cls_model, reg_model) -> dict:
    test_sub = dev_df[dev_df.index.isin(test_d)]
    if len(test_sub) < 10:
        return {"test_ic": None, "test_top_decile_edge": None}
    X_te = test_sub[FEATURE_COLS].fillna(0).values
    raw_te = cls_model.predict(X_te)
    test_sub = test_sub.copy()
    test_sub["_raw"] = raw_te

    ic = float(pd.Series(raw_te).corr(pd.Series(test_sub["target_return"].values), method="spearman"))

    edges = []
    for date, g in test_sub.groupby(test_sub.index):
        if len(g) < 10:
            continue
        cutoff = g["_raw"].quantile(0.9)
        top_ret = g.loc[g["_raw"] >= cutoff, "target_return"].mean()
        all_ret = g["target_return"].mean()
        edges.append(top_ret - all_ret)
    edge = float(np.mean(edges)) if edges else None
    return {"test_ic": ic, "test_top_decile_edge": edge}


def _spearman(x: pd.Series, y: pd.Series) -> float:
    mask = x.notna() & y.notna()
    if mask.sum() < 5:
        return float("nan")
    return float(x[mask].corr(y[mask], method="spearman"))


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    tickers = list(model_features.keys())

    print(f"[dispersion] {len(splits)} splits, {len(tickers)} tickers.\n")
    rows = []
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_end = pd.DatetimeIndex(train_d).max()
        cls_model = lgbm.cls_models[i]
        reg_model = lgbm.reg_models[i]
        proxies = _proxies_for_split(data, model_features, tickers, train_end, cls_model, val_d, dev_df)
        targets = _targets_for_split(dev_df, test_d, cls_model, reg_model)
        row = {"split": i + 1, "train_end": train_end.date().isoformat(),
               "val_auc_best": lgbm.fold_diagnostics_[i].get("cls_val_auc"),
               **proxies, **targets}
        rows.append(row)
        print(f"  split {i+1}/{len(splits)}: disp_ret4w={row['dispersion_ret_4w']:.4f} "
              f"disp_prob_raw={row['dispersion_prob_raw']:.4f} pct_pos_trend={row['pct_positive_trend']:.2f} "
              f"avg_corr={row['avg_pairwise_corr']:.3f} | test_ic={row['test_ic']} edge={row['test_top_decile_edge']}")

    df = pd.DataFrame(rows)
    df.to_csv("results/dispersion_proxy_analysis.csv", index=False)
    print(f"\n[dispersion] Sparat: results/dispersion_proxy_analysis.csv\n")

    proxy_cols = ["dispersion_ret_4w", "dispersion_ret_12w", "dispersion_mom12_1",
                  "dispersion_prob_raw", "pct_positive_trend", "avg_pairwise_corr", "val_auc_best"]
    target_cols = ["test_ic", "test_top_decile_edge"]

    print(f"{'='*100}\nSpearman-korrelation: proxy -> mål (n={len(df)})\n{'='*100}")
    corr_rows = []
    for p in proxy_cols:
        for t in target_cols:
            corr_rows.append({"proxy": p, "target": t, "spearman": _spearman(df[p], df[t])})
    corr_df = pd.DataFrame(corr_rows).pivot(index="proxy", columns="target", values="spearman")
    print(corr_df.to_string())
    corr_df.to_csv("results/dispersion_proxy_correlations.csv")

    print(f"\n{'='*100}\nKvintiler per proxy (mot test_ic, test_top_decile_edge)\n{'='*100}")
    for p in proxy_cols:
        valid = df.dropna(subset=[p, "test_ic", "test_top_decile_edge"])
        if len(valid) < 10:
            print(f"  {p}: för få giltiga observationer ({len(valid)}), hoppar över kvintiler.")
            continue
        try:
            q = pd.qcut(valid[p], 5, labels=False, duplicates="drop")
        except ValueError:
            print(f"  {p}: kunde inte dela i 5 kvintiler (för få unika värden).")
            continue
        summary = valid.assign(quintile=q).groupby("quintile")[["test_ic", "test_top_decile_edge", p]].mean()
        print(f"\n  -- {p} --")
        print(summary.to_string())

    for target in ["test_ic", "test_top_decile_edge"]:
        print(f"\n{'='*100}\nLeave-one-split-out robusthet (Spearman mot {target})\n{'='*100}")
        for p in proxy_cols:
            valid = df.dropna(subset=[p, target])
            if len(valid) < 8:
                continue
            loo_corrs = []
            for idx in valid.index:
                sub = valid.drop(index=idx)
                loo_corrs.append(_spearman(sub[p], sub[target]))
            loo_corrs = [c for c in loo_corrs if not np.isnan(c)]
            full_corr = _spearman(valid[p], valid[target])
            sign_flips = sum(1 for c in loo_corrs if np.sign(c) != np.sign(full_corr))
            print(f"  {p:22s}: full={full_corr:+.3f}  LOO min={min(loo_corrs):+.3f} max={max(loo_corrs):+.3f} "
                  f"  teckenbyten vid borttag av 1 split: {sign_flips}/{len(loo_corrs)}")


if __name__ == "__main__":
    main()
