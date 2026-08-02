"""
tune_disagreement_filter.py – TESTKATALOG_INFOR_KORNING_2026-07-30.md A2:
modellosäkerhet (#164:s split-oenighetsmått) som ekonomiskt filter, inte
bara ett validerat mått. #164 visade att oenighet mellan angränsande
splitmodeller BETER SIG som ett äkta osäkerhetsmått (mer oense om
mittenaktier) - men mätte aldrig om det faktiskt spelar någon ekonomisk
roll att agera på det.

Metod: vid varje historiskt ombalanseringsdatum (kalenderbaserat, samma
17 datum som produktionen), prediktera med den DÅ "levande" splitmodellen
OCH dess närmaste grannar (idx-1, idx, idx+1, klippt till giltigt
intervall) på det datumets fulla kandidatpanel. Oenighet = std av
z-normaliserade poäng över de (upp till 3) modellerna, per ticker.

Fyra varianter jämförs mot BASLINJEN (dagens signals.csv, oförändrad):
  filter        – exkludera de 20% MEST oense kandidaterna ur den
                  behöriga poolen INNAN topp-N väljs.
  downweight    – behåll alla, men skala position_size med
                  (1 - oenighet_percentil) för de 20% mest oense.
  random_control – exkludera samma ANTAL kandidater, men SLUMPMÄSSIGT
                  (samma seed per datum) - isolerar om effekten kommer
                  från oenigheten specifikt eller bara från att portföljen
                  blir annorlunda/mindre koncentrerad av VILKEN anledning
                  som helst.

    /opt/momentum/venv/bin/python3 tune_disagreement_filter.py
"""
import sys
sys.path.insert(0, ".")
import config

segment = "large"
seg = config.SEGMENTS[segment]
config.RESULTS_DIR = seg["results_dir"]
if "max_positions" in seg:
    config.MAX_POSITIONS = seg["max_positions"]
if "forward_weeks" in seg:
    config.FORWARD_WEEKS = seg["forward_weeks"]
    config.REBALANCE_WEEKS = seg["rebalance_weeks"]
if "atr_stop_enabled" in seg:
    config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
if "market_filter_exposure" in seg:
    config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]

import numpy as np
import pandas as pd

from features.feature_engineering import to_model_df, FEATURE_COLS
if "drop_features" in seg:
    dropped_set = set(seg["drop_features"])
    filtered = [c for c in FEATURE_COLS if c not in dropped_set]
    FEATURE_COLS.clear()
    FEATURE_COLS.extend(filtered)
from models.lgbm_model import MomentumLGBM
from backtest.backtester import MomentumBacktester
from data.data_loader import load_sweden_universe, fetch_weekly_data, filter_active_universe, filter_liquid_universe

DISAGREE_FRAC = 0.20
SEED = 42


def cross_sectional_model_disagreement(preds: np.ndarray) -> np.ndarray:
    """Spridning mellan modellers *tvärsnittsrankning* per aktie.

    Kolumn = modell, rad = aktie. Varje modell standardiseras över aktier
    innan spridningen tas över modeller. Att standardisera varje rad över
    modeller först gör radens std definitionsmässigt ≈1 och förstör signalen.
    """
    preds = np.asarray(preds, dtype=float)
    if preds.ndim != 2:
        raise ValueError("preds måste ha formen (aktier, modeller)")
    if preds.shape[1] < 2:
        return np.zeros(preds.shape[0], dtype=float)
    means = preds.mean(axis=0, keepdims=True)
    scales = preds.std(axis=0, keepdims=True)
    z = (preds - means) / np.where(scales > 1e-12, scales, 1.0)
    return z.std(axis=1)


