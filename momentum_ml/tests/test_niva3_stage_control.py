import json
from pathlib import Path

import pytest

import niva3_stage_control as sc


def test_niva3_chain_keeps_latest_healthy_on_mutation(tmp_path, monkeypatch):
    root = tmp_path; stages = root / "results/niva3_stages"
    monkeypatch.setattr(sc, "ROOT", root); monkeypatch.setattr(sc, "STAGES", stages)
    monkeypatch.setattr(sc, "LATEST", stages / "latest_healthy.json")
    a = root / "a.txt"; a.write_text("healthy")
    first = sc.freeze_stage("00", [a], {"gate": "baseline"})
    assert sc.verify_latest()["stage"] == "00"
    pointer_before = json.loads(sc.LATEST.read_text())
    a.write_text("infected")
    with pytest.raises(RuntimeError, match="mutated/missing"):
        sc.verify_manifest(first)
    assert json.loads(sc.LATEST.read_text()) == pointer_before


def test_niva3_child_verifies_parent_recursively(tmp_path, monkeypatch):
    root = tmp_path; stages = root / "results/niva3_stages"
    monkeypatch.setattr(sc, "ROOT", root); monkeypatch.setattr(sc, "STAGES", stages)
    monkeypatch.setattr(sc, "LATEST", stages / "latest_healthy.json")
    a = root / "a"; b = root / "b"; a.write_text("a"); b.write_text("b")
    first = sc.freeze_stage("00", [a], {})
    second = sc.freeze_stage("01", [b], {}, parent=first)
    assert sc.verify_manifest(second)["parent_manifest_sha256"] == sc.verify_manifest(first)["manifest_sha256"]
