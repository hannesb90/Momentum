"""Create and verify the immutable external EODHD RAW snapshot contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "validated/external_dependencies_manifest.json"
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inventory(root: Path) -> list[dict]:
    return [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size,
             "sha256": sha(p)} for p in sorted(root.rglob("*")) if p.is_file()]


def aggregate(files: list[dict]) -> str:
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def inventory_matches(expected: list[dict], actual: list[dict], expected_aggregate: str) -> bool:
    """Pure comparison shared by the production gate and mutation tests."""
    return actual == expected and aggregate(actual) == expected_aggregate


def verify_external_source(manifest_path: Path = OUT) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dep = manifest["active_dependencies"][0]
    root = Path(dep["local_path"])
    actual = inventory(root)
    if not inventory_matches(dep["files"], actual, dep["aggregate_sha256"]):
        raise RuntimeError("EODHD external RAW differs from locked manifest: added, removed, resized or changed file")
    if dep["consumer_access_mode"] != "READ_ONLY":
        raise RuntimeError("EODHD consumer contract is not read-only")


def build() -> None:
    files = inventory(EOD)
    payload = {
        "manifest_version": "2.0.0",
        "active_dependencies": [{
            "classification": "IMMUTABLE EXTERNAL RAW SOURCE",
            "name": "EODHD Stockholm archive snapshot",
            "local_path": str(EOD),
            "consumer": "tools/build_validated_prices.py",
            "imports_external_code_or_config": False,
            "consumer_access_mode": "READ_ONLY",
            "source_filesystem_permissions": "recorded by path/hash inventory; immutability is enforced cryptographically before build, not asserted from Unix ownership",
            "n_source_files": len(files),
            "files": files,
            "aggregate_sha256": aggregate(files),
            "reproducibility_rule": "exact recursive path/size/SHA256 set; changed, added or removed file fails before A build",
        }],
        "legacy_code_or_config_imports": [],
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{OUT}: {len(files)} files, aggregate={aggregate(files)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    verify_external_source() if args.verify else build()
