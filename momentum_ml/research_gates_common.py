"""Shared helpers for the pre-research integrity gates."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pandas as pd
import config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "research_gates"


def apply_large() -> dict:
    seg = config.SEGMENTS["large"]
    config.ACTIVE_SEGMENT = "large"
    mapping = (("results_dir", "RESULTS_DIR"),
               ("max_positions", "MAX_POSITIONS"),
               ("conviction_blend", "CONVICTION_BLEND"),
               ("index_ticker", "INDEX_BENCHMARK_TICKER"),
               ("index_label", "INDEX_BENCHMARK_LABEL"),
               ("gate_enabled", "MOMENTUM_GATE_ENABLED"),
               ("gate_min", "MOMENTUM_GATE_MIN"),
               ("forward_weeks", "FORWARD_WEEKS"),
               ("rebalance_weeks", "REBALANCE_WEEKS"),
               ("embargo_weeks", "EMBARGO_WEEKS"),
               ("rank_ema_span", "RANK_EMA_SPAN"),
               ("atr_stop_enabled", "ATR_STOP_ENABLED"),
               ("market_filter_exposure", "MARKET_FILTER_EXPOSURE"),
               ("drop_features", "DROP_FEATURES"))
    for key, attr in mapping:
        if key in seg:
            setattr(config, attr, seg[key])
    return seg


def contract_snapshot(feature_cols: list[str] | None = None) -> dict:
    """Serializable research identity; fail loudly when a script drifts."""
    return {
        "segment": getattr(config, "ACTIVE_SEGMENT", None),
        "forward_weeks": int(config.FORWARD_WEEKS),
        "rebalance_weeks": int(config.REBALANCE_WEEKS),
        "embargo_weeks": int(config.EMBARGO_WEEKS),
        "max_positions": int(config.MAX_POSITIONS),
        "market_filter_exposure": dict(config.MARKET_FILTER_EXPOSURE),
        "index_ticker": config.INDEX_BENCHMARK_TICKER,
        "feature_cols": list(feature_cols or []),
    }


def validate_large_contract(feature_cols: list[str] | None = None) -> dict:
    seg = config.SEGMENTS["large"]
    snap = contract_snapshot(feature_cols)
    expected = {"segment": "large", "forward_weeks": int(seg["forward_weeks"]),
                "rebalance_weeks": int(seg["rebalance_weeks"]),
                "embargo_weeks": int(seg["embargo_weeks"]),
                "max_positions": int(seg["max_positions"]),
                "market_filter_exposure": dict(seg["market_filter_exposure"]),
                "index_ticker": seg["index_ticker"]}
    mismatch = {k: {"actual": snap[k], "expected": v} for k, v in expected.items()
                if snap[k] != v}
    if mismatch:
        raise RuntimeError(f"Large research contract mismatch: {mismatch}")
    if feature_cols is not None and not feature_cols:
        raise RuntimeError("Research contract has no locked feature columns")
    return snap


def load_prices(path: Path | None = None) -> dict[str, pd.DataFrame]:
    frame = pd.read_csv(path or ROOT / "results" / "prices.csv", parse_dates=["date"])
    return {ticker: g.set_index("date").sort_index()[["close"]].rename(columns={"close": "Close"})
            for ticker, g in frame.groupby("ticker")}


def fingerprint(frame: pd.DataFrame, columns: list[str]) -> str:
    clean = frame[columns].copy().reset_index()
    return hashlib.sha256(pd.util.hash_pandas_object(clean, index=False).values.tobytes()).hexdigest()


def write_report(name: str, report: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
