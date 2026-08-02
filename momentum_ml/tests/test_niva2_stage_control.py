from pathlib import Path
import tempfile
from niva2_stage_control import freeze_stage,verify_manifest

def test_stage_hash_chain_detects_clean_artifacts():
    with tempfile.NamedTemporaryFile(dir="results",delete=False) as f:
        f.write(b"stage-test");p=Path(f.name)
    try:
        m=freeze_stage("zz_test_stage",[p],{"test":True})
        assert verify_manifest(m)["status"]=="FROZEN_PASS"
    finally:
        p.unlink(missing_ok=True);m.unlink(missing_ok=True)
