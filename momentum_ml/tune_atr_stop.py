"""
tune_atr_stop.py – A/B:ar den ATR-baserade trailing-stopen (individnivå) mot
baslinjen utan den.

Stopet säljer ETT innehav mellan schemalagda rebalanseringar om priset faller
ATR_STOP_MULT × ATR från sin högsta notering SEDAN KÖP - en volatilitets-
normaliserad, per-position variant av _trend_exit (som är SMA-baserad och
kräver att BREDARE trend redan vänt). Poängen är att kapa en enskild
"rakets" snabba rekyl innan SMA:n hinner reagera - risk-hygien, precis som
VOL_TARGET_ENABLED/SIZING_MODE=inverse_vol. Holdouten (äkta OOS) avgör om
den behålls, samma regel som fällde/adopterade de andra.

Laddar SPARAD modell + cache (ingen omträning), bygger signals en gång och
kör om backtesten per tröskel. Kör på Pi:n EFTER att segmentet tränats:

    /opt/momentum/venv/bin/python tune_atr_stop.py [large|small]
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
from backtest.benchmark import benchmark_report

# (etikett, enabled, mult). Baslinjen (av) först. Fast ATR_WINDOW_WEEKS=10
# (config-default) - fönstrets känslighet är en separat fråga, sveps inte här.
SETTINGS = [
    ("av (baslinje)", False, None),
    ("1.5x ATR",       True,  1.5),
    ("2.0x ATR",       True,  2.0),
    ("2.5x ATR",       True,  2.5),
    ("3.0x ATR",       True,  3.0),
    ("3.5x ATR",       True,  3.5),
    ("4.0x ATR",       True,  4.0),
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
    # OHLCV krävs (High/Low för ATR) - fetch_weekly_data ger redan detta.
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    # Tillväxt-features (rev_growth_yoy/eps_growth_yoy/days_since_report) ur MFN-
    # rapporternas hårddata - modellen förväntar sig dessa kolumner (FEATURE_COLS),
    # se main.py:s STEG 2 (samma anropsordning: EFTER kategoriska features, FÖRE
    # to_model_df/predict). Saknas underlaget blir kolumnerna bara NaN, ingen krasch.
    feats = attach_fundamentals_features(feats, segment=segment)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}

    # Signals byggs en gång – ATR-stopet påverkar bara EXEKVERINGEN i backtesten,
    # inte vilka bolag modellen rankar högt.
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    hw = config.HOLDOUT_WEEKS

    def evaluate(enabled, mult):
        config.ATR_STOP_ENABLED = enabled
        if mult is not None:
            config.ATR_STOP_MULT = mult
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        return s["CAGR"], s["Sharpe"], s["Sortino"], s["Max Drawdown"], b["alpha_cagr"], ho_cagr

    print("\n" + "=" * 82)
    print(f"  ATR-STOP-SVEP ({seg['label']}) – risk-justerad effekt av individ-stopet")
    print("=" * 82)
    print(f"  {'tröskel':>16} {'CAGR':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>8} {'alfa':>7} {'holdout':>8}")
    print("-" * 82)
    base = None
    for label, enabled, mult in SETTINGS:
        cagr, sharpe, sortino, maxdd, alpha, ho = evaluate(enabled, mult)
        note = ""
        sh = float(sharpe)
        if base is None:
            base = sh
        elif sh > base:
            note = "  <-- bättre Sharpe än baslinjen"
        print(f"  {label:>16} {cagr:>7} {sharpe:>7} {sortino:>8} {maxdd:>8} "
              f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}%{note}")
    # återställ default
    config.ATR_STOP_ENABLED = False
    print("-" * 82)
    print("  Behåll stopet bara om det höjer Sharpe/Sortino ELLER dämpar MaxDD UTAN att")
    print("  försämra holdouten. En för TAJT tröskel (låg multipel) riskerar att bara")
    print("  stoppa ut brus (whipsaw) - se om resultatet degraderar monotont nedåt i mult.")


if __name__ == "__main__":
    main()
