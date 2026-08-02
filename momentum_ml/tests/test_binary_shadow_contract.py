import joblib
from pathlib import Path

def test_frozen_binary_artifact_is_explicitly_nonproduction():
    p=Path("results/challengers/binary_raw_v1.joblib")
    if not p.exists(): return
    x=joblib.load(p)
    assert x["production"] is False
    assert x["tuning_locked"] is True
    assert x["version"]=="binary_raw_v1"
