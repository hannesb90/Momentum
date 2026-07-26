import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
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


def _two_week_decomposition_df():
    """Ett enda övergångstillfälle (2020-01-06 -> 2020-01-13) konstruerat så
    att rank 1-4 var för sig visar upp precis en av de fyra möjliga orsakerna:
      rank 1 (A): stabil - samma ticker, samma rank, båda veckorna.
      rank 2 (B): universe_exit - B har INGEN rad alls vecka 2 (avnoterad/
        filtrerad ur universumet, inte bara ur urvalet).
      rank 3 (C): filter_exit - C har en rad vecka 2 men selection_eligible=0.
      rank 4 (D): score_reorder - D finns kvar OCH är eligible vecka 2, men
        har fått en så mycket bättre poäng att det klättrar till rank 2 i
        stället (F tar över rank 4).
    """
    w1 = pd.Timestamp("2020-01-06")
    w2 = pd.Timestamp("2020-01-13")
    rows = [
        # Vecka 1: A=1.0(1) B=0.9(2) C=0.8(3) D=0.7(4) E=0.6(5) F=0.5(6)
        {"Date": w1, "ticker": "A", "prob_raw": 1.0, "prob_up": 1.0, "selection_rank": 1.0, "selection_eligible": 1},
        {"Date": w1, "ticker": "B", "prob_raw": 0.9, "prob_up": 0.9, "selection_rank": 0.9, "selection_eligible": 1},
        {"Date": w1, "ticker": "C", "prob_raw": 0.8, "prob_up": 0.8, "selection_rank": 0.8, "selection_eligible": 1},
        {"Date": w1, "ticker": "D", "prob_raw": 0.7, "prob_up": 0.7, "selection_rank": 0.7, "selection_eligible": 1},
        {"Date": w1, "ticker": "E", "prob_raw": 0.6, "prob_up": 0.6, "selection_rank": 0.6, "selection_eligible": 1},
        {"Date": w1, "ticker": "F", "prob_raw": 0.5, "prob_up": 0.5, "selection_rank": 0.5, "selection_eligible": 1},
        # Vecka 2: A stabil(1.0); B saknas helt; C finns men ej eligible;
        # D:s poäng hoppar upp (score_reorder); E/F fyller ut resten.
        {"Date": w2, "ticker": "A", "prob_raw": 1.0, "prob_up": 1.0, "selection_rank": 1.0, "selection_eligible": 1},
        {"Date": w2, "ticker": "C", "prob_raw": 0.8, "prob_up": 0.8, "selection_rank": 0.8, "selection_eligible": 0},
        {"Date": w2, "ticker": "D", "prob_raw": 0.85, "prob_up": 0.85, "selection_rank": 0.85, "selection_eligible": 1},
        {"Date": w2, "ticker": "E", "prob_raw": 0.75, "prob_up": 0.75, "selection_rank": 0.75, "selection_eligible": 1},
        {"Date": w2, "ticker": "F", "prob_raw": 0.65, "prob_up": 0.65, "selection_rank": 0.65, "selection_eligible": 1},
    ]
    return pd.DataFrame(rows).set_index("Date")


def test_turnover_decomposition_identifies_stable_rank():
    df = _two_week_decomposition_df()
    report = diag.rank_gap_and_turnover_report(
        df, rank_pairs=((1, 2),), max_turnover_rank=4, recent_weeks=2, rebalance_weeks=1)
    assert report["turnover_rank_1"] == pytest.approx(0.0)
    assert report["turnover_rank_1_universe_exit_frac"] == pytest.approx(0.0)
    assert report["turnover_rank_1_filter_exit_frac"] == pytest.approx(0.0)
    assert report["turnover_rank_1_score_reorder_frac"] == pytest.approx(0.0)
    assert report["turnover_rank_1_common_universe_turnover"] == pytest.approx(0.0)


def test_turnover_decomposition_identifies_universe_exit():
    df = _two_week_decomposition_df()
    report = diag.rank_gap_and_turnover_report(
        df, rank_pairs=((1, 2),), max_turnover_rank=4, recent_weeks=2, rebalance_weeks=1)
    assert report["turnover_rank_2"] == pytest.approx(1.0)
    assert report["turnover_rank_2_universe_exit_frac"] == pytest.approx(1.0)
    assert report["turnover_rank_2_filter_exit_frac"] == pytest.approx(0.0)
    assert report["turnover_rank_2_score_reorder_frac"] == pytest.approx(0.0)


def test_turnover_decomposition_identifies_filter_exit():
    df = _two_week_decomposition_df()
    report = diag.rank_gap_and_turnover_report(
        df, rank_pairs=((1, 2),), max_turnover_rank=4, recent_weeks=2, rebalance_weeks=1)
    assert report["turnover_rank_3"] == pytest.approx(1.0)
    assert report["turnover_rank_3_filter_exit_frac"] == pytest.approx(1.0)
    assert report["turnover_rank_3_universe_exit_frac"] == pytest.approx(0.0)
    assert report["turnover_rank_3_score_reorder_frac"] == pytest.approx(0.0)


def test_turnover_decomposition_identifies_score_reorder():
    df = _two_week_decomposition_df()
    report = diag.rank_gap_and_turnover_report(
        df, rank_pairs=((1, 2),), max_turnover_rank=4, recent_weeks=2, rebalance_weeks=1)
    assert report["turnover_rank_4"] == pytest.approx(1.0)
    assert report["turnover_rank_4_score_reorder_frac"] == pytest.approx(1.0)
    assert report["turnover_rank_4_universe_exit_frac"] == pytest.approx(0.0)
    assert report["turnover_rank_4_filter_exit_frac"] == pytest.approx(0.0)


