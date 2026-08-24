"""WINNER_PATH_PATTERN_DISCOVERY. RETROSPEKTIV, EXPLORATIV. Alla fynd ar HYPOTHESIS_GENERATING."""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/winner_path_discovery"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "WINNER_PATH_DISCOVERY_PLAN.json") != json.loads((UT / "PLAN_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: planen har andrats.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
_f = importlib.util.spec_from_file_location("F", V2 / "tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F); CWMAP = F.CWMAP
NTOP, LEADS = 20, 8
SIG = ["mom4","mom13","mom26","mom52","mom12_1","accel13","h0_score","vol13","vol52",
       "trend_consistency52","sma52_gap","high52_ratio","maxdd52"]

def shape(bana):
    """DETERMINISTISK klassning enligt fryst plan. Ingen anpassad troskel."""
    r8, r4, r0 = bana[0], bana[4], bana[-1]
    if r8 >= 0.85: return "ALREADY_HIGH"
    n_upp = sum(1 for j in range(1, len(bana)) if bana[j] > bana[j-1])
    peak = bana[0]; maxdd = 0.0; peak_fore = bana[0]
    for x in bana:
        if x > peak: peak = x
        maxdd = max(maxdd, peak - x)
    if n_upp >= 6 and maxdd <= 0.15: return "STEADY_CLIMB"
    if maxdd > 0.15 and r0 > peak_fore and r0 > max(bana[:-1]): return "TWO_STEP"
    if r4 < float(np.median(bana)) and r0 >= 0.85: return "LATE_SURGE"
    return "OVRIGT"

def kor(wn):
    W = R.load_window(wn); rk, P = W["rankings"], W["paneler"]
    obs = R.build_obs(W); names = R.NAMES; ix = {n:i for i,n in enumerate(names)}
    pidx = {d:i for i,d in enumerate(P)}
    rp = {}
    for d in P:
        rows = rk.get(d, []); n = len(rows)
        for j,r in enumerate(rows,1): rp[(r["kod"], d)] = 1.0 - (j-1)/max(1,n-1)
    ob = {}
    for o in obs: ob[(o["kod"], o["date"])] = o
    top20 = {d: set([r["kod"] for r in rk[d]][:NTOP]) for d in P}
    ut = []
    for i, d in enumerate(P):
        if i % 2 or i < LEADS or i + 2 >= len(P): continue
        for k in top20[d]:
            o = ob.get((k, d))
            if o is None or o["y"] is None: continue
            bana = [rp.get((k, P[i-j])) for j in range(LEADS, -1, -1)]
            if any(b is None for b in bana): continue
            traj = {}
            ok = True
            for s in SIG:
                v = []
                for j in range(LEADS, -1, -1):
                    oo = ob.get((k, P[i-j]))
                    x = oo["x"][ix[s]] if (oo and s in ix) else None
                    v.append(None if (x is None or not np.isfinite(x)) else float(x))
                if v[-1] is None: ok = False
                traj[s] = v
            if not ok: continue
            nr = G.nasdaq_rad(k, None, d) or {}
            ut.append({"panel": d, "pi": i, "kod": k, "y": o["y"], "ny_entry": k not in top20.get(P[i-2], set()),
                       "rank_bana": [round(b,4) for b in bana], "shape": shape(bana), "traj": traj,
                       "mc": nr.get("market_cap"), "icb": CWMAP.get(nr.get("industry")),
                       "vol13": traj["vol13"][-1]})
    # terciler av y inom panel
    byp = {}
    for r in ut: byp.setdefault(r["pi"], []).append(r)
    for p, S in byp.items():
        S2 = sorted(S, key=lambda r: r["y"])
        for j, r in enumerate(S2): r["utfall"] = ["NEDRE","MITTEN","OVRE"][min(2, 3*j//max(1,len(S2)))]
    # kontroller: samma panel, narmaste h0_score bland icke-innehav
    kontr = []
    for i, d in enumerate(P):
        if i % 2 or i < LEADS or i + 2 >= len(P): continue
        held = top20[d]
        kand = []
        for r in rk[d]:
            k = r["kod"]
            if k in held: continue
            o = ob.get((k, d))
            if o is None or o["y"] is None: continue
            bana = [rp.get((k, P[i-j])) for j in range(LEADS, -1, -1)]
            if any(b is None for b in bana): continue
            kand.append((r["score"], k, o, bana))
        if not kand: continue
        for r in [x for x in ut if x["pi"] == i]:
            sc = ob[(r["kod"], d)]["x"][ix["h0_score"]]
            near = sorted(kand, key=lambda c: abs(c[0]-sc))[:2]
            for _, k2, o2, b2 in near:
                nr = G.nasdaq_rad(k2, None, d) or {}
                tj = {}
                for s in SIG:
                    tj[s] = [ (lambda oo: None if (oo is None or not np.isfinite(oo["x"][ix[s]])) else float(oo["x"][ix[s]]))(ob.get((k2, P[i-j]))) for j in range(LEADS,-1,-1) ]
                kontr.append({"panel": d, "pi": i, "kod": k2, "y": o2["y"], "rank_bana":[round(x,4) for x in b2],
                              "shape": shape(b2), "traj": tj, "mc": nr.get("market_cap"),
                              "icb": CWMAP.get(nr.get("industry")), "vol13": tj["vol13"][-1], "matchad_till": r["kod"]})
    return ut, kontr

def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    meta = {"version":"WINNER_PATH_DISCOVERY_V1",
            "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "plan_sha256": sha(UT / "WINNER_PATH_DISCOVERY_PLAN.json"),
            "standard_sha256":"afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
            "DEL16":"HYPOTHESIS_GENERATING", "fonster":{}}
    for wn in ("W1_2014_2019","W2_2020_2026"):
        ut, kontr = kor(wn)
        with open(UT/f"entries_{wn}.jsonl","w") as f:
            for r in ut: f.write(json.dumps(r,ensure_ascii=False)+"\n")
        with open(UT/f"controls_{wn}.jsonl","w") as f:
            for r in kontr: f.write(json.dumps(r,ensure_ascii=False)+"\n")
        from collections import Counter
        meta["fonster"][wn] = {"n_entries": len(ut), "n_kontroller": len(kontr),
            "n_nya_entries": sum(1 for r in ut if r["ny_entry"]),
            "shape_entries": dict(Counter(r["shape"] for r in ut)),
            "shape_kontroller": dict(Counter(r["shape"] for r in kontr)),
            "utfall": dict(Counter(r["utfall"] for r in ut))}
        print(f"{wn}: {len(ut)} entries, {len(kontr)} kontroller, shapes {meta['fonster'][wn]['shape_entries']}", flush=True)
    (UT/"datalager.json").write_text(json.dumps(meta,ensure_ascii=False,indent=1))
    print("skrivet")

if __name__ == "__main__":
    main()
