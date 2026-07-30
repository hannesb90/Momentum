"""
tune_voltarget.py – A/B:ar target-vol-overlayn (Barroso & Santa-Clara) mot
baslinjen utan overlay.

Overlayn skalar bruttoexponeringen mot en mål-vol (skalar bara NER mot kontanter,
long-only, ingen hävstång). Poängen är RISK-justerad: lägre drawdowns och högre
Sharpe/Sortino snarare än högre rå CAGR. Tabellen visar därför de måtten – och
holdouten (äkta OOS) avgör om den behålls, samma regel som fällde v2/PEAD.

Laddar SPARAD modell + cache (ingen omträning), bygger signals en gång och kör om
backtesten per overlay-inställning. Kör på Pi:n EFTER att segmentet tränats:

    MOMENTUM_HOME=/home/hannesb/momentum_prod_work \\
    PYTHONPATH=/home/hannesb/momentum_prod_work/momentum_ml \\
    /opt/momentum/venv/bin/python tune_voltarget.py [large|small]

FIX 2026-07-29: applicerar nu alla per-segment overrides (forward_weeks,
drop_features, gate_enabled, atr_stop_enabled, fundamentals) korrekt.
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

# (etikett, enabled, target_vol). Baslinjen (config-default) ALLTID FÖRST.
SETTINGS = [
    ("av (baslinje)", False, None),
    ("target  8%",    True,  0.08),
    ("target 10%",    True,  0.10),
    ("target 12%",    True,  0.12),
    ("target 15%",    True,  0.15),
]


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg     = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]

    # ── Applicera ALLA segment-overrides (samma logik som main.py) ─────────
    config.RESULTS_DIR      = seg["results_dir"]
    config.MAX_POSITIONS    = seg.get("max_positions",    config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    if "index_ticker"    in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
    if "index_label"     in seg: config.INDEX_BENCHMARK_LABEL  = seg["index_label"]
    if "gate_enabled"    in seg: config.MOMENTUM_GATE_ENABLED  = seg["gate_enabled"]
    if "gate_min"        in seg: config.MOMENTUM_GATE_MIN      = seg["gate_min"]
    if "atr_stop_enabled" in seg: config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    if "forward_weeks"   in seg:
        config.FORWARD_WEEKS   = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
        config.EMBARGO_WEEKS   = seg["embargo_weeks"]
    if "rank_ema_span"   in seg: config.RANK_EMA_SPAN = seg["rank_ema_span"]
    if "drop_features"   in seg:
        config.DROP_FEATURES = seg["drop_features"]
        dropped = set(seg["drop_features"])
        filtered = [c for c in FEATURE_COLS if c not in dropped]
        FEATURE_COLS.clear()
        FEATURE_COLS.extend(filtered)

    print(f"[Segment] {segment} ({seg['label']}) – modell: {config.RESULTS_DIR}/lgbm_model.pkl")
    print(f"  forward_weeks={config.FORWARD_WEEKS}, max_positions={config.MAX_POSITIONS}, "
          f"drop_features={len(getattr(config,'DROP_FEATURES',[]))} st, "
          f"atr_stop={config.ATR_STOP_ENABLED}")

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)   # buggmönster 12-fix 2026-07-30 (UTVECKLINGSLOGG #129)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment=segment, prices=data)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm  = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5]))
             for t, f in feats.items() if len(f) > 0}

    # Signals byggs en gång – vol-overlaydn påverkar bara backtesten, inte signalen.
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    hw  = config.HOLDOUT_WEEKS

    # Spara undan ursprungsvärde så vi kan återställa efter svepet
    orig_enabled = config.VOL_TARGET_ENABLED
    orig_target  = config.VOL_TARGET_ANNUAL

    def evaluate(enabled, target):
        config.VOL_TARGET_ENABLED = enabled
        if target is not None:
            config.VOL_TARGET_ANNUAL = target
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s  = bt.statistics()
        b  = benchmark_report(bt._results["portfolio_value"], data)
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

    # Återställ original-config (inte bara False som tidigare)
    config.VOL_TARGET_ENABLED = orig_enabled
    config.VOL_TARGET_ANNUAL  = orig_target
    print("-" * 82)
    print("  Behåll overlayn bara om den höjer Sharpe/Sortino ELLER dämpar MaxDD")
    print("  UTAN att försämra holdouten. Annars: risk-hygien som inte lönar sig här.")


if __name__ == "__main__":
    main()
