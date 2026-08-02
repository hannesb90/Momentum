"""Independent hash chain for Large Level-3 research."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ROOT / "results/niva3_stages"
LATEST = STAGES / "latest_healthy.json"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def manifest_hash(data):
    clean = {k: v for k, v in data.items() if k != "manifest_sha256"}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False).encode()).hexdigest()

def verify_manifest(path):
    path = Path(path); data = json.loads(path.read_text())
    if data.get("manifest_sha256") != manifest_hash(data):
        raise RuntimeError(f"N3 manifest mutated: {path}")
    for item in data["artifacts"]:
        artifact = ROOT / item["path"]
        if not artifact.exists() or sha(artifact) != item["sha256"]:
            raise RuntimeError(f"N3 artifact mutated/missing: {artifact}")
    parent = data.get("parent_manifest")
    if parent:
        pd = verify_manifest(ROOT / parent)
        if pd["manifest_sha256"] != data["parent_manifest_sha256"]:
            raise RuntimeError("N3 parent hash mismatch")
    return data

def freeze_stage(name, artifacts, metadata, parent=None):
    STAGES.mkdir(parents=True, exist_ok=True)
    parent_data = verify_manifest(parent) if parent else None
    data = {"stage": name, "status": "FROZEN_PASS",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "parent_manifest": str(Path(parent).resolve().relative_to(ROOT)) if parent else None,
            "parent_manifest_sha256": parent_data["manifest_sha256"] if parent_data else None,
            "artifacts": [{"path": str(Path(p).resolve().relative_to(ROOT)),
                           "sha256": sha(Path(p).resolve()), "bytes": Path(p).stat().st_size}
                          for p in artifacts], "metadata": metadata}
    data["manifest_sha256"] = manifest_hash(data)
    path = STAGES / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    verified = verify_manifest(path)
    # Mutable recovery pointer, written only AFTER recursive verification. It is
    # deliberately not part of the immutable chain and never advances on error.
    latest = {"stage": name, "manifest": str(path.relative_to(ROOT)),
              "manifest_sha256": verified["manifest_sha256"],
              "verified_at": datetime.now(timezone.utc).isoformat()}
    LATEST.write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path

def verify_latest():
    if not LATEST.exists():
        raise RuntimeError("No healthy N3 checkpoint exists")
    latest = json.loads(LATEST.read_text())
    data = verify_manifest(ROOT / latest["manifest"])
    if data["manifest_sha256"] != latest["manifest_sha256"]:
        raise RuntimeError("N3 latest-healthy pointer/hash mismatch")
    return data
