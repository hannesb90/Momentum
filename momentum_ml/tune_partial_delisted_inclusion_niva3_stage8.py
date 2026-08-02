"""N3 stage 08: partial survivorship remediation with defensible Large/Mid names.

ICA has a documented Large-cap category in the archived universe.  Collector
(COLL) has an exact Börsdata price-path match and PIT reports whose shares times
average price stay above a conservative SEK 2bn Large+Mid floor.  These two are
added to the full feature universe and seed-42 LambdaRank is retrained on the
same OOF protocol.  This is a partial sensitivity test, never a full lower bound.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from research_gates_common import apply_large, validate_large_contract

apply_large()

from backtest.backtester import MomentumBacktester
from build_delisted_pit_features_niva3 import _weekly_adjusted
from data.data_loader import load_sweden_universe
from features.feature_engineering import (FEATURE_COLS, add_cross_sectional,
    attach_categorical_features, to_model_df)
from models.ensemble import MomentumEnsemble, build_full_output
from models.lgbm_model import walk_forward_splits
from niva3_stage_control import freeze_stage, verify_manifest
from tune_abstention_gate import _load_state
from tune_objective_comparison import _train_lambdarank
from tune_seed_fitdate_stability_niva3_stage5 import _set_seed
from tune_target_horizon_isolated import raw_preds, targets_from_prices


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/07_pit_universe_delisting_audit.json"
FEATURE_DIR = ROOT / "results/niva3_delisted_features"
EOD_DIR = ROOT / "momentum_ml/cache/eodhd_delisted"
OUT = ROOT / "results/niva3_partial_delisted_inclusion.json"
SIGNALS_OUT = ROOT / "results/niva3_partial_delisted_signals.csv"
SELECTIONS = ROOT / "results/niva3_partial_delisted_selections.csv"
BUILD_REPORT = ROOT / "results/niva3_delisted_feature_build.json"
MAPPING = ROOT / "results/niva3_delisted_borsdata_mapping.csv"
CANDIDATES = ("ICA.ST", "COLL.ST")


class NoCorrelationBacktester(MomentumBacktester):
    def _correlation_filter(self, target_weights, date):
        return target_weights


def _coll_market_cap_evidence() -> dict:
    payload = json.loads((ROOT / "momentum_ml/cache/borsdata/reports_740_max20.json").read_text())
    rows = []
    for r in payload["reportsYear"]:
        date = pd.to_datetime(r.get("report_Date"), errors="coerce")
        shares = pd.to_numeric(r.get("number_Of_Shares"), errors="coerce")
        price = pd.to_numeric(r.get("stock_Price_Average"), errors="coerce")
        if pd.notna(date) and pd.notna(shares) and pd.notna(price):
            rows.append({"report_date": str(date.date()), "market_cap_msek": float(shares * price)})
    relevant = [r for r in rows if "2016-01-01" <= r["report_date"] <= "2022-12-31"]
    return {"rows": relevant, "minimum_market_cap_msek": min(r["market_cap_msek"] for r in relevant),
            "conservative_mid_floor_msek": 2000.0,
            "robust_mid_or_large": all(r["market_cap_msek"] >= 2000 for r in relevant)}


def main():
    parent = verify_manifest(PARENT)
    if parent["metadata"].get("survivorship_gate") != "FAIL":
        raise RuntimeError("Partial remediation requires failed SR48")
    build_report = json.loads(BUILD_REPORT.read_text())
    if build_report["feature_files"] != 67:
        raise RuntimeError("Expected all 67 complete delisted feature files")
    mapping = pd.read_csv(MAPPING).set_index("ticker")
    if not bool(mapping.loc["COLL.ST", "accepted"]) or int(mapping.loc["COLL.ST", "borsdata_instrument"]) != 740:
        raise RuntimeError("COLL Börsdata path match is not frozen/accepted")
    coll_evidence = _coll_market_cap_evidence()
    if not coll_evidence["robust_mid_or_large"]:
        raise RuntimeError("COLL does not clear conservative PIT market-cap floor")

    features, prices, state, _ = _load_state()
    features = {ticker: frame.copy() for ticker, frame in features.items()}
    for ticker in CANDIDATES:
        features[ticker] = pd.read_pickle(FEATURE_DIR / f"{ticker}.pkl")
        daily = pd.read_csv(EOD_DIR / f"{ticker.replace('.', '_')}.csv")
        prices[ticker] = _weekly_adjusted(daily)
    _, sectors, caps, names = load_sweden_universe(
        min_market_cap=config.SEGMENTS["large"]["market_cap"])
    sectors = dict(sectors); caps = dict(caps); names = dict(names)
    sectors["ICA.ST"] = "Consumer Staples"; caps["ICA.ST"] = "Large Cap"; names["ICA.ST"] = "ICA Gruppen"
    sectors["COLL.ST"] = "Unknown"; caps["COLL.ST"] = "Mid Cap"; names["COLL.ST"] = "Collector"
    config.SECTOR_MAP.update(sectors); config.CAP_TIER_MAP.update(caps); config.NAME_MAP.update(names)

    # Recompute cross-sectional features for the complete augmented universe.
    features = add_cross_sectional(features)
    features = attach_categorical_features(features, sectors, caps)
    for ticker in CANDIDATES:
        for col in FEATURE_COLS:
            if col not in features[ticker]:
                features[ticker][col] = 365.0 if col == "days_since_report" else np.nan
    cols = list(getattr(state, "feature_cols_", []) or FEATURE_COLS)
    validate_large_contract(cols)
    base = to_model_df(features).sort_index(); base.index.name = "Date"
    target13 = targets_from_prices(base, prices, 13)
    target52 = targets_from_prices(base, prices, 52)
    feature_base = base.drop(columns=[c for c in base.columns if c.startswith("target_")], errors="ignore")
    t13 = target13.reset_index().rename(columns={"target_return": "ret13", "target_signal": "sig13"})
    t52 = target52.reset_index().rename(columns={"target_return": "ret52", "target_signal": "sig52"})
    panel = (feature_base.reset_index().merge(t13, on=["Date", "ticker"])
             .merge(t52, on=["Date", "ticker"]).dropna(subset=["ret13", "sig13", "ret52", "sig52"])
             .set_index("Date").sort_index())
    panel["target_return"] = panel.ret13; panel["target_signal"] = panel.sig13
    dates = panel.index.unique().sort_values(); purge = dates[-(config.HOLDOUT_WEEKS + 52)]
    dev = panel[panel.index < purge]
    splits = walk_forward_splits(dev.index, embargo_weeks=52)
    _set_seed(42); raw = []
    for split_i, (train_dates, val_dates, test_dates) in enumerate(splits):
        train = dev[dev.index.isin(train_dates)].sort_index()
        val = dev[dev.index.isin(val_dates)].sort_index()
        test = dev[dev.index.isin(test_dates)].sort_index()
        model = _train_lambdarank(train, val, cols)
        piece = test[["ticker"]].copy(); piece["raw"] = model.predict(test[cols].fillna(0).values)
        raw.append(piece); print(f"augmented split {split_i+1}/{len(splits)}", flush=True)
    feature_dfs = {ticker: frame.assign(ticker=ticker) for ticker, frame in features.items()}
    config.REBALANCE_WEEKS = 52; config.SIZING_MODE = "inverse_vol"; config.CONVICTION_BLEND = .75
    sig = build_full_output(raw_preds(pd.concat(raw).sort_index()), None, feature_dfs,
                            MomentumEnsemble(), record_diagnostics=False)
    bt = NoCorrelationBacktester(sig, prices); bt.run(); stats = bt.statistics()
    selected = sig[sig.pred_signal.eq(1) & sig.ticker.isin(CANDIDATES)].reset_index()
    selected.to_csv(SELECTIONS, index=False); sig.to_csv(SIGNALS_OUT)
    baseline = json.loads((ROOT / "results/retraining_staleness_niva2.json").read_text())["retrain_13w_parity"]
    report = {"status": "PASS", "parent_stage": parent["manifest_sha256"],
              "test": "N3-SR48-partial-delisted-inclusion", "candidates": list(CANDIDATES),
              "candidate_basis": {"ICA.ST": "archived_universe_Large_Cap", "COLL.ST": coll_evidence},
              "augmented_rows": len(dev), "splits": len(splits),
              "candidate_rows": {t: int(dev.ticker.eq(t).sum()) for t in CANDIDATES},
              "candidate_selected_rows": {t: int(selected.ticker.eq(t).sum()) for t in CANDIDATES},
              "baseline": baseline, "partial_augmented_metrics": {k: stats[k] for k in
                  ("CAGR", "Sharpe", "Max Drawdown", "End Capital")},
              "full_survivorship_lower_bound": False,
              "remaining_gap": "65 complete-price delisted series not defensibly classified Large/Mid plus 23 incomplete series",
              "partial_remediation_gate": "PASS", "survivorship_gate": "FAIL",
              "production": False, "holdout_used": False}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    feature_files = [FEATURE_DIR / f"{ticker}.pkl" for ticker in
                     pd.read_csv(ROOT / "results/point_in_time/eodhd_delisted_coverage.csv")
                     .loc[lambda x: x.complete_from_listing.fillna(False).astype(bool), "ticker"]]
    stage = freeze_stage("08_partial_delisted_inclusion",
        [OUT, SIGNALS_OUT, SELECTIONS, BUILD_REPORT, MAPPING, Path(__file__).resolve(),
         ROOT / "momentum_ml/build_delisted_pit_features_niva3.py", *feature_files],
        {"test": "N3-SR48-partial", "partial_remediation_gate": "PASS",
         "survivorship_gate": "FAIL", "production": False}, parent=PARENT)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str)); print(stage)


if __name__ == "__main__":
    main()
