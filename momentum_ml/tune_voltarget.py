"""
tune_voltarget.py – A/B:ar target-vol-overlayn (Barroso & Santa-Clara) mot
baslinjen utan overlay.

Overlayn skalar bruttoexponeringen mot en mål-vol (skalar bara NER mot kontanter,
long-only, ingen hävstång). Poängen är RISK-justerad: lägre drawdowns och högre
Sharpe/Sortino snarare än högre rå CAGR. Tabellen visar därför de måtten – och
holdouten (äkta OOS) avgör om den behålls, samma regel som fällde v2/PEAD.

Laddar SPARAD modell + cache (ingen omträning), bygger signals en gång och kör om
backtesten per overlay-inställning. Kör på Pi:n EFTER att segmentet tränats:

    /opt/momentum/venv/bin/python tune_voltarget.py [large|small]
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

# (etikett, enabled, target_vol). Baslinjen först.
SETTINGS = [
    ("av (baslinje)", False, None),
    ("target 10%",    True,  0.10),
    ("target 15%",    True,  0.15),
    ("target 20%",    True,  0.20),
]


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
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

    # Signals byggs en gång – overlayn påverkar bara backtesten, inte signalen.
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    hw = config.HOLDOUT_WEEKS

    def evaluate(enabled, target):
        config.VOL_TARGET_ENABLED = enabled
        if target is not None:
            config.VOL_TARGET_ANNUAL = target
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        return s["CAGR"], s["Sharpe"], s["Sortino"], s["Max Drawdown"], b["alpha_cagr"], ho_cagr

    print("\n" + "=" * 82)
    print(f"  TARGET-VOL-SVEP ({seg['label']}) – risk-justerad effekt av overlayn")
    print("=" * 82)
    print(f"  {'overlay':>16} {'CAGR':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>8} {'alfa':>7} {'holdout':>8}")
    print("-" * 82)
    base = None
    for label, enabled, target in SETTINGS:
        cagr, sharpe, sortino, maxdd, alpha, ho = evaluate(enabled, target)
        note = ""
        sh = float(sharpe)
        if base is None:
            base = sh
        elif sh > base:
            note = "  <-- bättre Sharpe än baslinjen"
        print(f"  {label:>16} {cagr:>7} {sharpe:>7} {sortino:>8} {maxdd:>8} "
              f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}%{note}")
    # återställ default
    config.VOL_TARGET_ENABLED = False
    print("-" * 82)
    print("  Behåll overlayn bara om den höjer Sharpe/Sortino ELLER dämpar MaxDD")
    print("  UTAN att försämra holdouten. Annars: risk-hygien som inte lönar sig här.")


if __name__ == "__main__":
    main()
