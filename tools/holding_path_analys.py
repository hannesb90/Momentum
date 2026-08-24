"""HOLDING_PATH — OVERALL forst enligt fryst standard, darefter subgrupper."""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
from scipy import stats
UT = Path("/home/hannesb/momentum_v2/research_k/holding_path_audit")
MIN = 30

def load(wn): return [json.loads(l) for l in open(UT / f"path_{wn}.jsonl")]

def klust(y, pid):
    y = np.asarray(y, float); pid = np.asarray(pid)
    n = len(y); m = float(y.mean()); G = len(np.unique(pid))
    if G < 2 or n == 0: return m, float("nan"), float("nan"), n, G
    s = np.array([(y[pid == p] - m).sum() for p in np.unique(pid)])
    se = math.sqrt(max((G / (G - 1)) * (s ** 2).sum() / n ** 2, 0))
    return m, se, (m / se if se > 0 else float("nan")), n, G

def diff(ya, pa, yb, pb):
    ma, sa, _, na, _ = klust(ya, pa); mb, sb, _, nb, _ = klust(yb, pb)
    d = ma - mb; se = math.sqrt(sa ** 2 + sb ** 2)
    t = d / se if se > 0 else float("nan")
    p = float(2 * (1 - stats.norm.cdf(abs(t)))) if np.isfinite(t) else None
    return {"A_medel_pct": round(100 * ma, 3), "B_medel_pct": round(100 * mb, 3),
            "diff_pct": round(100 * d, 3), "se_pct": round(100 * se, 3),
            "t": round(float(t), 3) if np.isfinite(t) else None, "p": round(p, 5) if p else None,
            "ki95_pct": [round(100 * (d - 1.96 * se), 3), round(100 * (d + 1.96 * se), 3)],
            "MDE80_pct": round(100 * 2.80 * se, 3), "nA": na, "nB": nb}

def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: (ps[i] is None, ps[i])); out = [None] * len(ps); run = 0.0
    for r, i in enumerate(idx):
        if ps[i] is None: continue
        adj = min(1.0, (len(ps) - r) * ps[i]); run = max(run, adj); out[i] = round(run, 5)
    return out

res = {"version": "HOLDING_PATH_ANALYS_V1",
       "prereg_sha256": hashlib.sha256((UT / "HOLDING_PERIOD_RETURN_PATH_AUDIT_PREREGISTRATION.json").read_bytes()).hexdigest(),
       "standard_sha256": "afe0128b160c4e50a018a3642c3bb5ca10c18cc674216e834cd1dce355a06e8a",
       "PRIMARY": {}, "NO_PROGRESS": {}, "KONTINUERLIG": {}, "RECOVERY": {},
       "SECONDARY_HETEROGENEITY": {}, "MULTIPLICITET": {}, "OPPORTUNITY_COST": {}}

