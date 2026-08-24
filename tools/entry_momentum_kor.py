"""ENTRY_MOMENTUM_SATURATION — datalager. DIAGNOSTIK, ingen regel."""
from __future__ import annotations
import bisect, hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/entry_momentum_saturation"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "ENTRY_MOMENTUM_SATURATION_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
_f = importlib.util.spec_from_file_location("F", V2 / "tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F); CWMAP = F.CWMAP
NTOP = 20

KPI = defaultdict(list)
for r in json.loads((V2 / "validated/kpi_pit/29_Rorelsemarginal_r12.json").read_text()):
    if r.get("report_date") and r.get("v") is not None: KPI[r["kod"]].append((r["report_date"], float(r["v"])))
for k in KPI: KPI[k].sort()
def marginal(kod, dt):
    a = KPI.get(kod)
    if not a: return None
    i = bisect.bisect_right([x[0] for x in a], dt) - 1
    return a[i][1] if i >= 0 else None


def mom(ser, k, dt, weeks):
    """ORDAGRANT h0_v3_kor.momentum()."""
    ds, v = ser[k]; now = np.datetime64(dt); mal = now - np.timedelta64(7 * weeks, "D")
    i = int(np.searchsorted(ds, now, side="right")) - 1
    j = int(np.searchsorted(ds, mal, side="right")) - 1
    if i < 0 or j < 0 or int((mal - ds[j]) / np.timedelta64(1, "D")) > 10: return None
    return float(v[i] / v[j] - 1.0)


def kor(wn):
    W = R.load_window(wn); rk, ser, P = W["rankings"], W["serie"], W["paneler"]
    preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text()) for m in ("EXTRATREES", "XGBOOST")}
    dagar = sorted(preds["EXTRATREES"]); fe = P.index(dagar[0])
    def s1(d): return [r["kod"] for r in rk[d]]
    def sml(m):
        def f(d):
            p = [r["kod"] for r in rk[d]][:30]; s = preds[m].get(d, {})
            return sorted(p, key=lambda k: (-s.get(k, -1e18), k))
        return f
    ORD = {"S1": s1, "S2": sml("EXTRATREES"), "S3": sml("XGBOOST")}
    ut = []
    for s, of in ORD.items():
        for i, day in enumerate(P):
            if i % 2 or i < fe or i + 2 >= len(P): continue
            held = of(day)[:NTOP]; d_mid, d_end = P[i + 1], P[i + 2]
            # ---- sektorrelativ percentil kraver HELA panelens tvarsnitt
            univ = [r["kod"] for r in rk[day]]
            sekt = defaultdict(list)
            m12u = {}
            for k in univ:
                if k not in ser: continue
                m = mom(ser, k, day, 52)
                if m is None: continue
                m12u[k] = m
                nr = G.nasdaq_rad(k, None, day) or {}
                g = CWMAP.get(nr.get("industry"))
                if g: sekt[g].append((m, k))
            spct = {}
            for g, lst in sekt.items():
                if len(lst) < 5: continue
                lst.sort()
                for j2, (_, k) in enumerate(lst): spct[k] = j2 / max(1, len(lst) - 1)
            kar = {}
            for k in held:
                if k not in ser or k not in m12u: continue
                ds, v = ser[k]
                a = int(np.searchsorted(ds, np.datetime64(day), side="right"))
                if a >= len(v) or a < 61 or v[a] <= 0: continue
                rr = np.diff(v[a - 60:a + 1]) / v[a - 60:a]
                vol = float(np.std(rr) * math.sqrt(252))
                nr = G.nasdaq_rad(k, None, day) or {}
                kar[k] = {"a": a, "vol": vol, "mc": nr.get("market_cap"), "icb": CWMAP.get(nr.get("industry")),
                          "liq": nr.get("turnover_velocity"), "marg": marginal(k, day),
                          "m12": m12u[k], "m18": mom(ser, k, day, 78), "spct": spct.get(k)}
            if len(kar) < 10: continue
            def terc(f):
                vals = sorted((f(x), k) for k, x in kar.items() if f(x) is not None)
                return {k: ["LOW", "MID", "HIGH"][min(2, 3 * j // max(1, len(vals)))] for j, (_, k) in enumerate(vals)}
            tv = terc(lambda x: x["vol"]); tm = terc(lambda x: float(x["mc"]) if x["mc"] else None)
            tl = terc(lambda x: float(x["liq"]) if x["liq"] else None)
            for k, c in kar.items():
                ds, v = ser[k]; a = c["a"]
                b = int(np.searchsorted(ds, np.datetime64(d_end), side="right")) - 1
                m_a = int(np.searchsorted(ds, np.datetime64(d_mid), side="right"))
                if b <= a: continue
                ut.append({"ark": s, "panel": day, "pi": i, "kod": k,
                    "m12": c["m12"], "m18": c["m18"],
                    "m12_vol": c["m12"] / (c["vol"] * 1.0) if c["vol"] > 0 else None,
                    "m18_vol": (c["m18"] / (c["vol"] * math.sqrt(1.5))) if (c["m18"] is not None and c["vol"] > 0) else None,
                    "m12_sektorpct": c["spct"],
                    "R_slut": float(v[b] / v[a] - 1.0),
                    "R_mid": float(v[min(m_a, b)] / v[a] - 1.0) if m_a > a else None,
                    "vol": c["vol"], "vol_terc": tv.get(k), "size_terc": tm.get(k), "liq_terc": tl.get(k),
                    "icb": c["icb"], "lonsam": (None if c["marg"] is None else bool(c["marg"] > 0))})
    return ut


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    meta = {"version": "ENTRY_MOMENTUM_DATALAGER_V1",
            "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "prereg_sha256": sha(UT / "ENTRY_MOMENTUM_SATURATION_PREREGISTRATION.json"),
            "standard_sha256": "afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
            "momentum_definition": "ORDAGRANT h0_v3_kor.momentum(): 52v och 78v, ingen skip, 10 dagars startolerans",
            "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        ev = kor(wn)
        with open(UT / f"entry_{wn}.jsonl", "w") as f:
            for r in ev: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        m = [r["m12"] for r in ev]
        meta["fonster"][wn] = {"n": len(ev),
            "m12_median": round(float(np.median(m)), 4), "m12_p90": round(float(np.percentile(m, 90)), 4),
            "tackning_sektorpct": round(sum(1 for r in ev if r["m12_sektorpct"] is not None) / max(1, len(ev)), 4),
            "tackning_m18": round(sum(1 for r in ev if r["m18"] is not None) / max(1, len(ev)), 4),
            "tackning_lonsamhet": round(sum(1 for r in ev if r["lonsam"] is not None) / max(1, len(ev)), 4)}
        print(f"{wn}: {len(ev)} innehav, m12 median {meta['fonster'][wn]['m12_median']:+.3f} "
              f"p90 {meta['fonster'][wn]['m12_p90']:+.3f}, sektorpct-tackning {meta['fonster'][wn]['tackning_sektorpct']:.3f}", flush=True)
    (UT / "datalager.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "datalager.json")


if __name__ == "__main__":
    main()
