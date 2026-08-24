"""MEM-R — STOCK-SPECIFIC RECOVERY MEMORY (LEVEL 3)

Regel 5 kord: inga nya artefakter sedan G-PATH-1. Gates respekterade: endast
H0-rankning anvands. Ingen fundamenta, inget omsatt varde, ingen volym.

FORREGISTRERAT INNAN KORNING — ingen definition andras efter utfall:

EVENT      pullback = band S vid T-1, icke-S vid T. Eventet intraffar vid T.
           Populationen ar den redan dokumenterade laasta: T+13 < sista panel.
RECOVERY   band == S nagon gang i panel T+1 .. T+13.
PIT-LOSNING for tidigare event j: res(j) = min(forsta recoverypanel, j+13).
           Tidigaste tidpunkt da utfallet faktiskt ar kant. Ett tidigare event
           far anvandas i minnet vid T endast om res(j) < T.
POPULATIONSCELL  band vid eventet (N / W / -). Expanderande PIT.
p_pop(x)   populationens recoveryfrekvens i x:s cell bland events med res < x.pi.
           Detta ar vad populationen hade forutsagt for event x nar det intraffade.
MEM-R      aktiens genomsnittliga AVVIKELSE, ej raa recovery-rate:
             dev_i(T) = mean_j [ ut_j - p_pop(j) ]  over egna events med res(j) < T
SHRINKAGE  momentbaserad empirisk Bayes, PIT. n_i = 0 ger exakt noll.
BINS       teckenbaserade: negativ / ingen historik / positiv. Inga efterhandsbins.
MATERIALITET  kalibreras mot matched-random placebo, INTE mot G-PATH-1:s 12 pp.

Events utan rank (namnet lamnade det rankbara universumet) ingar i populationen
men utesluts ur LPM, dar rank ar obligatorisk kontroll. Antalet redovisas.

Kor: /opt/momentum/venv/bin/python tools/mem_r_recovery_memory.py
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
OUT = V2 / "research_k/mem_r_results.json"
H, SEED, DRAWS, PLACEBO = 13, 20260818, 2000, 1000


def band(r): return "-" if r is None else ("S" if r <= 30 else ("N" if r <= 60 else "W"))


def events(F):
    dts = F["eval_dates"]; P = len(dts)
    rk, sc = {}, {}
    for dt in dts:
        for i, r in enumerate(F["rankings"][dt]):
            rk[(r["kod"], dt)] = i + 1; sc[(r["kod"], dt)] = r["score"]
    ev = []
    for t in sorted({k for k, _ in rk}):
        b = [band(rk.get((t, dt))) for dt in dts]
        for i in range(1, P):
            if b[i - 1] != "S" or b[i] == "S" or i + H >= P:
                continue
            rec = next((j for j in range(i + 1, i + H + 1) if b[j] == "S"), None)
            ev.append({"tic": t, "pi": i, "cell": b[i], "rank": rk.get((t, dts[i])),
                       "ut": 1 if rec is not None else 0,
                       "res": rec if rec is not None else i + H})
    ev.sort(key=lambda e: (e["pi"], e["tic"]))
    return ev, P


def forbered(ev):
    """Precomputar p_pop per event och behorighetsmatrisen (res_j < pi_i)."""
    n = len(ev)
    pi = np.array([e["pi"] for e in ev]); rs = np.array([e["res"] for e in ev])
    ut = np.array([e["ut"] for e in ev], float)
    cell = np.array([e["cell"] for e in ev]); tic = np.array([e["tic"] for e in ev])
    behorig = rs[None, :] < pi[:, None]                      # [i, j]
    ppop = np.full(n, np.nan)
    for i in range(n):
        m = behorig[i] & (cell == cell[i])
        if m.any(): ppop[i] = ut[m].mean()
    for i, e in enumerate(ev): e["p_pop"] = None if np.isnan(ppop[i]) else float(ppop[i])
    return behorig, ppop, ut, cell, tic


def dev_egna(ev, behorig, ppop, ut, tic):
    n = len(ev); dev = np.zeros(n); nh = np.zeros(n, int)
    bidrag = np.where(np.isnan(ppop), 0.0, ut - np.nan_to_num(ppop))
    giltig = ~np.isnan(ppop)
    for i in range(n):
        m = behorig[i] & (tic == tic[i]) & giltig
        k = int(m.sum()); nh[i] = k
        if k: dev[i] = float(bidrag[m].mean())
    return dev, nh


def dev_placebo(behorig, ppop, ut, cell, tic, nh, rng):
    """Matched-random: samma antal tidigare events, ur ANDRA tickers, samma cell."""
    n = len(nh); dev = np.zeros(n)
    bidrag = np.where(np.isnan(ppop), 0.0, ut - np.nan_to_num(ppop))
    giltig = ~np.isnan(ppop)
    for i in range(n):
        if nh[i] == 0: continue
        m = behorig[i] & (tic != tic[i]) & (cell == cell[i]) & giltig
        idx = np.flatnonzero(m)
        if not len(idx): continue
        pick = rng.choice(idx, size=min(nh[i], len(idx)), replace=False)
        dev[i] = float(bidrag[pick].mean())
    return dev


def lpm(ev, memvals, kluster="tic"):
    idx = [i for i, e in enumerate(ev) if e["p_pop"] is not None and e["rank"] is not None]
    if len(idx) < 20: return None
    y = np.array([ev[i]["ut"] for i in idx], float)
    mem = np.array([memvals[i] for i in idx], float)
    if mem.std() < 1e-12: return {"degenererad": True, "n": len(idx)}
    pp = np.array([ev[i]["p_pop"] for i in idx], float)
    rk = np.array([ev[i]["rank"] for i in idx], float)
    cn = np.array([1.0 if ev[i]["cell"] == "N" else 0.0 for i in idx])
    X = np.column_stack([np.ones(len(y)), mem, pp, rk, cn])
    XtX = np.linalg.pinv(X.T @ X); beta = XtX @ (X.T @ y); u = y - X @ beta
    g = np.array([ev[i][kluster] for i in idx]); meat = np.zeros((5, 5))
    for kl in set(g):
        m = g == kl; s = X[m].T @ u[m]; meat += np.outer(s, s)
    V = XtX @ meat @ XtX; se = float(np.sqrt(max(V[1, 1], 0)))
    return {"koeff": round(float(beta[1]), 4), "se": round(se, 4),
            "t": round(float(beta[1] / se), 3) if se > 0 else None,
            "ki": [round(float(beta[1] - 1.96 * se), 4), round(float(beta[1] + 1.96 * se), 4)],
            "n": len(idx), "degenererad": False}


def kor(F, namn, res):
    rng = np.random.default_rng(SEED)
    ev, P = events(F)
    behorig, ppop, ut, cell, tic = forbered(ev)
    dev, nh = dev_egna(ev, behorig, ppop, ut, tic)
    for i, e in enumerate(ev): e["dev"] = float(dev[i]); e["n_hist"] = int(nh[i])

    d = {"n_events": len(ev), "n_tickers": len(set(tic)),
         "recovery_rate": round(float(ut.mean()), 4),
         "cellfordelning": dict(Counter(e["cell"] for e in ev)),
         "events_utan_rank": sum(1 for e in ev if e["rank"] is None)}
    print(f"=== {namn} ===")
    print(f"  A. events {d['n_events']}, tickers {d['n_tickers']}, recovery {d['recovery_rate']:.4f}, "
          f"celler {d['cellfordelning']}, utan rank {d['events_utan_rank']}")

    d["historik"] = {"median": float(np.median(nh)),
                     **{f"andel_{k}": round(float((nh == k).mean()), 4) for k in range(5)},
                     "andel_5plus": round(float((nh >= 5).mean()), 4),
                     "andel_minst1": round(float((nh >= 1).mean()), 4),
                     "andel_minst2": round(float((nh >= 2).mean()), 4),
                     "andel_minst3": round(float((nh >= 3).mean()), 4),
                     "tickers_med_minst1": len({e["tic"] for e in ev if e["n_hist"] >= 1})}
    hh = d["historik"]
    print(f"  C. tidigare losta events: median {hh['median']:.0f} | 0:{hh['andel_0']:.1%} "
          f"1:{hh['andel_1']:.1%} 2:{hh['andel_2']:.1%} 3:{hh['andel_3']:.1%} "
          f"4:{hh['andel_4']:.1%} 5+:{hh['andel_5plus']:.1%} | >=1:{hh['andel_minst1']:.1%} "
          f">=2:{hh['andel_minst2']:.1%} >=3:{hh['andel_minst3']:.1%} | "
          f"tickers med >=1: {hh['tickers_med_minst1']}")

    # ---- heterogenitetsdiagnostik + shrinkage
    spar, mem = [], np.zeros(len(ev))
    for i, e in enumerate(ev):
        m = behorig[i]
        if m.sum() < 20 or nh[i] == 0: continue
        y = ut[m]; pbar = float(y.mean())
        per = defaultdict(list)
        for j in np.flatnonzero(m): per[tic[j]].append(ut[j])
        mm = np.array([np.mean(v) for v in per.values()])
        nn = np.array([len(v) for v in per.values()], float)
        V_obs = float(np.average((mm - pbar) ** 2, weights=nn))
        E_samp = float(np.mean(pbar * (1 - pbar) / nn))
        s2b = max(0.0, V_obs - E_samp)
        k = (pbar * (1 - pbar) / s2b) if s2b > 0 else np.inf
        w = nh[i] / (nh[i] + k) if np.isfinite(k) else 0.0
        mem[i] = w * dev[i]
        spar.append({"s2b": s2b, "s2w": pbar * (1 - pbar), "w": float(w)})
    if spar:
        s2b = np.array([x["s2b"] for x in spar]); ws = np.array([x["w"] for x in spar])
        d["heterogenitet"] = {"n_spar": len(spar),
            "sigma2_mellan_median": round(float(np.median(s2b)), 6),
            "sigma2_mellan_max": round(float(s2b.max()), 6),
            "andel_events_med_noll_mellanvarians": round(float((s2b <= 1e-12).mean()), 4),
            "sigma2_inom_median": round(float(np.median([x["s2w"] for x in spar])), 4),
            "shrinkagevikt_median": round(float(np.median(ws)), 4),
            "shrinkagevikt_max": round(float(ws.max()), 4)}
        h = d["heterogenitet"]
        print(f"  DIAGNOSTIK sigma2_MELLAN median {h['sigma2_mellan_median']:.6f} max "
              f"{h['sigma2_mellan_max']:.6f} — noll i {h['andel_events_med_noll_mellanvarians']:.1%} "
              f"av eventen. sigma2_inom {h['sigma2_inom_median']:.4f}. "
              f"shrinkagevikt median {h['shrinkagevikt_median']:.4f} max {h['shrinkagevikt_max']:.4f}")

    # ---- E/H bins
    bins = {"negativ": [e for e in ev if e["n_hist"] >= 1 and e["dev"] < 0],
            "ingen_historik": [e for e in ev if e["n_hist"] == 0],
            "positiv": [e for e in ev if e["n_hist"] >= 1 and e["dev"] > 0]}
    d["bins"] = {}
    for k, rows in bins.items():
        if not rows: continue
        rr = [e["rank"] for e in rows if e["rank"]]
        d["bins"][k] = {"n": len(rows), "tickers": len({e["tic"] for e in rows}),
                        "recovery": round(float(np.mean([e["ut"] for e in rows])), 4),
                        "median_rank": float(np.median(rr)) if rr else None,
                        "andel_cell_N": round(float(np.mean([e["cell"] == "N" for e in rows])), 4),
                        "median_p_pop": round(float(np.median(
                            [e["p_pop"] for e in rows if e["p_pop"] is not None])), 4)}
        b = d["bins"][k]
        print(f"  E. {k:15s} n {b['n']:>3} tickers {b['tickers']:>3} recovery {b['recovery']:.4f} "
              f"medianrank {b['median_rank']} andel N {b['andel_cell_N']:.2f} "
              f"p_pop {b['median_p_pop']:.3f}")
    if "positiv" in d["bins"] and "negativ" in d["bins"]:
        pp, pn = d["bins"]["positiv"]["recovery"], d["bins"]["negativ"]["recovery"]
        d["ra_diff_pp"] = round((pp - pn) * 100, 2)
        d["risk_ratio"] = round(pp / pn, 4) if pn else None
        d["odds_ratio"] = round((pp / (1 - pp)) / (pn / (1 - pn)), 4) if 0 < pn < 1 and pp < 1 else None
        print(f"  H. RA diff positiv - negativ {d['ra_diff_pp']:+.2f} pp  RR {d['risk_ratio']}  "
              f"OR {d['odds_ratio']}")

    d["lpm_dev_oshrunken"] = lpm(ev, dev)
    d["lpm_mem_shrunken"] = lpm(ev, mem)
    for kk in ("lpm_dev_oshrunken", "lpm_mem_shrunken"):
        q = d[kk]
        print(f"  D. {kk:20s} {q}")

    # ---- F. matched-random placebo pa den oshrunkna devien
    obs = d["lpm_dev_oshrunken"]["koeff"] if not d["lpm_dev_oshrunken"].get("degenererad") else None
    if obs is not None:
        pl = []
        for _ in range(PLACEBO):
            dp = dev_placebo(behorig, ppop, ut, cell, tic, nh, rng)
            r = lpm(ev, dp)
            if r and not r.get("degenererad"): pl.append(r["koeff"])
        pl = np.array(pl)
        d["placebo"] = {"n": len(pl), "median": round(float(np.median(pl)), 4),
                        "p2_5": round(float(np.percentile(pl, 2.5)), 4),
                        "p97_5": round(float(np.percentile(pl, 97.5)), 4),
                        "sd": round(float(pl.std()), 4), "observerad": obs,
                        "andel_minst_lika_extrem": round(float((np.abs(pl) >= abs(obs)).mean()), 4)}
        p = d["placebo"]
        print(f"  F. PLACEBO band [{p['p2_5']:+.4f}, {p['p97_5']:+.4f}] median {p['median']:+.4f} "
              f"sd {p['sd']:.4f} | observerad {p['observerad']:+.4f} | "
              f"andel minst lika extrem {p['andel_minst_lika_extrem']:.3f}")

    # ---- G. beroende
    tk = sorted(set(tic)); bytic = defaultdict(list)
    for e in ev: bytic[e["tic"]].append(e)
    bs = []
    for _ in range(DRAWS):
        pick = rng.choice(len(tk), size=len(tk), replace=True)
        s2 = [x for i in pick for x in bytic[tk[i]]]
        a = [e["ut"] for e in s2 if e["n_hist"] >= 1 and e["dev"] > 0]
        b = [e["ut"] for e in s2 if e["n_hist"] >= 1 and e["dev"] < 0]
        if a and b: bs.append(np.mean(a) - np.mean(b))
    bs = np.array(bs) * 100
    d["bootstrap_ticker_pp"] = {"ki_lo": round(float(np.percentile(bs, 2.5)), 2),
                                "ki_hi": round(float(np.percentile(bs, 97.5)), 2),
                                "andel_positiva": round(float((bs > 0).mean()), 4), "n": len(bs)}
    bas = d.get("ra_diff_pp", 0.0); lo = []
    for t in tk:
        a = [e["ut"] for e in ev if e["tic"] != t and e["n_hist"] >= 1 and e["dev"] > 0]
        b = [e["ut"] for e in ev if e["tic"] != t and e["n_hist"] >= 1 and e["dev"] < 0]
        if a and b: lo.append((t, (np.mean(a) - np.mean(b)) * 100))
    lv = np.array([x[1] for x in lo])
    d["leave_one_ticker_out_pp"] = {"min": round(float(lv.min()), 2),
        "max": round(float(lv.max()), 2),
        "teckenbyte": bool((lv > 0).any() and (lv <= 0).any()),
        "storsta": [{"tic": t, "utan_pp": round(v, 2), "paverkan_pp": round(bas - v, 2)}
                    for t, v in sorted(lo, key=lambda x: abs(x[1] - bas), reverse=True)[:3]]}
    g = d["bootstrap_ticker_pp"]; l = d["leave_one_ticker_out_pp"]
    print(f"  G. bootstrap ticker KI [{g['ki_lo']:+.2f}, {g['ki_hi']:+.2f}] pp, "
          f"andel positiva {g['andel_positiva']:.3f}")
    print(f"     LOO [{l['min']:+.2f}, {l['max']:+.2f}] pp, teckenbyte {l['teckenbyte']}, "
          f"storsta {l['storsta'][:2]}")
    print()
    res["fonster"][namn] = d


res = {"version": "MEM_R_V2", "niva": "LEVEL 3 — stock-specific recovery memory",
       "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
       "recovery_horisont_paneler": H, "fonster": {}}
for namn, F in (("2020_2026", S.F26), ("2014_2019", S.F19)):
    kor(F, namn, res)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("skrivet:", OUT)
