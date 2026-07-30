"""
tune_abstention_gate.py – Fullständigt, strikt walk-forward-backtest av
avstående-regeln (session 2026-07-26, uppföljning på
tune_reject_split_followup.py:s abstention/abstention_sweep). INTE en
kodändring i ensemble.py - detta är enbart en validerings-körning. Om
resultatet håller robust över flera trösklar (inte bara ett fåtal splits)
implementeras mekanismen därefter opt-in (ABSTENTION_ENABLED=False).

KRITISKT designkrav: varje historiskt datum får ENDAST använda den
val_auc_best som hörde till den splitmodell som faktiskt var tillgänglig
FÖR DET DATUMET (samma modell _select_model_idx skulle valt för det
datumet) - aldrig dagens/senaste splittens AUC retroaktivt. Det säkras här
genom att bygga en date -> val_auc_best-mappning direkt från den redan
tränade lgbm.fold_diagnostics_/split_starts/split_ends, med EXAKT samma
_select_model_idx-logik som predict() självt använder.

Tre faser (kör i ordning, varje sparar en checkpoint till disk):

    fetch    – hämtar FÄRSK rådata för hela large-universumet (Large+Mid
               Cap), bygger features, sparar till
               results/abstention_features.pkl.
    train    – laddar features-picklen, kör EXAKT samma
               MomentumLGBM.fit_walk_forward() som produktionen (samma
               kod, samma LGBM_PARAMS) - en enda riktig träning, inte en
               förenklad variant. Sparar till
               results/abstention_lgbm.pkl.
    backtest – laddar tränad modell + priser, bygger baseline-signals_df
               (via riktiga ensemble.py-funktioner) och flera
               avstående-varianter (jämviktad/benchmark/kontant/mjuk
               viktning) över trösklarna 0,50-0,54, kör MomentumBacktester
               på var och en, rapporterar CAGR/Sharpe/MaxDD/turnover/
               andel avstådd tid/antal berörda splits, uppdelat per split
               och per marknadsregim.

    /opt/momentum/venv/bin/python3 tune_abstention_gate.py fetch
    /opt/momentum/venv/bin/python3 tune_abstention_gate.py train
    /opt/momentum/venv/bin/python3 tune_abstention_gate.py backtest
"""
import sys
from pathlib import Path
import sys

sys.path.insert(0, ".")
import config

# Applicera large segment overrides för att filtrera FEATURE_COLS direkt vid import av feature_engineering
seg = config.SEGMENTS["large"]
config.RESULTS_DIR      = seg["results_dir"]
config.MAX_POSITIONS    = seg.get("max_positions",    config.MAX_POSITIONS)
config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
if "index_ticker"     in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
if "index_label"      in seg: config.INDEX_BENCHMARK_LABEL  = seg["index_label"]
if "gate_enabled"     in seg: config.MOMENTUM_GATE_ENABLED  = seg["gate_enabled"]
if "gate_min"         in seg: config.MOMENTUM_GATE_MIN      = seg["gate_min"]
if "atr_stop_enabled" in seg: config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
if "market_filter_exposure" in seg:
    config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
if "forward_weeks"    in seg:
    config.FORWARD_WEEKS   = seg["forward_weeks"]
    config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    config.EMBARGO_WEEKS   = seg["embargo_weeks"]
if "rank_ema_span"    in seg: config.RANK_EMA_SPAN = seg["rank_ema_span"]
if "drop_features"    in seg:
    config.DROP_FEATURES = seg["drop_features"]

import numpy as np
import pandas as pd

from data.data_loader import (
    fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, attach_fundamentals_features,
    to_model_df, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM, walk_forward_splits
from models.ensemble import MomentumEnsemble, build_full_output, kelly_position_size, _topn_invested_weights
from backtest.backtester import MomentumBacktester
from backtest.regime import classify_regimes

FEATURES_PKL = Path("results/abstention_features.pkl")
DATA_PKL = Path("results/abstention_price_data.pkl")
LGBM_PKL = Path("results/abstention_lgbm.pkl")

THRESHOLDS = [0.50, 0.51, 0.52, 0.53, 0.54]
FALLBACKS = ["equal_weight", "benchmark", "cash"]


# ── Fas 1: hämta + bygg features ─────────────────────────────────────────────

def cmd_fetch():
    seg = config.SEGMENTS["large"]
    tickers, sector_map, cap_tier_map, name_map = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)
    print(f"[abstention] {len(tickers)} tickers i large-universumet (Large+Mid Cap). Hämtar färsk data...")

    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    print(f"[abstention] {len(data)} tickers kvar efter filter.")

    print("[abstention] Bygger features...")
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment="large", prices=data)

    model_features = {t: f for t, f in feats.items() if config.CAP_TIER_MAP.get(t, "") != "Fond"}
    excluded = len(feats) - len(model_features)
    print(f"[abstention] Exkluderar {excluded} ETF/fonder ur modelluniversumet.")

    pd.to_pickle(model_features, FEATURES_PKL)
    pd.to_pickle(data, DATA_PKL)
    sample_tk = list(model_features.keys())[0]
    print(f"Sample ticker {sample_tk} columns after build:", list(model_features[sample_tk].columns))
    print(f"[abstention] Sparat: {FEATURES_PKL} ({len(model_features)} tickers), {DATA_PKL} (rådata, {len(data)} tickers)")


