"""Isolated Small/Micro 13-week monotone-rank shadow challenger.

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
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr


HOME = Path("/opt/momentum/momentum_ml")
RAW_FEATURES = [
    "mom_12_1", "mom_tstat_26w", "resid_mom", "atr_norm",
    "report_reaction_abn",
]
FEATURES = [
    "mom_12_1_rank", "mom_tstat_26w_rank", "resid_mom_rank",
    "atr_norm_rank", "report_reaction_abn_rank",
]
RANK_DIRECTIONS = [1, 1, 1, -1, 1]
CONSTRAINTS = [1] * len(FEATURES)
MODEL_VERSION = "small13_rank5_neutral_missing_v1"
TOP_N = 20
VAL_WEEKS = 26
FORWARD_WEEKS = 13
SEED = 42


def canonical_issuer(name: str) -> str:
    """Normalize share-class decorations without conflating different issuers."""
    value = str(name).lower()
    value = re.sub(r"\bclass\s+[a-z]\b", " ", value)
    value = re.sub(r"\bsek\s+[\d.]+\s+cum\s+pref.*$", " ", value)
    value = re.sub(r"\bpref(?:erence)?\.?\s*(?:shs|shares)?\b", " ", value)
    value = re.sub(r"\b(?:ab|publ)\b", " ", value)
    value = re.sub(r"[^a-z0-9åäö]+", " ", value)
    return " ".join(value.split())


def atomic_csv(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def atomic_json(obj: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    os.replace(tmp, path)


def load_panel() -> tuple[pd.DataFrame, Path]:
    explicit = os.environ.get("MOMENTUM_SMALL13_CACHE")
    caches = ([Path(explicit)] if explicit else sorted(
        (HOME / "results/small").glob("_features_cache_*.pkl"),
        key=lambda p: p.stat().st_mtime, reverse=True))
    if not caches:
        raise FileNotFoundError("Ingen Small/Micro-featurecache hittades.")
    cache = joblib.load(caches[0])
    gaps = {
        len(feat.loc[feat.target_return.last_valid_index():]) - 1
        for feat in cache.values()
        if "target_return" in feat and feat.target_return.last_valid_index() is not None
    }
    if gaps != {FORWARD_WEEKS}:
        raise ValueError(
            f"Fel targethorisont i Small/Micro-cachen: {sorted(gaps)}; "
            f"kräver exakt {FORWARD_WEEKS} veckor.")
    frames = []
    for ticker, feat in cache.items():
        missing = [c for c in RAW_FEATURES + ["target_return", "ret_1w"]
                   if c not in feat.columns]
        if missing:
            raise ValueError(f"{ticker}: saknar kolumner {missing}")
        x = feat[RAW_FEATURES + ["target_return", "ret_1w"]].copy()
        x["Date"] = pd.to_datetime(x.index)
        x["ticker"] = ticker
        frames.append(x.reset_index(drop=True))
    panel = pd.concat(frames, ignore_index=True)
    # Exakt Small/Micro-aktieuniversum. Featurecachen innehåller även sektor-ETF:er
    # för andra analysvyer; de får aldrig bli challenger-kandidater.
    universe = pd.read_csv(HOME / "data/sweden_universe.csv")
    allowed = set(universe.loc[
        universe.market_cap_category.isin(["Small Cap", "Micro Cap"]), "ticker"
    ])
    panel = panel[panel.ticker.isin(allowed)]
    issuer = universe.drop_duplicates("ticker").set_index("ticker")["name"]
    panel["issuer_name"] = panel.ticker.map(issuer).fillna(panel.ticker)
    panel["issuer_key"] = panel.issuer_name.map(canonical_issuer)
    panel = panel.sort_values(["Date", "ticker"]).reset_index(drop=True)
    panel = add_weekly_ranks(panel)
    return panel, caches[0]


def add_weekly_ranks(frame: pd.DataFrame) -> pd.DataFrame:
    """Create causal cross-sectional ranks; missing raw signals are neutral."""
    frame = frame.copy()
    for source, target, direction in zip(
            RAW_FEATURES, FEATURES, RANK_DIRECTIONS):
        values = frame[source].replace([np.inf, -np.inf], np.nan)
        ranked = values.groupby(frame["Date"]).rank(
            pct=True, method="average")
        if direction < 0:
            ranked = 1.0 - ranked
        frame[target] = ranked.fillna(0.5)
    return frame


def model_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    matrix = frame[FEATURES].replace([np.inf, -np.inf], np.nan)
    if matrix.isna().any().any():
        raise ValueError("Rankmatrisen innehåller saknade värden.")
    return matrix


def target_rank(frame: pd.DataFrame) -> pd.Series:
    return frame.groupby("Date").target_return.rank(pct=True)


def train(panel: pd.DataFrame) -> tuple[lgb.Booster, dict]:
    labelled = panel.dropna(subset=["target_return"]).copy()
    dates = pd.Index(sorted(labelled.Date.unique()))
    if len(dates) <= VAL_WEEKS + FORWARD_WEEKS:
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
        "constraints": CONSTRAINTS, "model_version": MODEL_VERSION,
        "forward_weeks": FORWARD_WEEKS,
    }
    return model, meta


def current_signals(panel: pd.DataFrame, model: lgb.Booster) -> pd.DataFrame:
    panel = panel.copy()
    if "issuer_key" not in panel:
        panel["issuer_key"] = panel.issuer_name.map(canonical_issuer)
    coverage = panel.groupby("Date").ticker.nunique()
    minimum = min(TOP_N, max(1, int(coverage.max() * 0.5)))
    complete_dates = coverage[coverage >= minimum]
    if complete_dates.empty:
        raise ValueError(
            f"Inget datum har tillräcklig tvärsnittstäckning (minst {minimum}).")
    latest_date = complete_dates.index.max()
    latest = panel[panel.Date == latest_date].copy()
    latest = latest[
        ~latest.ticker.str.contains(r"-PREF", case=False, regex=True)]
    latest["challenger_score"] = model.predict(
        model_matrix(latest), num_iteration=model.best_iteration)
    latest["challenger_rank"] = latest.challenger_score.rank(
        pct=True, method="average")
    latest = latest.sort_values(
        ["challenger_score", "ticker"], ascending=[False, True])
    latest["challenger_position"] = np.arange(1, len(latest) + 1)
    latest["challenger_top20"] = False
    unique_issuers = latest.drop_duplicates("issuer_key", keep="first").head(TOP_N)
    latest.loc[unique_issuers.index, "challenger_top20"] = True
    latest["issuer_duplicate"] = latest.duplicated("issuer_key", keep="first")
    latest["model_version"] = MODEL_VERSION

    prod_path = HOME / "results/small/signals_serving.csv"
    if not prod_path.exists():
        prod_path = HOME / "results/small/signals.csv"
    if prod_path.exists():
        prod = pd.read_csv(prod_path, parse_dates=["Date"])
        prod = prod[prod.Date == prod.Date.max()]
        keep = [c for c in ["ticker", "prob_raw", "prob_up", "prob_rank",
                             "pred_signal"] if c in prod.columns]
        latest = latest.merge(prod[keep], on="ticker", how="left")

    cols = [
        "Date", "ticker", "challenger_score", "challenger_rank",
        "challenger_position", "challenger_top20", "issuer_duplicate",
        "model_version",
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
        if ("realized_13w_return" not in old and
                "realized_52w_return" in old):
            old = old.rename(columns={
                "realized_52w_return": "realized_13w_return"})
        if "model_version" not in old:
            old["model_version"] = "legacy_rank5_raw_v1"
        ledger = pd.concat([old, new], ignore_index=True)
    else:
        ledger = new
    ledger["Date"] = pd.to_datetime(ledger["Date"])
    ledger = ledger.drop_duplicates(
        ["Date", "ticker", "model_version"], keep="first")

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


def update_vol15_nav(ledger: pd.DataFrame, panel: pd.DataFrame,
                     nav_path: Path) -> pd.DataFrame:
    """Mark one causal weekly return using prior week's top-20 and 15% vol cap."""
    if nav_path.exists():
        nav = pd.read_csv(nav_path, parse_dates=["Date"])
    else:
        nav = pd.DataFrame(columns=[
            "Date", "gross_return", "vol_exposure", "net_return", "nav"])
    dates = sorted(ledger.loc[
        ledger.model_version == MODEL_VERSION, "Date"].unique())
    if not dates:
        return nav
    current_date = pd.Timestamp(dates[-1])
    if not nav.empty and current_date <= nav.Date.max():
        return nav
    if nav.empty:
        row = {
            "Date": current_date, "gross_return": np.nan,
            "vol_exposure": 1.0, "net_return": np.nan, "nav": 1.0}
    else:
        previous_date = pd.Timestamp(dates[-2]) if len(dates) >= 2 else nav.Date.max()
        previous = ledger[
            (ledger.model_version == MODEL_VERSION) &
            (ledger.Date == previous_date) &
            ledger.challenger_top20.astype(str).str.lower().isin(["true", "1"])
        ]
        returns = panel[
            (panel.Date == current_date) &
            panel.ticker.isin(previous.ticker)
        ].ret_1w.dropna()
        gross = float(returns.mean()) if not returns.empty else 0.0
        nav_returns = nav["nav"].pct_change().dropna().tail(13)
        if len(nav_returns) >= 2 and nav_returns.std() > 0:
            realized_vol = float(nav_returns.std() * np.sqrt(52))
            exposure = min(0.15 / realized_vol, 1.0)
        else:
            exposure = 1.0
        net = gross * exposure
        row = {
            "Date": current_date, "gross_return": gross,
            "vol_exposure": exposure, "net_return": net,
            "nav": float(nav.iloc[-1]["nav"]) * (1 + net)}
    nav = pd.concat([nav, pd.DataFrame([row])], ignore_index=True)
    return nav.sort_values("Date")


