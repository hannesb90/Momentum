import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from tune_horizon_ensemble import blend_horizon_ranks  # noqa: E402


def test_zero_overlay_is_exact_52_week_anchor():
    r52 = pd.Series([0.8, 0.2], index=["A", "B"])
    r13 = pd.Series([0.1, 0.9], index=["A", "B"])
    pd.testing.assert_series_equal(
        blend_horizon_ranks(r52, r13, 0.0), r52, check_names=False
    )


def test_overlay_uses_common_panel_and_bounded_weight():
    out = blend_horizon_ranks(
        pd.Series([.1, .5, .9], index=["A", "B", "C"]),
        pd.Series([.9, .5, .1], index=["B", "C", "D"]),
        .20,
    )
    assert list(out.index) == ["B", "C"]
    assert out.loc["B"] == pytest.approx(.58)
    with pytest.raises(ValueError):
        blend_horizon_ranks(pd.Series(dtype=float), pd.Series(dtype=float), 1.1)
