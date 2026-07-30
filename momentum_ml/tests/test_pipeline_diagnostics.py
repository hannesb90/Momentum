import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest import pipeline_diagnostics as diag  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_diagnostics():
    diag.reset_all()
    yield
    diag.reset_all()


# ── Universumskonsistens ─────────────────────────────────────────────────────

def test_record_universe_stage_tracks_count_per_stage():
    diag.record_universe_stage("fetch", ["A", "B", "C"])
    diag.record_universe_stage("liquidity_filter", ["A", "C"])
    stages = diag.get_universe_stages()
    assert [s["stage"] for s in stages] == ["fetch", "liquidity_filter"]
    assert stages[0]["n"] == 3
    assert stages[1]["n"] == 2


def test_record_universe_stage_dedupes_tickers_for_the_hash():
    entry = diag.record_universe_stage("fetch", ["A", "A", "B"])
    assert entry["n"] == 2


def test_record_universe_stage_same_tickers_give_same_hash():
    e1 = diag.record_universe_stage("s1", ["B", "A"])
    e2 = diag.record_universe_stage("s2", ["A", "B"])
    assert e1["tickers_hash"] == e2["tickers_hash"]


def test_record_universe_stage_different_tickers_give_different_hash():
    e1 = diag.record_universe_stage("s1", ["A", "B"])
    e2 = diag.record_universe_stage("s2", ["A", "C"])
    assert e1["tickers_hash"] != e2["tickers_hash"]


# ── Silent NaN-propagation ───────────────────────────────────────────────────

def test_record_nan_counts_per_column_and_dropped_rows():
    before = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": [np.nan, np.nan, 3.0]})
    after = before.dropna(subset=["a"])
    entry = diag.record_nan("test_step", before, after, cols=["a", "b"])
    assert entry["rows_before"] == 3
    assert entry["rows_after"] == 2
    assert entry["rows_dropped"] == 1
    assert entry["nan_before"]["a"] == 1
    assert entry["nan_before"]["b"] == 2
    assert diag.get_nan_log() == [entry]


def test_record_nan_defaults_to_all_columns():
    before = pd.DataFrame({"a": [1.0, np.nan]})
    entry = diag.record_nan("step", before, before)
    assert set(entry["nan_before"]) == {"a"}


def test_record_nan_ignores_unknown_columns():
    before = pd.DataFrame({"a": [1.0, np.nan]})
    entry = diag.record_nan("step", before, before, cols=["a", "does_not_exist"])
    assert set(entry["nan_before"]) == {"a"}


# ── Feature drift ────────────────────────────────────────────────────────────

def test_feature_distribution_report_flags_large_mean_shift():
    idx = pd.date_range("2020-01-06", periods=200, freq="W-MON")
    df = pd.DataFrame({"f1": np.concatenate([np.zeros(150), np.full(50, 100.0)])}, index=idx)
    train_mask = pd.Series(False, index=idx)
    train_mask.iloc[:150] = True
    current_mask = pd.Series(False, index=idx)
    current_mask.iloc[150:] = True

    report = diag.feature_distribution_report(df, ["f1"], train_mask, current_mask, std_flag=3.0)
    row = report.iloc[0]
    assert row["feature"] == "f1"
    assert row["train_mean"] == pytest.approx(0.0)
    assert row["current_mean"] == pytest.approx(100.0)
    assert bool(row["drift_flag"]) is True


def test_feature_distribution_report_does_not_flag_stable_feature():
    idx = pd.date_range("2020-01-06", periods=200, freq="W-MON")
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"f1": rng.normal(0, 1, size=200)}, index=idx)
    train_mask = pd.Series(False, index=idx)
    train_mask.iloc[:150] = True
    current_mask = pd.Series(False, index=idx)
    current_mask.iloc[150:] = True

    report = diag.feature_distribution_report(df, ["f1"], train_mask, current_mask, std_flag=3.0)
    assert bool(report.iloc[0]["drift_flag"]) is False


def test_feature_distribution_report_skips_unknown_columns():
    idx = pd.date_range("2020-01-06", periods=10, freq="W-MON")
    df = pd.DataFrame({"f1": np.arange(10.0)}, index=idx)
    mask = pd.Series(True, index=idx)
    report = diag.feature_distribution_report(df, ["f1", "missing"], mask, mask)
    assert list(report["feature"]) == ["f1"]


# ── Targetbalans ─────────────────────────────────────────────────────────────

def test_target_balance_stats():
    df = pd.DataFrame({
        "target_signal": [1, 0, 1, 1, 0],
        "target_return": [0.1, -0.05, 0.2, 0.15, 0.0],
    })
    stats = diag.target_balance_stats(df)
    assert stats["n"] == 5
    assert stats["positive_share"] == pytest.approx(0.6)
    assert stats["median_forward_return"] == pytest.approx(0.1)