def main():
    lgbm = MomentumLGBM.load(f"{seg['results_dir']}/lgbm_model.pkl")
    model_features = pd.read_pickle("results/abstention_features.pkl")
    model_df = to_model_df(model_features)

    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    all_weeks = sorted(sig.index.unique())
    rw = int(seg.get("rebalance_weeks", 52))
    rebalance_dates = all_weeks[::rw]

    tickers, sector_map, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    n_models = len(lgbm.cls_models)
    disagree_by_date_ticker = {}
    rng = np.random.RandomState(SEED)
    excluded_random = {}

    print(f"[disagreement] Beräknar oenighet vid {len(rebalance_dates)} ombalanseringsdatum...")
    for d in rebalance_dates:
        if d not in model_df.index:
            continue
        day = model_df.loc[[d]].dropna(subset=FEATURE_COLS[:5])
        if day.empty:
            continue
        X = day[FEATURE_COLS].values
        idx = int(lgbm._select_model_idx(pd.DatetimeIndex([d]))[0])
        neighbor_idxs = sorted({max(0, idx - 1), idx, min(n_models - 1, idx + 1)})
        preds = np.column_stack([lgbm.cls_models[j].predict(X) for j in neighbor_idxs])
        disagreement = cross_sectional_model_disagreement(preds)
        tick = day["ticker"].values
        disagree_by_date_ticker[d] = dict(zip(tick, disagreement))

        cand = sig.loc[[d]]
        cand = cand[cand["selection_eligible"] == 1]["ticker"].tolist()
        n_excl = max(int(round(len(cand) * DISAGREE_FRAC)), 0)
        excluded_random[d] = set(rng.choice(cand, size=min(n_excl, len(cand)), replace=False)) if n_excl else set()

    def build_variant(mode: str) -> pd.DataFrame:
        out = sig.copy()
        for d in rebalance_dates:
            if d not in disagree_by_date_ticker:
                continue
            mask = out.index == d
            day = out.loc[mask]
            cand = day[day["selection_eligible"] == 1].copy()
            if cand.empty:
                continue
            disagree_map = disagree_by_date_ticker[d]
            cand["_disagree"] = cand["ticker"].map(disagree_map).fillna(cand["ticker"].map(disagree_map).mean() if disagree_map else 0.0)
            n_excl = max(int(round(len(cand) * DISAGREE_FRAC)), 0)

            if mode == "baseline":
                continue
            elif mode == "filter":
                worst = set(cand.nlargest(n_excl, "_disagree")["ticker"]) if n_excl else set()
                out.loc[mask & out["ticker"].isin(worst), "selection_eligible"] = 0
                out.loc[mask & out["ticker"].isin(worst), "position_size"] = 0.0
                out.loc[mask & out["ticker"].isin(worst), "pred_signal"] = 0
            elif mode == "downweight":
                pct = cand["_disagree"].rank(pct=True)
                scale = np.where(pct >= (1 - DISAGREE_FRAC), 1 - pct, 1.0)
                scale_map = dict(zip(cand["ticker"], scale))
                out.loc[mask, "position_size"] = out.loc[mask].apply(
                    lambda r: r["position_size"] * scale_map.get(r["ticker"], 1.0), axis=1)
            elif mode == "random_control":
                excl = excluded_random.get(d, set())
                out.loc[mask & out["ticker"].isin(excl), "selection_eligible"] = 0
                out.loc[mask & out["ticker"].isin(excl), "position_size"] = 0.0
                out.loc[mask & out["ticker"].isin(excl), "pred_signal"] = 0
        return out

    holdout_start = all_weeks[-config.HOLDOUT_WEEKS] if len(all_weeks) > config.HOLDOUT_WEEKS else None

    def _pct(stat_dict, key):
        return float(str(stat_dict[key]).rstrip("%")) / 100.0

    print("\n" + "=" * 90)
    print("Full backtest (large) - modellosäkerhet som ekonomiskt filter")
    print("=" * 90)
    for mode in ("baseline", "filter", "downweight", "random_control"):
        sig_variant = build_variant(mode)
        bt = MomentumBacktester(sig_variant, data)
        bt.run()
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        print(f"  {mode:<15}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%}")

    print("\n[disagreement] Klart.")


if __name__ == "__main__":
    main()
