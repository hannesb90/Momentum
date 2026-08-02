from pathlib import Path


def test_phase_script_declares_all_phases_and_forbids_selection():
    source = (Path(__file__).parents[1] / "tune_calendar52_phase_niva3_stage1.py").read_text()
    assert "for phase in range(52)" in source
    assert '"phase_selection_allowed": False' in source
    assert '"multiple_testing_arms": 52' in source
