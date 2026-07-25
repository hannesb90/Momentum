from pathlib import Path

import pandas as pd

import altdata.fi_blankning as fi


def test_attach_features_is_point_in_time_and_computes_8w(monkeypatch):
    dates = pd.date_range("2025-01-06", periods=10, freq="W-MON")
    frame = pd.DataFrame({"ticker": ["AAA.ST"] * 10}, index=dates)
    frame.index.name = "Date"
    events = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-07"), pd.Timestamp("2025-02-04")],
        "issuer": ["Alpha AB", "Alpha AB"],
        "short_pct": [1.0, 2.0],
        "isin": ["SE1", "SE1"],
    })
    monkeypatch.setattr(fi, "load_events", lambda path=None: events)
    monkeypatch.setattr(fi.config, "NAME_MAP", {"AAA.ST": "Alpha AB"})

    result = fi.attach_features(frame, Path("unused"))

    assert pd.isna(result.iloc[0]["short_pct"])
    assert result.iloc[1]["short_pct"] == 1.0
    assert result.iloc[-1]["short_pct"] == 2.0
    assert result.iloc[-1]["short_delta_8w"] == 1.0


def test_unmatched_ticker_is_unknown_not_zero(monkeypatch):
    frame = pd.DataFrame({"ticker": ["NOPE.ST"]},
                         index=pd.DatetimeIndex(["2025-01-06"], name="Date"))
    events = pd.DataFrame({
        "date": [pd.Timestamp("2025-01-01")], "issuer": ["Alpha AB"],
        "short_pct": [1.0], "isin": ["SE1"],
    })
    monkeypatch.setattr(fi, "load_events", lambda path=None: events)
    monkeypatch.setattr(fi.config, "NAME_MAP", {"NOPE.ST": "Other AB"})

    result = fi.attach_features(frame, Path("unused"))

    assert pd.isna(result.iloc[0]["short_pct"])


def test_attach_accepts_second_resolution_feature_dates(monkeypatch):
    dates = pd.date_range("2025-01-06", periods=10, freq="W-MON").values.astype("datetime64[s]")
    frame = pd.DataFrame({"ticker": ["AAA.ST"] * 10},
                         index=pd.DatetimeIndex(dates, name="Date"))
    events = pd.DataFrame({
        "date": pd.Series([pd.Timestamp("2025-01-07")], dtype="datetime64[us]"),
        "issuer": ["Alpha AB"], "short_pct": [1.0], "isin": ["SE1"],
    })
    monkeypatch.setattr(fi, "load_events", lambda path=None: events)
    monkeypatch.setattr(fi.config, "NAME_MAP", {"AAA.ST": "Alpha AB"})

    result = fi.attach_features(frame, Path("unused"))

    assert result["short_pct"].notna().sum() == 9
