"""
tune_combined_validation.py – TEST 10 i testplan_niva1_niva2.md: kombinerad
validering av alla adopterade fynd samtidigt, mot en färsktränad baseline
och mot OMXS30 (config.INDEX_BENCHMARK_TICKER).

Kombinerar (efter confound-korrigering av Test 5/6/7, 2026-07-29):
  - Test 5: sector_code som categorical_feature (blygsam men äkta vinst)
  - Test 7: TA BORT equal-date-weighting (stor vinst, se korrigerad Test 7)
  - Test 2: vol-target 10%
  - Test 3: regimfilter bear=0.50
Test 6 (rank_ic early stopping) exkluderas - lågprioriterat, marginell effekt.

"baseline" = färsktränad LambdaRank utan NÅGON av dagens ändringar (ren
jämförelsepunkt, inga overlays). "kombinerad" = alla fyra ändringar
samtidigt. Full backtest (topp-N, TA-score-filter, vol-target- och
regimfilter-overlays) via samma pipeline som produktionens main.py/
tune_voltarget.py/tune_regime_exposure.py använder - inte den förenklade
"topp-15 likaviktat"-utvärderingen tune_*_selection.py-skripten använde,
så siffrorna är inte direkt jämförbara med Test 5/6/7:s tabeller, bara med
varandra och med testplanens ursprungliga baslinje (CAGR 9.1%, Sharpe 0.92,
Holdout +4.3%, MaxDD -14.2%).

    /opt/momentum/venv/bin/python3 tune_combined_validation.py
"""
import sys
sys.path.insert(0, ".")
import config

segment = "large"
seg     = config.SEGMENTS[segment]
config.RESULTS_DIR      = seg["results_dir"]
config.MAX_POSITIONS    = seg.get("max_positions",    config.MAX_POSITIONS)
config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
if "index_ticker" in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
if "index_label"  in seg: config.INDEX_BENCHMARK_LABEL  = seg["index_label"]
if "drop_features" in seg: config.DROP_FEATURES = seg["drop_features"]

import numpy as np
import pandas as pd

from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import MomentumLGBM, walk_forward_splits
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report, winsorize_price_series
from data.data_loader import fetch_weekly_data
from tune_abstention_gate import _load_state
from tune_lambdarank_common import _slice_sorted, train_lambdarank_split

_SECTOR_IDX = FEATURE_COLS.index("sector_code")


def build_combined_model(dev_df: pd.DataFrame, categorical: bool, weighted: bool) -> MomentumLGBM:
    lgbm = MomentumLGBM()
    splits = walk_forward_splits(dev_df.index)
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = _slice_sorted(dev_df, train_d)
        if len(train_sub) < 100:
            continue
        model = train_lambdarank_split(
            train_sub, val_d, dev_df,
            categorical_feature=[_SECTOR_IDX] if categorical else None,
            use_date_weight=weighted,
        )
        lgbm.cls_models.append(model)
        lgbm.reg_models.append(model)
        lgbm.split_starts.append(test_d[0])
        lgbm.split_ends.append(test_d[-1])
        print(f"    split {i+1}/{len(splits)} klar")
    return lgbm


