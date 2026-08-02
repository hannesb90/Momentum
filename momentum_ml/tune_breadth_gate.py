"""
tune_breadth_gate.py – Fullständigt CAGR/Sharpe/MaxDD-backtest med
`pct_positive_trend` (marknadsbredd, andel bolag med roc_13w > 0) som
styrsignal i stället för `val_auc_best` (session 2026-07-26, uppföljning
på dispersion_proxy_analysis.md, som visade att breddmåttet var den enda
kandidatproxyn robust på BÅDA målen - test-IC och topp-decil-edge - och
kan beräknas VECKOVIS utan omträning, till skillnad från val_auc_best som
bara uppdateras var 13:e vecka).

Tre varianter:

  1. baseline        – ingen ändring alls.
  2. hard_threshold   – jämviktad exponering varje vecka där
                        pct_positive_trend < 0,30 (samma nedre
                        bandgräns som variant 3, för en rättvis
                        jämförelse hård/mjuk).
  3. soft_bands       – kontinuerlig blandning modell/jämvikt:
                          >70%   -> 100% modell
                          50-70% -> 75% modell
                          30-50% -> 50% modell
                          <30%   -> 0% modell (ren jämvikt)

`pct_positive_trend` beräknas VECKOVIS (inte bara per split som i
dispersion-analysen) direkt från roc_13w över hela tickeruniversumet -
ingen framåtblick (bara prisdata t.o.m. respektive vecka), ingen
modellträning krävs för att räkna ut den.

Kräver att 'tune_abstention_gate.py fetch' och 'train' redan körts.

    /opt/momentum/venv/bin/python3 tune_breadth_gate.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config
from data.data_loader import fetch_weekly_data
from backtest.backtester import MomentumBacktester
from backtest.regime import classify_regimes
from tune_abstention_gate import (
    _load_state, _build_baseline_signals, _equal_weight_positions,
    _apply_hard_fallback, _run_backtest, _turnover, _pct,
)

def _pct_positive_trend_by_date(model_features: dict) -> pd.Series:
    """Andel bolag med roc_13w > 0, per datum - helt vektoriserat, bara
    kontemporär prisdata (roc_13w för datum t använder bara priser t.o.m.
    t), ingen modell inblandad."""
    wide = pd.DataFrame({t: feat["roc_13w"] for t, feat in model_features.items()
                         if "roc_13w" in feat.columns})
    return (wide > 0).mean(axis=1)


def _blend_weight_for_breadth(breadth) -> float:
    """>70% -> 100% modell, 50-70% -> 75%, 30-50% -> 50%, <30% -> 0% (ren jämvikt)."""
    if breadth is None or (isinstance(breadth, float) and np.isnan(breadth)):
        return 1.0
    if breadth > 0.70:
        return 1.0
    if breadth >= 0.50:
        return 0.75
    if breadth >= 0.30:
        return 0.50
    return 0.0


def _apply_soft_bands(signals_df: pd.DataFrame, breadth_by_date: pd.Series) -> pd.DataFrame:
    df = signals_df.copy()
    for date in df.index.unique():
        blend = _blend_weight_for_breadth(breadth_by_date.get(date))
        if blend >= 1.0:
            continue
        mask = df.index == date
        g = df.loc[mask]
        normal = g["position_size"].values.astype(float)
        eq = _equal_weight_positions(g)
        blended = blend * normal + (1 - blend) * eq
        df.loc[mask, "position_size"] = blended
        df.loc[mask, "pred_signal"] = (blended > 1e-9).astype(int)
    return df


def main():
    model_features, data, lgbm, holdout_start = _load_state()
    print(f"[breadth] {len(model_features)} tickers, holdout_start={holdout_start}")

    bench_ticker = config.INDEX_BENCHMARK_TICKER
    bench_data = fetch_weekly_data([bench_ticker], start=config.START_DATE, end=None, use_cache=True)
    price_data = {**data, **bench_data}
    regimes = classify_regimes(bench_data)

    print("[breadth] Bygger BASELINE-signaler...")
    baseline_signals = _build_baseline_signals(model_features, lgbm)
    all_dates = pd.DatetimeIndex(sorted(baseline_signals.index.unique()))
    rebalance_weeks = int(getattr(config, "REBALANCE_WEEKS", 13))

    print("[breadth] Beräknar veckovis pct_positive_trend...")
    breadth_by_date = _pct_positive_trend_by_date(model_features).reindex(all_dates)
    band_labels = pd.cut(breadth_by_date, bins=[-0.01, 0.30, 0.50, 0.70, 1.01],
                         labels=["<30%", "30-50%", "50-70%", ">70%"])
    print("  Tidsandel per band (hela historiken):")
    print(band_labels.value_counts(normalize=True).sort_index().to_string())

    variants = {}
    variants["baseline"] = baseline_signals
    hard_abstain_dates = set(all_dates[breadth_by_date.reindex(all_dates) < 0.30])
    variants["hard_threshold_30pct"] = _apply_hard_fallback(
        baseline_signals, hard_abstain_dates, "equal_weight", bench_ticker)
    variants["soft_bands"] = _apply_soft_bands(baseline_signals, breadth_by_date)

    print(f"\n[breadth] Hård tröskel (<30%): {len(hard_abstain_dates)}/{len(all_dates)} "
          f"datum avstådda ({len(hard_abstain_dates)/len(all_dates):.1%})")

    rows = []
    backtests = {}
    for name, signals in variants.items():
        print(f"\n[breadth] Kör backtest: {name}...")
        stats = _run_backtest(signals, price_data, holdout_start)
        turnover = _turnover(signals, rebalance_weeks)
        row = {
            "variant": name,
            "dev_CAGR": _pct(stats["dev"], "CAGR"), "dev_Sharpe": float(stats["dev"]["Sharpe"]),
            "dev_MaxDD": _pct(stats["dev"], "Max Drawdown"),
            "holdout_CAGR": _pct(stats["holdout"], "CAGR") if stats["holdout"] else None,
            "holdout_Sharpe": float(stats["holdout"]["Sharpe"]) if stats["holdout"] else None,
            "holdout_MaxDD": _pct(stats["holdout"], "Max Drawdown") if stats["holdout"] else None,
            "turnover_annualized": turnover,
        }
        rows.append(row)
        print(f"  dev CAGR={row['dev_CAGR']:+.2%} Sharpe={row['dev_Sharpe']:.2f} MaxDD={row['dev_MaxDD']:.1%} | "
              f"holdout CAGR={row['holdout_CAGR']:+.2%} Sharpe={row['holdout_Sharpe']} turnover={turnover:.1f}x/år")

        bt = MomentumBacktester(signals, price_data)
        bt.run()
        backtests[name] = bt

    out = pd.DataFrame(rows)
    out.to_csv("results/breadth_gate_backtest.csv", index=False)
    print(f"\n[breadth] Sparat: results/breadth_gate_backtest.csv")
    print(out.to_string(index=False))

    print(f"\n{'='*100}\nPer marknadsregim (baseline vs soft_bands)\n{'='*100}")
    ret_baseline = backtests["baseline"]._results["portfolio_value"].pct_change()
    ret_soft = backtests["soft_bands"]._results["portfolio_value"].pct_change()
    ret_hard = backtests["hard_threshold_30pct"]._results["portfolio_value"].pct_change()
    regime_rows = []
    combined = pd.DataFrame({
        "baseline": ret_baseline, "soft_bands": ret_soft, "hard_threshold": ret_hard,
        "regime": regimes.reindex(ret_baseline.index),
    }).dropna(subset=["regime"])
    for regime_label, group in combined.groupby("regime"):
        regime_rows.append({
            "regime": regime_label, "n_weeks": len(group),
            "baseline_mean_weekly_ret": float(group["baseline"].mean()),
            "soft_bands_mean_weekly_ret": float(group["soft_bands"].mean()),
            "hard_threshold_mean_weekly_ret": float(group["hard_threshold"].mean()),
        })
    regime_df = pd.DataFrame(regime_rows)
    print(regime_df.to_string(index=False))
    regime_df.to_csv("results/breadth_gate_per_regime.csv", index=False)


if __name__ == "__main__":
    main()
