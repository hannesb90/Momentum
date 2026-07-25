"""Isolated serving/shadow runner for Momentum's monotone rank challenger.

It never imports portfolio/order code and never writes production signals.csv.
Outputs:
  signals_challenger.csv       current shadow ranking
  challenger_ledger.csv        append-only prediction ledger, later matured
  challenger_scorecard.json    forward-only comparison when labels mature
  challenger_model.pkl         current serving model
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr


HOME = Path("/opt/momentum/momentum_ml")
FEATURES = [
    "mom_12_1", "mom_tstat_26w", "resid_mom", "atr_norm",
    "report_reaction_abn",
]
CONSTRAINTS = [1, 1, 1, -1, 1]
TOP_N = 10
VAL_WEEKS = 26
SEED = 42


def atomic_csv(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def atomic_json(obj: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    os.replace(tmp, path)


def load_panel() -> tuple[pd.DataFrame, Path]:
    caches = sorted((HOME / "results").glob("_features_cache_*.pkl"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    if not caches:
        raise FileNotFoundError("Ingen Large/Mid-featurecache hittades.")
    cache = joblib.load(caches[0])
    frames = []
    for ticker, feat in cache.items():
        missing = [c for c in FEATURES + ["target_return"] if c not in feat.columns]
        if missing:
            raise ValueError(f"{ticker}: saknar kolumner {missing}")
        x = feat[FEATURES + ["target_return"]].copy()
        x["Date"] = pd.to_datetime(x.index)
        x["ticker"] = ticker
        frames.append(x.reset_index(drop=True))
    panel = pd.concat(frames, ignore_index=True)
    # Exakt Large/Mid-aktieuniversum. Featurecachen innehåller även sektor-ETF:er
    # för andra analysvyer; de får aldrig bli challenger-kandidater.
    universe = pd.read_csv(HOME / "data/sweden_universe.csv")
    allowed = set(universe.loc[
        universe.market_cap_category.isin(["Large Cap", "Mid Cap"]), "ticker"
    ])
    panel = panel[panel.ticker.isin(allowed)]
    panel = panel.sort_values(["Date", "ticker"]).reset_index(drop=True)
    return panel, caches[0]


def model_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0.0)


def target_rank(frame: pd.DataFrame) -> pd.Series:
    return frame.groupby("Date").target_return.rank(pct=True)


def train(panel: pd.DataFrame) -> tuple[lgb.Booster, dict]:
    labelled = panel.dropna(subset=["target_return"]).copy()
    dates = pd.Index(sorted(labelled.Date.unique()))
    if len(dates) <= VAL_WEEKS + 52:
        raise ValueError("För få labelade veckor för shadow-träning.")
    train_dates, val_dates = dates[:-VAL_WEEKS], dates[-VAL_WEEKS:]
    tr = labelled[labelled.Date.isin(train_dates)]
    va = labelled[labelled.Date.isin(val_dates)]
    params = {
        "objective": "regression", "metric": "l2", "learning_rate": 0.05,
        "num_leaves": 31, "min_child_samples": 50, "subsample": 0.8,
        "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 1.0,
        "verbosity": -1, "num_threads": 3, "seed": SEED,
        "bagging_seed": SEED, "feature_fraction_seed": SEED,
        "data_random_seed": SEED, "deterministic": True,
        "force_row_wise": True, "monotone_constraints": CONSTRAINTS,
        "monotone_constraints_method": "advanced",
    }
    model = lgb.train(
        params,
        lgb.Dataset(model_matrix(tr), label=target_rank(tr)),
        num_boost_round=1000,
        valid_sets=[lgb.Dataset(model_matrix(va), label=target_rank(va))],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )
    meta = {
        "train_start": train_dates[0], "train_end": train_dates[-1],
        "validation_start": val_dates[0], "validation_end": val_dates[-1],
        "best_iteration": model.best_iteration, "features": FEATURES,
        "constraints": CONSTRAINTS,
    }
    return model, meta


def current_signals(panel: pd.DataFrame, model: lgb.Booster) -> pd.DataFrame:
    latest_date = panel.Date.max()
    latest = panel[panel.Date == latest_date].copy()
    latest["challenger_score"] = model.predict(
        model_matrix(latest), num_iteration=model.best_iteration)
    latest["challenger_rank"] = latest.challenger_score.rank(
        pct=True, method="average")
    latest["challenger_position"] = latest.challenger_score.rank(
        ascending=False, method="first").astype(int)
    latest["challenger_top10"] = latest.challenger_position <= TOP_N

    prod_path = HOME / "results/signals_serving.csv"
    if not prod_path.exists():
        prod_path = HOME / "results/signals.csv"
    if prod_path.exists():
        prod = pd.read_csv(prod_path, parse_dates=["Date"])
        prod = prod[prod.Date == prod.Date.max()]
        keep = [c for c in ["ticker", "prob_raw", "prob_up", "prob_rank",
                             "pred_signal"] if c in prod.columns]
        latest = latest.merge(prod[keep], on="ticker", how="left")

    cols = [
        "Date", "ticker", "challenger_score", "challenger_rank",
        "challenger_position", "challenger_top10",
        *[c for c in ["prob_raw", "prob_up", "prob_rank", "pred_signal"]
          if c in latest.columns],
    ]
    return latest[cols].sort_values("challenger_position")


def update_ledger(signals: pd.DataFrame, panel: pd.DataFrame,
                  ledger_path: Path) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    new = signals.copy()
    new["created_at"] = now
    new["realized_13w_return"] = np.nan
    new["matured_at"] = ""

    if ledger_path.exists():
        old = pd.read_csv(ledger_path, parse_dates=["Date"])
        ledger = pd.concat([old, new], ignore_index=True)
    else:
        ledger = new
    ledger["Date"] = pd.to_datetime(ledger["Date"])
    ledger = ledger.drop_duplicates(["Date", "ticker"], keep="first")

    actual = panel[["Date", "ticker", "target_return"]].dropna()
    lookup = actual.set_index(["Date", "ticker"]).target_return
    pending = ledger.realized_13w_return.isna()
    keys = pd.MultiIndex.from_frame(ledger.loc[pending, ["Date", "ticker"]])
    values = lookup.reindex(keys).to_numpy()
    matured = pending.copy()
    matured.loc[pending] = pd.notna(values)
    ledger.loc[pending, "realized_13w_return"] = values
    ledger.loc[matured & (ledger.matured_at.fillna("") == ""), "matured_at"] = now
    return ledger.sort_values(["Date", "challenger_position"])


def scorecard(ledger: pd.DataFrame, meta: dict, cache_path: Path) -> dict:
    matured = ledger.dropna(subset=["realized_13w_return"]).copy()
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting" if matured.empty else "measuring",
        "cache": str(cache_path), "model": meta,
        "prediction_dates": int(ledger.Date.nunique()),
        "matured_prediction_dates": int(matured.Date.nunique()),
    }
    if matured.empty:
        return out
    weekly = []
    for date, g in matured.groupby("Date"):
        if len(g) < 20:
            continue
        ic = spearmanr(g.challenger_score, g.realized_13w_return).statistic
        top = g[g.challenger_top10.astype(str).str.lower().isin(["true", "1"])]
        rest = g.drop(top.index)
        weekly.append({
            "Date": date, "ic": ic,
            "top10_return": top.realized_13w_return.mean(),
            "top10_spread": (top.realized_13w_return.mean() -
                             rest.realized_13w_return.mean()),
        })
    w = pd.DataFrame(weekly)
    if not w.empty:
        out["forward_metrics"] = {
            "mean_ic": w.ic.mean(),
            "positive_ic_share": (w.ic > 0).mean(),
            "mean_top10_return": w.top10_return.mean(),
            "mean_top10_spread": w.top10_spread.mean(),
            "weeks": len(w),
        }
    return out


def run(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    panel, cache_path = load_panel()
    model, meta = train(panel)
    signals = current_signals(panel, model)
    atomic_csv(signals, out_dir / "signals_challenger.csv")
    joblib.dump({"model": model, "meta": meta},
                out_dir / "challenger_model.pkl")
    ledger = update_ledger(signals, panel, out_dir / "challenger_ledger.csv")
    atomic_csv(ledger, out_dir / "challenger_ledger.csv")
    card = scorecard(ledger, meta, cache_path)
    atomic_json(card, out_dir / "challenger_scorecard.json")
    overlap = np.nan
    if "pred_signal" in signals:
        prod = set(signals.loc[signals.pred_signal == 1, "ticker"])
        chall = set(signals.loc[signals.challenger_top10, "ticker"])
        overlap = len(prod & chall) / TOP_N
    print(json.dumps({
        "latest_date": str(signals.Date.max().date()),
        "top10": signals.head(TOP_N).ticker.tolist(),
        "production_overlap": overlap,
        "scorecard_status": card["status"],
        "out_dir": str(out_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path,
                        default=Path("/home/hannesb/momentum_shadow"))
    args = parser.parse_args()
    run(args.out_dir)
