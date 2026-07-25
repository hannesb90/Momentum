"""Forward-only conditional Large/Mid shadow portfolio.

The production portfolio is never changed.  The ordinary rank challenger
always contributes ten core names.  A second-stage model reranks its top 20,
while trend-qualified recent exits may remain for four weekly observations.
Otto-high blocks only those extra positions; report offsets are diagnostics.
"""
from __future__ import annotations

import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

import shadow_challenger as base


VERSION = "conditional_meta20_holder4_otto_v1"
META_FEATURES = base.FEATURES + ["base_rank"]
TOP_POOL = 20
CORE_N = 10
HOLDER_WEEKS = 4
OTTO_CACHE = Path("/opt/momentum/src/momentum_ml/cache/otto_band")
BENCHMARK_CACHE = Path(
    "/opt/momentum/momentum_ml/cache/features_by_ticker/XACT-OMXS30.ST.pkl")


def _bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def train_meta(panel: pd.DataFrame, model: lgb.Booster) -> tuple[lgb.Booster, dict]:
    """Fit the serving reranker; its claims are validated only forward."""
    labelled = panel.dropna(subset=["target_return"]).copy()
    labelled["base_score"] = model.predict(
        base.model_matrix(labelled), num_iteration=model.best_iteration)
    labelled["base_rank"] = labelled.groupby("Date").base_score.rank(pct=True)
    candidates = labelled[
        labelled.groupby("Date").base_score.rank(
            ascending=False, method="first") <= TOP_POOL].copy()
    candidates["meta_target"] = (
        candidates.groupby("Date").target_return.rank(
            ascending=False, method="first") <= CORE_N).astype(int)
    dates = pd.Index(sorted(candidates.Date.unique()))
    train_dates, val_dates = dates[:-base.VAL_WEEKS], dates[-base.VAL_WEEKS:]
    tr = candidates[candidates.Date.isin(train_dates)]
    va = candidates[candidates.Date.isin(val_dates)]
    params = {
        "objective": "binary", "metric": "binary_logloss",
        "learning_rate": .03, "num_leaves": 15, "min_child_samples": 40,
        "reg_alpha": .2, "reg_lambda": 1.0, "verbosity": -1,
        "num_threads": 3, "seed": base.SEED, "deterministic": True,
        "force_row_wise": True,
    }
    meta_model = lgb.train(
        params,
        lgb.Dataset(tr[META_FEATURES], label=tr.meta_target),
        num_boost_round=500,
        valid_sets=[lgb.Dataset(va[META_FEATURES], label=va.meta_target)],
        callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(-1)],
    )
    return meta_model, {
        "version": VERSION, "features": META_FEATURES,
        "train_start": train_dates[0], "train_end": train_dates[-1],
        "validation_start": val_dates[0], "validation_end": val_dates[-1],
        "best_iteration": meta_model.best_iteration,
        "note": "Serving reranker; investment claim is forward-only.",
    }


def select_meta(signals: pd.DataFrame, latest_panel: pd.DataFrame,
                meta_model: lgb.Booster) -> pd.DataFrame:
    candidates = signals.sort_values("challenger_position").head(TOP_POOL).copy()
    fields = ["ticker", "issuer_name", *base.FEATURES,
              "mom_12_1", "days_since_report", "Close"]
    candidates = candidates.merge(
        latest_panel[[c for c in fields if c in latest_panel]],
        on="ticker", how="left")
    candidates["base_rank"] = candidates.challenger_score.rank(pct=True)
    candidates["meta_probability"] = meta_model.predict(
        candidates[META_FEATURES],
        num_iteration=meta_model.best_iteration)
    # Preserve useful first-stage ordering while allowing the specialist to
    # discriminate inside the already-qualified candidate set.
    candidates["conditional_score"] = (
        candidates.base_rank * candidates.meta_probability)
    candidates = candidates.sort_values(
        ["conditional_score", "ticker"], ascending=[False, True])
    candidates["conditional_position"] = np.arange(1, len(candidates) + 1)
    candidates["conditional_core"] = False
    unique = candidates.drop_duplicates("issuer_name", keep="first").head(CORE_N)
    candidates.loc[unique.index, "conditional_core"] = True
    candidates["report_offset_8_14d"] = candidates.days_since_report.between(8, 14)
    return candidates


def trend_flags(panel: pd.DataFrame) -> dict[str, bool]:
    """Current causal trend: price>SMA20 and 26w return>equal-weight universe."""
    wide = panel.pivot(index="Date", columns="ticker", values="Close").sort_index()
    if len(wide) < 27:
        return {}
    p = wide.iloc[-1]
    sma = wide.iloc[-20:].mean()
    rel = p / wide.iloc[-27] - 1
    benchmark = rel.mean(skipna=True)
    return ((p > sma) & (rel > benchmark)).fillna(False).to_dict()


