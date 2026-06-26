"""
backtest/benchmark.py – Jämförelseindex (benchmark) och alfa/beta.

En strategi får bara värderas *relativt* ett passivt alternativ. Utan
benchmark går det inte att säga om en CAGR på t.ex. 1% är bra eller usel –
om indexet gav 10% förstörde strategin värde. Den här modulen bygger ett
likaviktat köp-och-behåll av samma universum som strategin handlar i (alltid
tillgängligt, ingen extra datakälla krävs) och skattar:

  * benchmarkens egen statistik (CAGR/Sharpe/MaxDD/total avkastning)
  * alfa  = strategins CAGR − benchmarkens CAGR (mer-/mindreavkastning)
  * beta  = lutningen mot benchmarken (marknadsexponering; long-only momentum
            bär marknadsrisk, beta visar hur mycket)

Vill man jämföra mot ett riktigt index i stället för universumet räcker det
att inkludera indexets ticker i prisdatan och peka ut den via
`benchmark_ticker`.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from backtest.backtester import MomentumBacktester


def equal_weight_buy_hold(
    prices: Dict[str, pd.DataFrame],
    dates: pd.DatetimeIndex,
    initial_capital: float = config.INITIAL_CAPITAL,
) -> pd.Series:
    """
    Likaviktat köp-och-behåll: vid första datumet fördelas kapitalet jämnt
    över alla tickers som har ett pris då, och innehaven hålls oförändrade
    (inga ombalanseringar, inga kostnader – ett passivt golv att slå).
    Returnerar en portföljvärde-serie indexerad på `dates`.
    """
    dates = pd.DatetimeIndex(dates).sort_values()
    if len(dates) == 0:
        return pd.Series(dtype=float)
    start = dates[0]

    # Pris vid start + hela serien (ffill) per ticker som existerade vid start.
    shares: Dict[str, float] = {}
    series: Dict[str, pd.Series] = {}
    eligible = []
    for ticker, df in prices.items():
        if "Close" not in df.columns:
            continue
        s = df["Close"].reindex(dates, method="ffill")
        p0 = df["Close"].reindex([start], method="ffill").iloc[0]
        if pd.isna(p0) or p0 <= 0:
            continue
        eligible.append(ticker)
        series[ticker] = s
        series[ticker]._p0 = p0  # noqa: SLF001 (lokal stash)

    if not eligible:
        return pd.Series(index=dates, dtype=float)

    alloc = initial_capital / len(eligible)
    for ticker in eligible:
        shares[ticker] = alloc / series[ticker]._p0

    value = pd.Series(0.0, index=dates)
    for ticker in eligible:
        value = value.add(series[ticker].fillna(0.0) * shares[ticker], fill_value=0.0)
    return value


def alpha_beta(strategy_value: pd.Series, benchmark_value: pd.Series) -> Dict[str, float]:
    """
    Skattar beta (lutning av strategins veckoavkastning mot benchmarkens) och
    alfa per år (skärningspunkt × 52). Bägge på gemensamma datum.
    """
    s = strategy_value.pct_change()
    b = benchmark_value.pct_change()
    df = pd.concat([s, b], axis=1, keys=["s", "b"]).dropna()
    if len(df) < 8 or df["b"].var() == 0:
        return {"beta": float("nan"), "alpha_annual": float("nan")}
    beta = float(df["s"].cov(df["b"]) / df["b"].var())
    alpha_week = float(df["s"].mean() - beta * df["b"].mean())
    return {"beta": beta, "alpha_annual": alpha_week * 52}


def benchmark_report(
    strategy_value: pd.Series,
    prices: Dict[str, pd.DataFrame],
    initial_capital: float = config.INITIAL_CAPITAL,
    label: str = "Likaviktat köp-och-behåll (universum)",
) -> Optional[Dict]:
    """
    Bygger benchmarken över strategins datumintervall och returnerar ett dict
    redo för stats.json: label, benchmarkens statistik, alfa (CAGR-differens)
    och beta. Returnerar även själva benchmark-serien för frontend-overlay.
    """
    if strategy_value is None or len(strategy_value) < 2:
        return None
    bench = equal_weight_buy_hold(prices, strategy_value.index, initial_capital)
    bench = bench.reindex(strategy_value.index).ffill()
    if bench.dropna().empty or (bench <= 0).all():
        return None

    bench_stats = MomentumBacktester._compute_stats(bench.dropna(), initial_capital)
    ab = alpha_beta(strategy_value, bench)

    # Alfa som ren CAGR-differens (lättare att kommunicera än regressionsalfan).
    def _pct_to_float(s: str) -> float:
        try:
            return float(str(s).strip().rstrip("%")) / 100.0
        except (ValueError, AttributeError):
            return float("nan")

    strat_stats = MomentumBacktester._compute_stats(strategy_value.dropna(), initial_capital)
    cagr_diff = _pct_to_float(strat_stats["CAGR"]) - _pct_to_float(bench_stats["CAGR"])

    return {
        "label":        label,
        "overall":      bench_stats,
        "alpha_cagr":   cagr_diff,            # strategi-CAGR − benchmark-CAGR
        "alpha_annual": ab["alpha_annual"],   # regressionsalfa (per år)
        "beta":         ab["beta"],
        "series":       bench,                # för portfolio.csv-overlay
    }
