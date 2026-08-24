#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "trackj/results/SPARJ_J1B_ATR_ADX_V1"
FREEZE = ROOT / "trackj/FREEZE_MANIFEST_J1B.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    assert not FREEZE.exists(), "no overwrite"
    paths = [
        ROOT / "trackj/J1B_PREREGISTRATION.json",
        ROOT / "trackj/ohlc_v1/manifest.json",
        ROOT / "tools/sparj_j1b_atr_adx.py",
        ROOT / "tools/test_sparj_j1b.py",
    ] + [p for p in sorted(OUT.rglob("*")) if p.is_file()]
    files = [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in paths]
    aggregate = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    payload = {
        "freeze_id": "SPARJ_J1B_ATR_ADX_V1_IMMUTABLE_2026-08-09",
        "status": "IMMUTABLE_FROZEN",
        "classifications": {
            "atr_normalized_risk": "SVAGT STÖD",
            "adx_trend_strength": "SVAGT STÖD",
            "atr_trailing_stop": "SVAGT STÖD",
        },
        "new_challenger": None,
        "H0_H1_H2_modified": False,
        "files": files,
        "aggregate_sha256": aggregate,
    }
    FREEZE.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    (ROOT / "trackj/FREEZE_MANIFEST_J1B.sha256").write_text(f"{sha(FREEZE)}  FREEZE_MANIFEST_J1B.json\n")
    print(json.dumps({"status": "FROZEN", "files": len(files), "manifest_sha256": sha(FREEZE), "aggregate_sha256": aggregate}))


if __name__ == "__main__":
    main()
