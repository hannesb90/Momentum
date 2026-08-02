"""Hash-chained, fail-closed checkpoints for the Level-2 research sequence."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];STAGES=ROOT/"results/niva2_stages"

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def manifest_hash(data:dict)->str:
    clean={k:v for k,v in data.items() if k!="manifest_sha256"}
    return hashlib.sha256(json.dumps(clean,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def verify_manifest(path:Path)->dict:
    data=json.loads(path.read_text())
    if data.get("manifest_sha256")!=manifest_hash(data):raise RuntimeError(f"Stage manifest mutated: {path}")
    for item in data["artifacts"]:
        p=ROOT/item["path"]
        if not p.exists() or sha(p)!=item["sha256"]:raise RuntimeError(f"Stage artifact mutated/missing: {p}")
    parent=data.get("parent_manifest")
    if parent:
        pp=ROOT/parent;pd=verify_manifest(pp)
        if pd["manifest_sha256"]!=data["parent_manifest_sha256"]:raise RuntimeError("Parent stage hash mismatch")
    return data

def freeze_stage(name:str,artifacts:list[Path],metadata:dict,parent:Path|None=None)->Path:
    STAGES.mkdir(parents=True,exist_ok=True)
    parent_data=verify_manifest(parent) if parent else None
    data={"stage":name,"status":"FROZEN_PASS","frozen_at":datetime.now(timezone.utc).isoformat(),
          "parent_manifest":str(parent.relative_to(ROOT)) if parent else None,
          "parent_manifest_sha256":parent_data["manifest_sha256"] if parent_data else None,
          "artifacts":[{"path":str(p.resolve().relative_to(ROOT)),"sha256":sha(p.resolve()),"bytes":p.stat().st_size} for p in artifacts],
          "metadata":metadata}
    data["manifest_sha256"]=manifest_hash(data);path=STAGES/f"{name}.json"
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    verify_manifest(path);return path
