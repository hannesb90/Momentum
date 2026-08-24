"""PERSISTENT_HIGH_RANK_DELAYED_ENTRY_AUDIT. DIAGNOSTIK."""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2/"tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2/"research_k/delayed_entry_audit"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT/"DELAYED_ENTRY_PLAN.json") != json.loads((UT/"PLAN_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: planen har andrats.")
_g = importlib.util.spec_from_file_location("G", V2/"tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
_f = importlib.util.spec_from_file_location("F", V2/"tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F); CWMAP = F.CWMAP
NTOP, POOL, LOOK = 20, 30, 26

def kor(wn):
    W = R.load_window(wn); rk, P = W["rankings"], W["paneler"]
    obs = R.build_obs(W); ob = {(o["kod"],o["date"]): o for o in obs}
    rank = {}; rpct = {}
    for d in P:
        rows = rk.get(d, []); n = len(rows)
        for j,r in enumerate(rows,1):
            rank[(r["kod"],d)] = j; rpct[(r["kod"],d)] = 1.0-(j-1)/max(1,n-1)
    top20 = {d:set([r["kod"] for r in rk[d]][:NTOP]) for d in P}
    ut = []
    for i,d in enumerate(P):
        if i % 2 or i+2 >= len(P) or i < LOOK: continue
        forra = top20.get(P[i-2], set())
        for k in top20[d]:
            if k in forra: continue                       # endast NYA entries
            o = ob.get((k,d))
            if o is None or o["y"] is None: continue
            hist = []
            for b in range(LOOK, 0, -1):
                pd_ = P[i-b]
                hist.append({"panel": pd_, "b": b, "rank": rank.get((k,pd_)),
                             "rpct": rpct.get((k,pd_)), "eligible": (k,pd_) in rank})
            i20 = [h["b"] for h in hist if h["rank"] and h["rank"] <= NTOP]
            i30 = [h["b"] for h in hist if h["rank"] and h["rank"] <= POOL]
            iel = [h["b"] for h in hist if h["eligible"]]
            n_el = len(iel)
            r = {"panel": d, "pi": i, "kod": k, "y": o["y"],
                 "delay_top20": max(i20) if i20 else 0, "delay_top30": max(i30) if i30 else 0,
                 "n_paneler_top20": len(i20), "n_paneler_top30": len(i30), "n_eligible": n_el,
                 "andel_top30": round(len(i30)/max(1,n_el),4),
                 "median_rpct": round(float(np.median([h["rpct"] for h in hist if h["rpct"] is not None])),4) if any(h["rpct"] for h in hist) else None,
                 "sämsta_rpct": round(float(np.min([h["rpct"] for h in hist if h["rpct"] is not None])),4) if any(h["rpct"] for h in hist) else None,
                 "rank_sd": round(float(np.std([h["rpct"] for h in hist if h["rpct"] is not None],ddof=1)),4) if sum(1 for h in hist if h["rpct"] is not None)>1 else None,
                 "rpct_vid_entry": rpct.get((k,d))}
            # langsta sammanhangande svit i Top-30 (bakat fran entry)
            svit = 0
            for b in range(1, LOOK+1):
                pd_ = P[i-b]; rr = rank.get((k,pd_))
                if rr and rr <= POOL: svit += 1
                else: break
            r["svit_top30"] = svit
            # LATENSKLASSNING enligt fryst plan
            if i20:
                b1 = max(i20); pd_ = P[i-b1]
                # var panelen udda (dvs ingen rebalans)?
                r["latens"] = "CADENCE" if (b1 == 1 and (i-1) % 2 == 1) else "SIGNAL"
                r["latens_paneler"] = b1
            elif n_el < LOOK:
                r["latens"] = "FILTER"; r["latens_paneler"] = 0
            else:
                r["latens"] = "SIGNAL"; r["latens_paneler"] = 0
            nr = G.nasdaq_rad(k, None, d) or {}
            r["mc"] = nr.get("market_cap"); r["icb"] = CWMAP.get(nr.get("industry"))
            x = o["x"]; ix = {n:j for j,n in enumerate(R.NAMES)}
            r["vol13"] = float(x[ix["vol13"]]) if np.isfinite(x[ix["vol13"]]) else None
            r["mom52"] = float(x[ix["mom52"]]) if np.isfinite(x[ix["mom52"]]) else None
            ut.append(r)
    byp = {}
    for r in ut: byp.setdefault(r["pi"],[]).append(r)
    for p,S in byp.items():
        S2 = sorted(S,key=lambda r:r["y"])
        for j,r in enumerate(S2): r["tercil"] = ["NEDRE","MITTEN","OVRE"][min(2,3*j//max(1,len(S2)))]
    return ut

def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    meta = {"version":"DELAYED_ENTRY_V1","run_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "plan_sha256": sha(UT/"DELAYED_ENTRY_PLAN.json"),
            "standard_sha256":"afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a","fonster":{}}
    for wn in ("W1_2014_2019","W2_2020_2026"):
        ut = kor(wn)
        with open(UT/f"entries_{wn}.jsonl","w") as f:
            for r in ut: f.write(json.dumps(r,ensure_ascii=False)+"\n")
        from collections import Counter
        meta["fonster"][wn] = {"n_nya_entries":len(ut),"latens":dict(Counter(r["latens"] for r in ut)),
            "median_delay_top30":float(np.median([r["delay_top30"] for r in ut])),
            "median_delay_top20":float(np.median([r["delay_top20"] for r in ut])),
            "andel_delay_top20_noll":round(float(np.mean([r["delay_top20"]==0 for r in ut])),4)}
        print(f"{wn}: {len(ut)} nya entries | latens {meta['fonster'][wn]['latens']} | "
              f"median delay top30 {meta['fonster'][wn]['median_delay_top30']:.0f} paneler", flush=True)
    (UT/"datalager.json").write_text(json.dumps(meta,ensure_ascii=False,indent=1))
    print("skrivet")

if __name__ == "__main__":
    main()
