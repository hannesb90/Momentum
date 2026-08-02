import pandas as pd
import pytest

from omx30_pit import members_on, validate_membership
from build_omx30_pit import fetch_date


def _frame(n=30):
    return pd.DataFrame({
        "ticker": [f"T{i}.ST" for i in range(n)],
        "member_from": pd.to_datetime(["2020-01-01"] * n),
        "member_to": pd.to_datetime([None] * n),
        "source_url": ["https://indexes.nasdaq.com/official"] * n,
    })


def test_membership_is_point_in_time():
    frame = _frame()
    assert len(members_on(frame, pd.Timestamp("2019-12-31"))) == 0
    assert len(members_on(frame, pd.Timestamp("2020-01-01"))) == 30


def test_validator_accepts_official_temporary_29_to_31_but_rejects_incomplete_history():
    assert validate_membership(_frame(), "2020-01-06", "2020-02-03")["weeks"] == 5
    assert validate_membership(_frame(29), "2020-01-06", "2020-02-03")["weeks"] == 5
    assert validate_membership(_frame(31), "2020-01-06", "2020-02-03")["weeks"] == 5
    with pytest.raises(ValueError, match="inte 29–31"):
        validate_membership(_frame(28), "2020-01-06", "2020-02-03")


def test_nasdaq_holiday_falls_back_only_backwards():
    class Response:
        def __init__(self, n): self.n = n
        def raise_for_status(self): return None
        def json(self): return {"aaData": [{"Symbol": str(i)} for i in range(self.n)]}
    class Session:
        def __init__(self): self.dates = []
        def post(self, _url, data, timeout):
            self.dates.append(data["tradeDate"][:10])
            return Response(0 if len(self.dates) == 1 else 30)
    session = Session()
    assert len(fetch_date(session, pd.Timestamp("2020-01-06"))) == 30
    assert session.dates == ["2020-01-06", "2020-01-05"]
