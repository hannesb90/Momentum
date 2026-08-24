"""G-PATH-1 — TIME-IN-STATE SUFFICIENCY (LEVEL 2, population path only)

Forregistrerad i docs/STATE_PATH_FEASIBILITY_OCH_PREREGISTRERING.md.

Population   alla (ticker, panel) i state S (rank <= 30) dar panel T+1 finns.
Behandling   EMERGING = TIS 1, ESTABLISHED = TIS >= 8. Inga andra cutoffs.
Utfall       band vid T+1: S / N / W. h = 1 panel, ingen overlappning.
Kontroll     score-decil inom panel (primar) + residualisering mot score och rank.

INGEN stock-specific memory, ingen portfolj, ingen avkastning, ingen kostnad,
ingen entry/exitregel, ingen G97-koppling, ingen H0-andring.

STRUKTURELL ASYMMETRI SOM MASTE REDOVISAS
  EMERGING ar per definition forsta panelen i en S-run -> exakt EN observation
  per run, oberoende mellan runs. ESTABLISHED ar panel 8+ i samma run -> manga
  observationer fran SAMMA run. Effektiv n skiljer sig darfor kraftigt mellan
  grupperna och radas ut som antal RUNS, inte antal observationer.

Kor: /opt/momentum/venv/bin/python tools/g_path_1_time_in_state.py
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
OUT = V2 / "research_k/g_path_1_results.json"
SEED, DRAWS, BLOCK = 20260818, 2000, 13
BENCH = 0.12          # forregistrerat power/materiality-riktmarke, 12 pp


def band(r):
    return "-" if r is None else ("S" if r <= 30 else ("N" if r <= 60 else "W"))


def bygg(F):
    """Returnerar radlista: (panelindex, ticker, rank, score, TIS, run_id, utfall)."""
    dts = F["eval_dates"]; P = len(dts)
    rk, sc = {}, {}
    for dt in dts:
        for i, r in enumerate(F["rankings"][dt]):
            rk[(r["kod"], dt)] = i + 1; sc[(r["kod"], dt)] = r["score"]
    tick = sorted({k for k, _ in rk})
    rader = []
    for t in tick:
        b = [band(rk.get((t, dt))) for dt in dts]
        tis, run, rid, nrun = [], 0, [], 0
        for i in range(P):
            if i > 0 and b[i] == b[i - 1]:
                run += 1
            else:
                run = 1
                if b[i] == "S":
                    nrun += 1
            tis.append(run); rid.append(f"{t}#{nrun}" if b[i] == "S" else None)
        for i in range(P - 1):
            if b[i] != "S" or b[i + 1] == "-":
                continue
            rader.append({"pi": i, "dt": dts[i], "tic": t, "rank": rk[(t, dts[i])],
                          "score": sc[(t, dts[i])], "tis": tis[i], "run": rid[i],
                          "ut": b[i + 1]})
    return rader, P


def grupp(rader, g):
    if g == "EMERGING":
        return [r for r in rader if r["tis"] == 1]
    return [r for r in rader if r["tis"] >= 8]


def andel(rows, mal="S"):
    return float(np.mean([r["ut"] == mal for r in rows])) if rows else float("nan")


def klusterdiff(A, B, nyckel):
    """Differens i P(S->S), A minus B, med cluster-robust SE pa `nyckel`."""
    y = np.array([1.0 if r["ut"] == "S" else 0.0 for r in A + B])
    x = np.array([1.0] * len(A) + [0.0] * len(B))
    g = np.array([r[nyckel] for r in A + B])
    X = np.column_stack([np.ones(len(y)), x])
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    u = y - X @ beta
    meat = np.zeros((2, 2))
    for kl in set(g):
        m = g == kl
        s = X[m].T @ u[m]
        meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv
    se = float(np.sqrt(max(V[1, 1], 0)))
    return {"diff_pp": round(float(beta[1]) * 100, 2), "se_pp": round(se * 100, 2),
            "t": round(float(beta[1] / se), 3) if se > 0 else None,
            "n_kluster": len(set(g))}


def klusterboot(A, B, nyckel, rng):
    """Bootstrap over kluster (hela kluster dras med aterlaggning)."""
    kl = defaultdict(lambda: ([], []))
    for r in A: kl[r[nyckel]][0].append(r)
    for r in B: kl[r[nyckel]][1].append(r)
    keys = list(kl); out = []
    for _ in range(DRAWS):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        a = [x for i in pick for x in kl[keys[i]][0]]
        b = [x for i in pick for x in kl[keys[i]][1]]
        if not a or not b: continue
        out.append(andel(a) - andel(b))
    o = np.array(out) * 100
    return {"ki_lo_pp": round(float(np.percentile(o, 2.5)), 2),
            "ki_hi_pp": round(float(np.percentile(o, 97.5)), 2),
            "andel_positiva": round(float((o > 0).mean()), 4), "n_draws": len(o)}


def blockboot(A, B, P, rng):
    """Projektstandard: block bootstrap over paneler, 13-panelsblock."""
    byp = defaultdict(lambda: ([], []))
    for r in A: byp[r["pi"]][0].append(r)
    for r in B: byp[r["pi"]][1].append(r)
    nb = int(np.ceil(P / BLOCK)); out = []
    for _ in range(DRAWS):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, max(1, P - BLOCK + 1)); idx += list(range(s, s + BLOCK))
        idx = [i for i in idx[:P]]
        a = [x for i in idx for x in byp[i][0]]
        b = [x for i in idx for x in byp[i][1]]
        if not a or not b: continue
        out.append(andel(a) - andel(b))
    o = np.array(out) * 100
    return {"ki_lo_pp": round(float(np.percentile(o, 2.5)), 2),
            "ki_hi_pp": round(float(np.percentile(o, 97.5)), 2), "n_draws": len(o)}


def mh_stratifierad(A, B, ndec=10):
    """Score-decil INOM panel. Poolad differens over strata dar bada finns."""
    byp = defaultdict(list)
    for r in A + B: byp[r["pi"]].append(r)
    dec = {}
    for pi, rows in byp.items():
        rows = sorted(rows, key=lambda r: -r["score"])
        # decilen bestams av rankordningen bland panelens 30 S-namn
        for r in rows:
            dec[(pi, r["tic"])] = min(ndec - 1, (r["rank"] - 1) * ndec // 30)
    celler = defaultdict(lambda: ([], []))
    for r in A: celler[(r["pi"], dec[(r["pi"], r["tic"])])][0].append(r)
    for r in B: celler[(r["pi"], dec[(r["pi"], r["tic"])])][1].append(r)
    anv = {k: v for k, v in celler.items() if v[0] and v[1]}
    if not anv:
        return {"anvandbara_celler": 0}
    w, d = [], []
    for (a, b) in anv.values():
        n1, n0 = len(a), len(b)
        w.append(n1 * n0 / (n1 + n0)); d.append(andel(a) - andel(b))
    w = np.array(w); d = np.array(d)
    return {"anvandbara_celler": len(anv), "totalt_celler_med_nagon": len(celler),
            "obs_i_anvandbara_A": sum(len(v[0]) for v in anv.values()),
            "obs_i_anvandbara_B": sum(len(v[1]) for v in anv.values()),
            "poolad_diff_pp": round(float(np.sum(w * d) / np.sum(w)) * 100, 2),
            "andel_celler_positiva": round(float((d > 0).mean()), 4)}


def lpm(A, B):
    """Linjar sannolikhetsmodell med score och rank som kontroller.
    Cluster-robust pa ticker. Detta ar residualiseringen."""
    rows = A + B
    y = np.array([1.0 if r["ut"] == "S" else 0.0 for r in rows])
    est = np.array([1.0 if r["tis"] >= 8 else 0.0 for r in rows])
    sc = np.array([r["score"] for r in rows]); rn = np.array([r["rank"] for r in rows])
    sc = (sc - sc.mean()) / sc.std(); rn = (rn - rn.mean()) / rn.std()
    X = np.column_stack([np.ones(len(y)), est, sc, rn])
    XtX_inv = np.linalg.pinv(X.T @ X); beta = XtX_inv @ (X.T @ y); u = y - X @ beta
    g = np.array([r["tic"] for r in rows]); meat = np.zeros((4, 4))
    for kl in set(g):
        m = g == kl; s = X[m].T @ u[m]; meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv
    se = float(np.sqrt(max(V[1, 1], 0)))
    return {"koeff_established_pp": round(float(beta[1]) * 100, 2), "se_pp": round(se * 100, 2),
            "t": round(float(beta[1] / se), 3) if se > 0 else None, "n": len(y)}


def loo(A, B):
    bas = andel(A) - andel(B)
    tic = sorted({r["tic"] for r in A + B}); ut = []
    for t in tic:
        a = [r for r in A if r["tic"] != t]; b = [r for r in B if r["tic"] != t]
        if not a or not b: continue
        ut.append((t, andel(a) - andel(b)))
    v = np.array([x[1] for x in ut])
    bidrag = sorted(ut, key=lambda x: abs(x[1] - bas), reverse=True)[:5]
    return {"bas_diff_pp": round(bas * 100, 2),
            "loo_min_pp": round(float(v.min()) * 100, 2),
            "loo_max_pp": round(float(v.max()) * 100, 2),
            "teckenbyte_vid_nagon_utelamning": bool((v > 0).any() and (v <= 0).any()),
            "storsta_bidragsgivare": [{"tic": t, "diff_utan_pp": round(d * 100, 2),
                                       "paverkan_pp": round((bas - d) * 100, 2)}
                                      for t, d in bidrag]}


res = {"version": "G_PATH_1_V1", "niva": "LEVEL 2 — population path only",
       "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
       "behandling": "EMERGING = TIS 1, ESTABLISHED = TIS >= 8 (forregistrerat, inga alternativ)",
       "utfall": "band vid T+1, h=1 panel, ingen overlappning",
       "power_benchmark_pp": 12.0, "fonster": {}}

for namn, F in (("2020_2026", S.F26), ("2014_2019", S.F19)):
    rng = np.random.default_rng(SEED)
    rader, P = bygg(F)
    E, X = grupp(rader, "EMERGING"), grupp(rader, "ESTABLISHED")
    d = {}
    for g, rows in (("EMERGING", E), ("ESTABLISHED", X)):
        d[g] = {"n_obs": len(rows), "n_runs": len({r["run"] for r in rows}),
                "n_tickers": len({r["tic"] for r in rows}),
                "P_S": round(andel(rows, "S"), 4), "P_N": round(andel(rows, "N"), 4),
                "P_W": round(andel(rows, "W"), 4),
                "P_forsvagning": round(andel(rows, "N") + andel(rows, "W"), 4),
                "median_rank": float(np.median([r["rank"] for r in rows])),
                "median_score": round(float(np.median([r["score"] for r in rows])), 4)}
    pe, px = d["EMERGING"]["P_S"], d["ESTABLISHED"]["P_S"]
    d["diff_pp"] = round((px - pe) * 100, 2)
    d["risk_ratio"] = round(px / pe, 4) if pe else None
    d["odds_ratio"] = round((px / (1 - px)) / (pe / (1 - pe)), 4) if 0 < pe < 1 and px < 1 else None
    d["cluster_ticker"] = klusterdiff(X, E, "tic")
    d["cluster_run"] = klusterdiff(X, E, "run")
    d["bootstrap_kluster_ticker"] = klusterboot(X, E, "tic", rng)
    d["bootstrap_block_panel"] = blockboot(X, E, P, rng)
    d["matched_score_decil"] = mh_stratifierad(X, E)
    d["lpm_residualiserad"] = lpm(X, E)
    d["leave_one_ticker_out"] = loo(X, E)
    d["nar_12pp"] = bool(abs(d["diff_pp"]) >= BENCH * 100)
    res["fonster"][namn] = d

    print(f"=== {namn} ===")
    for g in ("EMERGING", "ESTABLISHED"):
        q = d[g]
        print(f"  {g:12s} obs {q['n_obs']:>4}  runs {q['n_runs']:>4}  tickers {q['n_tickers']:>3}  "
              f"P(S->S) {q['P_S']:.4f}  P(->N) {q['P_N']:.4f}  P(->W) {q['P_W']:.4f}  "
              f"medianrank {q['median_rank']:.0f}")
    print(f"  DIFF (est - eme) {d['diff_pp']:+.2f} pp   RR {d['risk_ratio']}  OR {d['odds_ratio']}")
    print(f"  cluster ticker  {d['cluster_ticker']}")
    print(f"  cluster run     {d['cluster_run']}")
    print(f"  boot kluster    {d['bootstrap_kluster_ticker']}")
    print(f"  boot block      {d['bootstrap_block_panel']}")
    print(f"  matched decil   {d['matched_score_decil']}")
    print(f"  LPM residual    {d['lpm_residualiserad']}")
    print(f"  LOO             {d['leave_one_ticker_out']['bas_diff_pp']:+.2f} pp, "
          f"spann [{d['leave_one_ticker_out']['loo_min_pp']:+.2f}, "
          f"{d['leave_one_ticker_out']['loo_max_pp']:+.2f}], "
          f"teckenbyte {d['leave_one_ticker_out']['teckenbyte_vid_nagon_utelamning']}")
    print(f"  storsta bidrag  {d['leave_one_ticker_out']['storsta_bidragsgivare'][:3]}")
    print(f"  nar 12 pp: {d['nar_12pp']}\n")

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("skrivet:", OUT)
