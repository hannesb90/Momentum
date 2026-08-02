import config
from research_gates_common import apply_large, validate_large_contract


def test_apply_large_covers_full_execution_contract():
    apply_large()
    snap=validate_large_contract(["x"])
    assert snap["forward_weeks"]==snap["rebalance_weeks"]==snap["embargo_weeks"]
    assert snap["max_positions"]==config.SEGMENTS["large"]["max_positions"]
