"""REVALIDATION_ADAPTERS — gatade datakallor for legacy-skript.

En adapter ersatter ENBART datakallan. Den ror aldrig signaldefinition, parametrar,
ranking, filter, universumlogik eller resultatlogik. Originalskripten ar byte-identiska.

  prima_storbolag   adv() och index_serie() pekas om fran EODHD-rararkivet till de
                    gatade vyerna. ADV-definitionen — median av close x volume over 20
                    foregaende rader, minst 20 rader, nollor exkluderade — ar ordagrant
                    den samma; endast raderna kommer fran en gatad kalla.

Inputparitet ar verifierad innan adaptern far anvandas:
  2020-2026  1 925 / 1 957 identiska (98,4 %), alla 32 avvikelser forklarade
  2014-2019  1 382 / 1 431 identiska (96,6 %), alla 49 avvikelser forklarade
"""
from __future__ import annotations
import bisect, hashlib, json
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
CANON = V2 / "validated/prices_adjustment_repair_v4/prices_validated_adjustment_repair_v4.json"
H1419 = V2 / "validated/prices_h1419_gated/prices_h1419_gated_with_volume.json"
BENCH = V2 / "validated/benchmark_gated/benchmark_xact_sverige_gated.json"
ADAPTER_VERSION = "REVALIDATION_ADAPTERS_V1"


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def adapter_hashes() -> dict:
    return {"adapter_version": ADAPTER_VERSION,
            "adapter_sha256": sha(__file__),
            "canonical_prices_sha256": sha(CANON),
            "h1419_with_volume_sha256": sha(H1419),
            "benchmark_sha256": sha(BENCH)}


def _load_series() -> dict:
    """kod -> (datum, close*volume) ur BADA gatade fonstren, sammanfogade utan overlapp."""
    out: dict[str, tuple[list, np.ndarray]] = {}
    for path in (H1419, CANON):
        P = json.loads(Path(path).read_text())
        for kod, rows in P.items():
            ds = [r["d"] for r in rows]
            v = np.array([(r.get("close") or 0) * (r.get("v") or 0) for r in rows], dtype=float)
            if kod in out:
                pd, pv = out[kod]
                ny = [i for i, d in enumerate(ds) if d > (pd[-1] if pd else "")]
                out[kod] = (pd + [ds[i] for i in ny], np.concatenate([pv, v[ny]]))
            else:
                out[kod] = (ds, v)
    return out


def patch_prima_storbolag(mod) -> dict:
    """Byt ADV- och indexkalla i en redan importerad prima_storbolag-modul."""
    serier = _load_series()
    bench = json.loads(BENCH.read_text())["XACT-SVERIGE"]
    b_ds = [r["d"] for r in bench]
    b_adj = [r["adj"] for r in bench]

    def adv(k, dt):
        s = serier.get(k)
        if not s or not s[0]:
            return None
        ds, v = s
        i = bisect.bisect_right(ds, dt) - 1
        if i < 20:
            return None
        x = v[i - 20:i]
        x = x[x > 0]
        return float(np.median(x)) if len(x) else None

    def index_serie(dts):
        def px(dt):
            i = bisect.bisect_right(b_ds, dt) - 1
            return b_adj[i] if i >= 0 else None
        return np.array([(px(dts[j + 1]) / px(dts[j]) - 1)
                         if j < len(dts) - 1 and px(dts[j]) else 0.0
                         for j in range(len(dts))])

    mod.adv = adv
    mod.index_serie = index_serie
    return {**adapter_hashes(), "patched": ["adv", "index_serie"],
            "instrument_i_adv_kallan": len(serier),
            "benchmark_rader": len(bench),
            "unchanged": ["signal", "parametrar", "ranking", "filter", "universumlogik",
                          "resultatlogik"]}
