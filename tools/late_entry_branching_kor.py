"""LATE_ENTRY_TRAJECTORY_BRANCHING_AUDIT — daglig bunt bakat fran t0. DISCOVERY."""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/late_entry_branching"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "LATE_ENTRY_BRANCHING_PLAN.json") != json.loads((UT / "PLAN_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: planen har andrats.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
_f = importlib.util.spec_from_file_location("F", V2 / "tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F); CWMAP = F.CWMAP
NTOP, NBACK = 20, 252
FEAT = ["mom13","mom26","mom52","mom78","dist_52w_high","dd_from_peak","sma200_dist","vol60","rank_pct"]

def dagliga(ds, v, a0, rankfn):
    """Alla dagliga variabler for d = -NBACK..0. PIT: endast priser t.o.m. dag j."""
    lo = a0 - NBACK
    if lo < 400: return None
    idx = np.arange(lo, a0 + 1)
    out = {"d": (idx - a0).tolist(), "price_norm": (v[idx] / v[a0] * 100.0).tolist()}
    for nm, cal in (("mom13", 91), ("mom26", 182), ("mom52", 364), ("mom78", 546)):
        j = np.searchsorted(ds, ds[idx] - np.timedelta64(cal, "D"), side="right") - 1
        ok = j >= 0
        out[nm] = np.where(ok, v[idx] / np.where(ok, v[j], 1.0) - 1.0, np.nan).tolist()
    hi = np.array([float(np.max(v[max(0, i-251):i+1])) for i in idx])
    out["dist_52w_high"] = (v[idx] / hi - 1.0).tolist()
    out["dd_from_peak"] = out["dist_52w_high"]
    sma = np.array([float(np.mean(v[i-199:i+1])) if i >= 199 else np.nan for i in idx])
    out["sma200_dist"] = (v[idx] / sma - 1.0).tolist()
    rr = np.diff(v) / v[:-1]
    out["vol60"] = [float(np.std(rr[i-60:i]) * math.sqrt(252)) if i >= 61 else np.nan for i in idx]
    out["rank_pct"] = [rankfn(str(np.datetime64(ds[i], "D"))) for i in idx]
    return out

def kor(wn):
    W = R.load_window(wn); rk, P, ser = W["rankings"], W["paneler"], W["serie"]
    obs = R.build_obs(W); ob = {(o["kod"], o["date"]): o for o in obs}
    rp = {}
    for d in P:
        rows = rk.get(d, []); n = len(rows)
        for j, r in enumerate(rows, 1): rp[(r["kod"], d)] = 1.0 - (j-1)/max(1, n-1)
    top20 = {d: set([r["kod"] for r in rk[d]][:NTOP]) for d in P}
    ut = []
    for i, d in enumerate(P):
        if i % 2 or i + 2 >= len(P): continue
        for k in top20[d]:
            o = ob.get((k, d))
            if o is None or o["y"] is None or k not in ser: continue
            ds, v = ser[k]
            a0 = int(np.searchsorted(ds, np.datetime64(d), side="right"))     # T+1
            if a0 >= len(v) or a0 - NBACK < 400: continue
            # DEL 4: piecewise constant ranking fran senaste FAKTISKA panel
            def rankfn(datum, _k=k):
                pd_ = max([p for p in P if p <= datum], default=None)
                return rp.get((_k, pd_)) if pd_ else None
            bana = dagliga(ds, v, a0, rankfn)
            if bana is None: continue
            nr = G.nasdaq_rad(k, None, d) or {}
            ut.append({"panel": d, "pi": i, "kod": k, "y": o["y"], "bana": bana,
                       "mc": nr.get("market_cap"), "icb": CWMAP.get(nr.get("industry")),
                       "vol_t0": bana["vol60"][-1]})
    byp = {}
    for r in ut: byp.setdefault(r["pi"], []).append(r)
    for p, S in byp.items():
        S2 = sorted(S, key=lambda r: r["y"])
        for j, r in enumerate(S2): r["tercil"] = ["NEDRE","MITTEN","OVRE"][min(2, 3*j//max(1,len(S2)))]
    return ut

def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    meta = {"version":"LATE_ENTRY_BRANCHING_V1",
            "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "plan_sha256": sha(UT/"LATE_ENTRY_BRANCHING_PLAN.json"),
            "standard_sha256":"afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
            "DEL4_RANKING":"PIECEWISE CONSTANT fran senaste faktiska panel — ingen daglig rekonstruktion",
            "fonster":{}}
    for wn in ("W1_2014_2019","W2_2020_2026"):
        ut = kor(wn)
        with open(UT/f"bunt_{wn}.jsonl","w") as f:
            for r in ut: f.write(json.dumps(r,ensure_ascii=False)+"\n")
        from collections import Counter
        meta["fonster"][wn] = {"n_entries": len(ut), "n_dagar_per_bana": NBACK+1,
            "terciler": dict(Counter(r["tercil"] for r in ut)),
            "n_paneler": len(set(r["pi"] for r in ut))}
        print(f"{wn}: {len(ut)} entries med full 252-dagarshistorik, {meta['fonster'][wn]['n_paneler']} paneler", flush=True)
    (UT/"datalager.json").write_text(json.dumps(meta,ensure_ascii=False,indent=1))
    print("skrivet")

if __name__ == "__main__":
    main()
