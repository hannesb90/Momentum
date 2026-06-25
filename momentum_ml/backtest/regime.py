"""
backtest/regime.py – Marknadsregim-klassificering och prestanda-breakdown.

En enda aggregerad backtest-Sharpe döljer om edge:n bara existerar i
en specifik typ av marknad (t.ex. en lång bull-trend 2010-2021). Den
här modulen klassificerar varje vecka som bull/bear/sidledes utifrån
ett enkelt SMA-trend-proxy på ett brett, likaviktat indexsnitt över
universumet, och bryter ner strategins veckoavkastningar per regim.

OBS: Sharpe/avg-return/win-rate per regim är INTE path-dependent
CAGR/Max Drawdown – regimperioderna är diskontinuerliga i tid, så ett
sammanhängande drawdown-mått är inte meningsfullt här. Syftet är att
visa OM edge:n håller över olika marknadsklimat, inte att simulera en
portfölj som bara handlas under en regim.
"""

from typing import Dict

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def _market_proxy(price_data: Dict[str, pd.DataFrame]) -> pd.Series:
    """Likaviktat, normaliserat prisindex över alla tickers (bas=1.0)."""
    normalized = []
    for ticker, df in price_data.items():
        close = df["Close"].dropna()
        if close.empty:
            continue
        normalized.append(close / close.iloc[0])
    if not normalized:
        raise ValueError("Ingen prisdata tillgänglig för marknadsproxyn.")
    combined = pd.concat(normalized, axis=1).mean(axis=1)
    combined.name = "market_proxy"
    return combined.sort_index()


def classify_regimes(
    price_data: Dict[str, pd.DataFrame],
    sma_weeks: int = config.REGIME_SMA_WEEKS,
) -> pd.Series:
    """
    Klassificerar varje vecka som 'bull' (index > SMA, stigande SMA),
    'bear' (index < SMA, fallande SMA) eller 'sideways' (övrigt), baserat
    på den likaviktade marknadsproxyn.
    """
    proxy = _market_proxy(price_data)
    sma = proxy.rolling(sma_weeks).mean()
    sma_slope = sma.diff()

    regime = pd.Series(index=proxy.index, dtype=object)
    regime[:] = "sideways"
    regime[(proxy > sma) & (sma_slope > 0)] = "bull"
    regime[(proxy < sma) & (sma_slope < 0)] = "bear"
    regime[sma.isna()] = np.nan

    return regime.dropna()


def regime_breakdown(
    portfolio_returns: pd.Series,
    regimes: pd.Series,
) -> pd.DataFrame:
    """
    Slår ihop strategins veckoavkastningar med regim-etiketter och
    beräknar Sharpe/avg-return/win-rate per regim.
    """
    aligned = pd.DataFrame({
        "ret": portfolio_returns,
        "regime": regimes.reindex(portfolio_returns.index, method="ffill"),
    }).dropna()

    rows = []
    for regime, group in aligned.groupby("regime"):
        rets = group["ret"]
        sharpe = (rets.mean() / rets.std()) * np.sqrt(52) if rets.std() > 0 else 0.0
        rows.append({
            "regime":     regime,
            "n_weeks":    len(rets),
            "avg_return": rets.mean(),
            "sharpe":     sharpe,
            "win_rate":   (rets > 0).mean(),
        })

    return pd.DataFrame(rows).set_index("regime")


def print_regime_breakdown(breakdown: pd.DataFrame):
    print("\n" + "=" * 50)
    print("  REGIM-BREAKDOWN (ej path-dependent CAGR/DD)")
    print("=" * 50)
    for regime, row in breakdown.iterrows():
        print(f"  {regime:<10} n={int(row['n_weeks']):<4} "
              f"avg_ret={row['avg_return']:+.2%}  "
              f"sharpe={row['sharpe']:.2f}  win_rate={row['win_rate']:.1%}")
    print("=" * 50)
