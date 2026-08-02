"""
tune_asymmetric_exit.py – Test 4: A/B-test av ASYMMETRIC_EXIT (SMA-trendbaserad exit)

Config-kommentaren (config.py rad ~95) säger explicit:
  "slå på och A/B-testa (predict-only) innan den görs permanent"

Testet: Backtestaren stöder redan ASYMMETRIC_EXIT – den säljer ett innehav
om kursen faller under EXIT_SMA_WEEKS-veckors glidande medel MELLAN ordinarie
rebalanseringar, utan att köpa ett nytt (kapital stannar i kassa).

Vi testar:
  - Av (baslinje)
  - EXIT_SMA_WEEKS = 13  (kortare SMA, mer reaktiv)
  - EXIT_SMA_WEEKS = 20  (config-default, balanserad)
  - EXIT_SMA_WEEKS = 26  (trögare, färre falsklarm)

Kräver: results/lgbm_model.pkl + cache (ingen omträning).
Inga hämtningar från FI/insynsregister.

    MOMENTUM_HOME=/home/hannesb/momentum_prod_work \\
    PYTHONPATH=/home/hannesb/momentum_prod_work/momentum_ml \\
    /opt/momentum/venv/bin/python tune_asymmetric_exit.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import config

# Hämta segment-konfigurationen först för att applicera drop_features innan import av feature_engineering
segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
seg     = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]

# Applicera drop_features till config innan feature_engineering importeras
if "drop_features" in seg:
    config.DROP_FEATURES = seg["drop_features"]

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

# (etikett, exit_enabled, sma_weeks)
SETTINGS = [
    ("av (baslinje)", False, 20),
    ("SMA-exit 13v",  True,  13),
    ("SMA-exit 20v",  True,  20),   # config default
    ("SMA-exit 26v",  True,  26),
]


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg     = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]

    # ── Applicera ALLA segment-overrides ─────────────────────────────────────
    config.RESULTS_DIR      = seg["results_dir"]
    config.MAX_POSITIONS    = seg.get("max_positions",    config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    if "index_ticker"     in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
    if "index_label"      in seg: config.INDEX_BENCHMARK_LABEL  = seg["index_label"]
    if "gate_enabled"     in seg: config.MOMENTUM_GATE_ENABLED  = seg["gate_enabled"]
    if "gate_min"         in seg: config.MOMENTUM_GATE_MIN      = seg["gate_min"]
    if "atr_stop_enabled" in seg: config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    if "forward_weeks"    in seg:
        config.FORWARD_WEEKS   = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
        config.EMBARGO_WEEKS   = seg["embargo_weeks"]
    if "rank_ema_span"    in seg: config.RANK_EMA_SPAN = seg["rank_ema_span"]

    print(f"[Segment] {segment} ({seg['label']}) – ASYMMETRIC EXIT SWEEP")
    print(f"  forward_weeks={config.FORWARD_WEEKS}, max_positions={config.MAX_POSITIONS}, "
          f"atr_stop={config.ATR_STOP_ENABLED}")

    # ── Data & signals ────────────────────────────────────────────────────────
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

    # Signals byggs en gång – asymmetric exit påverkar bara backtesten
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    hw  = config.HOLDOUT_WEEKS

    # Spara ursprungsvärden
    orig_exit = config.ASYMMETRIC_EXIT
    orig_sma  = config.EXIT_SMA_WEEKS

    def evaluate(exit_enabled, sma_weeks):
        config.ASYMMETRIC_EXIT = exit_enabled
        config.EXIT_SMA_WEEKS  = sma_weeks
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s  = bt.statistics()
        b  = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1

        # Räkna antal early exits (mäter om regeln triggar för ofta)
        results = bt._results
        n_early = results.get("n_asymmetric_exits", "N/A")
        return s["CAGR"], s["Sharpe"], s["Sortino"], s["Max Drawdown"], b["alpha_cagr"], ho_cagr, n_early

    print("\n" + "=" * 90)
    print(f"  ASYMMETRIC EXIT SVEP ({seg['label']}) – SMA-trendbaserad exit mellan rebalanseringar")
    print("=" * 90)
    print(f"  {'konfiguration':>16} {'CAGR':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>8} "
          f"{'alfa':>7} {'holdout':>8} {'exits':>7}")
    print("-" * 90)

    base_sharpe = None
    for label, exit_en, sma_w in SETTINGS:
        cagr, sharpe, sortino, maxdd, alpha, ho, n_exits = evaluate(exit_en, sma_w)
        note = ""
        sh = float(sharpe)
        if base_sharpe is None:
            base_sharpe = sh
        elif sh > base_sharpe:
            note = "  <-- bättre Sharpe"
        print(f"  {label:>16} {cagr:>7} {sharpe:>7} {sortino:>8} {maxdd:>8} "
              f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}% {str(n_exits):>7}{note}")

    # Återställ
    config.ASYMMETRIC_EXIT = orig_exit
    config.EXIT_SMA_WEEKS  = orig_sma

    print("-" * 90)
    print("  Beslutskriterium: Aktivera om holdout-CAGR förbättras OCH MaxDD minskar")
    print("  UTAN att exits-räknaren är orimligt hög (>50% av innehavsperioderna → whipsaw).")


if __name__ == "__main__":
    main()