# ── Fas 2: träna (EXAKT produktionskoden) ───────────────────────────────────

def cmd_train():
    import sys
    print("sys.path inside cmd_train:", sys.path)
    print("config file path:", config.__file__)
    print("walk_forward_splits file path:", walk_forward_splits.__code__.co_filename)
    if not FEATURES_PKL.exists():
        raise SystemExit(f"{FEATURES_PKL} saknas - kör 'fetch' först.")
    model_features = pd.read_pickle(FEATURES_PKL)
    model_df = to_model_df(model_features)
    print(f"[abstention] model_df: {len(model_df):,} rader, {model_df['ticker'].nunique()} tickers.")
    missing = [c for c in FEATURE_COLS if c not in model_df.columns]
    print("Missing columns in model_df:", missing)
    print("Available columns in model_df:", list(model_df.columns))

    all_dates = model_df.index.unique().sort_values()
    if len(all_dates) > config.HOLDOUT_WEEKS + config.FORWARD_WEEKS:
        holdout_start = all_dates[-config.HOLDOUT_WEEKS]
        purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
        dev_df = model_df[model_df.index < purge_start]
        print(f"[abstention] Frusen holdout: {holdout_start.date()} -> slut.")
    else:
        holdout_start = None
        dev_df = model_df
        print("[abstention] [VARNING] för kort historik för en frusen holdout.")

    lgbm = MomentumLGBM()
    lgbm.fit_walk_forward(dev_df)   # EXAKT samma anrop som main.py --train-lgbm-only
    lgbm.print_fold_diagnostics()

    pd.to_pickle({"lgbm": lgbm, "holdout_start": holdout_start}, LGBM_PKL)
    print(f"[abstention] Sparat: {LGBM_PKL}")


# ── Fas 3: bygg signalvarianter + kör riktig backtest ────────────────────────

def _load_state():
    for p in (FEATURES_PKL, DATA_PKL, LGBM_PKL):
        if not p.exists():
            raise SystemExit(f"{p} saknas - kör 'fetch' och 'train' först.")
    model_features = pd.read_pickle(FEATURES_PKL)
    data = pd.read_pickle(DATA_PKL)
    state = pd.read_pickle(LGBM_PKL)
    return model_features, data, state["lgbm"], state["holdout_start"]


def _val_auc_by_date(lgbm, dates: pd.DatetimeIndex) -> pd.Series:
    """Date -> val_auc_best för den split _select_model_idx FAKTISKT skulle
    valt för just det datumet. Varje splits val_auc_best beräknades under
    träningen, på data som ligger helt före dess egna testfönster - denna
    mappning bär alltså aldrig in framtida information i ett historiskt
    datum, oavsett vilket datum som frågas efter."""
    idx = lgbm._select_model_idx(dates)
    aucs = [lgbm.fold_diagnostics_[i].get("cls_val_auc") for i in idx]
    return pd.Series(aucs, index=dates)


def _build_baseline_signals(model_features, lgbm) -> pd.DataFrame:
    lgbm_preds_by_ticker = {}
    for ticker, feat_df in model_features.items():
        feat_df_clean = feat_df.dropna(subset=FEATURE_COLS[:5])
        if len(feat_df_clean) > 0:
            lgbm_preds_by_ticker[ticker] = lgbm.predict(feat_df_clean)
    ensemble = MomentumEnsemble()
    feature_dfs = {t: df.assign(ticker=t) for t, df in model_features.items()}
    return build_full_output(lgbm_preds_by_ticker, None, feature_dfs, ensemble)


