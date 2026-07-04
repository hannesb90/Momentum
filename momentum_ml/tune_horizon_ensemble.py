"""
tune_horizon_ensemble.py – Ger en HORISONT-ENSEMBLE mer edge än enbart 13v?

IDÉ: modellen tränas idag på EN horisont (FORWARD_WEEKS=13). Olika horisonter
fångar olika delar av momentum: 8v är snabbare/mer taktisk, 26v långsammare/mer
uthållig. En ensemble som blandar prob_up-RANK över flera horisonter blir mindre
känslig för valet av en enda horisont och jämnar ut regimberoendet (en horisont
kan vara utfasad just när en annan lyser). Ekonomiskt = diversifiering över
signal-hastighet, inte över bolag.

A/B-STUDIE, inte live-kod. Rör inte signal-pipelinen. Om ensemblen slår 13v-
baslinjen tydligt på holdouten är nästa steg att baka in den bakom en flagga.

Metod (inget framåtläckage):
  1. För varje horisont h i HORIZONS: bygg features/target för h, träna primär-
     LGBM walk-forward på DEV, OOF-predikta prob_up på hela panelen.
  2. Rangordna prob_up per datum inom varje horisont (rank i [0,1]) och blanda
     till ett ensemble-score = medel av rankerna över horisonterna.
  3. Utvärdera på HOLDOUT mot en GEMENSAM måttstock: realiserad 13v-
     framåtavkastning (rebalans-horisonten). Jämför topp-N-korg valda på
     (a) enbart 13v prob_up (baslinje) vs (b) ensemble-score.

Kör på Pi:n från /opt/momentum/src/momentum_ml (bakgrund, ~30–60 min –
tränar om per horisont):

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

HORIZONS = [8, 13, 26]
SCORE_HORIZON = 13   # gemensam måttstock: realiserad avkastning över denna horisont


def _oof_prob(data, sector_map, cap_tier_map, fw, dev_dates):
    """Träna primär-LGBM på DEV för horisont fw, returnera OOF prob_up-panel."""
    config.FORWARD_WEEKS = fw
    config.REBALANCE_WEEKS = fw
    config.EMBARGO_WEEKS = fw

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    mdf = to_model_df(feats)
    dev = mdf[mdf.index.isin(dev_dates)]

    lgbm = MomentumLGBM()
    lgbm.fit_walk_forward(dev)

    frames = []
    for t, f in feats.items():
        fclean = f.dropna(subset=FEATURE_COLS)
        if fclean.empty:
            continue
        p = lgbm.predict(fclean)[["prob_up"]].copy()
        p["ticker"] = t
        frames.append(p)
    panel = pd.concat(frames)
    del feats, mdf, lgbm
    gc.collect()
    # rangordna prob_up per datum → jämförbart mellan horisonter
    panel[f"rank_{fw}"] = panel.groupby(level=0)["prob_up"].rank(pct=True)
    return panel.rename(columns={"prob_up": f"prob_{fw}"})


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

    # Datumbas för dev/holdout-split: använd SCORE_HORIZON:s panel som referens.
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

    # Realiserad framåtavkastning över SCORE_HORIZON (gemensam måttstock).
    score_ret = pd.concat(
        [f[["target_return"]].assign(ticker=t) for t, f in feats0.items()]
    )
    del feats0, mdf0
    gc.collect()

    print("\n" + "=" * 68)
    print(f"  HORISONT-ENSEMBLE A/B (large) · horisonter {HORIZONS}")
    print(f"  DEV t.o.m {purge_start.date()} · HOLDOUT från {holdout_start.date()}")
    print("=" * 68)

    merged = None
    for fw in HORIZONS:
        print(f"\n[horisont {fw}v] tränar + OOF...")
        panel = _oof_prob(data, sector_map, cap_tier_map, fw, dev_dates)
        panel = panel.reset_index().rename(columns={"index": "date"})
        panel.columns = ["date"] + list(panel.columns[1:])
        if merged is None:
            merged = panel
        else:
            merged = merged.merge(panel, on=["date", "ticker"], how="inner")

    rank_cols = [f"rank_{fw}" for fw in HORIZONS]
    merged["ens_score"] = merged[rank_cols].mean(axis=1)

    # koppla på gemensam måttstock (13v-utfall)
    sr = score_ret.reset_index()
    sr.columns = ["date", "target_return", "ticker"]
    merged = merged.merge(sr, on=["date", "ticker"], how="inner").dropna(subset=["target_return"])

    ho = merged[merged["date"] >= holdout_start]
    if ho.empty:
        print("Tom holdout – avbryter.")
        return

    def basket_stats(df, rank_col):
        rets, hits = [], []
        for date, grp in df.groupby("date"):
            if len(grp) < n_pos:
                continue
            pick = grp.nlargest(n_pos, rank_col)
            rets.append(pick["target_return"].mean())
            hits.append((pick["target_return"] > 0).mean())
        rets = np.array(rets)
        ppy = 52 / SCORE_HORIZON
        ir = (rets.mean() / rets.std() * np.sqrt(ppy)) if rets.std() > 0 else float("nan")
        return rets.mean(), np.mean(hits), ir, len(rets)

    base = basket_stats(ho, f"prob_{SCORE_HORIZON}")
    ens  = basket_stats(ho, "ens_score")

    print("\n" + "-" * 62)
    print(f"  {'variant':<26}{'snitt-avk':>12}{'träffkvot':>12}{'IR (ann.)':>12}")
    print("-" * 62)
    print(f"  {f'baslinje ({SCORE_HORIZON}v prob_up)':<26}{base[0]:>11.2%}{base[1]:>12.1%}{base[2]:>12.2f}")
    print(f"  {f'ensemble {HORIZONS}':<26}{ens[0]:>11.2%}{ens[1]:>12.1%}{ens[2]:>12.2f}")
    print("-" * 62)
    print(f"  Δ avk: {ens[0]-base[0]:>+.2%}   Δ träff: {ens[1]-base[1]:>+.1%}   "
          f"Δ IR: {ens[2]-base[2]:>+.2f}   (n={base[3]} veckor)")
    print()
    if ens[2] > base[2] and ens[0] >= base[0]:
        print("  → HORISONT-ENSEMBLE HJÄLPER på holdouten. Värt att baka in bakom flagga.")
    else:
        print("  → Ingen tydlig ensemble-vinst. Behåll enbart 13v.")


if __name__ == "__main__":
    main()