def test_common_universe_turnover_excludes_universe_exit_from_denominator():
    """#1 i uppföljningsfrågan: rankstabilitet bara för aktier kvar i
    universumet - universe_exit-fallet (rank 2) ska INTE räknas alls i det
    här måttet, medan filter_exit (rank 3) och score_reorder (rank 4)
    fortfarande räknas som "byte" eftersom tickern fanns kvar i universumet."""
    df = _two_week_decomposition_df()
    report = diag.rank_gap_and_turnover_report(
        df, rank_pairs=((1, 2),), max_turnover_rank=4, recent_weeks=2, rebalance_weeks=1)
    assert report["turnover_rank_1_common_universe_turnover"] == pytest.approx(0.0)
    assert report["turnover_rank_3_common_universe_turnover"] == pytest.approx(1.0)
    assert report["turnover_rank_4_common_universe_turnover"] == pytest.approx(1.0)


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


# ── Modell-trädhälsa ("varför blir score identiska?" - uppföljning) ──────────

class _FakeBooster:
    def __init__(self, num_trees, best_iteration=None):
        self._num_trees = num_trees
        self.best_iteration = num_trees if best_iteration is None else best_iteration

    def num_trees(self):
        return self._num_trees


class _FakeLGBMModel:
    """Minimal stub som replikerar MomentumLGBM:s kontrakt för
    model_tree_health_report: .cls_models, .split_starts, ._select_model_idx
    (samma searchsorted-logik som den riktiga modellklassen)."""

    def __init__(self, cls_models, split_starts):
        self.cls_models = cls_models
        self.split_starts = split_starts

    def _select_model_idx(self, dates):
        starts = pd.DatetimeIndex(self.split_starts)
        idx = starts.searchsorted(dates, side="right") - 1
        return np.clip(idx, 0, len(self.split_starts) - 1)


def test_model_tree_health_report_marks_active_split():
    starts = pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01"])
    fake = _FakeLGBMModel([_FakeBooster(20), _FakeBooster(15), _FakeBooster(30)], list(starts))
    report = diag.model_tree_health_report(fake, as_of=pd.Timestamp("2020-05-01"))
    assert report["active_split_index"] == 1
    assert report["active_num_trees"] == 15
    assert report["critical"] is False
    assert report["degenerate_split_count"] == 0
    assert [s["active"] for s in report["splits"]] == [False, True, False]


def test_model_tree_health_report_flags_critical_when_active_split_degenerate():
    starts = pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01"])
    fake = _FakeLGBMModel([_FakeBooster(20), _FakeBooster(1), _FakeBooster(30)], list(starts))
    report = diag.model_tree_health_report(fake, as_of=pd.Timestamp("2020-05-01"))
    assert report["critical"] is True
    assert report["active_num_trees"] == 1
    assert report["degenerate_split_count"] == 1


def test_model_tree_health_report_counts_all_degenerate_splits_not_just_active():
    starts = pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01"])
    fake = _FakeLGBMModel([_FakeBooster(1), _FakeBooster(15), _FakeBooster(1)], list(starts))
    report = diag.model_tree_health_report(fake, as_of=pd.Timestamp("2020-05-01"))
    assert report["degenerate_split_count"] == 2
    assert report["critical"] is False   # den AKTIVA splitten (index 1) är frisk


def test_model_tree_health_report_extrapolates_to_last_split_for_future_dates():
    starts = pd.to_datetime(["2020-01-01", "2020-04-01"])
    fake = _FakeLGBMModel([_FakeBooster(10), _FakeBooster(20)], list(starts))
    report = diag.model_tree_health_report(fake, as_of=pd.Timestamp("2026-01-01"))
    assert report["active_split_index"] == 1


def test_model_tree_health_report_empty_model_returns_no_active_split():
    fake = _FakeLGBMModel([], [])
    report = diag.model_tree_health_report(fake, as_of=pd.Timestamp("2020-01-01"))
    assert report["n_splits"] == 0
    assert report["active_split_index"] is None
    assert report["critical"] is False


# ── Reproducerbarhetsmetadata ─────────────────────────────────────────────────

def test_reproducibility_metadata_has_expected_keys_and_is_deterministic():
    m1 = diag.reproducibility_metadata()
    m2 = diag.reproducibility_metadata()
    assert set(m1) == {"code_hash", "random_seed", "lgbm_params", "feature_cols_count", "feature_cols_hash"}
    assert m1 == m2
    assert m1["random_seed"] == config.RANDOM_SEED


def test_build_and_write_report_includes_tree_health_and_reproducibility(tmp_path):
    feature_drift = pd.DataFrame(columns=["feature", "drift_flag"])
    target_balance = {"n": 10, "positive_share": 0.5, "median_forward_return": 0.01}
    calibration_resolution = {"n": 10, "n_unique": 3, "largest_plateau_frac": 0.5}
    tree_health = {
        "critical": True, "active_num_trees": 1, "active_best_iteration": 1,
        "active_split_start": "2023-09-11", "degenerate_split_count": 10,
        "fallback_used": True, "splits": [{"split_index": 0, "num_trees": 1}],
    }
    reproducibility = diag.reproducibility_metadata()

    report = diag.build_and_write_report(
        feature_drift=feature_drift, target_balance=target_balance,
        calibration_resolution=calibration_resolution,
        tree_health=tree_health, reproducibility=reproducibility, out_dir=str(tmp_path),
    )
    assert report["tree_health"]["critical"] is True
    assert report["reproducibility"]["random_seed"] == config.RANDOM_SEED
    hist = pd.read_csv(tmp_path / "pipeline_health_history.csv")
    assert bool(hist.iloc[0]["tree_health_critical"]) is True
    assert hist.iloc[0]["active_num_trees"] == 1
    assert (tmp_path / "model_tree_health.csv").exists()
