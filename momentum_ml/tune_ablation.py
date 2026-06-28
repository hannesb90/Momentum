"""
tune_ablation.py – Var ligger den gyllene medelvägen? Skala BORT features, inte till.

Vår logg visar att ADDERA features dödar modellen (v2/PEAD inverterade
capture-spreaden). Komplementfrågan är: kan vi SKÄRA bort feature-grupper och
hitta en enklare modell med lika bra eller bättre edge? Färre parametrar =
mindre överanpassning (Occam). Det här verktyget mäter det ärligt.

Två lägen:
  logo     – leave-one-group-out: träna om utan VARJE grupp i tur och ordning och
             jämför mot full modell. Visar varje grupps marginella bidrag. (~9 omträn.)
  backward – girig bakåt-eliminering: ta bort den grupp vars borttagande hjälper
             (eller skadar minst), upprepa tills det börjar skada. Hittar
             sweet-spot-vägen. (~O(grupper²) omträn – kör över natten.)

Metrik (ärlig): OOS capture-spread (2016+) = huvudmått på rangordnings-edge, plus
holdout-CAGR och full-period-alfa. "Bäst" = högst capture-spread.

VIKTIGT om processer: LGBM-träna→predikt i SAMMA process SIGILL:ar på Pi:ns
ARM-CPU (se main.py). Därför spawnar varje variant två subprocesser (train→eval),
exakt som main.py. Kör på Pi:n EFTER att datacachen finns:

    /opt/momentum/venv/bin/python tune_ablation.py large            # logo (default)
    /opt/momentum/venv/bin/python tune_ablation.py large backward   # girig bakåt

OBS: ablationen körs på LGBM ENBART (snabbt + konsistent). Den vinnande minimala
gruppuppsättningen ska re-valideras med fulla pipelinen (LGBM+LSTM) på holdouten
innan den adopteras.
"""
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, '.')
import pandas as pd
import numpy as np
import config
import features.feature_engineering as fe
import models.lgbm_model as lgbm_mod
from features.feature_engineering import (
    build_all_features, attach_categorical_features, to_model_df, FEATURE_COLS as FULL_COLS,
)
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from models.lgbm_model import MomentumLGBM
from models.ensemble import MomentumEnsemble, build_full_output
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report

ABLATION_MODEL = "ablation_model.pkl"   # temp-modell (per variant), läggs i results_dir


# ── Feature-grupper (speglar FEATURE_COLS-blocken, byggs ur config) ───────────
def feature_groups() -> dict:
    g = {
        "momentum":        [f"roc_{w}w" for w in config.MOMENTUM_WINDOWS]
                           + ["mom_12_1", "ret_skew_13w", "ret_kurt_13w"],
        "trend":           [f"ema_cross_{f}_{s}" for f, s in config.EMA_PAIRS]
                           + [f"ema_slope_{f}w" for f, _ in config.EMA_PAIRS]
                           + ["adx", "di_diff", "adx_trend"],
        "volatilitet":     [f"rvol_{w}w" for w in config.VOLATILITY_WINDOWS]
                           + ["atr_norm", "vol_ratio", "bb_position"],
        "volym":           [f"vol_ratio_{w}w" for w in config.VOLUME_WINDOWS]
                           + ["obv_roc_4w", "obv_roc_13w", "ad_roc_4w"],
        "pris_niva":       ["high52_ratio", "low52_ratio", "price_vs_sma52"],
        "tidig_entry":     ["donchian_pos", "breakout_nw", "roc_accel_4w", "pullback"],
        "cross_sectional": ["rs_4w", "rs_13w", "rs_26w", "rank_4w", "rank_26w",
                            "liquidity_rank", "rank_change_4w"],
        "klassificering":  ["sector_code", "cap_tier_code"],
    }
    # behåll bara namn som faktiskt finns (robust mot config-drift)
    return {k: [c for c in v if c in FULL_COLS] for k, v in g.items()}


def _set_active(cols: list) -> None:
    """Åsidosätt feature-listan modellen tränar/predikterar på. `from ... import
    FEATURE_COLS` skapar en egen bindning i lgbm_model → patcha DEN."""
    lgbm_mod.FEATURE_COLS = cols
    fe.FEATURE_COLS = cols


# ── Delad data/feature-uppbyggnad (körs i varje worker) ───────────────────────
def _load(seg):
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    return data, feats


