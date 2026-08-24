"""Byte-for-byte gates for every active dataset_v1.0 artefact."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
def load(p): return json.loads((V2 / p).read_text(encoding="utf-8"))
def sha(p): return hashlib.sha256((V2 / p).read_bytes()).hexdigest()

def main():
    a, b, bx, c = (load(p) for p in ("validated/manifest_sparA.json", "validated/manifest_sparB.json",
                                     "validated/manifest_sparB_extra.json", "validated/manifest_sparC.json"))
    assert sha("validated/prices/prices_validated.json") == a["dataset_sha256"]
    for key in ("ar", "kvartal", "r12"):
        x=b["tabeller"][key]
        assert sha("validated/fundamentals/" + x["fil"]) == x["file_sha256"]
    for x in bx["artefakter"].values(): assert sha(x["fil"]) == x["sha256"]
    for x in c["paneler"].values(): assert sha(x["fil"]) == x["sha256"]
    for x in c["auxiliary_artifacts"].values(): assert sha(x["fil"]) == x["sha256"]
    assert sha("docs/probes/feature_registry.json") == c["feature_registry"]["sha256"]
    assert c["beroenden"]["spar_A_dataset_sha256"] == a["dataset_sha256"]
    assert c["beroenden"]["spar_B_kombinerad_sha256"] == b["kombinerad_sha256"]
    assert c["beroenden"]["spar_B_extra_dataset_sha256"] == bx["dataset_sha256"]
    from build_external_dependencies_manifest import verify_external_source
    verify_external_source()
    print(json.dumps({"status":"PASS", "active_artifacts_byte_matched": 13,
                      "registry_version": c["feature_registry"]["version"]}, indent=2))
if __name__ == "__main__": main()