def evaluate(label, sig, price_data, holdout_start, vol_enabled, vol_target, bear_exposure):
    config.VOL_TARGET_ENABLED = vol_enabled
    if vol_target is not None:
        config.VOL_TARGET_ANNUAL = vol_target
    config.MARKET_FILTER_EXPOSURE = {"bull": 1.0, "sideways": 1.0, "bear": bear_exposure}

    bt = MomentumBacktester(sig, price_data, market_filter=True)
    bt.run()
    overall = bt.statistics()
    dev = bt.statistics_for_period(end=holdout_start)
    holdout = bt.statistics_for_period(start=holdout_start)
    bench = benchmark_report(bt._results["portfolio_value"], price_data)

    idx_cagr = idx_alpha = idx_window = None
    idx_df = price_data.get(config.INDEX_BENCHMARK_TICKER)
    if idx_df is not None and "Close" in idx_df:
        results = bt._results
        idx_close = idx_df["Close"].reindex(idx_df.index.union(results.index)).sort_index().ffill().reindex(results.index)
        idx_close = winsorize_price_series(idx_close)
        valid = idx_close.dropna()
        if valid.size >= 2:
            start_dt = valid.index[0]
            overlap = results.loc[results.index >= start_dt, "portfolio_value"]
            weeks = max(len(valid) - 1, 1)
            idx_cagr = float((valid.iloc[-1] / valid.iloc[0]) ** (52 / weeks) - 1)
            strat_cagr = float((overlap.iloc[-1] / overlap.iloc[0]) ** (52 / max(len(overlap) - 1, 1)) - 1)
            idx_alpha = strat_cagr - idx_cagr
            idx_window = f"{start_dt.date()} -> {results.index[-1].date()}"

    return {
        "label": label,
        "overall_CAGR": overall["CAGR"], "overall_Sharpe": overall["Sharpe"], "overall_MaxDD": overall["Max Drawdown"],
        "dev_CAGR": dev["CAGR"], "dev_Sharpe": dev["Sharpe"], "dev_MaxDD": dev["Max Drawdown"],
        "holdout_CAGR": holdout["CAGR"] if holdout else None,
        "holdout_Sharpe": holdout["Sharpe"] if holdout else None,
        "holdout_MaxDD": holdout["Max Drawdown"] if holdout else None,
        "eqweight_alpha_cagr": bench["alpha_cagr"] if bench else None,
        "omxs30_cagr": idx_cagr, "omxs30_alpha_cagr": idx_alpha, "omxs30_window": idx_window,
    }


def main():
    model_features, data, _, holdout_start = _load_state()
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]

    print("[test10] Hamtar OMXS30-jamforelseticker...")
    bench_data = fetch_weekly_data([config.INDEX_BENCHMARK_TICKER], start=config.START_DATE, end=None, use_cache=True)
    price_data = {**data, **bench_data}
    feature_dfs = {t: f.assign(ticker=t) for t, f in model_features.items()}

    print("[test10] Tranar BASELINE-modell (ren LambdaRank, inga andringar)...")
    lgbm_base = build_combined_model(dev_df, categorical=False, weighted=True)

    print("[test10] Tranar KOMBINERAD modell (kategorisk sektor + ingen datumviktning)...")
    lgbm_combo = build_combined_model(dev_df, categorical=True, weighted=False)

    def build_signals(lgbm):
        preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5]))
                 for t, f in model_features.items() if len(f) > 0}
        return build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")

    print("[test10] Bygger signaler...")
    sig_base = build_signals(lgbm_base)
    sig_combo = build_signals(lgbm_combo)

    orig_vol_enabled = config.VOL_TARGET_ENABLED
    orig_vol_target = config.VOL_TARGET_ANNUAL
    orig_filter = dict(config.MARKET_FILTER_EXPOSURE)

    print("[test10] Kor backtest: baseline (inga overlays)...")
    row_base = evaluate("baseline (ren LambdaRank, inga overlays)", sig_base, price_data, holdout_start,
                         vol_enabled=False, vol_target=None, bear_exposure=1.0)

    print("[test10] Kor backtest: kombinerad (alla 4 andringar)...")
    row_combo = evaluate("kombinerad (kat.sektor+ingen viktning+voltarget10%+regime bear0.5)",
                          sig_combo, price_data, holdout_start,
                          vol_enabled=True, vol_target=0.10, bear_exposure=0.50)

    config.VOL_TARGET_ENABLED = orig_vol_enabled
    config.VOL_TARGET_ANNUAL = orig_vol_target
    config.MARKET_FILTER_EXPOSURE = orig_filter

    df = pd.DataFrame([row_base, row_combo])
    print(f"\n{'='*110}\nTEST 10 - Kombinerad validering\n{'='*110}")
    print(df.to_string(index=False))
    df.to_csv("results/test10_combined_validation.csv", index=False)
    print("\n[test10] Sparat: results/test10_combined_validation.csv")


if __name__ == "__main__":
    main()
