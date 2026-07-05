"""
tune_horizon_ensemble.py – Ger en HORISONT-ENSEMBLE mer edge än enbart 13v?

IDÉ: modellen tränas idag på EN horisont (FORWARD_WEEKS=13). Olika horisonter
fångar olika delar av momentum: 8v är snabbare/mer taktisk, 26v långsammare/mer
uthållig. En ensemble som blandar prob_up över flera horisonter blir mindre
känslig för valet av en enda horisont och jämnar ut regimberoendet.

A/B-STUDIE, inte live-kod. Rör inte signal-pipelinen.

Två utvärderingar på HOLDOUTEN (inget framåtläckage – primärmodellerna tränas
bara på DEV, prob:en är out-of-fold):
  1. KORG-IC: topp-N vald på ensemble-score vs enbart 13v (brutto, före kostnad).
  2. RIKTIG BACKTEST: ensemble-prob matas genom build_full_output + hela
     MomentumBacktester (courtage, vol-overlay, marknadsfilter, drawdown-guard),
     och holdout-CAGR/Sharpe jämförs mot 13v-baslinjen NETTO efter kostnader.
     Det är den avgörande kontrollen – korg-IC:t kan lysa men ätas upp av
     omsättning när ensemblen byter innehav oftare.

Kör på Pi:n från /opt/momentum/src/momentum_ml (bakgrund, ~30–60 min):

    nohup env PYTHONUNBUFFERED=1 /opt/momentum/venv/bin/python tune_horizon_ensemble.py > /tmp/hz_ens.log 2>&1 &
    tail -f /tmp/hz_ens.log
"""
import sys, gc
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, to_model_df, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester

HORIZONS = [8, 13, 26]
SCORE_HORIZON = 13   # rebalans-/måttstockshorisont


def _train_horizon(data, cap_tier_map, fw, dev_dates, keep_feats=False):
    """
    Träna primär-LGBM på DEV för horisont fw. Returnera:
      preds_by_ticker: {ticker: DataFrame(prob_up, pred_signal, pred_return)} (OOF)
      feats:           per-ticker feature-dict (bara om keep_feats, för sizing/backtest)
    """
    config.FORWARD_WEEKS = fw
    config.REBALANCE_WEEKS = fw
    config.EMBARGO_WEEKS = fw

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    mdf = to_model_df(feats)
    dev = mdf[mdf.index.isin(dev_dates)]

    lgbm = MomentumLGBM()
    lgbm.fit_walk_forward(dev)

    preds = {}
    for t, f in feats.items():
        fclean = f.dropna(subset=FEATURE_COLS)
        if fclean.empty:
            continue
        preds[t] = lgbm.predict(fclean)   # prob_up, pred_signal, pred_return

    del mdf, lgbm
    if not keep_feats:
        del feats
        feats = None
    gc.collect()
    return preds, feats


