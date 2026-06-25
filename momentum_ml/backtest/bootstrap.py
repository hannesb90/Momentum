"""
backtest/bootstrap.py – Statistisk robusthet för backtestresultat.

En enskild historisk path säger för lite om en strategis verkliga
edge. De här funktionerna skattar osäkerhet kring Sharpe/CAGR/MaxDD
(block bootstrap) och sannolikheten att den sanna Sharpe-kvoten är
positiv givet skevhet/kurtosis i avkastningarna (Probabilistic Sharpe
Ratio, Bailey & López de Prado).
"""

import math
from typing import Dict

import numpy as np
import pandas as pd
from scipy.stats import norm

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

EULER_MASCHERONI = 0.5772156649015329


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def block_bootstrap_stats(
    returns: pd.Series,
    n_sims: int = config.BOOTSTRAP_N_SIMS,
    block_weeks: int = config.BOOTSTRAP_BLOCK_WEEKS,
    ann_factor: int = 52,
    seed: int = None,
) -> Dict[str, Dict[str, float]]:
    """
    Block bootstrap på veckoavkastningar. Block-resampling (i stället för
    IID-resampling av enskilda veckor) bevarar kort-sikt-autokorrelation,
    vilket gör konfidensintervallen mindre missvisande för en
    momentum-strategi.

    Returnerar {metric: {p5, p50, p95}} för sharpe/cagr/max_dd, plus
    andelen simuleringar med Sharpe <= 0.
    """
    rng = np.random.default_rng(seed)
    r = returns.dropna().values
    n = len(r)
    if n < block_weeks * 4:
        raise ValueError(f"För få datapunkter ({n}) för en meningsfull bootstrap.")

    n_blocks = int(np.ceil(n / block_weeks))
    sharpes, cagrs, max_dds = [], [], []

    for _ in range(n_sims):
        starts = rng.integers(0, n - block_weeks + 1, size=n_blocks)
        sample = np.concatenate([r[s:s + block_weeks] for s in starts])[:n]

        mean, std = sample.mean(), sample.std()
        sharpe = (mean / std) * np.sqrt(ann_factor) if std > 0 else 0.0

        cum = np.cumprod(1 + sample)
        cagr = cum[-1] ** (ann_factor / n) - 1
        dd = (cum / np.maximum.accumulate(cum) - 1).min()

        sharpes.append(sharpe)
        cagrs.append(cagr)
        max_dds.append(dd)

    def _pct(arr):
        return {
            "p5":  float(np.percentile(arr, 5)),
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
        }

    return {
        "sharpe": _pct(sharpes),
        "cagr":   _pct(cagrs),
        "max_dd": _pct(max_dds),
        "prob_sharpe_below_0": float(np.mean(np.array(sharpes) <= 0)),
    }


def probabilistic_sharpe_ratio(
    returns: pd.Series,
    benchmark_sr: float = 0.0,
    ann_factor: int = 52,
) -> float:
    """
    PSR: sannolikheten att den sanna (annualiserade) Sharpe-kvoten
    överstiger benchmark_sr, med hänsyn till skevhet och kurtosis i
    veckoavkastningarna (en hög Sharpe på skev/fettsvansad data är mindre
    trovärdig än samma Sharpe på normalfördelad data).
    """
    r = returns.dropna().values
    n = len(r)
    mean, std = r.mean(), r.std()
    if std == 0 or n < 4:
        return 0.5

    sr_period = mean / std
    skew = pd.Series(r).skew()
    kurt = pd.Series(r).kurt() + 3  # excess -> raw kurtosis

    denom = math.sqrt(max(1 - skew * sr_period + (kurt - 1) / 4 * sr_period ** 2, 1e-12))
    benchmark_period = benchmark_sr / math.sqrt(ann_factor)
    z = (sr_period - benchmark_period) * math.sqrt(n - 1) / denom

    return _norm_cdf(z)


def expected_max_sharpe(n_trials: int, trial_sr_std: float = 1.0) -> float:
    """
    Förväntat maximum av n_trials oberoende Sharpe-skattningar (alla med
    sann Sharpe=0, std=trial_sr_std), enligt Bailey & López de Prado.
    Detta är benchmark-Sharpe:n man måste slå för att en uppmätt Sharpe
    ska räknas som signal snarare än det bästa resultatet av att testat
    många strategier/parametrar (multiple-testing-bias).
    """
    if n_trials <= 1:
        return 0.0
    z_term = (1 - EULER_MASCHERONI) * norm.ppf(1 - 1.0 / n_trials)
    z_term += EULER_MASCHERONI * norm.ppf(1 - 1.0 / (n_trials * math.e))
    return trial_sr_std * z_term


def deflated_sharpe_ratio(
    returns: pd.Series,
    n_trials: int = 1,
    trial_sr_std: float = 1.0,
    ann_factor: int = 52,
) -> float:
    """
    PSR med expected_max_sharpe(n_trials) som benchmark i stället för 0,
    vilket deflaterar konfidensen i proportion till hur många
    strategier/parameterval som testades innan den här valdes.
    n_trials=1 reducerar till vanlig PSR.
    """
    benchmark_sr = expected_max_sharpe(n_trials, trial_sr_std) * math.sqrt(ann_factor)
    return probabilistic_sharpe_ratio(returns, benchmark_sr=benchmark_sr, ann_factor=ann_factor)


def robustness_report(returns: pd.Series, n_trials: int = 1) -> Dict:
    """Sammanställer bootstrap-CI + PSR/DSR i ett resultat redo att skrivas ut."""
    boot = block_bootstrap_stats(returns)
    psr  = probabilistic_sharpe_ratio(returns)
    dsr  = deflated_sharpe_ratio(returns, n_trials=n_trials)
    return {"bootstrap": boot, "psr": psr, "dsr": dsr, "n_trials": n_trials}


def print_robustness_report(returns: pd.Series, n_trials: int = 1):
    report = robustness_report(returns, n_trials=n_trials)
    boot, psr, dsr = report["bootstrap"], report["psr"], report["dsr"]

    print("\n" + "=" * 50)
    print("  ROBUSTHET (block bootstrap, n={})".format(config.BOOTSTRAP_N_SIMS))
    print("=" * 50)
    print(f"  Sharpe   p5={boot['sharpe']['p5']:.2f}  p50={boot['sharpe']['p50']:.2f}  "
          f"p95={boot['sharpe']['p95']:.2f}")
    print(f"  CAGR     p5={boot['cagr']['p5']:.1%}  p50={boot['cagr']['p50']:.1%}  "
          f"p95={boot['cagr']['p95']:.1%}")
    print(f"  Max DD   p5={boot['max_dd']['p5']:.1%}  p50={boot['max_dd']['p50']:.1%}  "
          f"p95={boot['max_dd']['p95']:.1%}")
    print(f"  P(Sharpe <= 0)        {boot['prob_sharpe_below_0']:.1%}")
    print(f"  Probabilistic Sharpe  {psr:.1%}  (P(sann Sharpe > 0))")
    if n_trials > 1:
        print(f"  Deflated Sharpe       {dsr:.1%}  (n_trials={n_trials})")
    print("=" * 50)
