import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402


def test_segment_horizon_contract_matches_validated_decisions():
    """#124 validerade Large 52v efter LambdaRank; Small 52v kom från #31."""
    large = config.SEGMENTS["large"]
    small = config.SEGMENTS["small"]
    assert (
        large["forward_weeks"],
        large["rebalance_weeks"],
        large["embargo_weeks"],
    ) == (52, 52, 52)
    assert (
        small["forward_weeks"],
        small["rebalance_weeks"],
        small["embargo_weeks"],
    ) == (52, 52, 52)
