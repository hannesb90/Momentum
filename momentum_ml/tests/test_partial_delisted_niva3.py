from tune_partial_delisted_inclusion_niva3_stage8 import _coll_market_cap_evidence


def test_coll_market_cap_clears_conservative_mid_floor():
    evidence = _coll_market_cap_evidence()
    assert evidence["rows"]
    assert evidence["minimum_market_cap_msek"] >= 2000
    assert evidence["robust_mid_or_large"] is True
