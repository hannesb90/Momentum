"""
tune_cash_drag_atr.py – Kvantifierar cash-drag-kostnaden av mellanliggande
ATR-trailing-stop-exits (EDGE_RISK_SCENARIO_TESTKO.md Tier 2 #11,
[SCN-SÄLJ-2]). _atr_stop_exit() säljer en position mellan schemalagda
rebalanseringar men köper INGET nytt - kapitalet ligger kontant tills nästa
schemalagda rebalans. För large-segmentet är REBALANCE_WEEKS=52, dvs en exit
strax efter en rebalans kan i värsta fall lämna kapitalet kontant i nästan
ETT ÅR. #116 (UTVECKLINGSLOGG) fann att ATR_STOP_MULT=3.5x var en svag men
genuin SHADOW-kandidat (MaxDD -21,7%->-18,1%, holdout i praktiken oförändrat)
men mätte ALDRIG denna specifika kostnadskomponent separat - bara nettot i
CAGR/Sharpe/MaxDD, som redan innefattar cash-draget dolt i totalsumman.

Metod: kör samma backtest som #116:s 3.5x-variant (samma modell/signaler,
ta_filter="score", market_filter=True), men med en instrumenterad
MomentumBacktester-subklass som loggar varje ATR-stop-exit (datum, ticker).
Efter körningen: för varje exit, hitta nästa SCHEMALAGDA rebalanseringsdatum
(samma i % REBALANCE_WEEKS == 0-logik som run() själv använder) och mät (a)
antal veckor kapitalet låg kontant, (b) segmentbenchmarkens (XACT-SVERIGE.ST)
avkastning under exakt den perioden - den missade marknadsavkastningen är en
direkt, konservativ proxy för draget (antar att den frigjorda platsen annars
skulle hållit ett genomsnittligt marknadsexponerat innehav, inte specifikt
den sålda aktien själv som redan visat sig svag).

    /opt/momentum/venv/bin/python3 tune_cash_drag_atr.py [large|small]
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

ATR_STOP_MULT = 3.5   # #116:s SHADOW-kandidat


class InstrumentedBacktester(MomentumBacktester):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exit_events = []   # (date, ticker)

    def _atr_stop_exit(self, date, cash):
        before = set(self._portfolio.keys())
        cash = super()._atr_stop_exit(date, cash)
        for ticker in before - set(self._portfolio.keys()):
            self.exit_events.append((date, ticker))
        return cash


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    if "index_ticker" in seg: config.INDEX_BENCHMARK_TICKER = seg["index_ticker"]
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
    print(f"[cash_drag] {segment} ({seg['label']}), REBALANCE_WEEKS={config.REBALANCE_WEEKS}, "
          f"ATR_STOP_MULT={ATR_STOP_MULT}, benchmark={config.INDEX_BENCHMARK_TICKER}")

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

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}
    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")

    config.ATR_STOP_ENABLED = True
    config.ATR_STOP_MULT = ATR_STOP_MULT
    bt = InstrumentedBacktester(sig, data, market_filter=True)
    bt.run()
    config.ATR_STOP_ENABLED = False   # återställ default

    dates = list(sig.index.unique().sort_values())
    rw = max(int(config.REBALANCE_WEEKS), 1)
    idx_of = {d: i for i, d in enumerate(dates)}
    bench = config.INDEX_BENCHMARK_TICKER

    rows = []
    for date, ticker in bt.exit_events:
        i = idx_of.get(date)
        if i is None:
            continue
        # nästa schemalagda rebalans: minsta k>i med k % rw == 0
        k = ((i // rw) + 1) * rw
        if k >= len(dates):
            k = len(dates) - 1
        idle_weeks = k - i
        p0 = bt._get_price(bench, date)
        p1 = bt._get_price(bench, dates[k])
        bench_ret = (p1 / p0 - 1.0) if (p0 and p1) else None
        rows.append({"date": date, "ticker": ticker, "idle_weeks": idle_weeks, "bench_ret": bench_ret})

    print(f"\n[cash_drag] {len(rows)} ATR-stop-exits (mult={ATR_STOP_MULT}) i backtesten.")
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows)
        valid = df.dropna(subset=["bench_ret"])
        print(f"  Genomsnittligt antal veckor kontant till nästa rebalans: {df['idle_weeks'].mean():.1f} "
              f"(min={df['idle_weeks'].min()}, max={df['idle_weeks'].max()}, median={df['idle_weeks'].median():.0f})")
        print(f"  Genomsnittlig missad benchmark-avkastning ({bench}) under kontantperioden: "
              f"{valid['bench_ret'].mean():+.2%} (median {valid['bench_ret'].median():+.2%})")
        print(f"  Andel exits där benchmarken steg under kontantperioden (dvs draget var negativt): "
              f"{(valid['bench_ret'] > 0).mean():.1%}")
        print(f"  Summan av alla missade avkastningar (grov, icke-sammansatt magnitudindikation): "
              f"{valid['bench_ret'].sum():+.1%} över {len(valid)} exits, {len(dates)} veckor totalt "
              f"({dates[0].date()} -> {dates[-1].date()})")
        print("\n  Per-exit detalj:")
        for _, r in df.sort_values("date").iterrows():
            br = f"{r['bench_ret']:+.2%}" if pd.notna(r["bench_ret"]) else "n/a"
            print(f"    {r['date'].date()}  {r['ticker']:<16} idle={int(r['idle_weeks']):>3}v  "
                  f"missad_bench_avk={br}")
    print("\n[cash_drag] Klart.")


if __name__ == "__main__":
    main()
