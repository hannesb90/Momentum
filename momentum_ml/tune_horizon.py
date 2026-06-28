"""
tune_horizon.py – Är FORWARD_WEEKS (13) den optimala horisonten? Svep ±några v.

Tränar OM modellen för varje horisont (targetet = framåtavkastning över horisonten,
så det går inte att predict-only:a). Kör large-segmentet och skriver alfa/Sharpe/
holdout per horisont. REBALANCE_WEEKS och EMBARGO_WEEKS följer horisonten.

Kör på Pi:n från /opt/momentum/momentum_ml (i bakgrunden – tar ~20-40 min):

    nohup env PYTHONUNBUFFERED=1 /opt/momentum/venv/bin/python tune_horizon.py > /tmp/horizon_sweep.log 2>&1 &
    tail -f /tmp/horizon_sweep.log
"""
import sys, gc
sys.path.insert(0, '.')
import pandas as pd
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import build_all_features, attach_categorical_features, to_model_df, FEATURE_COLS
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report

HORIZONS = [8, 10, 11, 12, 13, 14, 15, 17]


def main():
    seg = config.SEGMENTS["large"]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    print("\n" + "=" * 70)
    print("  HORISONT-SVEP (large) – tränar om per horisont")
    print("=" * 70)
    print(f"  {'horisont':>8} {'CAGR':>7} {'Sharpe':>7} {'alfa':>7} {'holdout':>8} {'spread':>8}")
    print("-" * 70)

    best = None
    for fw in HORIZONS:
        config.FORWARD_WEEKS = fw
        config.REBALANCE_WEEKS = fw
        config.EMBARGO_WEEKS = fw

        feats = build_all_features(data)
        feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
        mdf = to_model_df(feats)
        all_dates = mdf.index.unique().sort_values()
        holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None
        dev = mdf[mdf.index < holdout_start] if holdout_start is not None else mdf

        lgbm = MomentumLGBM()
        lgbm.fit_walk_forward(dev)
        preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}
        sig = build_full_output(preds, None, {t: f.assign(ticker=t) for t, f in feats.items()},
                                MomentumEnsemble(), ta_filter="score")
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-config.HOLDOUT_WEEKS:] if len(pv) > config.HOLDOUT_WEEKS else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1

        # capture-spread (hög vs låg prob_up faktisk framåtavkastning)
        panel = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d})
        fr = panel.shift(-fw) / panel - 1
        sig2 = sig.reset_index()
        act = fr.reset_index().melt(id_vars=fr.index.name or "index", var_name="ticker", value_name="fwd")
        act.columns = ["Date", "ticker", "fwd"]
        m = sig2.merge(act, on=["Date", "ticker"], how="inner").dropna(subset=["fwd"])
        hi = m["prob_up"].quantile(0.80)
        spread = m[m["prob_up"] >= hi]["fwd"].mean() - m[m["prob_up"] < hi]["fwd"].mean()

        alpha = b["alpha_cagr"] if b else float("nan")
        star = ""
        score = alpha  # välj på alfa
        if best is None or score > best[0]:
            best = (score, fw); star = "  <-- bäst"
        print(f"  {fw:>8d} {s['CAGR']:>7} {s['Sharpe']:>7} {alpha*100:>+6.1f}% "
              f"{ho_cagr*100:>+7.1f}% {spread*100:>+7.1f}%{star}")
        del feats, mdf, dev, lgbm, preds, sig
        gc.collect()

    print("-" * 70)
    print(f"  Bäst alfa: horisont={best[1]}v  ({best[0]*100:+.1f}%)")
    print("  (alfa mot likaviktat; holdout = OOS; spread = capture-edge. Nuvarande = 13v.)")


if __name__ == "__main__":
    main()
