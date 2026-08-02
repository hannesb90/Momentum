"""
tune_statistical_power.py – Test 1: Statistisk power-analys

Frågar: Är de resultat vi ser statistiskt meningsfulla givet det begränsade
antalet icke-överlappande observationer (holdout 2023-2026 = ~3 år = ~3 icke-
överlappande 52v-perioder)?

Metod:
  1. Block-bootstrap på portföljens veckoavkastningsserie (håller tidskorrelation).
     Blockstorlek = 52v (= en hel innehavscykel). N=2000 replikat → 95%-CI för
     CAGR och Sharpe.
  2. Permutationstest: shufflar portföljens veckoavkastningar 1000 ggr och
     räknar ut hur stor andel av slumpen som slår faktisk CAGR/alpha.
     → p-värde för H0: "portföljens alpha = 0"

Kräver: results/lgbm_model.pkl och cache (ingen ny träning).

    MOMENTUM_HOME=/home/hannesb/momentum_prod_work \\
    PYTHONPATH=/home/hannesb/momentum_prod_work/momentum_ml \\
    /opt/momentum/venv/bin/python tune_statistical_power.py large
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import FEATURE_COLS
from backtest.backtester import MomentumBacktester


def _apply_segment(segment: str):
    """Applicera per-segment config-overrides korrekt (samma som main.py)."""
    seg = config.SEGMENTS.get(segment, config.SEGMENTS[config.DEFAULT_SEGMENT])
    config.RESULTS_DIR      = seg["results_dir"]
    config.MAX_POSITIONS    = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    if "index_ticker"   in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
    if "index_label"    in seg: config.INDEX_BENCHMARK_LABEL  = seg["index_label"]
    if "gate_enabled"   in seg: config.MOMENTUM_GATE_ENABLED  = seg["gate_enabled"]
    if "gate_min"       in seg: config.MOMENTUM_GATE_MIN      = seg["gate_min"]
    if "atr_stop_enabled" in seg: config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    if "forward_weeks"  in seg:
        config.FORWARD_WEEKS   = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
        config.EMBARGO_WEEKS   = seg["embargo_weeks"]
    if "rank_ema_span"  in seg: config.RANK_EMA_SPAN = seg["rank_ema_span"]
    if "drop_features"  in seg:
        config.DROP_FEATURES = seg["drop_features"]
        dropped = set(seg["drop_features"])
        filtered = [c for c in FEATURE_COLS if c not in dropped]
        FEATURE_COLS.clear()
        FEATURE_COLS.extend(filtered)
    return seg


def _cagr(ret_series: pd.Series) -> float:
    n = len(ret_series)
    if n < 2:
        return float("nan")
    return float((1 + ret_series).prod() ** (52 / n) - 1)


def _sharpe(ret_series: pd.Series) -> float:
    if len(ret_series) < 4 or ret_series.std() == 0:
        return float("nan")
    return float(ret_series.mean() / ret_series.std() * np.sqrt(52))


def _max_drawdown(ret_series: pd.Series) -> float:
    pv   = (1 + ret_series).cumprod()
    peak = pv.cummax()
    return float(((pv - peak) / peak).min())


def block_bootstrap_ci(ret: pd.Series, block_size: int = 52,
                       n_boot: int = 2000, ci: float = 0.95) -> dict:
    """Stationary block-bootstrap: drar block av längd block_size med wrap-around."""
    rng  = np.random.default_rng(42)
    vals = ret.values
    n    = len(vals)
    n_blocks = int(np.ceil(n / block_size))

    boot_cagrs, boot_sharpes = np.empty(n_boot), np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n, size=n_blocks)
        blocks = [vals[s: s + block_size] if s + block_size <= n
                  else np.concatenate([vals[s:], vals[:s + block_size - n]])
                  for s in starts]
        sample = np.concatenate(blocks)[:n]
        s = pd.Series(sample)
        boot_cagrs[b]   = _cagr(s)
        boot_sharpes[b] = _sharpe(s)

    alpha = (1 - ci) / 2
    return {
        "cagr_median": float(np.nanmedian(boot_cagrs)),
        "cagr_lo":     float(np.nanpercentile(boot_cagrs,   alpha * 100)),
        "cagr_hi":     float(np.nanpercentile(boot_cagrs,   (1 - alpha) * 100)),
        "sharpe_lo":   float(np.nanpercentile(boot_sharpes, alpha * 100)),
        "sharpe_hi":   float(np.nanpercentile(boot_sharpes, (1 - alpha) * 100)),
        "sharpe_median": float(np.nanmedian(boot_sharpes)),
    }


def permutation_test(port_ret: pd.Series, idx_ret: pd.Series,
                     n_perm: int = 1000) -> tuple:
    """Shufflar portföljens avkastningar, jämför alpha mot faktisk."""
    rng = np.random.default_rng(99)
    vals = port_ret.values
    actual_alpha = _cagr(port_ret) - _cagr(idx_ret)
    perm_alphas  = np.array([
        _cagr(pd.Series(rng.permutation(vals))) - _cagr(idx_ret)
        for _ in range(n_perm)
    ])
    p = float((perm_alphas >= actual_alpha).mean())
    return p, perm_alphas


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg     = _apply_segment(segment)
    label   = seg["label"]
    print(f"[Segment] {segment} ({label}) – Statistical Power Analysis")
    print(f"  forward_weeks={config.FORWARD_WEEKS}, max_positions={config.MAX_POSITIONS}, "
          f"drop_features={len(getattr(config, 'DROP_FEATURES', []))} st borttagna")

    # ── Data ─────────────────────────────────────────────────────────────────
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(
        min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)   # buggmönster 12-fix 2026-07-30 (UTVECKLINGSLOGG #129)

    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    # Poweranalysen gäller den faktiskt sparade strategin. Återanvänd frusna
    # signaler så analysen inte blandas ihop med en feature-/modellombyggnad.
    sig = pd.read_csv(f"{config.RESULTS_DIR}/signals.csv", parse_dates=["Date"]).set_index("Date").sort_index()

    # ── Backtest ─────────────────────────────────────────────────────────────
    bt = MomentumBacktester(sig, data, market_filter=True)
    bt.run()
    pv          = bt._results["portfolio_value"]
    weekly_rets = pv.pct_change().dropna()

    # Index-avkastning
    idx_ticker = config.INDEX_BENCHMARK_TICKER
    if idx_ticker in data and len(data[idx_ticker]) > 10:
        idx_px  = data[idx_ticker]["Close"].reindex(pv.index).ffill()
        idx_ret = idx_px.pct_change().dropna()
    else:
        print(f"  [WARN] Indexdata saknas för {idx_ticker}, sätter idx_ret=0")
        idx_ret = pd.Series(0.0, index=weekly_rets.index)

    # Synkronisera index
    common      = weekly_rets.index.intersection(idx_ret.index)
    weekly_rets = weekly_rets.loc[common]
    idx_ret     = idx_ret.loc[common]

    hw              = config.HOLDOUT_WEEKS
    full_rets       = weekly_rets
    holdout_rets    = weekly_rets.iloc[-hw:]
    holdout_idx_ret = idx_ret.iloc[-hw:]

    # ── Bootstrap ────────────────────────────────────────────────────────────
    print(f"\n  Kör block-bootstrap (block=52v, N=2000) på {len(full_rets)} veckor helperiod "
          f"och {len(holdout_rets)} veckor holdout...")
    full_ci    = block_bootstrap_ci(full_rets,    block_size=52, n_boot=2000)
    holdout_ci = block_bootstrap_ci(holdout_rets, block_size=52, n_boot=2000)

    # ── Permutation ───────────────────────────────────────────────────────────
    print("  Kör permutationstest (N=1000)...")
    p_full,    _  = permutation_test(full_rets,    idx_ret,         n_perm=1000)
    p_holdout, _  = permutation_test(holdout_rets, holdout_idx_ret, n_perm=1000)

    # ── Rapport ───────────────────────────────────────────────────────────────
    n_no_full    = len(full_rets)    // config.FORWARD_WEEKS
    n_no_holdout = len(holdout_rets) // config.FORWARD_WEEKS

    print()
    print("=" * 78)
    print(f"  STATISTISK POWER-ANALYS – {label}")
    print("=" * 78)
    print(f"\n  Datapunkter (icke-överlappande {config.FORWARD_WEEKS}v-perioder):")
    print(f"    Helperiod : {len(full_rets)} veckor  → {n_no_full} perioder")
    print(f"    Holdout   : {len(holdout_rets)} veckor → {n_no_holdout} perioder  ← OBS: litet urval")

    W = 22
    print(f"\n  {'Mätetal':<{W}} {'Faktisk':>9} {'95%-CI lo':>10} {'Median':>9} {'95%-CI hi':>10}")
    print(f"  {'-'*64}")

    def row_pct(name, val, lo, med, hi):
        print(f"  {name:<{W}} {val*100:>+8.1f}% {lo*100:>+9.1f}% {med*100:>+8.1f}% {hi*100:>+9.1f}%")

    def row_num(name, val, lo, med, hi):
        print(f"  {name:<{W}} {val:>9.2f} {lo:>10.2f} {med:>9.2f} {hi:>10.2f}")

    row_pct("Helperiod CAGR",    _cagr(full_rets),    full_ci["cagr_lo"],    full_ci["cagr_median"],    full_ci["cagr_hi"])
    row_pct("Holdout CAGR",      _cagr(holdout_rets), holdout_ci["cagr_lo"], holdout_ci["cagr_median"], holdout_ci["cagr_hi"])
    print()
    row_num("Helperiod Sharpe",  _sharpe(full_rets),  full_ci["sharpe_lo"],    full_ci["sharpe_median"],    full_ci["sharpe_hi"])
    row_num("Holdout Sharpe",    _sharpe(holdout_rets), holdout_ci["sharpe_lo"], holdout_ci["sharpe_median"], holdout_ci["sharpe_hi"])

    print()
    def p_label(p):
        if p < 0.01:  return "✅ p<0.01 (starkt signifikant)"
        if p < 0.05:  return "✅ p<0.05 (signifikant)"
        if p < 0.10:  return "⚠️  p<0.10 (marginellt signifikant)"
        return         f"❌ p={p:.2f} (ej signifikant – kan vara brus)"

    print(f"  Permutationstest alpha vs index:")
    print(f"    Helperiod : p = {p_full:.3f}  → {p_label(p_full)}")
    print(f"    Holdout   : p = {p_holdout:.3f}  → {p_label(p_holdout)}")

    print()
    lo, hi = holdout_ci["cagr_lo"], holdout_ci["cagr_hi"]
    if lo > 0:
        conc = f"✅ 95%-CI EXKLUDERAR noll [{lo*100:+.1f}%..{hi*100:+.1f}%] – holdout statistiskt positiv"
    elif hi < 0:
        conc = f"🔴 95%-CI EXKLUDERAR noll NEGATIVT [{lo*100:+.1f}%..{hi*100:+.1f}%] – holdout signifikant negativ"
    else:
        conc = f"⚠️  95%-CI INKLUDERAR noll [{lo*100:+.1f}%..{hi*100:+.1f}%] – för få obs för säker slutsats"

    print(f"  Slutsats: {conc}")
    print("=" * 78)


if __name__ == "__main__":
    main()
