from argparse import Namespace

import config
import main


def _args():
    return Namespace(
        segment="small",
        tickers=None,
        universe="sweden",
        market_cap=["Small Cap", "Micro Cap"],
        include_ngm=False,
        start="2010-01-01",
        end=None,
        min_turnover=100000.0,
        stale_weeks=8,
        min_history=120,
        no_liquidity_filter=False,
    )


def test_aggregate_feature_cache_key_changes_with_forward_horizon(monkeypatch):
    monkeypatch.setattr(config, "FORWARD_WEEKS", 13)
    key_13 = main._feature_cache_key(_args())

    monkeypatch.setattr(config, "FORWARD_WEEKS", 52)
    key_52 = main._feature_cache_key(_args())

    assert key_13 != key_52


def test_aggregate_feature_cache_key_is_stable_for_same_runtime(monkeypatch):
    monkeypatch.setattr(config, "FORWARD_WEEKS", 52)
    assert main._feature_cache_key(_args()) == main._feature_cache_key(_args())
