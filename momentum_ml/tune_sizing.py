"""
tune_sizing.py – Svep CONVICTION_BLEND × MAX_POSITIONS och mät alfa/Sharpe.

Konverterar modellens bevisade rangordnings-edge (capture_analysis visade +8-10pp
kvantil-spread) till portföljavkastning genom att hitta bästa positionssizing.
Laddar SPARAD modell + cache (ingen omträning) och bygger om signals + backtest
per kombination.

Kör på Pi:n från /opt/momentum/momentum_ml EFTER att segmentet tränats:

    /opt/momentum/venv/bin/python tune_sizing.py [large|small]
"""
import csv
import os
import sys
sys.path.insert(0, '.')
import config

_seg_arg = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
_seg = config.SEGMENTS.get(_seg_arg) or config.SEGMENTS[config.DEFAULT_SEGMENT]
if "drop_features" in _seg:
    config.DROP_FEATURES = _seg["drop_features"]

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

BLENDS = [0.5, 0.75, 1.0]      # 0=likavikt, 1=ren conviction
NPOS = [10, 15, 20, 25]         # antal innehav
MODES = ["conviction", "inverse_vol"]   # tilt-fördelning bland de N namnen


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    print(f"[Segment] {segment} ({seg['label']}) – modell: {config.RESULTS_DIR}/lgbm_model.pkl")

    if "drop_features" in seg:
        config.DROP_FEATURES = seg["drop_features"]
        dropped_set = set(seg["drop_features"])
        filtered = [c for c in FEATURE_COLS if c not in dropped_set]
        FEATURE_COLS.clear()
        FEATURE_COLS.extend(filtered)

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    config.CAP_TIER_MAP.update(cap_tier_map)   # buggmönster 12-fix 2026-07-30 (UTVECKLINGSLOGG #129)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    from features.feature_engineering import attach_fundamentals_features
    feats = attach_fundamentals_features(feats, segment=segment, prices=data)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}

    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/lgbm_model.pkl")
    preds = {t: lgbm.predict(f.dropna(subset=FEATURE_COLS[:5])) for t, f in feats.items() if len(f) > 0}

    hw = config.HOLDOUT_WEEKS

    def evaluate(blend, npos, mode):
        config.CONVICTION_BLEND = blend
        config.MAX_POSITIONS = npos
        config.SIZING_MODE = mode
        sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        s = bt.statistics()
        b = benchmark_report(bt._results["portfolio_value"], data)
        pv = bt._results["portfolio_value"]
        ho = pv.iloc[-hw:] if len(pv) > hw else pv
        ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
        return s["CAGR"], s["Sharpe"], b["alpha_cagr"], ho_cagr

    # Checkpoint: en rad per (mode,blend,npos)-kombination skrivs till disk direkt
    # efter att den räknats klart, så ett earlyoom-dödande mitt i svepet bara
    # kostar EN kombination, inte hela körningen. Vid omstart läses redan klara
    # kombinationer in och hoppas över.
    ckpt_path = f"{config.RESULTS_DIR}/tune_sizing_checkpoint.csv"
    fieldnames = ["mode", "blend", "npos", "cagr", "sharpe", "alpha", "holdout"]
    done = {}
    if os.path.exists(ckpt_path):
        with open(ckpt_path, newline="") as f:
            for row in csv.DictReader(f):
                key = (row["mode"], row["blend"], row["npos"])
                done[key] = row
        print(f"[checkpoint] {len(done)} kombination(er) redan klara, hoppar över dem: {ckpt_path}")
    ckpt_is_new = not os.path.exists(ckpt_path)
    ckpt_f = open(ckpt_path, "a", newline="")
    ckpt_writer = csv.DictWriter(ckpt_f, fieldnames=fieldnames)
    if ckpt_is_new:
        ckpt_writer.writeheader()
        ckpt_f.flush()

    print("\n" + "=" * 76)
    print(f"  SIZING-SVEP ({seg['label']}) – alfa mot index, per kombination")
    print("=" * 76)
    print(f"  {'läge':>12} {'blend':>6} {'innehav':>8} {'CAGR':>7} {'Sharpe':>7} {'alfa':>7} {'holdout':>8}")
    print("-" * 76)
    for mode in MODES:
        for blend in BLENDS:
            for npos in NPOS:
                key = (mode, f"{blend:.2f}", str(npos))
                if key in done:
                    row = done[key]
                    cagr, sharpe = row["cagr"], row["sharpe"]
                    alpha, ho = float(row["alpha"]), float(row["holdout"])
                    print(f"  {mode:>12} {blend:>6.2f} {npos:>8d} {cagr:>7} {sharpe:>7} "
                          f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}%  [checkpoint]")
                    continue
                cagr, sharpe, alpha, ho = evaluate(blend, npos, mode)
                ckpt_writer.writerow({"mode": mode, "blend": f"{blend:.2f}", "npos": npos,
                                       "cagr": cagr, "sharpe": sharpe, "alpha": alpha, "holdout": ho})
                ckpt_f.flush()
                print(f"  {mode:>12} {blend:>6.2f} {npos:>8d} {cagr:>7} {sharpe:>7} "
                      f"{alpha*100:>+6.1f}% {ho*100:>+7.1f}%")
        print("-" * 76)
    ckpt_f.close()

    with open(ckpt_path, newline="") as f:
        all_rows = list(csv.DictReader(f))
    best = max(all_rows, key=lambda r: float(r["alpha"]))
    print(f"  Bäst alfa: läge={best['mode']}, blend={best['blend']}, innehav={best['npos']}  "
          f"({float(best['alpha'])*100:+.1f}%)")
    print("  (alfa mot likaviktat köp-och-behåll; holdout = äkta out-of-sample)")


if __name__ == "__main__":
    main()