def otto_high_flags(panel: pd.DataFrame, tickers: set[str]) -> dict[str, bool]:
    """Point-in-time expanding own-multiple high band, using cache only."""
    wide = panel.pivot(index="Date", columns="ticker", values="Close").sort_index()
    asof = wide.index.max()
    flags = {}
    for ticker in tickers:
        path = OTTO_CACHE / f"{ticker.replace('.', '_')}.pkl"
        flags[ticker] = False
        if not path.exists() or ticker not in wide:
            continue
        df = pickle.loads(path.read_bytes())
        if df.empty:
            continue
        prior = df[df.index < asof.year].sort_index()
        for col in ("mult_ebit", "mult_ebitda"):
            values = prior[col].dropna() if col in prior else pd.Series(dtype=float)
            if len(values) < 3:
                continue
            last_year = values.index.max()
            row = prior.loc[last_year]
            base_date = pd.Timestamp(row["date"])
            hist = wide[ticker].dropna()
            earlier = hist[hist.index <= base_date]
            if earlier.empty or asof not in hist:
                break
            current_mult = float(row[col]) * float(hist.loc[asof] / earlier.iloc[-1])
            flags[ticker] = current_mult >= float(values.quantile(.90))
            break
    return flags


def update_holders(previous: dict, old_core: set[str], new_core: set[str],
                   trend: dict[str, bool], otto: dict[str, bool]) -> dict[str, int]:
    active = {
        ticker: int(weeks) - 1
        for ticker, weeks in previous.items()
        if int(weeks) > 1 and ticker not in new_core
        and trend.get(ticker, False) and not otto.get(ticker, False)
    }
    for ticker in old_core - new_core:
        if trend.get(ticker, False) and not otto.get(ticker, False):
            active[ticker] = HOLDER_WEEKS
    return active


def update_ledger(signals: pd.DataFrame, panel: pd.DataFrame, path: Path) -> pd.DataFrame:
    columns = [
        "Date", "ticker", "conditional_position", "conditional_core",
        "qualified_holder", "selected", "challenger_top10", "pred_signal",
        "otto_high", "report_offset_8_14d", "conditional_score",
    ]
    new = signals[[c for c in columns if c in signals]].copy()
    new["version"] = VERSION
    new["created_at"] = datetime.now(timezone.utc).isoformat()
    new["realized_13w_return"] = np.nan
    new["matured_at"] = ""
    old = pd.read_csv(path, parse_dates=["Date"]) if path.exists() else new.iloc[0:0]
    ledger = pd.concat([old, new], ignore_index=True)
    ledger["Date"] = pd.to_datetime(ledger.Date)
    ledger = ledger.drop_duplicates(["Date", "ticker", "version"], keep="first")
    actual = panel.dropna(subset=["target_return"]).set_index(
        ["Date", "ticker"]).target_return
    pending = ledger.realized_13w_return.isna()
    keys = pd.MultiIndex.from_frame(ledger.loc[pending, ["Date", "ticker"]])
    values = actual.reindex(keys).to_numpy()
    matured = pending.copy()
    matured.loc[pending] = pd.notna(values)
    ledger.loc[pending, "realized_13w_return"] = values
    ledger.loc[matured & ledger.matured_at.fillna("").eq(""), "matured_at"] = (
        datetime.now(timezone.utc).isoformat())
    return ledger.sort_values(["Date", "ticker"])


def benchmark_targets() -> pd.Series:
    if not BENCHMARK_CACHE.exists():
        return pd.Series(dtype=float)
    payload = pickle.loads(BENCHMARK_CACHE.read_bytes())
    frame = payload.get("features") if isinstance(payload, dict) else payload
    if frame is None or "target_return" not in frame:
        return pd.Series(dtype=float)
    result = frame.target_return.copy()
    result.index = pd.to_datetime(result.index)
    return result


def scorecard(ledger: pd.DataFrame, meta: dict,
              benchmark: pd.Series | None = None) -> dict:
    current = ledger[ledger.version == VERSION].copy()
    matured = current.dropna(subset=["realized_13w_return"])
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "collecting" if matured.empty else "measuring",
        "prediction_dates": int(current.Date.nunique()),
        "matured_dates": int(matured.Date.nunique()), "model": meta,
        "production_change_authorized": False,
    }
    benchmark = benchmark if benchmark is not None else pd.Series(dtype=float)
    weekly = []
    for date, group in matured.groupby("Date"):
        conditional = group[_bool(group.selected)]
        base_rows = group[_bool(group.challenger_top10)]
        prod = group[
            pd.to_numeric(group.get("pred_signal", 0), errors="coerce").eq(1)]
        if conditional.empty or base_rows.empty:
            continue
        row = {
            "conditional": conditional.realized_13w_return.mean(),
            "base": base_rows.realized_13w_return.mean(),
            "production": prod.realized_13w_return.mean() if not prod.empty else np.nan,
            "index": benchmark.get(pd.Timestamp(date), np.nan),
        }
        row["alpha_base"] = row["conditional"] - row["base"]
        row["alpha_production"] = row["conditional"] - row["production"]
        row["alpha_index"] = row["conditional"] - row["index"]
        weekly.append(row)
    w = pd.DataFrame(weekly)
    if not w.empty:
        out["forward_metrics"] = {
            "mean_conditional_return": w.conditional.mean(),
            "mean_alpha_vs_base": w.alpha_base.mean(),
            "positive_alpha_vs_base_share": (w.alpha_base > 0).mean(),
            "mean_alpha_vs_production": w.alpha_production.mean(),
            "positive_alpha_vs_production_share": (
                w.alpha_production > 0).mean(),
            "mean_alpha_vs_index": w.alpha_index.mean(),
            "positive_alpha_vs_index_share": (w.alpha_index > 0).mean(),
            "weeks": len(w),
        }
    return out


