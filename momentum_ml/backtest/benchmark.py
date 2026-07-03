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


def equal_weight_index(
    prices: Dict[str, pd.DataFrame],
    dates: pd.DatetimeIndex,
    initial_capital: float = config.INITIAL_CAPITAL,
) -> pd.Series:
    """
    Likaviktat totalavkastnings-index, VECKOVIS OMBALANSERAT: varje vecka =
    medelavkastningen över alla tickers som har pris BÅDA veckorna, kumulerat.

    BUGFIX (ersätter det gamla köp-och-behåll): ett buy-hold som köps likaviktat
    2010 och ALDRIG ombalanseras låter en enskild vinnare/dataglitch växa obundet
    och dominera summan – en ojusterad split eller en enda 100-baggare drog
    benchmarken till orimliga nivåer (20×/2 Mkr på 100k). Veckovis ombalansering
    kapar det (varje bolag väger lika igen varje vecka), och veckoavkastningar
    VINSORISERAS vid SUSPICIOUS_JUMP_THRESHOLD så ett ojusterat prishopp inte kan
    injicera fantomavkastning. Immunt även mot att bolag kommer/går (skipna).

    Kvarstår (kan ej kodas bort): survivorship – bara dagens överlevare finns i
    historiken, så nivån är fortfarande optimistisk mot ett äkta index.
    """
    dates = pd.DatetimeIndex(dates).sort_values()
    if len(dates) == 0:
        return pd.Series(dtype=float)
    closes = pd.DataFrame({t: df["Close"] for t, df in prices.items()
                           if "Close" in df and not df["Close"].dropna().empty})
    if closes.empty:
        return pd.Series(index=dates, dtype=float)
    closes = closes.sort_index().reindex(dates, method="ffill")
    rets = closes.pct_change(fill_method=None)                # NaN där endera veckan saknas
    clip = float(getattr(config, "SUSPICIOUS_JUMP_THRESHOLD", 0.60))
    rets = rets.clip(-clip, clip)                             # vinsorisera dataglitchar
    mean_ret = rets.mean(axis=1, skipna=True).fillna(0.0)     # likavikt, veckovis ombalanserat
    return initial_capital * (1.0 + mean_ret).cumprod()


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
    label: str = "Likaviktat index (veckovis ombalanserat, survivorship-biased)",
) -> Optional[Dict]:
    """
    Bygger benchmarken över strategins datumintervall och returnerar ett dict
    redo för stats.json: label, benchmarkens statistik, alfa (CAGR-differens)
    och beta. Returnerar även själva benchmark-serien för frontend-overlay.
    """
    if strategy_value is None or len(strategy_value) < 2:
        return None
    bench = equal_weight_index(prices, strategy_value.index, initial_capital)
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