def _equal_weight_positions(g: pd.DataFrame) -> np.ndarray:
    elig = (g["selection_eligible"] == 1).values
    n = int(elig.sum())
    out = np.zeros(len(g))
    if n:
        out[elig] = 1.0 / n
    return out


def _apply_hard_fallback(signals_df: pd.DataFrame, abstain_dates: set, fallback: str,
                          benchmark_ticker: str) -> pd.DataFrame:
    df = signals_df.copy()
    is_abstain = df.index.isin(abstain_dates)
    if not is_abstain.any():
        return df
    if fallback == "cash":
        df.loc[is_abstain, "position_size"] = 0.0
        df.loc[is_abstain, "pred_signal"] = 0
    elif fallback == "equal_weight":
        for date in sorted(d for d in df.index.unique() if d in abstain_dates):
            mask = df.index == date   # boolsk mask - df.index har dubbletter (en rad/ticker),
            g = df.loc[mask]          # .loc[[date]] blandar ihop antalet rader vid dubblerat index
            w = _equal_weight_positions(g)
            df.loc[mask, "position_size"] = w
            df.loc[mask, "pred_signal"] = (w > 0).astype(int)
    elif fallback == "benchmark":
        df.loc[is_abstain, "position_size"] = 0.0
        df.loc[is_abstain, "pred_signal"] = 0
        abstain_sorted = sorted(d for d in df.index.unique() if d in abstain_dates)
        if abstain_sorted:
            bench_df = pd.DataFrame({
                "ticker": benchmark_ticker, "prob_up": 0.5, "prob_raw": 0.5, "pred_return": 0.0,
                "selection_eligible": 1, "pred_signal": 1, "position_size": 1.0,
            }, index=pd.DatetimeIndex(abstain_sorted, name=df.index.name))
            df = pd.concat([df, bench_df])
    else:
        raise ValueError(f"Okänt fallback: {fallback!r}")
    return df


def _apply_soft_weight(signals_df: pd.DataFrame, val_auc_by_date: pd.Series,
                        lo: float = 0.52, hi: float = 0.54) -> pd.DataFrame:
    """Mjuk viktning (separat variant, INTE en del av tröskelsvepet): linjär
    blandning mellan normal topp-N-vikt (vid AUC>=hi) och jämviktad
    exponering (vid AUC<=lo), i stället för en skarp av/på-gräns."""
    df = signals_df.copy()
    for date in df.index.unique():
        auc = val_auc_by_date.get(date)
        if auc is None or auc >= hi:
            continue
        blend = 0.0 if auc <= lo else (auc - lo) / (hi - lo)
        mask = df.index == date
        g = df.loc[mask]
        normal = g["position_size"].values.astype(float)
        eq = _equal_weight_positions(g)
        blended = blend * normal + (1 - blend) * eq
        df.loc[mask, "position_size"] = blended
        df.loc[mask, "pred_signal"] = (blended > 1e-9).astype(int)
    return df


def _turnover(signals_df: pd.DataFrame, rebalance_weeks: int) -> float:
    """Annualiserad ensidig omsättning: summan av |viktförändring| per
    rebalansering (samma kadens som backtestern faktiskt handlar på),
    skalat till per år."""
    dates = sorted(signals_df.index.unique())
    rebal_dates = dates[::max(rebalance_weeks, 1)]
    prev_w: dict = {}
    total_change, n_rebals = 0.0, 0
    for date in rebal_dates:
        g = signals_df.loc[[date]]
        cur_w = {row["ticker"]: row["position_size"] for _, row in g.iterrows()
                 if row["pred_signal"] == 1 and row["position_size"] > 0}
        all_t = set(prev_w) | set(cur_w)
        total_change += sum(abs(cur_w.get(t, 0.0) - prev_w.get(t, 0.0)) for t in all_t)
        n_rebals += 1
        prev_w = cur_w
    if n_rebals == 0:
        return 0.0
    return (total_change / n_rebals) * (52.0 / max(rebalance_weeks, 1))


def _run_backtest(signals_df: pd.DataFrame, price_data: dict, holdout_start) -> dict:
    bt = MomentumBacktester(signals_df, price_data)
    bt.run()
    overall = bt.statistics()
    dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
    holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
    return {"overall": overall, "dev": dev, "holdout": holdout}


def _pct(stat_dict: dict, key: str) -> float:
    return float(str(stat_dict[key]).rstrip("%")) / 100.0