def scorecard(ledger: pd.DataFrame, meta: dict, cache_path: Path,
              nav: pd.DataFrame | None = None) -> dict:
    current = ledger[ledger.model_version == MODEL_VERSION].copy()
    matured = current.dropna(subset=["realized_13w_return"]).copy()
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting" if matured.empty else "measuring",
        "cache": str(cache_path), "model": meta,
        "prediction_dates": int(current.Date.nunique()),
        "matured_prediction_dates": int(matured.Date.nunique()),
        "risk_overlay": {
            "type": "causal_vol_target", "annual_target": 0.15,
            "max_leverage": 1.0,
            "nav_observations": 0 if nav is None else len(nav),
            "current_exposure": (
                None if nav is None or nav.empty
                else float(nav.iloc[-1].vol_exposure)),
            "nav": (
                None if nav is None or nav.empty
                else float(nav.iloc[-1]["nav"])),
        },
    }
    if matured.empty:
        return out
    weekly = []
    for date, g in matured.groupby("Date"):
        if len(g) < 20:
            continue
        ic = spearmanr(g.challenger_score, g.realized_13w_return).statistic
        top = g[g.challenger_top20.astype(str).str.lower().isin(["true", "1"])]
        rest = g.drop(top.index)
        weekly.append({
            "Date": date, "ic": ic,
            "top20_return": top.realized_13w_return.mean(),
            "top20_spread": (top.realized_13w_return.mean() -
                             rest.realized_13w_return.mean()),
        })
    w = pd.DataFrame(weekly)
    if not w.empty:
        out["forward_metrics"] = {
            "mean_ic": w.ic.mean(),
            "positive_ic_share": (w.ic > 0).mean(),
            "mean_top20_return": w.top20_return.mean(),
            "mean_top20_spread": w.top20_spread.mean(),
            "positive_top_spread_share": (w.top20_spread > 0).mean(),
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
    nav = update_vol15_nav(
        ledger, panel, out_dir / "challenger_vol15_nav.csv")
    atomic_csv(nav, out_dir / "challenger_vol15_nav.csv")
    card = scorecard(ledger, meta, cache_path, nav)
    atomic_json(card, out_dir / "challenger_scorecard.json")
    overlap = np.nan
    if "pred_signal" in signals:
        prod = set(signals.loc[signals.pred_signal == 1, "ticker"])
        chall = set(signals.loc[signals.challenger_top20, "ticker"])
        overlap = len(prod & chall) / TOP_N
    print(json.dumps({
        "latest_date": str(signals.Date.max().date()),
        "top20": signals.loc[signals.challenger_top20, "ticker"].head(
            TOP_N).tolist(),
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
