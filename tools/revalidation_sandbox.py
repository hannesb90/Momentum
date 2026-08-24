"""REVALIDATION_SANDBOX — sokvagsavlyssning for REVALIDATION-mode.

Installeras i barnprocessen INNAN maalskriptet importeras. Legacy-skript ar
byte-identiska; det ar filaccessen som omdirigeras eller stoppas.

Tre klasser av sokvagar:

  REDIRECTED   den kanoniska legacy-prisvagen pekas om till den gatade vyn.
               Varje omdirigering loggas — ingen tyst substitution.
  FORBIDDEN    aldre/superseded prisversioner, ra-arkiv och legacy-cache.
               HARD FAIL. Ett revalidation-test far aldrig lasa dem.
  ALLOWED      allt ovrigt.

Hookar: builtins.open, io.open, gzip.open, pathlib.Path.open/read_text/read_bytes,
os.open, och pandas read_csv/read_json/read_parquet/read_pickle om pandas finns.
"""
from __future__ import annotations

import builtins
import gzip
import io
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

V2 = pathlib.Path("/home/hannesb/momentum_v2")
LOG: list[dict] = []
_STATE = {"active": False, "redirect": {}, "forbidden": [], "run_id": None, "test_id": None}


class RevalidationAccessError(RuntimeError):
    """Hart fel. Ett revalidation-test forsokte lasa forbjuden data."""


def _norm(p) -> str:
    try:
        return os.path.abspath(os.fspath(p))
    except Exception:
        return str(p)


def _log(kind: str, path: str, target: str | None = None) -> None:
    LOG.append({"ts": datetime.now(timezone.utc).isoformat(), "kind": kind,
                "path": path, "target": target,
                "run_id": _STATE["run_id"], "test_id": _STATE["test_id"]})


def _resolve(path):
    if not _STATE["active"]:
        return path
    ap = _norm(path)
    tgt = _STATE["redirect"].get(ap)
    if tgt:
        _log("REDIRECT", ap, tgt)
        return tgt
    for f in _STATE["forbidden"]:
        if ap == f or ap.startswith(f.rstrip("/") + "/"):
            _log("DENY", ap)
            raise RevalidationAccessError(
                f"HARD FAIL — forbjuden datavag i REVALIDATION-mode.\n"
                f"  run_id  : {_STATE['run_id']}\n  test_id : {_STATE['test_id']}\n"
                f"  sokvag  : {ap}\n"
                f"  Skalet  : aldre eller ogatad prisdata far inte lasas av en revalidation.\n"
                f"  Kor i HISTORICAL_REPRODUCTION-mode om du vill reproducera en gammal korning.")
    return path


_orig = {}


def install(redirect: dict, forbidden: list, run_id: str, test_id: str) -> None:
    """Aktivera avlyssningen. Idempotent."""
    _STATE.update(active=True, run_id=run_id, test_id=test_id,
                  redirect={_norm(k): _norm(v) for k, v in redirect.items()},
                  forbidden=[_norm(f) for f in forbidden])
    if _orig:
        return
    _orig["open"] = builtins.open
    _orig["io_open"] = io.open
    _orig["gzip_open"] = gzip.open
    _orig["p_open"] = pathlib.Path.open
    _orig["p_rt"] = pathlib.Path.read_text
    _orig["p_rb"] = pathlib.Path.read_bytes
    _orig["os_open"] = os.open

    def _open(file, *a, **k):
        return _orig["open"](_resolve(file), *a, **k)

    def _ioopen(file, *a, **k):
        return _orig["io_open"](_resolve(file), *a, **k)

    def _gopen(filename, *a, **k):
        return _orig["gzip_open"](_resolve(filename), *a, **k)

    def _popen(self, *a, **k):
        return _orig["p_open"](pathlib.Path(_resolve(self)), *a, **k)

    def _prt(self, *a, **k):
        return _orig["p_rt"](pathlib.Path(_resolve(self)), *a, **k)

    def _prb(self, *a, **k):
        return _orig["p_rb"](pathlib.Path(_resolve(self)), *a, **k)

    def _osopen(path, *a, **k):
        return _orig["os_open"](_resolve(path), *a, **k)

    builtins.open = _open
    io.open = _ioopen
    gzip.open = _gopen
    pathlib.Path.open = _popen
    pathlib.Path.read_text = _prt
    pathlib.Path.read_bytes = _prb
    os.open = _osopen

    try:
        import pandas as pd
        for name in ("read_csv", "read_json", "read_parquet", "read_pickle", "read_table"):
            if not hasattr(pd, name):
                continue
            fn = getattr(pd, name)
            _orig["pd_" + name] = fn

            def mk(f):
                def w(path_or_buf, *a, **k):
                    if isinstance(path_or_buf, (str, os.PathLike)):
                        path_or_buf = _resolve(path_or_buf)
                    return f(path_or_buf, *a, **k)
                return w
            setattr(pd, name, mk(fn))
    except ImportError:
        pass


def uninstall() -> None:
    _STATE["active"] = False


def dump_log(path: pathlib.Path) -> None:
    _orig.get("p_rt") and None
    path.write_text(json.dumps(LOG, ensure_ascii=False, indent=1))
