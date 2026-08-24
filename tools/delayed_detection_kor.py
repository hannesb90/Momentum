"""DELAYED_MOMENTUM_DETECTION_AND_OWNERSHIP_AUDIT.
SAME MODEL, DIFFERENT OBSERVATION FREQUENCY. Ingen parameter andras."""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2/"tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2/"research_k/delayed_detection_audit"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT/"DELAYED_DETECTION_PLAN.json") != json.loads((UT/"PLAN_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: planen har andrats.")
_g = importlib.util.spec_from_file_location("G", V2/"tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
NTOP = 20

def bygg_daglig(wn):
    """Rekonstruerar H0 V3:s ranking varje handelsdag med EXAKT samma logik."""
    W = R.load_window(wn); ser, P, rk = W["serie"], W["paneler"], W["rankings"]
    ISIN = R.isin_map(R.WINDOWS[wn]["isin"])
    # gemensam handelskalender
    alla = sorted({d for k in ser for d in ser[k][0]})
    alla = np.array(alla)
    d0 = np.datetime64(P[0]); d1 = np.datetime64(P[-1])
    dagar = [d for d in alla if d0 <= d <= d1]
    # eligibility-cache per (kod, ar-manad) — medlemskapet ar manatligt
    elig_cache = {}
    def elig(k, dt_str, ym):
        key = (k, ym)
        if key not in elig_cache:
            elig_cache[key] = bool(R.PITMEDLEM(k, ISIN.get(k), dt_str)[0])
        return elig_cache[key]
    def handlas(k, d):
        ds, _ = ser[k]
        i = int(np.searchsorted(ds, d, side="right")) - 1
        if i < 0: return None
        return i if int((d - ds[i])/np.timedelta64(1,"D")) <= 30 else None
    def mom(k, d, weeks):
        ds, v = ser[k]; mal = d - np.timedelta64(7*weeks, "D")
        i = int(np.searchsorted(ds, d, side="right")) - 1
        j = int(np.searchsorted(ds, mal, side="right")) - 1
        if i < 0 or j < 0 or int((mal - ds[j])/np.timedelta64(1,"D")) > 10: return None
        return float(v[i]/v[j] - 1.0)
    def ranking(d):
        dt = str(np.datetime64(d, "D")); ym = dt[:7]
        rows = []
        for k in ser:
            if handlas(k, d) is None: continue
            if not elig(k, dt, ym): continue
            rows.append({"kod": k, "m12": mom(k, d, 52), "m18": mom(k, d, 78)})
        for col in ("m12","m18"):
            g = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            grp = defaultdict(list)
            for val,kod in g: grp[val].append(kod)
            ranks, pos = {}, 1
            for val in sorted(grp):
                ks = grp[val]; s = (pos+pos+len(ks)-1)/2/max(1,len(g))
                for kod in ks: ranks[kod] = s
                pos += len(ks)
            for r in rows: r[col+"_rank"] = ranks.get(r["kod"])
        raa = [0.5*(r["m12_rank"]+r["m18_rank"]) if r["m12_rank"] is not None and r["m18_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raa if x is not None])) if any(x is not None for x in raa) else 0.5
        sc = [{**r, "score": med if v is None else v} for r,v in zip(rows,raa)]
        sc.sort(key=lambda x:(x["score"], x["kod"]), reverse=True)
        return sc
    return W, dagar, ranking

def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version":"DELAYED_DETECTION_V1","run_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "plan_sha256": sha(UT/"DELAYED_DETECTION_PLAN.json"),
          "standard_sha256":"afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
          "DEL15_REPRODUKTIONSGRIND":{}, "fonster":{}}
    grind_ok = True
    for wn in ("W1_2014_2019","W2_2020_2026"):
        W, dagar, ranking = bygg_daglig(wn)
        rk, P = W["rankings"], W["paneler"]
        # ---- DEL 15: reproduktionsgrind pa FAKTISKA paneldagar
        n_ok_top20 = n_ok_univ = n_ok_full = 0
        avvik = []
        for d in P:
            dd = np.datetime64(d)
            mine = ranking(dd)
            real = rk.get(d, [])
            u_m = set(r["kod"] for r in mine); u_r = set(r["kod"] for r in real)
            t_m = [r["kod"] for r in mine][:NTOP]; t_r = [r["kod"] for r in real][:NTOP]
            if u_m == u_r: n_ok_univ += 1
            if set(t_m) == set(t_r): n_ok_top20 += 1
            if [r["kod"] for r in mine] == [r["kod"] for r in real]: n_ok_full += 1
            elif len(avvik) < 5:
                avvik.append({"panel": d, "n_univ_mine": len(u_m), "n_univ_real": len(u_r),
                              "univ_diff": sorted(u_m ^ u_r)[:6],
                              "top20_diff": sorted(set(t_m) ^ set(t_r))[:6]})
        g = {"n_paneler": len(P), "reproduktion_universum": round(n_ok_univ/len(P),4),
             "reproduktion_top20": round(n_ok_top20/len(P),4),
             "reproduktion_full_ordning": round(n_ok_full/len(P),4), "avvikelser": avvik}
        g["PASS"] = bool(g["reproduktion_universum"] == 1.0 and g["reproduktion_top20"] == 1.0)
        ut["DEL15_REPRODUKTIONSGRIND"][wn] = g
        grind_ok &= g["PASS"]
        print(f"GRIND {wn}: univ={g['reproduktion_universum']:.4f} top20={g['reproduktion_top20']:.4f} "
              f"full={g['reproduktion_full_ordning']:.4f} {'PASS' if g['PASS'] else 'FAIL'}", flush=True)
        if not g["PASS"]:
            for a in avvik[:3]: print("   avvikelse:", a, flush=True)
            continue
        # ---- daglig ranking for hela spannet
        dag_top = {}; dag_rank = {}
        for d in dagar:
            sc = ranking(d)
            ds = str(np.datetime64(d,"D"))
            dag_top[ds] = [r["kod"] for r in sc][:NTOP]
            dag_rank[ds] = {k: j for j,k in enumerate([r["kod"] for r in sc],1)}
        np.save(UT/f"dagar_{wn}.npy", np.array([str(np.datetime64(d,"D")) for d in dagar]))
        with open(UT/f"daglig_top20_{wn}.json","w") as f: json.dump(dag_top,f)
        with open(UT/f"daglig_rank_{wn}.json","w") as f: json.dump(dag_rank,f)
        ut["fonster"][wn] = {"n_handelsdagar": len(dagar), "forsta": str(np.datetime64(dagar[0],"D")),
                             "sista": str(np.datetime64(dagar[-1],"D"))}
        print(f"  {wn}: {len(dagar)} handelsdagar rekonstruerade", flush=True)
    ut["GRIND_TOTAL"] = "PASS" if grind_ok else "FAIL"
    (UT/"reproduktion.json").write_text(json.dumps(ut,ensure_ascii=False,indent=1))
    print("GRIND_TOTAL:", ut["GRIND_TOTAL"])

if __name__ == "__main__":
    main()