def cmd_backtest():
    model_features, data, lgbm, holdout_start = _load_state()
    print(f"[abstention] {len(model_features)} tickers, holdout_start={holdout_start}")

    print("[abstention] Hämtar benchmark-ticker för regim + benchmark-fallback...")
    bench_ticker = config.INDEX_BENCHMARK_TICKER
    bench_data = fetch_weekly_data([bench_ticker], start=config.START_DATE, end=None, use_cache=True)
    price_data = {**data, **bench_data}
    regimes = classify_regimes(bench_data)

    print("[abstention] Bygger BASELINE-signaler (ingen avstående)...")
    baseline_signals = _build_baseline_signals(model_features, lgbm)
    all_dates = pd.DatetimeIndex(sorted(baseline_signals.index.unique()))
    val_auc_by_date = _val_auc_by_date(lgbm, all_dates)

    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))

    print("[abstention] Kör BASELINE-backtest...")
    baseline_stats = _run_backtest(baseline_signals, price_data, holdout_start)
    baseline_turnover = _turnover(baseline_signals, rebalance_weeks)
    print(f"  baseline: dev CAGR={baseline_stats['dev']['CAGR']} Sharpe={baseline_stats['dev']['Sharpe']} "
          f"MaxDD={baseline_stats['dev']['Max Drawdown']} | holdout CAGR="
          f"{baseline_stats['holdout']['CAGR'] if baseline_stats['holdout'] else '–'}")

    rows = []
    n_total_dates = len(all_dates)
    total_splits = len(lgbm.cls_models)

    for threshold in THRESHOLDS:
        abstain_dates = set(all_dates[val_auc_by_date.reindex(all_dates) < threshold])
        affected_split_idx = sorted(set(lgbm._select_model_idx(pd.DatetimeIndex(sorted(abstain_dates)))
                                         if abstain_dates else []))
        time_share = len(abstain_dates) / n_total_dates if n_total_dates else 0.0
        print(f"\n[abstention] Tröskel {threshold}: {len(abstain_dates)}/{n_total_dates} datum avstådda "
              f"({time_share:.1%}), {len(affected_split_idx)}/{total_splits} splits berörda: {affected_split_idx}")

        for fallback in FALLBACKS:
            variant_signals = _apply_hard_fallback(baseline_signals, abstain_dates, fallback, bench_ticker)
            stats = _run_backtest(variant_signals, price_data, holdout_start)
            turnover = _turnover(variant_signals, rebalance_weeks)
            row = {
                "threshold": threshold, "fallback": fallback,
                "n_abstain_dates": len(abstain_dates), "time_share_abstain": time_share,
                "n_affected_splits": len(affected_split_idx),
                "dev_CAGR": _pct(stats["dev"], "CAGR"), "dev_Sharpe": float(stats["dev"]["Sharpe"]),
                "dev_MaxDD": _pct(stats["dev"], "Max Drawdown"),
                "holdout_CAGR": _pct(stats["holdout"], "CAGR") if stats["holdout"] else None,
                "holdout_Sharpe": float(stats["holdout"]["Sharpe"]) if stats["holdout"] else None,
                "holdout_MaxDD": _pct(stats["holdout"], "Max Drawdown") if stats["holdout"] else None,
                "turnover_annualized": turnover,
            }
            rows.append(row)
            print(f"    [{fallback:12s}] dev CAGR={row['dev_CAGR']:+.2%} Sharpe={row['dev_Sharpe']:.2f} "
                  f"MaxDD={row['dev_MaxDD']:.1%} | holdout CAGR="
                  f"{row['holdout_CAGR']:+.2%} Sharpe={row['holdout_Sharpe']} turnover={turnover:.1f}x/år")

    # Baseline-rad för jämförelse
    rows.append({
        "threshold": None, "fallback": "baseline_no_abstention",
        "n_abstain_dates": 0, "time_share_abstain": 0.0, "n_affected_splits": 0,
        "dev_CAGR": _pct(baseline_stats["dev"], "CAGR"), "dev_Sharpe": float(baseline_stats["dev"]["Sharpe"]),
        "dev_MaxDD": _pct(baseline_stats["dev"], "Max Drawdown"),
        "holdout_CAGR": _pct(baseline_stats["holdout"], "CAGR") if baseline_stats["holdout"] else None,
        "holdout_Sharpe": float(baseline_stats["holdout"]["Sharpe"]) if baseline_stats["holdout"] else None,
        "holdout_MaxDD": _pct(baseline_stats["holdout"], "Max Drawdown") if baseline_stats["holdout"] else None,
        "turnover_annualized": baseline_turnover,
    })

    # Mjuk viktning (0,52-0,54), SEPARAT variant, inte en del av tröskelsvepet.
    print("\n[abstention] Mjuk viktning (0,52-0,54 linjär blandning mot jämvikt)...")
    soft_signals = _apply_soft_weight(baseline_signals, val_auc_by_date)
    soft_stats = _run_backtest(soft_signals, price_data, holdout_start)
    soft_turnover = _turnover(soft_signals, rebalance_weeks)
    rows.append({
        "threshold": "soft_0.52_0.54", "fallback": "soft_weight_blend",
        "n_abstain_dates": None, "time_share_abstain": None, "n_affected_splits": None,
        "dev_CAGR": _pct(soft_stats["dev"], "CAGR"), "dev_Sharpe": float(soft_stats["dev"]["Sharpe"]),
        "dev_MaxDD": _pct(soft_stats["dev"], "Max Drawdown"),
        "holdout_CAGR": _pct(soft_stats["holdout"], "CAGR") if soft_stats["holdout"] else None,
        "holdout_Sharpe": float(soft_stats["holdout"]["Sharpe"]) if soft_stats["holdout"] else None,
        "holdout_MaxDD": _pct(soft_stats["holdout"], "Max Drawdown") if soft_stats["holdout"] else None,
        "turnover_annualized": soft_turnover,
    })
    print(f"  mjuk viktning: dev CAGR={rows[-1]['dev_CAGR']:+.2%} Sharpe={rows[-1]['dev_Sharpe']:.2f} | "
          f"holdout CAGR={rows[-1]['holdout_CAGR']}")

    out = pd.DataFrame(rows)
    out.to_csv("results/abstention_backtest_sweep.csv", index=False)
    print(f"\n[abstention] Sparat: results/abstention_backtest_sweep.csv")
    print(out.to_string(index=False))

    # ── Per-split och per-regim breakdown (för tröskel 0,52, jämviktad) ──────
    print(f"\n{'='*100}\nPer-split breakdown, tröskel 0,52, jämviktad fallback\n{'='*100}")
    abstain_052 = set(all_dates[val_auc_by_date.reindex(all_dates) < 0.52])
    variant_052 = _apply_hard_fallback(baseline_signals, abstain_052, "equal_weight", bench_ticker)
    bt_variant = MomentumBacktester(variant_052, price_data)
    bt_variant.run()
    bt_baseline = MomentumBacktester(baseline_signals, price_data)
    bt_baseline.run()
    weekly_ret_variant = bt_variant._results["portfolio_value"].pct_change()
    weekly_ret_baseline = bt_baseline._results["portfolio_value"].pct_change()

    split_rows = []
    for i, model in enumerate(lgbm.cls_models):
        split_start, split_end = lgbm.split_starts[i], lgbm.split_ends[i]
        mask = (weekly_ret_baseline.index >= split_start) & (weekly_ret_baseline.index <= split_end)
        if not mask.any():
            continue
        split_rows.append({
            "split": i + 1, "val_auc_best": lgbm.fold_diagnostics_[i].get("cls_val_auc"),
            "regime_mode": regimes.reindex(weekly_ret_baseline.index[mask]).mode().iloc[0]
                           if regimes.reindex(weekly_ret_baseline.index[mask]).notna().any() else None,
            "baseline_mean_weekly_ret": float(weekly_ret_baseline[mask].mean()),
            "abstention_mean_weekly_ret": float(weekly_ret_variant[mask].mean()),
        })
    split_df = pd.DataFrame(split_rows)
    print(split_df.to_string(index=False))
    split_df.to_csv("results/abstention_per_split_breakdown.csv", index=False)

    print(f"\n{'='*100}\nPer marknadsregim (tröskel 0,52, jämviktad)\n{'='*100}")
    regime_rows = []
    for regime_label, group in pd.DataFrame({
        "baseline": weekly_ret_baseline, "abstention": weekly_ret_variant,
        "regime": regimes.reindex(weekly_ret_baseline.index),
    }).dropna(subset=["regime"]).groupby("regime"):
        regime_rows.append({
            "regime": regime_label, "n_weeks": len(group),
            "baseline_mean_weekly_ret": float(group["baseline"].mean()),
            "abstention_mean_weekly_ret": float(group["abstention"].mean()),
        })
    regime_df = pd.DataFrame(regime_rows)
    print(regime_df.to_string(index=False))
    regime_df.to_csv("results/abstention_per_regime_breakdown.csv", index=False)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    {"fetch": cmd_fetch, "train": cmd_train, "backtest": cmd_backtest}[cmd]()
