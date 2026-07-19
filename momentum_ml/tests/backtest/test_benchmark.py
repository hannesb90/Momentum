import pytest
import math
from backtest.benchmark import pct_to_float

def test_pct_to_float_happy_path():
    assert math.isclose(pct_to_float("10.5%"), 0.105)
    assert math.isclose(pct_to_float("-5.2%"), -0.052)
    assert math.isclose(pct_to_float("0%"), 0.0)
    assert math.isclose(pct_to_float("100%"), 1.0)

def test_pct_to_float_whitespace():
    assert pct_to_float("  15%  ") == 0.15
    assert pct_to_float("\t2.5%\n") == 0.025

def test_pct_to_float_no_percent_sign():
    # It divides by 100 regardless of the presence of '%'
    assert pct_to_float("10") == 0.1
    assert pct_to_float("0.5") == 0.005

def test_pct_to_float_numbers():
    assert pct_to_float(10.5) == 0.105
    assert pct_to_float(5) == 0.05

def test_pct_to_float_invalid_strings():
    assert math.isnan(pct_to_float("invalid"))
    assert math.isnan(pct_to_float("10.5.5%"))
    assert math.isnan(pct_to_float(""))

def test_pct_to_float_none_and_objects():
    assert math.isnan(pct_to_float(None))
    assert math.isnan(pct_to_float({}))
    assert math.isnan(pct_to_float([]))
