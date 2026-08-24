"""HOLDING_PERIOD_RETURN_PATH_AUDIT — datalager. DIAGNOSTIK, ingen regel."""
from __future__ import annotations
import bisect, hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/holding_path_audit"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "HOLDING_PERIOD_RETURN_PATH_AUDIT_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
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

hu = lambda x: int(math.floor(x + 0.5))          # half-up, INTE bankers rounding


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
            kar = {}
            for k in held:
                if k not in ser: continue
                ds, v = ser[k]
                a = int(np.searchsorted(ds, np.datetime64(day), side="right"))
                if a >= len(v) or a < 61 or v[a] <= 0: continue
                rr = np.diff(v[a - 60:a + 1]) / v[a - 60:a]
                nr = G.nasdaq_rad(k, None, day) or {}
                kar[k] = {"a": a, "vol": float(np.std(rr) * math.sqrt(252)),
                          "mc": nr.get("market_cap"), "icb": nr.get("industry"),
                          "liq": nr.get("turnover_velocity"), "marg": marginal(k, day)}
            if len(kar) < 10: continue
            def terc(f):
                vals = sorted((f(x), k) for k, x in kar.items() if f(x) is not None)
                return {k: ["LOW", "MID", "HIGH"][min(2, 3 * j // max(1, len(vals)))] for j, (_, k) in enumerate(vals)}
            tv = terc(lambda x: x["vol"]); tm = terc(lambda x: float(x["mc"]) if x["mc"] else None)
            tl = terc(lambda x: float(x["liq"]) if x["liq"] else None)
            # ---- DEL 12: opportunity cost, PIT-ranking vid mellanpanelen
            oppo = None
            if d_mid in rk:
                kand = [k for k in of(d_mid) if k not in held][:NTOP]
                rets = []
                for k in kand:
                    if k not in ser: continue
                    ds, v = ser[k]
                    m0 = int(np.searchsorted(ds, np.datetime64(d_mid), side="right"))
                    e0 = int(np.searchsorted(ds, np.datetime64(d_end), side="right")) - 1
                    if m0 < len(v) and e0 > m0 and v[m0] > 0: rets.append(float(v[e0] / v[m0] - 1.0))
                if rets: oppo = {"n": len(rets), "medel": float(np.mean(rets)), "median": float(np.median(rets))}
            for k, c in kar.items():
                ds, v = ser[k]; a = c["a"]
                b = int(np.searchsorted(ds, np.datetime64(d_end), side="right")) - 1
                m_arch = int(np.searchsorted(ds, np.datetime64(d_mid), side="right"))   # T+1 efter mellanpanel
                if b <= a or m_arch >= b or m_arch <= a: continue
                n = b - a
                q = {p: a + hu(f * n) for p, f in (("q25", .25), ("q50", .50), ("q75", .75))}
                px = lambda j: float(v[min(max(j, a), b)])
                e0, ee = px(a), px(b)
                rad = {"ark": s, "panel": day, "pi": i, "kod": k,
                       "n_handelsdagar": int(n), "entry": e0,
                       "R_q25": px(q["q25"]) / e0 - 1.0, "R_q50": px(q["q50"]) / e0 - 1.0,
                       "R_q75": px(q["q75"]) / e0 - 1.0, "R_slut": ee / e0 - 1.0,
                       "R_mid_arch": px(m_arch) / e0 - 1.0,
                       "R_future": ee / px(m_arch) - 1.0,
                       "inkr": {"a_q25": px(q["q25"]) / e0 - 1.0,
                                "q25_q50": px(q["q50"]) / px(q["q25"]) - 1.0,
                                "q50_q75": px(q["q75"]) / px(q["q50"]) - 1.0,
                                "q75_slut": ee / px(q["q75"]) - 1.0},
                       "vol": c["vol"], "vol_terc": tv.get(k), "size_terc": tm.get(k),
                       "liq_terc": tl.get(k), "icb": CWMAP.get(c["icb"]),
                       "lonsam": (None if c["marg"] is None else bool(c["marg"] > 0)),
                       "oppo": oppo}
                seg = v[m_arch:b + 1]
                rad["MAE_efter_mid"] = float(np.min(seg) / px(m_arch) - 1.0)
                rad["MFE_efter_mid"] = float(np.max(seg) / px(m_arch) - 1.0)
                rad["nar_entry_efter_mid"] = bool(np.max(seg) >= e0)
                rad["slut_positiv"] = bool(ee >= e0)
                ut.append(rad)
    return ut


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    meta = {"version": "HOLDING_PATH_DATALAGER_V1",
            "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "prereg_sha256": sha(UT / "HOLDING_PERIOD_RETURN_PATH_AUDIT_PREREGISTRATION.json"),
            "standard_sha256": "afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
            "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        ev = kor(wn)
        with open(UT / f"path_{wn}.jsonl", "w") as f:
            for r in ev: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        nd = [r["n_handelsdagar"] for r in ev]
        meta["fonster"][wn] = {"n_innehav": len(ev), "median_handelsdagar": int(np.median(nd)),
            "min_dagar": int(np.min(nd)), "max_dagar": int(np.max(nd)),
            "n_no_progress": sum(1 for r in ev if r["R_mid_arch"] <= 0),
            "andel_no_progress": round(sum(1 for r in ev if r["R_mid_arch"] <= 0) / max(1, len(ev)), 4),
            "tackning_lonsamhet": round(sum(1 for r in ev if r["lonsam"] is not None) / max(1, len(ev)), 4)}
        print(f"{wn}: {len(ev)} innehav, median {meta['fonster'][wn]['median_handelsdagar']} handelsdagar, "
              f"no-progress {meta['fonster'][wn]['andel_no_progress']:.3f}, "
              f"KPI-tackning {meta['fonster'][wn]['tackning_lonsamhet']:.3f}", flush=True)
    (UT / "datalager.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "datalager.json")


if __name__ == "__main__":
    main()
