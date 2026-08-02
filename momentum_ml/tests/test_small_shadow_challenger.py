import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
try:
    import small_shadow_challenger as challenger
except ImportError:
    import momentum_small_shadow_challenger as challenger


def sample_panel():
    dates = pd.to_datetime(["2025-01-06"] * 3 + ["2025-01-13"] * 3)
    return pd.DataFrame({
        "Date": dates,
        "mom_12_1": [1.0, np.nan, 3.0, 4.0, 5.0, 6.0],
        "mom_tstat_26w": [1, 2, 3, 4, 5, 6],
        "resid_mom": [1, 2, 3, 4, 5, 6],
        "atr_norm": [1, 2, 3, 4, 5, 6],
        "report_reaction_abn": [1, 2, 3, 4, 5, 6],
        "days_since_report": [10, 20, 500, 30, 40, 50],
    })


def test_missing_raw_signal_gets_neutral_rank():
    ranked = challenger.add_weekly_ranks(sample_panel())
    assert ranked.loc[1, "mom_12_1_rank"] == 0.5


def test_atr_rank_is_inverted_before_monotone_model():
    ranked = challenger.add_weekly_ranks(sample_panel())
    assert ranked.loc[0, "atr_norm_rank"] > ranked.loc[2, "atr_norm_rank"]


def test_rank_matrix_has_no_missing_values():
    ranked = challenger.add_weekly_ranks(sample_panel())
    assert not challenger.model_matrix(ranked).isna().any().any()


class FakeModel:
    best_iteration = 1

    def predict(self, matrix, num_iteration=None):
        return np.arange(len(matrix), 0, -1, dtype=float)


def test_top10_never_contains_two_share_classes_of_same_issuer():
    rows = 12
    panel = pd.DataFrame({
        "Date": pd.to_datetime(["2025-01-06"] * rows),
        "ticker": [f"T{i}" for i in range(rows)],
        "issuer_name": ["Same issuer", "Same issuer"] +
                       [f"Issuer {i}" for i in range(2, rows)],
    })
    for feature in challenger.FEATURES:
        panel[feature] = np.linspace(1, 0, rows)
    signals = challenger.current_signals(panel, FakeModel())
    chosen = signals[signals.challenger_top20]
    assert len(chosen) == rows - 1
    assert chosen.ticker.isin(["T0", "T1"]).sum() == 1
