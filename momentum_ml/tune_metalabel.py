"""
tune_metalabel.py – Ger meta-labeling extra edge? (López de Prado, AFML kap. 3)

IDÉ: primärmodellen (LGBM prob_up) avgör RIKTNING/urval – vilka bolag som är
kandidater. En SEKUNDÄR "meta"-modell avgör om man ska AGERA på en primärsignal,
dvs. skattar sannolikheten att en högt rankad kandidat faktiskt levererar. Den
lär sig i vilka lägen primärmodellen brukar ha FEL (t.ex. hög prob_up men i fel
regim/likviditet/vol) och filtrerar bort dem. Netto: högre precision, färre
falska positiva, mindre churn.

Detta är en A/B-STUDIE, inte live-kod. Den rör inte signal-pipelinen. Om
holdout-siffrorna nedan är tydligt bättre än baslinjen är nästa steg att baka in
meta-modellen i ensemble.py bakom en default-av flagga.

Metod (inget framåtläckage):
  1. Träna primär-LGBM walk-forward på DEV.
  2. Out-of-fold prob_up/pred_return (predict() attribuerar varje datum till den
     modell vars test-fönster täcker datumet → äkta OOF på DEV, samt sista
     modellen på den frusna HOLDOUTEN – exakt vad som vore tillgängligt live).
  3. Meta-target per datum: bland veckans topp-2N kandidater (efter prob_up),
     y=1 om namnet faktiskt hamnar i topp-N på REALISERAD framåtavkastning.
     Dvs. "var den höga rankningen befogad?".
  4. Meta-LGBM (features + prob_up + pred_return → y) tränas på DEV-poolen,
     appliceras på HOLDOUT-poolen.
  5. Jämför på HOLDOUT: baslinje (topp-N på prob_up) vs meta (topp-N på
     prob_up × meta_prob) – snitt-framåtavkastning, träffkvot, information ratio.

Kör på Pi:n från /opt/momentum/src/momentum_ml (bakgrund, ~20–40 min):

    nohup env PYTHONUNBUFFERED=1 /opt/momentum/venv/bin/python tune_metalabel.py > /tmp/metalabel.log 2>&1 &
    tail -f /tmp/metalabel.log
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd
import lightgbm as lgb

import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import (
    build_all_features, attach_categorical_features, to_model_df, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM


META_FEATURES = FEATURE_COLS + ["prob_up", "pred_return"]


def _oof_primary(feats, dev_dates):
    """Träna primär-LGBM på DEV, returnera OOF-prediktioner på HELA panelen."""
    mdf = to_model_df(feats)
    dev = mdf[mdf.index.isin(dev_dates)]

    lgbm = MomentumLGBM()
    lgbm.fit_walk_forward(dev)

    # OOF-prediktion på varje tickers fulla feature-DF (walk-forward-attribuering
    # inuti predict() gör detta out-of-fold på DEV och sista-modell på HOLDOUT).
    frames = []
    for t, f in feats.items():
        fclean = f.dropna(subset=FEATURE_COLS)
        if fclean.empty:
            continue
        p = lgbm.predict(fclean)
        p["ticker"] = t
        p["target_return"] = fclean["target_return"].values
        for col in META_FEATURES:
            if col in fclean.columns and col not in ("prob_up", "pred_return"):
                p[col] = fclean[col].values
        frames.append(p)
    panel = pd.concat(frames)
    panel = panel.dropna(subset=["target_return"])
    return panel


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

    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)

    mdf = to_model_df(feats)
    all_dates = mdf.index.unique().sort_values()
    if len(all_dates) <= config.HOLDOUT_WEEKS:
        print("För kort historik för holdout.")
        return
    holdout_start = all_dates[-config.HOLDOUT_WEEKS]
    # Purga DEV FORWARD_WEEKS före holdout (labels läcker annars in i holdouten).
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_dates = all_dates[all_dates < purge_start]

    print("\n" + "=" * 68)
    print("  META-LABELING A/B (large-segment)")
    print(f"  DEV t.o.m {purge_start.date()} · HOLDOUT från {holdout_start.date()}")
    print("=" * 68)

    print("\n[1/4] Tränar primärmodell + OOF-prediktion...")
    panel = _oof_primary(feats, dev_dates)

    # ── Bygg meta-pool + labels per datum ────────────────────────────────────
    print("[2/4] Bygger meta-labels (topp-2N pool, y=topp-N på utfall)...")
    panel = panel.copy()
    panel["_ticker"] = panel["ticker"]
    pools = []
    for date, grp in panel.groupby(level=0):
        if len(grp) < n_pos + 2:
            continue
        pool = grp.nlargest(min(2 * n_pos, len(grp)), "prob_up").copy()
        win_tickers = set(grp.nlargest(n_pos, "target_return")["_ticker"])
        pool["meta_y"] = pool["_ticker"].isin(win_tickers).astype(int)
        pools.append(pool)
    pool_df = pd.concat(pools).sort_index()

    dev_pool = pool_df[pool_df.index < purge_start]
    ho_pool  = pool_df[pool_df.index >= holdout_start]
    if dev_pool.empty or ho_pool.empty:
        print("Tom pool – avbryter.")
        return

    # ── Träna meta-LGBM walk-forward på DEV, applicera på HOLDOUT ─────────────
    print(f"[3/4] Tränar meta-LGBM ({len(dev_pool)} dev-rader)...")
    feat_cols = [c for c in META_FEATURES if c in dev_pool.columns]
    Xtr = dev_pool[feat_cols].fillna(0).values
    ytr = dev_pool["meta_y"].values
    params = {k: v for k, v in config.LGBM_PARAMS.items()
              if k not in ("n_estimators", "early_stopping_rounds")}
    params["objective"] = "binary"
    meta = lgb.train(params, lgb.Dataset(Xtr, label=ytr),
                     num_boost_round=config.LGBM_PARAMS.get("n_estimators", 300))
    ho_pool = ho_pool.copy()
    ho_pool["meta_prob"] = meta.predict(ho_pool[feat_cols].fillna(0).values)

    # ── A/B på HOLDOUT ────────────────────────────────────────────────────────
    print("[4/4] Utvärderar på holdout...\n")

    def basket_stats(rank_col):
        rets, hits = [], []
        for date, grp in ho_pool.groupby(level=0):
            if len(grp) < n_pos:
                continue
            pick = grp.nlargest(n_pos, rank_col)
            r = pick["target_return"].mean()
            rets.append(r)
            hits.append((pick["target_return"] > 0).mean())
        rets = np.array(rets)
        # IR: snitt / std av periodavkastning, annualiserad (13v-perioder → 4/år)
        periods_per_year = 52 / config.FORWARD_WEEKS
        ir = (rets.mean() / rets.std() * np.sqrt(periods_per_year)) if rets.std() > 0 else float("nan")
        return rets.mean(), np.mean(hits), ir, len(rets)

    ho_pool["_blend"] = ho_pool["prob_up"] * ho_pool["meta_prob"]
    base_ret, base_hit, base_ir, n = basket_stats("prob_up")
    meta_ret, meta_hit, meta_ir, _ = basket_stats("_blend")

    print(f"  {'variant':<24}{'snitt-avk/13v':>14}{'träffkvot':>12}{'IR (ann.)':>12}")
    print("-" * 62)
    print(f"  {'baslinje (prob_up)':<24}{base_ret:>13.2%}{base_hit:>12.1%}{base_ir:>12.2f}")
    print(f"  {'meta (prob×meta_prob)':<24}{meta_ret:>13.2%}{meta_hit:>12.1%}{meta_ir:>12.2f}")
    print("-" * 62)
    print(f"  Δ avkastning: {meta_ret - base_ret:>+.2%}/13v   "
          f"Δ träffkvot: {meta_hit - base_hit:>+.1%}   "
          f"Δ IR: {meta_ir - base_ir:>+.2f}   (n={n} veckor)")
    print()
    if meta_ir > base_ir and meta_ret >= base_ret:
        print("  → META-LABELING HJÄLPER på holdouten. Värt att baka in bakom flagga.")
    else:
        print("  → Ingen tydlig meta-vinst på holdouten. Behåll baslinjen.")


if __name__ == "__main__":
    main()
