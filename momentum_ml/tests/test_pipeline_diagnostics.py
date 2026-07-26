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


# ── Rank-gap / bytesfrekvens ─────────────────────────────────────────────────

def _make_signals_df(n_weeks=30, n_tickers=25, rotate=False, weekly_drift=0.0):
    """Syntetisk signals_df: DatetimeIndex 'Date', ticker, prob_raw/prob_up/
    selection_rank (satta lika för enkelhetens skull - sorteringsordningen
    bryr sig bara om den relativa storleken) och selection_eligible=1.

    rotate=False: ticker T{k} ligger alltid på rank-position k (0-indexerad)
    varje vecka -> 0% bytesfrekvens, deterministiskt gap mellan valfria
    rankpar.
    rotate=True: rankpositionerna roterar en tickerpositon per vecka -> 100%
    bytesfrekvens vid varje enskild vecko-övergång (skift 1 mod n_tickers är
    aldrig 0).
    weekly_drift: en UNIFORM offset (drift*veckoindex) läggs till ALLA
    tickers score samma vecka - påverkar inte rank-ordningen eller gapet
    mellan rankpar (kancellerar i differensen), men ger EN tickers egen
    score en exakt, känd vecko-till-vecko-förändring (= weekly_drift) att
    mäta brus-referensen mot.
    """
    dates = pd.date_range("2020-01-06", periods=n_weeks, freq="W-MON")
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    base_scores = np.linspace(1.0, 0.0, n_tickers)
    rows = []
    for wi, date in enumerate(dates):
        order = list(np.roll(tickers, wi)) if rotate else tickers
        for rank_pos, ticker in enumerate(order):
            score = float(base_scores[rank_pos] + weekly_drift * wi)
            rows.append({
                "Date": date, "ticker": ticker,
                "prob_raw": score, "prob_up": score, "selection_rank": score,
                "selection_eligible": 1,
            })
    return pd.DataFrame(rows).set_index("Date")


def test_rank_gap_matches_expected_score_difference():
    df = _make_signals_df(n_weeks=5, n_tickers=25)
    report = diag.rank_gap_and_turnover_report(
        df, rank_pairs=((5, 6),), recent_weeks=5)
    base_scores = np.linspace(1.0, 0.0, 25)
    expected = base_scores[4] - base_scores[5]   # rank 5/6 -> index 4/5
    assert report["gap_prob_raw_5_6"] == pytest.approx(expected)


def test_turnover_is_zero_when_ticker_identity_is_stable():
    df = _make_signals_df(n_weeks=10, n_tickers=25, rotate=False)
    report = diag.rank_gap_and_turnover_report(
        df, recent_weeks=10, rebalance_weeks=1, max_turnover_rank=20)
    for n in range(1, 21):
        assert report[f"turnover_rank_{n}"] == pytest.approx(0.0)


def test_turnover_is_full_when_tickers_rotate_every_week():
    df = _make_signals_df(n_weeks=10, n_tickers=25, rotate=True)
    report = diag.rank_gap_and_turnover_report(
        df, recent_weeks=10, rebalance_weeks=1, max_turnover_rank=20)
    for n in range(1, 21):
        assert report[f"turnover_rank_{n}"] == pytest.approx(1.0)


def test_own_score_weekly_noise_and_signal_to_noise_ratio():
    df = _make_signals_df(n_weeks=10, n_tickers=25, rotate=False, weekly_drift=0.001)
    report = diag.rank_gap_and_turnover_report(
        df, rank_pairs=((10, 11),), recent_weeks=10)
    assert report["own_score_weekly_median"] == pytest.approx(0.001)
    base_scores = np.linspace(1.0, 0.0, 25)
    expected_gap = base_scores[9] - base_scores[10]
    assert report["gap_prob_raw_10_11"] == pytest.approx(expected_gap)
    assert report["signal_to_noise_10_11"] == pytest.approx(expected_gap / 0.001)


def test_signal_to_noise_absent_when_no_own_score_movement():
    df = _make_signals_df(n_weeks=5, n_tickers=25, rotate=False, weekly_drift=0.0)
    report = diag.rank_gap_and_turnover_report(df, rank_pairs=((10, 11),), recent_weeks=5)
    assert "signal_to_noise_10_11" not in report


def test_rank_gap_report_empty_df_returns_zero_weeks_checked():
    df = pd.DataFrame(
        columns=["ticker", "prob_raw", "prob_up", "selection_rank", "selection_eligible"])
    df.index = pd.DatetimeIndex([], name="Date")
    report = diag.rank_gap_and_turnover_report(df)
    assert report["n_weeks_checked"] == 0


def test_rank_gap_report_skips_weeks_with_too_few_candidates():
    df = _make_signals_df(n_weeks=3, n_tickers=15)   # < rank 21 needed for default pairs
    report = diag.rank_gap_and_turnover_report(df, recent_weeks=3)
    assert report["n_weeks_checked"] == 0


def test_build_and_write_report_includes_rank_gap_turnover(tmp_path):
    feature_drift = pd.DataFrame(columns=["feature", "drift_flag"])
    target_balance = {"n": 10, "positive_share": 0.5, "median_forward_return": 0.01}
    calibration_resolution = {"n": 10, "n_unique": 3, "largest_plateau_frac": 0.5}
    rank_gap_turnover = {
        "gap_prob_raw_10_11": 0.001, "turnover_rank_10": 0.8,
        "own_score_weekly_std": 0.01, "signal_to_noise_10_11": 0.5,
    }

    report = diag.build_and_write_report(
        feature_drift=feature_drift, target_balance=target_balance,
        calibration_resolution=calibration_resolution,
        rank_gap_turnover=rank_gap_turnover, out_dir=str(tmp_path),
    )
    assert report["rank_gap_turnover"] == rank_gap_turnover
    hist = pd.read_csv(tmp_path / "pipeline_health_history.csv")
    assert hist.iloc[0]["turnover_rank_10"] == pytest.approx(0.8)


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