def _holdout_start(model_df):
    dates = model_df.index.unique().sort_values()
    return dates[-config.HOLDOUT_WEEKS] if len(dates) > config.HOLDOUT_WEEKS else None


# ── Worker: träna ─────────────────────────────────────────────────────────────
def worker_train(seg, active):
    _set_active(active)
    _, feats = _load(seg)
    model_df = to_model_df(feats)
    hs = _holdout_start(model_df)
    dev_df = model_df[model_df.index < hs] if hs is not None else model_df
    lgbm = MomentumLGBM()
    lgbm.fit_walk_forward(dev_df)
    lgbm.save(f"{config.RESULTS_DIR}/{ABLATION_MODEL}")
    print(f"[train] klar – {len(active)} features, modell sparad.")


# ── Worker: utvärdera ─────────────────────────────────────────────────────────
def worker_eval(seg, active):
    _set_active(active)
    data, feats = _load(seg)
    feature_dfs = {t: f.assign(ticker=t) for t, f in feats.items()}
    lgbm = MomentumLGBM.load(f"{config.RESULTS_DIR}/{ABLATION_MODEL}")
    preds = {t: lgbm.predict(f.dropna(subset=active[:5])) for t, f in feats.items() if len(f) > 0}

    sig = build_full_output(preds, None, feature_dfs, MomentumEnsemble(), ta_filter="score")
    bt = MomentumBacktester(sig, data, market_filter=True)
    bt.run()
    s = bt.statistics()
    b = benchmark_report(bt._results["portfolio_value"], data)
    pv = bt._results["portfolio_value"]
    hw = config.HOLDOUT_WEEKS
    ho = pv.iloc[-hw:] if len(pv) > hw else pv
    ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1

    # OOS capture-spread (2016+): rangordnar prob_up framåtavkastningen?
    fwd = config.FORWARD_WEEKS
    rows = []
    for t, df in data.items():
        c = df["Close"]; fr = c.shift(-fwd) / c - 1
        for d, r in fr.dropna().items():
            rows.append((d, t, float(r)))
    act = pd.DataFrame(rows, columns=["Date", "ticker", "fwd_ret"])
    m = act.merge(sig.reset_index()[["Date", "ticker", "prob_up"]], on=["Date", "ticker"], how="inner")
    m = m[m["Date"] >= config.SENTIMENT_OOS_START] if "SENTIMENT_OOS_START" in dir(config) else m[m["Date"] >= "2016"]
    if len(m) > 50:
        hi = m["prob_up"].quantile(0.80)
        cap = m[m["prob_up"] >= hi]["fwd_ret"].mean() - m[m["prob_up"] < hi]["fwd_ret"].mean()
    else:
        cap = float("nan")

    out = {"n_features": len(active), "cagr": s["CAGR"], "sharpe": s["Sharpe"],
           "alpha": b["alpha_cagr"], "holdout_cagr": ho_cagr, "capture": float(cap)}
    print("ABLATION_RESULT " + json.dumps(out))


