from pathlib import Path

def test_remediation_has_phase_distributions_and_no_phase_selection():
    s=(Path(__file__).parents[1]/"tune_phase_robust_rotation_niva3_stage2.py").read_text()
    assert '("calendar13",13,range(13))' in s
    assert '("staggered4",4,range(13))' in s
    assert '("staggered13",13,range(4))' in s
    assert '("staggered52",52,range(1))' in s
    assert '"phase_selection_allowed":False' in s