def run(out_dir: Path, panel: pd.DataFrame, base_model: lgb.Booster,
        base_signals: pd.DataFrame) -> dict:
    required = {"Close", "target_return"}
    if not required.issubset(panel):
        raise ValueError(f"Conditional shadow saknar {sorted(required-set(panel))}")
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_model, meta = train_meta(panel, base_model)
    latest = panel[panel.Date == base_signals.Date.max()].copy()
    signals = select_meta(base_signals, latest, meta_model)
    state_path = out_dir / "conditional_shadow_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    old_core = set(state.get("core", []))
    previous_holders = state.get("holders", {})
    new_core = set(signals.loc[signals.conditional_core, "ticker"])
    trend = trend_flags(panel)
    possible = old_core | set(previous_holders)
    otto = otto_high_flags(panel, possible)
    holders = update_holders(previous_holders, old_core, new_core, trend, otto)
    signals["qualified_holder"] = signals.ticker.isin(holders)
    # Add retained names that fell outside today's top-20.
    missing = set(holders) - set(signals.ticker)
    if missing:
        extra = latest[latest.ticker.isin(missing)][
            ["Date", "ticker", "issuer_name", "days_since_report"]].copy()
        extra["qualified_holder"] = True
        extra["conditional_core"] = False
        extra["conditional_position"] = np.nan
        extra["conditional_score"] = np.nan
        extra["challenger_top10"] = False
        extra["report_offset_8_14d"] = extra.days_since_report.between(8, 14)
        if "pred_signal" in base_signals:
            extra = extra.merge(base_signals[["ticker", "pred_signal"]],
                                on="ticker", how="left")
        signals = pd.concat([signals, extra], ignore_index=True, sort=False)
    # Carry every production holding into the ledger, even when it is outside
    # the top-20 pool, so the forward comparator is not selection-biased.
    if "pred_signal" in base_signals:
        prod_missing = set(base_signals.loc[
            pd.to_numeric(base_signals.pred_signal, errors="coerce").eq(1),
            "ticker"]) - set(signals.ticker)
        if prod_missing:
            prod = base_signals[base_signals.ticker.isin(prod_missing)].merge(
                latest[["ticker", "issuer_name", "days_since_report"]],
                on="ticker", how="left")
            prod["qualified_holder"] = False
            prod["conditional_core"] = False
            prod["conditional_position"] = np.nan
            prod["conditional_score"] = np.nan
            prod["report_offset_8_14d"] = prod.days_since_report.between(8, 14)
            signals = pd.concat([signals, prod], ignore_index=True, sort=False)
    signals["otto_high"] = signals.ticker.map(otto).fillna(False)
    signals["holder_weeks_remaining"] = signals.ticker.map(holders).fillna(0).astype(int)
    signals["selected"] = signals.conditional_core | signals.qualified_holder
    n_selected = int(signals.selected.sum())
    signals["target_weight"] = np.where(
        signals.selected, 1 / n_selected if n_selected else 0, 0)
    signals["version"] = VERSION
    base.atomic_csv(signals, out_dir / "signals_conditional_shadow.csv")
    with open(out_dir / "conditional_meta_model.pkl.tmp", "wb") as handle:
        pickle.dump({"model": meta_model, "meta": meta}, handle)
    os.replace(out_dir / "conditional_meta_model.pkl.tmp",
               out_dir / "conditional_meta_model.pkl")
    base.atomic_json({
        "version": VERSION, "asof": str(base_signals.Date.max().date()),
        "core": sorted(new_core), "holders": holders,
    }, state_path)
    ledger = update_ledger(
        signals, panel, out_dir / "conditional_shadow_ledger.csv")
    base.atomic_csv(ledger, out_dir / "conditional_shadow_ledger.csv")
    card = scorecard(ledger, meta, benchmark_targets())
    base.atomic_json(card, out_dir / "conditional_shadow_scorecard.json")
    return card