def main():
    seg = config.SEGMENTS["large"]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    n_pos = int(config.MAX_POSITIONS)

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    # Datumbas för dev/holdout-split via SCORE_HORIZON-panelen.
    config.FORWARD_WEEKS = SCORE_HORIZON
    feats0 = build_all_features(data)
    feats0 = attach_categorical_features(feats0, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    mdf0 = to_model_df(feats0)
    all_dates = mdf0.index.unique().sort_values()
    if len(all_dates) <= config.HOLDOUT_WEEKS:
        print("För kort historik för holdout.")
        return
    holdout_start = all_dates[-config.HOLDOUT_WEEKS]
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + SCORE_HORIZON)]
    dev_dates = all_dates[all_dates < purge_start]
    del feats0, mdf0
    gc.collect()

    print("\n" + "=" * 68)
    print(f"  HORISONT-ENSEMBLE A/B (large) · horisonter {HORIZONS}")
    print(f"  DEV t.o.m {purge_start.date()} · HOLDOUT från {holdout_start.date()}")
    print("=" * 68)

    # ── Träna varje horisont, behåll per-ticker prob (+ feats för 13v) ────────
    preds_by_h = {}
    feats_ref = None
    for fw in HORIZONS:
        print(f"\n[horisont {fw}v] tränar + OOF...")
        preds, feats = _train_horizon(data, cap_tier_map, fw, dev_dates,
                                      keep_feats=(fw == SCORE_HORIZON))
        preds_by_h[fw] = preds
        if fw == SCORE_HORIZON:
            feats_ref = feats

    # Återställ config till referens-horisonten för backtest/sizing.
    config.FORWARD_WEEKS = SCORE_HORIZON
    config.REBALANCE_WEEKS = SCORE_HORIZON
    config.EMBARGO_WEEKS = SCORE_HORIZON

    # ── 1. KORG-IC (brutto) ───────────────────────────────────────────────────
    # Rank-panel per horisont, ensemble = medel av rankerna.
    rank_frames = []
    for fw in HORIZONS:
        rows = []
        for t, p in preds_by_h[fw].items():
            s = p[["prob_up"]].copy()
            s["ticker"] = t
            rows.append(s)
        panel = pd.concat(rows).reset_index()
        panel.columns = ["date", f"prob_{fw}", "ticker"]
        panel[f"rank_{fw}"] = panel.groupby("date")[f"prob_{fw}"].rank(pct=True)
        rank_frames.append(panel)

    merged = rank_frames[0]
    for panel in rank_frames[1:]:
        merged = merged.merge(panel, on=["date", "ticker"], how="inner")
    merged["ens_rank"] = merged[[f"rank_{fw}" for fw in HORIZONS]].mean(axis=1)

    # gemensam måttstock: 13v realiserad framåtavkastning (ur referens-feats)
    sr_rows = []
    for t, f in feats_ref.items():
        if "target_return" in f:
            s = f[["target_return"]].copy()
            s["ticker"] = t
            sr_rows.append(s)
    sr = pd.concat(sr_rows).reset_index()
    sr.columns = ["date", "target_return", "ticker"]
    merged = merged.merge(sr, on=["date", "ticker"], how="inner").dropna(subset=["target_return"])
    ho = merged[merged["date"] >= holdout_start]

    def basket(df, rank_col):
        rets, hits = [], []
        for _, grp in df.groupby("date"):
            if len(grp) < n_pos:
                continue
            pick = grp.nlargest(n_pos, rank_col)
            rets.append(pick["target_return"].mean())
            hits.append((pick["target_return"] > 0).mean())
        rets = np.array(rets)
        ppy = 52 / SCORE_HORIZON
        ir = (rets.mean() / rets.std() * np.sqrt(ppy)) if rets.std() > 0 else float("nan")
        return rets.mean(), np.mean(hits), ir, len(rets)

    b = basket(ho, f"prob_{SCORE_HORIZON}")
    e = basket(ho, "ens_rank")
    print("\n── 1. KORG-IC (brutto, före kostnad) ──")
    print(f"  {'variant':<24}{'snitt-avk':>11}{'träff':>9}{'IR':>8}")
    print(f"  {f'baslinje {SCORE_HORIZON}v':<24}{b[0]:>10.2%}{b[1]:>9.1%}{b[2]:>8.2f}")
    print(f"  {'ensemble':<24}{e[0]:>10.2%}{e[1]:>9.1%}{e[2]:>8.2f}")
    print(f"  Δ avk {e[0]-b[0]:+.2%}  Δ träff {e[1]-b[1]:+.1%}  Δ IR {e[2]-b[2]:+.2f}  (n={b[3]})")

    # ── 2. RIKTIG BACKTEST (netto) ────────────────────────────────────────────
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats_ref.items()}

    def make_preds(kind):
        """kind='base' → 13v prob; kind='ens' → medel-prob över horisonter."""
        out = {}
        for t in preds_by_h[SCORE_HORIZON]:
            base = preds_by_h[SCORE_HORIZON][t]
            if kind == "base":
                out[t] = base.copy()
            else:
                cols = {}
                for fw in HORIZONS:
                    if t in preds_by_h[fw]:
                        cols[fw] = preds_by_h[fw][t]["prob_up"]
                prob = pd.DataFrame(cols).mean(axis=1).reindex(base.index)
                df = base.copy()
                df["prob_up"] = prob.values
                out[t] = df
        return out

    def holdout_stats(preds):
        sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
        bt = MomentumBacktester(sig, data, market_filter=True)
        bt.run()
        return bt.statistics_for_period(holdout_start)

    print("\n── 2. RIKTIG BACKTEST (netto efter kostnad, holdout) ──")
    base_stats = holdout_stats(make_preds("base"))
    ens_stats  = holdout_stats(make_preds("ens"))
    keys = ["CAGR", "Sharpe", "Sortino", "Max Drawdown"]
    print(f"  {'mått':<16}{'baslinje 13v':>16}{'ensemble':>16}")
    for k in keys:
        print(f"  {k:<16}{str(base_stats.get(k,'—')):>16}{str(ens_stats.get(k,'—')):>16}")

    def _num(s):
        try:
            return float(str(s).replace('%', '').replace(',', '.'))
        except Exception:
            return None
    bc, ec = _num(base_stats.get("CAGR")), _num(ens_stats.get("CAGR"))
    bs, es = _num(base_stats.get("Sharpe")), _num(ens_stats.get("Sharpe"))
    print()
    if None not in (bc, ec, bs, es) and ec >= bc and es > bs:
        print("  → HORISONT-ENSEMBLE HJÄLPER NETTO på holdouten. Värt att baka in bakom flagga.")
    else:
        print("  → Ingen NETTO-vinst efter kostnad. Korg-IC:t åts upp av omsättning/overlay.")


if __name__ == "__main__":
    main()