for wn in ("W1_2014_2019", "W2_2020_2026"):
    ev = load(wn); pid = [r["pi"] for r in ev]
    # ---- DEL 1+3 kumulativ path
    blk = {"n_innehav": len(ev), "n_paneler": len(set(pid))}
    slut_m = float(np.mean([r["R_slut"] for r in ev]))
    for cp in ("R_q25", "R_q50", "R_q75", "R_slut", "R_mid_arch"):
        y = [r[cp] for r in ev]; m, se, t, n, G = klust(y, pid)
        blk[cp] = {"medel_pct": round(100 * m, 3), "median_pct": round(100 * float(np.median(y)), 3),
                   "se_pct": round(100 * se, 3), "andel_pos": round(float(np.mean(np.array(y) > 0)), 4),
                   "andel_neg": round(float(np.mean(np.array(y) < 0)), 4),
                   "andel_kring_noll": round(float(np.mean(np.abs(np.array(y)) <= 0.01)), 4),
                   "p10": round(100 * float(np.percentile(y, 10)), 2), "p25": round(100 * float(np.percentile(y, 25)), 2),
                   "p75": round(100 * float(np.percentile(y, 75)), 2), "p90": round(100 * float(np.percentile(y, 90)), 2),
                   "andel_av_slutlig_edge": round(m / slut_m, 4) if slut_m != 0 else None}
    # ---- DEL 4 inkrementellt
    blk["INKREMENTELL"] = {}
    for seg in ("a_q25", "q25_q50", "q50_q75", "q75_slut"):
        y = [r["inkr"][seg] for r in ev]; m, se, t, n, G = klust(y, pid)
        blk["INKREMENTELL"][seg] = {"medel_pct": round(100 * m, 3), "se_pct": round(100 * se, 3),
            "t": round(float(t), 3) if np.isfinite(t) else None,
            "andel_pos": round(float(np.mean(np.array(y) > 0)), 4),
            "bidrag_till_edge": round(m / slut_m, 4) if slut_m != 0 else None}
    res["PRIMARY"][wn] = blk

    # ---- DEL 5 no-progress
    A = [r for r in ev if r["R_mid_arch"] <= 0]; B = [r for r in ev if r["R_mid_arch"] > 0]
    res["NO_PROGRESS"][wn] = {"n_A_no_progress": len(A), "n_B_progress": len(B),
        "R_future": diff([r["R_future"] for r in A], [r["pi"] for r in A],
                         [r["R_future"] for r in B], [r["pi"] for r in B]),
        "R_slut_total": diff([r["R_slut"] for r in A], [r["pi"] for r in A],
                             [r["R_slut"] for r in B], [r["pi"] for r in B]),
        "median_future_A_pct": round(100 * float(np.median([r["R_future"] for r in A])), 3),
        "median_future_B_pct": round(100 * float(np.median([r["R_future"] for r in B])), 3),
        "winrate_future_A": round(float(np.mean([r["R_future"] > 0 for r in A])), 4),
        "winrate_future_B": round(float(np.mean([r["R_future"] > 0 for r in B])), 4)}

    # ---- DEL 7 recovery
    res["RECOVERY"][wn] = {}
    for nm, S in (("NO_PROGRESS", A), ("PROGRESS", B)):
        res["RECOVERY"][wn][nm] = {"n": len(S),
            "P_nar_entry_efter_mid": round(float(np.mean([r["nar_entry_efter_mid"] for r in S])), 4),
            "P_slut_positiv": round(float(np.mean([r["slut_positiv"] for r in S])), 4),
            "medel_R_future_pct": round(100 * float(np.mean([r["R_future"] for r in S])), 3),
            "medel_MAE_pct": round(100 * float(np.mean([r["MAE_efter_mid"] for r in S])), 3),
            "medel_MFE_pct": round(100 * float(np.mean([r["MFE_efter_mid"] for r in S])), 3)}

    # ---- DEL 6 kontinuerlig
    x = np.array([r["R_mid_arch"] for r in ev]); y = np.array([r["R_future"] for r in ev])
    rho, prho = stats.spearmanr(x, y)
    xm = x - x.mean(); b1 = float((xm * y).sum() / (xm ** 2).sum())
    resid = y - (y.mean() + b1 * xm); P = np.array(pid)
    meat = sum((xm[P == p] * resid[P == p]).sum() ** 2 for p in np.unique(P))
    seb = math.sqrt(meat) / (xm ** 2).sum()
    terc = {}
    for g in ("LOW", "MID", "HIGH"):
        pass
    ordn = np.argsort(x); lab = np.empty(len(x), dtype=object)
    for j, ix in enumerate(ordn): lab[ix] = ["T1_lagst", "T2", "T3_hogst"][min(2, 3 * j // len(x))]
    for g in ("T1_lagst", "T2", "T3_hogst"):
        S = [i for i in range(len(ev)) if lab[i] == g]
        m, se, t, n, G = klust(y[S], np.array(pid)[S])
        terc[g] = {"n": n, "medel_R_mid_pct": round(100 * float(x[S].mean()), 2),
                   "medel_R_future_pct": round(100 * m, 3), "se_pct": round(100 * se, 3)}
    res["KONTINUERLIG"][wn] = {"spearman_rho": round(float(rho), 4), "spearman_p": round(float(prho), 6),
        "lutning_b1": round(b1, 4), "se_klustrad": round(seb, 4),
        "t": round(b1 / seb, 3) if seb > 0 else None,
        "p": round(float(2 * (1 - stats.norm.cdf(abs(b1 / seb)))), 5) if seb > 0 else None,
        "terciler": terc}

    # ---- DEL 12 opportunity cost
    oc = [r["oppo"] for r in ev if r["oppo"]]
    if oc:
        res["OPPORTUNITY_COST"][wn] = {
            "kandidatavkastning_mid_till_slut_medel_pct": round(100 * float(np.mean([o["medel"] for o in oc])), 3),
            "no_progress_R_future_medel_pct": res["RECOVERY"][wn]["NO_PROGRESS"]["medel_R_future_pct"],
            "progress_R_future_medel_pct": res["RECOVERY"][wn]["PROGRESS"]["medel_R_future_pct"],
            "STATUS": "DIAGNOSTIK ENDAST — inte ett replacement-backtest"}

    # ---- DEL 8+9 heterogenitet
    dims = {"volatility": lambda r: r["vol_terc"], "size": lambda r: r["size_terc"],
            "sector": lambda r: r["icb"],
            "profitability": lambda r: (None if r["lonsam"] is None else ("LONSAM" if r["lonsam"] else "OLONSAM")),
            "liquidity": lambda r: r["liq_terc"]}
    res["SECONDARY_HETEROGENEITY"][wn] = {}; res["MULTIPLICITET"][wn] = {}
    for dim, fn in dims.items():
        out = {}; ps = []; nyck = []
        for g in sorted(set(fn(r) for r in ev if fn(r) is not None)):
            Ag = [r for r in A if fn(r) == g]; Bg = [r for r in B if fn(r) == g]
            if len(Ag) < MIN or len(Bg) < MIN:
                out[g] = {"nA": len(Ag), "nB": len(Bg), "status": "NOT_IDENTIFIABLE"}; continue
            d = diff([r["R_future"] for r in Ag], [r["pi"] for r in Ag],
                     [r["R_future"] for r in Bg], [r["pi"] for r in Bg])
            out[g] = {**d, "status": "OK"}; ps.append(d["p"]); nyck.append(g)
        for g, pa in zip(nyck, holm(ps)): out[g]["holm_p"] = pa
        res["SECONDARY_HETEROGENEITY"][wn][dim] = out
        res["MULTIPLICITET"][wn][dim] = {"n_tester": len(ps), "raa_p": ps, "holm_p": holm(ps)}

(UT / "analys.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("PRIMARY — kumulativ path och andel av slutlig edge\n")
print(f"{'fonster':13}{'cp':12}{'medel %':>9}{'median':>8}{'and.pos':>9}{'and.edge':>10}{'p10':>8}{'p90':>8}")
for wn, b in res["PRIMARY"].items():
    for cp in ("R_q25", "R_q50", "R_q75", "R_slut"):
        c = b[cp]
        print(f"{wn[:11]:13}{cp:12}{c['medel_pct']:9.2f}{c['median_pct']:8.2f}{c['andel_pos']:9.3f}"
              f"{str(c['andel_av_slutlig_edge']):>10}{c['p10']:8.1f}{c['p90']:8.1f}")
print("\nINKREMENTELL — var uppstar avkastningen?")
print(f"{'fonster':13}{'segment':12}{'medel %':>9}{'t':>8}{'and.pos':>9}{'bidrag':>9}")
for wn, b in res["PRIMARY"].items():
    for seg, c in b["INKREMENTELL"].items():
        print(f"{wn[:11]:13}{seg:12}{c['medel_pct']:9.3f}{str(c['t']):>8}{c['andel_pos']:9.3f}{str(c['bidrag_till_edge']):>9}")
