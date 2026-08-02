import pandas as pd

from altdata.fundamentals import _date, coverage_rows, metric_rows
from features import feature_engineering as fe


def test_borsdata_dates_are_preserved_in_metric_rows():
    reports = {
        "TEST.ST": {
            2023: {"revenue": 100, "report_date": "2024-02-01"},
            2024: {
                "revenue": 120,
                "report_date": "2025-02-06",
                "report_start_date": "2024-01-01",
                "report_end_date": "2024-12-31",
            },
        }
    }
    rows = metric_rows(reports)
    assert rows[0]["available_date"] == "2025-02-06"
    assert rows[0]["report_end_date"] == "2024-12-31"


def test_date_parser_rejects_bad_values():
    assert _date("2025-02-06T00:00:00") == "2025-02-06"
    assert _date(None) is None
    assert _date("not-a-date") is None


def test_coverage_distinguishes_rows_from_point_in_time_rows():
    rows = [
        {"ticker": "A.ST", "year": 2024, "available_date": "2025-02-01",
         "f_score": 1.0},
        {"ticker": "B.ST", "year": 2024, "available_date": None,
         "f_score": 0.5},
    ]
    coverage = coverage_rows(rows)[0]
    assert coverage["tickers"] == 2
    assert coverage["pit_tickers"] == 1
    assert coverage["pit_coverage"] == 0.5


def test_borsdata_feature_is_never_visible_before_publication(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    pd.DataFrame([{
        "ticker": "TEST.ST",
        "year": 2024,
        "available_date": "2025-02-06",
        "f_score": 0.75,
        "rev_growth": 0.20,
    }]).to_csv(results / "fundamentals.csv", index=False)

    monkeypatch.setattr(fe.config, "RESULTS_DIR", str(results))
    monkeypatch.setattr(fe, "_load_fundamentals_growth",
                        lambda segment, prices=None: pd.DataFrame())
    idx = pd.to_datetime(["2025-02-03", "2025-02-10"])
    features = {"TEST.ST": pd.DataFrame(index=idx)}

    result = fe.attach_fundamentals_features(features)["TEST.ST"]

    assert pd.isna(result.loc["2025-02-03", "f_score"])
    assert result.loc["2025-02-10", "f_score"] == 0.75


def test_legacy_csv_without_publication_date_is_not_guessed(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    pd.DataFrame([{
        "ticker": "TEST.ST", "year": 2024, "f_score": 1.0,
    }]).to_csv(results / "fundamentals.csv", index=False)

    monkeypatch.setattr(fe.config, "RESULTS_DIR", str(results))
    monkeypatch.setattr(fe, "_load_fundamentals_growth",
                        lambda segment, prices=None: pd.DataFrame())
    features = {"TEST.ST": pd.DataFrame(
        index=pd.to_datetime(["2025-12-29"])
    )}

    result = fe.attach_fundamentals_features(features)["TEST.ST"]
    assert pd.isna(result.iloc[0]["f_score"])
