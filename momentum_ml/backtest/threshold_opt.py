"""
backtest/threshold_opt.py – Data-driven köptröskel.

I stället för en hårdkodad köpregel (prob_up > 0.5) söker vi igenom ett rutnät
av kandidattrösklar PÅ DEV-PERIODEN (in-sample) och väljer den som maximerar
ett robust mål (default Sharpe). Den valda tröskeln tillämpas sedan på hela
körningen och valideras implicit på den frusna holdouten – som ALDRIG används
i sökningen, så holdout-statistiken förblir ett ärligt out-of-sample-test.

Varför detta behövs: en välkalibrerad P(>5% på 4 veckor) passerar sällan 0.5,
så portföljen hamnar nästan alltid i kontanter (låg avkastning, pytteliten
drawdown, låg "win rate"). Att låta datan välja nivån löser cash-draget utan
att vi gissar en magisk konstant.

Överanpassningsskydd:
  * Sökningen ser bara dev-data (in_sample_end skär bort holdouten).
  * Varje testad tröskel räknas som ett "trial" -> höjer n_trials -> deflaterar
    Deflated Sharpe Ratio (multipeltestning), se backtest/bootstrap.py.
  * Default-målet är Sharpe (riskjusterat), inte rå avkastning – rå max-
    avkastning lockar mot en knivseggs-tröskel som inte generaliserar.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from models.ensemble import build_full_output
from backtest.backtester import MomentumBacktester


# ─────────────────────────────────────────────────────────────────────────────
# Målfunktion
# ─────────────────────────────────────────────────────────────────────────────

def _objective_value(pv: pd.Series, objective: str) -> float:
    """
    Räknar ut målvärdet för en portföljvärde-serie (veckodata).
      sharpe – mean/std * sqrt(52)   (riskjusterat, default)
      cagr   – årlig tillväxttakt    (rå avkastning)
      calmar – CAGR / |max drawdown| (avkastning per drawdown-enhet)
    Tomma/degenererade serier (t.ex. alltid kontanter) ger -inf så att de
    aldrig vinner sökningen.
    """
    rets = pv.pct_change().dropna()
    if len(rets) < 2 or rets.std() == 0:
        return float("-inf")

    if objective == "sharpe":
        return float(rets.mean() / rets.std() * np.sqrt(52))

    weeks = len(rets)
    cagr = (pv.iloc[-1] / pv.iloc[0]) ** (52 / weeks) - 1
    if objective == "cagr":
        return float(cagr)
    if objective == "calmar":
        max_dd = (pv / pv.cummax() - 1).min()
        if max_dd >= 0:
            return float("-inf")
        return float(cagr / abs(max_dd))

    raise ValueError(
        f"Okänt threshold-objective: {objective!r}. Välj 'sharpe', 'cagr' eller 'calmar'."
    )


def _invested_fraction(results: pd.DataFrame) -> float:
    """Andel veckor med minst en öppen position (för tie-break och diagnostik)."""
    if "n_positions" not in results.columns or len(results) == 0:
        return 0.0
    return float((results["n_positions"] > 0).mean())


# ─────────────────────────────────────────────────────────────────────────────
# Sökning
# ─────────────────────────────────────────────────────────────────────────────

def optimize_buy_threshold(
    lgbm_preds_by_ticker: Dict[str, pd.DataFrame],
    lstm_preds_by_ticker: Optional[Dict[str, pd.DataFrame]],
    feature_dfs: Dict[str, pd.DataFrame],
    ensemble,
    prices: Dict[str, pd.DataFrame],
    in_sample_end: Optional[pd.Timestamp],
    ta_filter: Optional[str] = None,
    ta_strictness: str = config.TA_FILTER_STRICTNESS,
    grid: Optional[List[float]] = None,
    objective: Optional[str] = None,
) -> Tuple[float, List[dict]]:
    """
    Söker fram köptröskeln som maximerar `objective` på in-sample-perioden
    (datum < in_sample_end). Returnerar (best_threshold, grid_results), där
    grid_results är en lista med {threshold, score, invested} för transparens.

    in_sample_end: holdout-startdatum. Alla preds skärs till datum < detta så
    att holdouten aldrig påverkar valet. None = använd all data (ingen holdout).
    """
    grid = list(grid if grid is not None else config.BUY_THRESHOLD_GRID)
    objective = objective or config.THRESHOLD_OBJECTIVE

    # Skär preds till in-sample-fönstret (undvik holdout-läckage).
    def _slice(preds):
        if preds is None:
            return None
        if in_sample_end is None:
            return preds
        out = {}
        for t, p in preds.items():
            sl = p[p.index < in_sample_end]
            if len(sl) > 0:
                out[t] = sl
        return out

    lg_is = _slice(lgbm_preds_by_ticker)
    ls_is = _slice(lstm_preds_by_ticker)

    grid_results: List[dict] = []
    for thr in grid:
        signals = build_full_output(
            lg_is, ls_is, feature_dfs, ensemble,
            ta_filter=ta_filter, ta_strictness=ta_strictness,
            buy_threshold=thr,
        )
        if signals.empty:
            grid_results.append({"threshold": thr, "score": float("-inf"), "invested": 0.0})
            continue

        bt = MomentumBacktester(signals, prices)
        results = bt.run()
        score = _objective_value(results["portfolio_value"], objective)
        grid_results.append({
            "threshold": thr,
            "score": score,
            "invested": _invested_fraction(results),
        })

    # Välj högst score; tie-break mot att vara mer investerad (mot cash-trap).
    best = max(grid_results, key=lambda r: (round(r["score"], 4), r["invested"]))
    return best["threshold"], grid_results


def print_threshold_search(best: float, grid_results: List[dict], objective: str):
    """Skriver ut sökningens resultat (alla testade trösklar + vald nivå)."""
    print("\n" + "=" * 50)
    print(f"  KÖPTRÖSKEL-SÖKNING (mål: {objective}, in-sample/dev)")
    print("=" * 50)
    print(f"  {'tröskel':>8}  {'score':>10}  {'investerad':>10}")
    for r in grid_results:
        mark = "  <- vald" if r["threshold"] == best else ""
        score = "-inf" if r["score"] == float("-inf") else f"{r['score']:.3f}"
        print(f"  {r['threshold']:>8.2f}  {score:>10}  {r['invested']:>9.0%}{mark}")
    print("=" * 50)
