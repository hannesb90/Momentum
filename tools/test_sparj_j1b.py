#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sparj_j1b_atr_adx import PREREG, ROOT, weekly_indicators


def test_preregistration_is_fixed() -> None:
    p = json.loads(PREREG.read_text())
    assert p["multiple_testing"]["parameter_search"] is False
    assert p["tests"]["atr_normalized_risk"]["legacy_replication_parameter"] == "14 weekly observations"
    assert p["tests"]["adx_trend_strength"]["legacy_replication_parameter"] == "14 weekly observations"
    stop = p["tests"]["atr_trailing_stop"]["legacy_replication_parameters"]
    assert stop["atr_window"].startswith("10 completed weekly bars")
    assert stop["stop_distance"].startswith("2.5 * ATR10")


def test_indicator_is_past_only_and_ohlc_consistent() -> None:
    rows = []
    for i in range(140):
        day = (pd.Timestamp("2020-01-01") + pd.Timedelta(days=i)).date().isoformat()
        close = 100 + i * 0.1
        rows.append({"d": day, "adjusted_open": close - 0.2, "adjusted_high": close + 1, "adjusted_low": close - 1, "adjusted_close": close})
    original = weekly_indicators(rows)
    changed = [dict(row) for row in rows]
    for row in changed[-14:]:
        row["adjusted_high"] *= 10
    modified = weekly_indicators(changed)
    cutoff = pd.Timestamp(changed[-15]["d"])
    left = original.loc[original.index <= cutoff, ["atr_norm_14w", "adx_14w"]]
    right = modified.loc[modified.index <= cutoff, ["atr_norm_14w", "adx_14w"]]
    assert np.allclose(left, right, equal_nan=True)


def test_no_target_in_decision_or_indicator_functions() -> None:
    tree = ast.parse((ROOT / "tools/sparj_j1b_atr_adx.py").read_text())
    functions = {node.name: ast.get_source_segment((ROOT / "tools/sparj_j1b_atr_adx.py").read_text(), node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("weekly_indicators", "load", "atr_stop_portfolio"):
        assert "target_fwd52w" not in functions[name]


if __name__ == "__main__":
    test_preregistration_is_fixed()
    test_indicator_is_past_only_and_ohlc_consistent()
    test_no_target_in_decision_or_indicator_functions()
    print(json.dumps({"status": "PASS", "tests": 3}))
