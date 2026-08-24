"""DRAWDOWN_EXIT_HETEROGENEITY_CLOSURE — eventniva-diagnostik med KORREKT state.

Peak trackas fran KOP over hela innehavsperioden (tva paneler). Kassa varar till nasta
ORDINARIE rebalans. Bada felen i exit_architecture_factorial_kor.py ar rattade har.

INGEN TRADINGREGEL SKAPAS. INGEN PARAMETER OPTIMERAS.
"""
from __future__ import annotations
import bisect, hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/dd_heterogeneity_closure"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "DRAWDOWN_EXIT_HETEROGENEITY_CLOSURE_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
_f = importlib.util.spec_from_file_location("F", V2 / "tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F)
CWMAP = F.CWMAP
NTOP, DD = 20, [-0.10, -0.20, -0.30, -0.40]

# ---- PIT-lonsamhet: senaste report_date <= kopdatum
KPI = defaultdict(list)
for r in json.loads((V2 / "validated/kpi_pit/29_Rorelsemarginal_r12.json").read_text()):
    if r.get("report_date") and r.get("v") is not None:
        KPI[r["kod"]].append((r["report_date"], float(r["v"])))
for k in KPI: KPI[k].sort()
def marginal(kod, dt):
    a = KPI.get(kod)
    if not a: return None
    i = bisect.bisect_right([x[0] for x in a], dt) - 1
    return a[i][1] if i >= 0 else None


def kor(wn):
    W = R.load_window(wn); rk, ser, P = W["rankings"], W["serie"], W["paneler"]
    preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text()) for m in ("EXTRATREES", "XGBOOST")}
    dagar = sorted(preds["EXTRATREES"]); fe = P.index(dagar[0])
    isin = {}
    ORD = F.__dict__ and None
    def s1(d): return [r["kod"] for r in rk[d]]
    def sml(m):
        def f(d):
            p = [r["kod"] for r in rk[d]][:30]; s = preds[m].get(d, {})
            return sorted(p, key=lambda k: (-s.get(k, -1e18), k))
        return f
    ORD = {"S1": s1, "S2": sml("EXTRATREES"), "S3": sml("XGBOOST")}

    ev = []
    for s, of in ORD.items():
        for i, day in enumerate(P):
            if i % 2 or i < fe or i + 2 >= len(P): continue
            held = of(day)[:NTOP]
            d_end = P[i + 2]; d_mid = P[i + 1]
            # tvarsnittsvariabler vid KOP
            kar = {}
            for k in held:
                if k not in ser: continue
                ds, v = ser[k]
                a = int(np.searchsorted(ds, np.datetime64(day), side="right"))
                if a >= len(v) or a < 61 or v[a] <= 0: continue
                rr = np.diff(v[a - 60:a + 1]) / v[a - 60:a]
                vol = float(np.std(rr) * math.sqrt(252))
                nr = G.nasdaq_rad(k, None, day) or {}
                kar[k] = {"vol": vol, "mc": nr.get("market_cap"), "icb": nr.get("industry"),
                          "liq": nr.get("turnover_velocity"), "marg": marginal(k, day), "a": a}
            if len(kar) < 10: continue
            def terc(f):
                vals = sorted((f(x), k) for k, x in kar.items() if f(x) is not None)
                out = {}
                for j, (_, k) in enumerate(vals): out[k] = ["LOW", "MID", "HIGH"][min(2, 3 * j // max(1, len(vals)))]
                return out
            tv = terc(lambda x: x["vol"]); tm = terc(lambda x: float(x["mc"]) if x["mc"] else None)
            tl = terc(lambda x: float(x["liq"]) if x["liq"] else None)
            for k, c in kar.items():
                ds, v = ser[k]; a = c["a"]
                b = int(np.searchsorted(ds, np.datetime64(d_end), side="right")) - 1
                bm = int(np.searchsorted(ds, np.datetime64(d_mid), side="right")) - 1
                if b <= a: continue
                entry = float(v[a]); peak = entry
                traff = {d: None for d in DD}
                for t in range(a, b + 1):
                    px = float(v[t])
                    if px > peak: peak = px
                    d_ = px / peak - 1.0
                    for lv in DD:
                        if traff[lv] is None and d_ <= lv: traff[lv] = (t, peak)
                rad = {"ark": s, "panel": day, "pi": i, "kod": k, "entry": entry,
                       "full_ret": float(v[b] / v[a] - 1.0),
                       "vol": c["vol"], "vol_terc": tv.get(k), "size_terc": tm.get(k),
                       "liq_terc": tl.get(k), "icb": CWMAP.get(c["icb"]),
                       "lonsam": (None if c["marg"] is None else bool(c["marg"] > 0)),
                       "events": {}}
                for lv in DD:
                    if traff[lv] is None: continue
                    t0, pk = traff[lv]
                    te = t0 + 1
                    if te > b: continue
                    px_e = float(v[te])
                    fw = {}
                    for h in (5, 10, 20):
                        j = min(te + h, b)
                        fw[f"fwd{h}"] = float(v[j] / px_e - 1.0) if j > te else 0.0
                    fw["fwd_mid"] = float(v[min(bm, b)] / px_e - 1.0) if bm > te else 0.0
                    fw["fwd_slut"] = float(v[b] / px_e - 1.0)
                    rad["events"][str(lv)] = {**fw, "dag": te - a, "dd_vid_event": float(v[t0] / pk - 1.0),
                        "dd_over_sigma": float((v[t0] / pk - 1.0) / (c["vol"] / math.sqrt(252) * math.sqrt(max(1, t0 - a)))) if c["vol"] > 0 and t0 > a else None,
                        "ater_entry": bool(np.max(v[te:b + 1]) >= entry) if b > te else False,
                        "ater_peak": bool(np.max(v[te:b + 1]) >= pk) if b > te else False,
                        "positiv_slut": bool(v[b] >= px_e)}
                ev.append(rad)
    return ev


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "DD_HETEROGENEITY_CLOSURE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "DRAWDOWN_EXIT_HETEROGENEITY_CLOSURE_PREREGISTRATION.json"),
          "standard_sha256": "afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
          "ingen_tradingregel": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        ev = kor(wn)
        with open(UT / f"holdings_{wn}.jsonl", "w") as f:
            for r in ev: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        ut["fonster"][wn] = {"n_innehav": len(ev),
            "n_events": {str(lv): sum(1 for r in ev if str(lv) in r["events"]) for lv in DD},
            "tackning_lonsamhet": round(sum(1 for r in ev if r["lonsam"] is not None) / max(1, len(ev)), 4),
            "tackning_size": round(sum(1 for r in ev if r["size_terc"]) / max(1, len(ev)), 4),
            "tackning_icb": round(sum(1 for r in ev if r["icb"]) / max(1, len(ev)), 4),
            "tackning_liq": round(sum(1 for r in ev if r["liq_terc"]) / max(1, len(ev)), 4)}
        print(f"{wn}: {len(ev)} innehav, events {ut['fonster'][wn]['n_events']}, "
              f"lonsamhetstackning {ut['fonster'][wn]['tackning_lonsamhet']:.3f}", flush=True)
    (UT / "datalager.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "datalager.json")


if __name__ == "__main__":
    main()
