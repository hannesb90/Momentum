"""SIZE_EXPOSURE_AND_REGIME_DECOMPOSITION — small-cap-regim eller daligt stock selection?

Forregistrering: research_k/size_exposure_regime/SIZE_EXPOSURE_AND_REGIME_DECOMPOSITION_PREREGISTRATION.json
INGA MODELLER TRANAS. Ingen routing. Ingen ny feature. Ingen cutoff-sokning.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/size_exposure_regime"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "SIZE_EXPOSURE_AND_REGIME_DECOMPOSITION_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats.")
N, POOL, COST, PPY, RF = 20, 30, 0.002, 13.0, 0.0224
ENG = ("H0", "ET", "XGB"); TERC = ("Small", "Mid", "Large")


def stat(x):
    x = np.asarray(x, float); w = np.cumprod(1 + x)
    c = float(w[-1] ** (PPY / len(x)) - 1); v = float(x.std(ddof=1) * math.sqrt(PPY))
    return {"cagr": round(c, 4), "sharpe": round((c - RF) / v, 4) if v else 0.0, "vol": round(v, 4),
            "maxdd": round(float((w / np.maximum.accumulate(w) - 1).min()), 4),
            "mean_panel": round(float(x.mean()), 5), "hit": round(float(np.mean(x > 0)), 4)}


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    _g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
    G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
    ut = {"version": "SIZE_EXPOSURE_REGIME_V1", "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "SIZE_EXPOSURE_AND_REGIME_DECOMPOSITION_PREREGISTRATION.json"),
          "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm = W["rankings"], W["retmap"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text()) for m in ("EXTRATREES", "XGBOOST")}
        dagar = [d for d in sorted(preds["EXTRATREES"]) if d in rk]
        P = []
        for d in dagar:
            u = [r["kod"] for r in rk[d] if (r["kod"], d) in rm]
            h0s = {r["kod"]: r["score"] for r in rk[d]}
            mc = {}
            for k in u:
                r_ = G.nasdaq_rad(k, isin.get(k), d)
                if r_ and r_.get("market_cap"): mc[k] = float(r_["market_cap"])
            ok = [k for k in u if k in mc]
            if len(ok) < 20: continue
            sc = {"H0": {k: h0s[k] for k in ok},
                  "ET": {k: preds["EXTRATREES"].get(d, {}).get(k, np.nan) for k in ok},
                  "XGB": {k: preds["XGBOOST"].get(d, {}).get(k, np.nan) for k in ok}}
            if any(not np.all(np.isfinite(list(v.values()))) for v in sc.values()): continue
            order = sorted(ok, key=lambda k: mc[k]); n = len(order)
            terc = {k: ("Small" if i < n / 3 else "Mid" if i < 2 * n / 3 else "Large") for i, k in enumerate(order)}
            pool = [k for k in [r["kod"] for r in rk[d]][:POOL] if k in mc]
            P.append({"d": d, "names": ok, "mc": mc, "terc": terc, "sc": sc,
                      "ret": {k: rm[(k, d)] for k in u}, "pool": pool,
                      "logmc": {k: math.log1p(mc[k]) for k in ok}})
        res = {"n_paneler": len(P)}

        # ---------- DEL 4/5: size-benchmarks ----------
        bench = {t: np.array([np.mean([p["ret"][k] for k in p["names"] if p["terc"][k] == t]) for p in P]) for t in TERC}
        univ = np.array([np.mean([p["ret"][k] for k in p["names"]]) for p in P])
        SmL = bench["Small"] - bench["Large"]
        res["size_benchmarks"] = {t: stat(bench[t]) for t in TERC}
        res["size_benchmarks"]["Universe"] = stat(univ)
        res["size_spread"] = {"Small_minus_Large_mean_panel": round(float(SmL.mean()), 5),
            "Small_minus_Large_annualiserad_pp": round(100 * (float(np.prod(1 + bench["Small"]) ** (PPY / len(P)) - 1) -
                float(np.prod(1 + bench["Large"]) ** (PPY / len(P)) - 1)), 3),
            "andel_paneler_SmL_positiv": round(float(np.mean(SmL > 0)), 4),
            "Mid_minus_Large_ann_pp": round(100 * (float(np.prod(1 + bench["Mid"]) ** (PPY / len(P)) - 1) -
                float(np.prod(1 + bench["Large"]) ** (PPY / len(P)) - 1)), 3),
            "panelserie_SmL": [round(float(x), 5) for x in SmL]}

        # ---------- portfoljer + DEL 3 exponering ----------
        def valj(p, eng, popn):
            cand = p["names"] if popn == "FULL" else p["pool"]
            return sorted(cand, key=lambda k: (-p["sc"][eng][k], k))[:N]

        def kor(seq_fn):
            prev, nets, turns = [], [], []
            for i, p in enumerate(P):
                if i % 2 == 0 or not prev:
                    cur = seq_fn(p); turn = len(set(cur) - set(prev)) / max(1, N) if prev else 0.0; prev = cur
                else: turn = 0.0
                nets.append(np.mean([p["ret"].get(k, 0.0) for k in prev]) - COST * turn); turns.append(turn)
            return np.asarray(nets), np.asarray(turns)

        res["portfoljer"] = {}; res["exponering"] = {}
        HOLD = {}
        for popn in ("FULL", "POOL"):
            for e in ENG:
                nets, t = kor(lambda p, e=e, popn=popn: valj(p, e, popn))
                res["portfoljer"][f"{popn}_{e}"] = {**stat(nets), "mean_turnover": round(float(t.mean()), 4)}
                # exponering
                mcp, sh = [], defaultdict(list)
                hold = []
                for i, p in enumerate(P):
                    pick = valj(p, e, popn); hold.append(pick)
                    order = sorted(p["names"], key=lambda k: p["mc"][k])
                    pos = {k: j / max(1, len(order) - 1) for j, k in enumerate(order)}
                    mcp.append(np.mean([pos[k] for k in pick]))
                    c = defaultdict(int)
                    for k in pick: c[p["terc"][k]] += 1
                    for tt in TERC: sh[tt].append(c[tt] / len(pick))
                HOLD[f"{popn}_{e}"] = hold
                res["exponering"][f"{popn}_{e}"] = {
                    "median_mcap_mdr": round(float(np.median([p["mc"][k] for i, p in enumerate(P) for k in HOLD[f"{popn}_{e}"][i]])) / 1e9, 3),
                    "mean_mcap_percentil": round(float(np.mean(mcp)), 4),
                    **{f"andel_{tt}": round(float(np.mean(sh[tt])), 4) for tt in TERC}}
        for popn in ("FULL", "POOL"):
            for e in ("ET", "XGB"):
                a = res["exponering"][f"{popn}_{e}"]; b = res["exponering"][f"{popn}_H0"]
                a["tilt_mot_H0_percentil"] = round(a["mean_mcap_percentil"] - b["mean_mcap_percentil"], 4)
                a["tilt_mot_H0_andel_Small_pp"] = round(100 * (a["andel_Small"] - b["andel_Small"]), 2)

        # ---------- DEL 6: within-size selection ----------
        res["within_size"] = {}
        for t in TERC:
            o = {}
            for e in ENG:
                ics, tops = [], []
                for p in P:
                    ks = [k for k in p["names"] if p["terc"][k] == t]
                    if len(ks) < 5: continue
                    ics.append(sp([p["sc"][e][k] for k in ks], [p["ret"][k] for k in ks]))
                    nt = max(3, int(round(0.20 * len(ks))))
                    top = sorted(ks, key=lambda k: -p["sc"][e][k])[:nt]
                    tops.append(np.mean([p["ret"][k] for k in top]) - np.mean([p["ret"][k] for k in ks]))
                o[e] = {"ic": round(float(np.nanmean(ics)), 4), "n_paneler": len(ics),
                        "topp20pct_spread_pp_per_panel": round(100 * float(np.mean(tops)), 3),
                        "hit": round(float(np.mean(np.array(tops) > 0)), 3)}
            for e in ("ET", "XGB"):
                o[f"{e}_minus_H0_ic"] = round(o[e]["ic"] - o["H0"]["ic"], 4)
                o[f"{e}_minus_H0_spread_pp"] = round(o[e]["topp20pct_spread_pp_per_panel"] - o["H0"]["topp20pct_spread_pp_per_panel"], 3)
            res["within_size"][t] = o

        # ---------- DEL 7: size-neutral edge ----------
        res["size_neutral"] = {}
        for e in ENG:
            raw, neu = [], []
            for p in P:
                ks = p["names"]; y = np.array([p["ret"][k] for k in ks]); x = np.array([p["logmc"][k] for k in ks])
                xz = (x - x.mean()) / (x.std() or 1)
                yres = y - np.dot(y, xz) / np.dot(xz, xz) * xz
                raw.append(sp([p["sc"][e][k] for k in ks], y)); neu.append(sp([p["sc"][e][k] for k in ks], yres))
            res["size_neutral"][e] = {"raw_ic": round(float(np.nanmean(raw)), 4), "size_neutral_ic": round(float(np.nanmean(neu)), 4)}
        for e in ("ET", "XGB"):
            res["size_neutral"][f"{e}_minus_H0_raw"] = round(res["size_neutral"][e]["raw_ic"] - res["size_neutral"]["H0"]["raw_ic"], 4)
            res["size_neutral"][f"{e}_minus_H0_neutral"] = round(res["size_neutral"][e]["size_neutral_ic"] - res["size_neutral"]["H0"]["size_neutral_ic"], 4)

        # ---------- DEL 9/10/11: Brinson + kontrafaktiska (FULL-armen) ----------
        res["brinson_FULL"] = {}; res["kontrafaktiska_FULL"] = {}
        bser = {t: bench[t] for t in TERC}
        def decomp(hold):
            A = np.zeros(len(P)); S = np.zeros(len(P)); I = np.zeros(len(P))
            for i, p in enumerate(P):
                pick = hold[i]
                for t in TERC:
                    ks = [k for k in pick if p["terc"][k] == t]
                    wP = len(ks) / len(pick); wU = 1 / 3
                    rU_g = bser[t][i]; rU = univ[i]
                    rP_g = np.mean([p["ret"][k] for k in ks]) if ks else rU_g
                    A[i] += (wP - wU) * (rU_g - rU); S[i] += wU * (rP_g - rU_g); I[i] += (wP - wU) * (rP_g - rU_g)
            return A, S, I
        DEC = {e: decomp(HOLD[f"FULL_{e}"]) for e in ENG}
        for e in ("ET", "XGB"):
            dA = DEC[e][0] - DEC["H0"][0]; dS = DEC[e][1] - DEC["H0"][1]; dI = DEC[e][2] - DEC["H0"][2]
            res["brinson_FULL"][e] = {"allocation_pp_per_ar": round(100 * float(dA.mean()) * PPY, 3),
                "selection_pp_per_ar": round(100 * float(dS.mean()) * PPY, 3),
                "interaction_pp_per_ar": round(100 * float(dI.mean()) * PPY, 3),
                "summa_pp_per_ar": round(100 * float((dA + dS + dI).mean()) * PPY, 3)}
            # KF1: H0:s size-mix, modellens urval inom tercil
            kf1 = []
            for i, p in enumerate(P):
                h = HOLD["FULL_H0"][i]; cnt = defaultdict(int)
                for k in h: cnt[p["terc"][k]] += 1
                pick = []
                for t in TERC:
                    ks = [k for k in p["names"] if p["terc"][k] == t]
                    pick += sorted(ks, key=lambda k: -p["sc"][e][k])[:cnt[t]]
                kf1.append(np.mean([p["ret"][k] for k in pick]) if pick else 0.0)
            # KF2: modellens size-mix, neutralt urval
            kf2 = []
            for i, p in enumerate(P):
                m = HOLD[f"FULL_{e}"][i]; cnt = defaultdict(int)
                for k in m: cnt[p["terc"][k]] += 1
                kf2.append(sum(cnt[t] / len(m) * bser[t][i] for t in TERC))
            act = np.array([np.mean([p["ret"][k] for k in HOLD[f"FULL_{e}"][i]]) for i, p in enumerate(P)])
            h0a = np.array([np.mean([p["ret"][k] for k in HOLD["FULL_H0"][i]]) for i, p in enumerate(P)])
            res["kontrafaktiska_FULL"][e] = {
                "ACTUAL_brutto_pp_per_ar": round(100 * (float(np.prod(1 + act) ** (PPY / len(P)) - 1)), 3),
                "H0_SIZE_MIX_pp_per_ar": round(100 * (float(np.prod(1 + np.array(kf1)) ** (PPY / len(P)) - 1)), 3),
                "SIZE_MIX_ONLY_pp_per_ar": round(100 * (float(np.prod(1 + np.array(kf2)) ** (PPY / len(P)) - 1)), 3),
                "H0_ACTUAL_brutto_pp_per_ar": round(100 * (float(np.prod(1 + h0a) ** (PPY / len(P)) - 1)), 3)}

        # ---------- DEL 14: regimdiagnostik ----------
        res["regim"] = {}
        for popn in ("FULL", "POOL"):
            for e in ("ET", "XGB"):
                a = np.array([np.mean([p["ret"][k] for k in HOLD[f"{popn}_{e}"][i]]) for i, p in enumerate(P)])
                b = np.array([np.mean([p["ret"][k] for k in HOLD[f"{popn}_H0"][i]]) for i, p in enumerate(P)])
                edge = a - b
                sl = float(np.polyfit(SmL, edge, 1)[0])
                res["regim"][f"{popn}_{e}"] = {"lutning_edge_mot_SmL": round(sl, 4),
                    "korr": round(float(np.corrcoef(SmL, edge)[0, 1]), 4),
                    "edge_nar_SmL_positiv_pp": round(100 * float(edge[SmL > 0].mean()), 3),
                    "edge_nar_SmL_negativ_pp": round(100 * float(edge[SmL < 0].mean()), 3),
                    "n_pos": int((SmL > 0).sum()), "n_neg": int((SmL < 0).sum())}
        ut["fonster"][wn] = res
        print(f"{wn} klart: {len(P)} paneler", flush=True)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