def test_target_balance_stats_empty_df_returns_nan():
    df = pd.DataFrame({"target_signal": [], "target_return": []})
    stats = diag.target_balance_stats(df)
    assert stats["n"] == 0
    assert np.isnan(stats["positive_share"])


# ── Datumsynkronisering ──────────────────────────────────────────────────────

def test_assert_date_alignment_flags_future_published():
    dates = pd.to_datetime(["2024-01-01", "2024-01-08"])   # båda måndagar
    df = pd.DataFrame({"published": pd.to_datetime(["2023-12-30", "2024-01-15"])}, index=dates)
    result = diag.assert_date_alignment(df, date_col="Date")
    assert result["future_published_rows"] == 1
    assert result["non_monday_dates"] == 0


def test_assert_date_alignment_flags_non_monday_dates():
    dates = pd.to_datetime(["2024-01-02", "2024-01-08"])   # tisdag, måndag
    df = pd.DataFrame({"x": [1, 2]}, index=dates)
    result = diag.assert_date_alignment(df, date_col="Date")
    assert result["non_monday_dates"] == 1


def test_assert_date_alignment_clean_data_has_zero_flags():
    dates = pd.to_datetime(["2024-01-01", "2024-01-08"])
    df = pd.DataFrame({"published": pd.to_datetime(["2023-12-01", "2023-12-15"])}, index=dates)
    result = diag.assert_date_alignment(df, date_col="Date")
    assert result == {"n": 2, "non_monday_dates": 0, "future_published_rows": 0}


# ── Eligible-mask-tratt ───────────────────────────────────────────────────────

def test_record_eligible_funnel_and_get():
    diag.record_eligible_funnel("2024-01-01", n_scored=10, n_eligible=6, n_after_gate=4, n_final=3)
    funnel = diag.get_eligible_funnel()
    assert len(funnel) == 1
    assert funnel[0]["date"] == "2024-01-01"
    assert funnel[0]["n_scored"] == 10
    assert funnel[0]["n_final"] == 3


# ── Datumsynk-ackumulator ────────────────────────────────────────────────────

def test_record_and_get_date_alignment_log():
    diag.record_date_alignment("fundamentals_merge_asof", {"n": 10, "non_monday_dates": 0, "future_published_rows": 1})
    log = diag.get_date_alignment_log()
    assert len(log) == 1
    assert log[0]["step"] == "fundamentals_merge_asof"
    assert log[0]["future_published_rows"] == 1


# ── Samlad rapport ────────────────────────────────────────────────────────────

def test_build_and_write_report_writes_json_and_history_csv(tmp_path):
    diag.record_universe_stage("fetch", ["A", "B"])
    diag.record_eligible_funnel("2024-01-01", n_scored=2, n_eligible=2, n_after_gate=1, n_final=1)

    feature_drift = pd.DataFrame([
        {"feature": "f1", "train_mean": 0.0, "train_std": 1.0,
         "current_mean": 5.0, "current_std": 1.0, "drift_flag": True},
    ])
    target_balance = {"n": 100, "positive_share": 0.33, "median_forward_return": 0.02}
    calibration_resolution = {"n": 100, "n_unique": 5, "largest_plateau_frac": 0.8}

    report = diag.build_and_write_report(
        feature_drift=feature_drift,
        target_balance=target_balance,
        calibration_resolution=calibration_resolution,
        out_dir=str(tmp_path),
    )

    assert report["feature_drift_n_flagged"] == 1
    assert (tmp_path / "pipeline_health.json").exists()
    assert (tmp_path / "pipeline_health_history.csv").exists()
    assert (tmp_path / "feature_drift_report.csv").exists()
    assert (tmp_path / "eligible_funnel_history.csv").exists()


def test_build_and_write_report_computes_change_vs_previous(tmp_path):
    diag.record_universe_stage("fetch", ["A", "B", "C"])
    feature_drift = pd.DataFrame(columns=["feature", "drift_flag"])
    target_balance = {"n": 10, "positive_share": 0.5, "median_forward_return": 0.01}
    calibration_resolution = {"n": 10, "n_unique": 3, "largest_plateau_frac": 0.5}

    diag.build_and_write_report(
        feature_drift=feature_drift, target_balance=target_balance,
        calibration_resolution=calibration_resolution, out_dir=str(tmp_path),
    )

    diag.reset_all()
    diag.record_universe_stage("fetch", ["A", "B"])   # krympt universum
    target_balance2 = {"n": 10, "positive_share": 0.4, "median_forward_return": 0.01}
    report2 = diag.build_and_write_report(
        feature_drift=feature_drift, target_balance=target_balance2,
        calibration_resolution=calibration_resolution, out_dir=str(tmp_path),
    )

    assert report2["change_vs_previous"]["universe_n"] == pytest.approx(-1.0)
    assert report2["change_vs_previous"]["positive_share"] == pytest.approx(-0.1)
