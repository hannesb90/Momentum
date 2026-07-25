from pathlib import Path
import joblib

from large13_shadow_refresh import atomic_joblib


def test_atomic_joblib_replaces_snapshot(tmp_path: Path):
    path = tmp_path / "features.pkl"
    atomic_joblib({"version": 1}, path)
    atomic_joblib({"version": 2}, path)
    assert joblib.load(path) == {"version": 2}
