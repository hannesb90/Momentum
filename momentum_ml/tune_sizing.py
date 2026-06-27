"""
tune_sizing.py – Svep CONVICTION_BLEND × MAX_POSITIONS och mät alfa/Sharpe.

Konverterar modellens bevisade rangordnings-edge (capture_analysis visade +8-10pp
kvantil-spread) till portföljavkastning genom att hitta bästa positionssizing.
Laddar SPARAD modell + cache (ingen omträning) och bygger om signals + backtest
per kombination.

Kör på Pi:n från /opt/momentum/momentum_ml EFTER att segmentet tränats:

    /opt/momentum/venv/bin/python tune_sizing.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import pandas as pd
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import build_all_features, attach_categorical_features, FEATURE_COLS
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report

BLENDS = [0.5, 0.75, 1.0]      # 0=likavikt, 1=ren conviction
NPOS = [10, 15, 20, 25]         # antal innehav


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    print(f"[Segment] {segment} ({seg['label']}) – modell: {config.RESULTS_DIR}/lgbm_model.pkl")

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}

    hw = config.HOLDOUT_WEEKS

    def evaluate(blend, npos):
        config.CONVICTION_BLEND = blend
        config.MAX_POSITIONS = npos
        sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        return s["CAGR"], s["Sharpe"], b["alpha_cagr"], ho_cagr

    print("\n" + "=" * 64)
    print(f"  SIZING-SVEP ({seg['label']}) – alfa mot index, per kombination")
    print("=" * 64)
    print(f"  {'blend':>6} {'innehav':>8} {'CAGR':>7} {'Sharpe':>7} {'alfa':>7} {'holdout':>8}")
    print("-" * 64)
    best = None
    for blend in BLENDS:
        for npos in NPOS:
            cagr, sharpe, alpha, ho = evaluate(blend, npos)
            star = ""
            if best is None or alpha > best[0]:
                best = (alpha, blend, npos); star = "  <-- bäst alfa"
            print(f"  {blend:>6.2f} {npos:>8d} {cagr:>7} {sharpe:>7} "
                  f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}%{star}")
    print("-" * 64)
    print(f"  Bäst alfa: blend={best[1]}, innehav={best[2]}  ({best[0]*100:+.1f}%)")
    print("  (alfa mot likaviktat köp-och-behåll; holdout = äkta out-of-sample)")


if __name__ == "__main__":
    main()