# ── Orchestrering ─────────────────────────────────────────────────────────────
def _run_variant(seg_name, active) -> dict:
    """Spawnar train→eval i separata processer (SIGILL-säkert) och returnerar metrik."""
    feat_arg = ",".join(active)
    base = [sys.executable, __file__, "--worker", "--segment", seg_name, "--features", feat_arg]
    r = subprocess.run(base + ["--mode", "train"])
    if r.returncode != 0:
        return {"n_features": len(active), "error": "train failed"}
    p = subprocess.run(base + ["--mode", "eval"], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("ABLATION_RESULT "):
            return json.loads(line[len("ABLATION_RESULT "):])
    print(p.stdout[-2000:]); print(p.stderr[-1000:])
    return {"n_features": len(active), "error": "eval failed"}


def _fmt(label, m):
    if "error" in m:
        return f"  {label:>26} {m['n_features']:>4}   {m['error']}"
    return (f"  {label:>26} {m['n_features']:>4}  {m['cagr']:>7} {m['sharpe']:>7} "
            f"{m['alpha']*100:>+6.1f}% {m['holdout_cagr']*100:>+7.1f}% {m['capture']*100:>+7.1f}pp")


def run_logo(seg_name, seg):
    groups = feature_groups()
    print("\n" + "=" * 92)
    print(f"  ABLATION (LOGO) – {seg['label']} – tar bort en grupp i taget (LGBM-only)")
    print("=" * 92)
    print(f"  {'variant':>26} {'#f':>4}  {'CAGR':>7} {'Sharpe':>7} {'alfa':>7} {'holdout':>8} {'capture':>9}")
    print("-" * 92)
    full = _run_variant(seg_name, list(FULL_COLS))
    print(_fmt("FULL (alla grupper)", full)); base_cap = full.get("capture", float("nan"))
    print("-" * 92)
    results = []
    for gname, gcols in groups.items():
        active = [c for c in FULL_COLS if c not in set(gcols)]
        m = _run_variant(seg_name, active); m["group"] = gname
        results.append(m)
        delta = "" if "error" in m or pd.isna(base_cap) else f"  Δcapture {(m['capture']-base_cap)*100:+.1f}pp"
        print(_fmt(f"− {gname}", m) + delta)
    print("-" * 92)
    ok = [r for r in results if "error" not in r and not pd.isna(r.get("capture", float('nan')))]
    if ok:
        best = max(ok, key=lambda r: r["capture"])
        print(f"  Bäst capture utan en grupp: −{best['group']} ({best['capture']*100:+.1f}pp "
              f"vs full {base_cap*100:+.1f}pp)")
        print("  Positiv Δcapture = gruppen TILLFÖR brus (skär bort den). Negativ = gruppen bär edge.")


def run_backward(seg_name, seg):
    groups = feature_groups()
    remaining = dict(groups)
    active_groups = set(groups.keys())
    print("\n" + "=" * 92)
    print(f"  ABLATION (girig bakåt) – {seg['label']} – skär tills capture slutar förbättras")
    print("=" * 92)

    def active_cols(grpset):
        keep = set()
        for g in grpset:
            keep.update(groups[g])
        return [c for c in FULL_COLS if c in keep]

    cur = _run_variant(seg_name, active_cols(active_groups))
    print(_fmt("FULL", cur))
    best_cap = cur.get("capture", float("nan"))
    path = []
    while len(active_groups) > 1:
        cand = []
        for g in list(active_groups):
            trial = active_groups - {g}
            m = _run_variant(seg_name, active_cols(trial)); m["group"] = g
            cand.append(m)
            print(_fmt(f"− {g}", m))
        ok = [c for c in cand if "error" not in c and not pd.isna(c.get("capture", float('nan')))]
        if not ok:
            break
        best = max(ok, key=lambda r: r["capture"])
        if pd.isna(best_cap) or best["capture"] >= best_cap:
            active_groups -= {best["group"]}
            best_cap = best["capture"]
            path.append(best["group"])
            print(f"  -> tar bort '{best['group']}' (capture {best_cap*100:+.1f}pp). Kvar: {sorted(active_groups)}")
            print("-" * 92)
        else:
            print(f"  -> STOPP: ingen borttagning förbättrar capture ({best_cap*100:+.1f}pp).")
            break
    print("=" * 92)
    print(f"  Borttagna i ordning: {path}")
    print(f"  Sweet-spot-grupper kvar: {sorted(active_groups)}  (capture {best_cap*100:+.1f}pp)")


def main():
    args = sys.argv[1:]
    if "--worker" in args:
        seg_name = args[args.index("--segment") + 1]
        seg = config.SEGMENTS.get(seg_name) or config.SEGMENTS[config.DEFAULT_SEGMENT]
        config.RESULTS_DIR = seg["results_dir"]
        config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
        config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
        active = args[args.index("--features") + 1].split(",")
        mode = args[args.index("--mode") + 1]
        if mode == "train":
            worker_train(seg, active)
        else:
            worker_eval(seg, active)
        return

    seg_name = args[0] if args else config.DEFAULT_SEGMENT
    mode = args[1] if len(args) > 1 else "logo"
    seg = config.SEGMENTS.get(seg_name) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    config.RESULTS_DIR = seg["results_dir"]
    config.MAX_POSITIONS = seg.get("max_positions", config.MAX_POSITIONS)
    config.CONVICTION_BLEND = seg.get("conviction_blend", config.CONVICTION_BLEND)
    print(f"[Segment] {seg_name} ({seg['label']}) – {len(FULL_COLS)} features i full modell")
    if mode == "backward":
        run_backward(seg_name, seg)
    else:
        run_logo(seg_name, seg)


if __name__ == "__main__":
    main()
