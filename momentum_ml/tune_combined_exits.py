"""
tune_combined_exits.py – [SCN-HÅLL-2] _trend_exit (SMA-baserad, #115) +
_atr_stop_exit (volatilitetsnormaliserad, #116) samtidigt aktiverade –
aldrig testade tillsammans, bara var för sig (EDGE_RISK_SCENARIO_TESTKO.md
Tier 3 #21). Båda är AV i produktion idag (#115 förkastad, #116 reverserad
efter buggmönster 12-fixen, se #130) - detta har lägre praktisk brådska än
kvällens andra tester, men frågan "täcker de olika fall, eller är den ena
redundant om båda är på" är obesvarad.

Fyra varianter: av/av (baslinje), bara trend_exit (EXIT_SMA_WEEKS=20,
config-default), bara atr_stop (ATR_STOP_MULT=3,5, #116:s tidigare
SHADOW-nivå), båda samtidigt. Redan patchad mot buggmönster 12
(CAP_TIER_MAP.update).

    /opt/momentum/venv/bin/python3 tune_combined_exits.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, attach_fundamentals_features, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester

SETTINGS = [
    ("av/av (baslinje)",       False, False),
    ("bara trend_exit (20v)",  True,  False),
    ("bara atr_stop (3.5x)",   False, True),
    ("båda samtidigt",         True,  True),
]


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    if "forward_weeks" in seg:
        config.FORWARD_WEEKS = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    if "drop_features" in seg:
        dropped_set = set(seg["drop_features"])
        filtered = [c for c in FEATURE_COLS if c not in dropped_set]
        FEATURE_COLS.clear()
        FEATURE_COLS.extend(filtered)

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)   # buggmönster 12-fix
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment=segment, prices=data)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    hw = config.HOLDOUT_WEEKS

    def evaluate(trend_on, atr_on):
        config.ASYMMETRIC_EXIT = trend_on
        config.EXIT_SMA_WEEKS = 20
        config.ATR_STOP_ENABLED = atr_on
        config.ATR_STOP_MULT = 3.5
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        return s["CAGR"], s["Sharpe"], s["Max Drawdown"], ho_cagr

    print("\n" + "=" * 90)
    print(f"  KOMBINERADE EXITS ({seg['label']}) – trend_exit + atr_stop var för sig och tillsammans")
    print("=" * 90)
    print(f"  {'variant':<24} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'holdout':>9}")
    print("-" * 90)
    for label, trend_on, atr_on in SETTINGS:
        cagr, sharpe, maxdd, ho = evaluate(trend_on, atr_on)
        print(f"  {label:<24} {cagr:>8} {sharpe:>8} {maxdd:>8} {ho*100:>+8.1f}%")
    config.ASYMMETRIC_EXIT = False
    config.ATR_STOP_ENABLED = False
    print("\n[combined_exits] Klart.")


if __name__ == "__main__":
    main()
