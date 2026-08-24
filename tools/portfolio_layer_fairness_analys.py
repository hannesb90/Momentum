"""Analys av PORTFOLIO_LAYER_FAIRNESS_RACE enligt forregistreringen. Ingen ny simulering."""
from __future__ import annotations
import json, math
from itertools import product
from pathlib import Path
import numpy as np

UT = Path("/home/hannesb/momentum_v2/research_k/portfolio_layer_fairness")
PPY, BLOCK, DRAWS, SEED = 13.0, 13, 2000, 20260815
EXP, K5, K6, K7 = ("E0", "E1", "E2"), ("likavikt", "invvol1.5"), ("noFR", "FR"), ("inget", "legacy")
RANK = ("H0", "ET", "XGB")
key = lambda e, v, f, t: f"{e}|{v}|{f}|{t}"
fn = lambda w, r, k: UT / f"nets_{w}_{r}_{k.replace('|','_').replace('.','p')}.npy"


def load(wn):
    return {(r, key(e, v, f, t)): np.load(fn(wn, r, key(e, v, f, t)))
            for r in RANK for e, v, f, t in product(EXP, K5, K6, K7)}


def cagr(x): return float(np.prod(1 + x) ** (PPY / len(x)) - 1)


def boot_sets(n, rng):
    out = []
    for _ in range(DRAWS):
        ix = []
        while len(ix) < n:
            s = rng.integers(0, max(1, n - BLOCK + 1)); ix.extend(range(s, min(s + BLOCK, n)))
        out.append(np.array(ix[:n]))
    return out


def komp_par(c):
    """Returnerar (hog_key, lag_key)-par for komponent c, snittat over ovriga faktorer."""
    if c == "K4a": return [(key("E2", v, f, t), key("E0", v, f, t)) for v, f, t in product(K5, K6, K7)]
    if c == "K4b": return [(key("E1", v, f, t), key("E2", v, f, t)) for v, f, t in product(K5, K6, K7)]
    if c == "K4":  return [(key("E1", v, f, t), key("E0", v, f, t)) for v, f, t in product(K5, K6, K7)]
    if c == "K5":  return [(key(e, "invvol1.5", f, t), key(e, "likavikt", f, t)) for e, f, t in product(EXP, K6, K7)]
    if c == "K6":  return [(key(e, v, "FR", t), key(e, v, "noFR", t)) for e, v, t in product(EXP, K5, K7)]
    if c == "K7":  return [(key(e, v, f, "legacy"), key(e, v, f, "inget")) for e, v, f in product(EXP, K5, K6)]
    raise ValueError(c)


def main():
    res = json.loads((UT / "results.json").read_text())
    out = {"version": "PORTFOLIO_LAYER_FAIRNESS_ANALYS_V1", "prereg_sha256": res["prereg_sha256"],
           "huvudeffekter": {}, "ranking_x_komponent": {}, "maximin": {}, "arkitekturjamforelse": {}}
    Sw, IX = {}, {}
    for wn in res["fonster"]:
        Sw[wn] = load(wn)
        n = len(next(iter(Sw[wn].values())))
        IX[wn] = boot_sets(n, np.random.default_rng(SEED))

    # ---- huvudeffekter + ranking x komponent
    for wn in res["fonster"]:
        S, idxs = Sw[wn], IX[wn]
        out["huvudeffekter"][wn] = {}; out["ranking_x_komponent"][wn] = {}
        for c in ("K4a", "K4b", "K4", "K5", "K6", "K7"):
            pars = komp_par(c)
            eff = {r: float(np.mean([cagr(S[(r, a)]) - cagr(S[(r, b)]) for a, b in pars])) for r in RANK}
            out["huvudeffekter"][wn][c] = {r: round(100 * eff[r], 3) for r in RANK}
            out["ranking_x_komponent"][wn][c] = {}
            for r in ("ET", "XGB"):
                d = eff[r] - eff["H0"]
                bs = []
                for ix in idxs:
                    er = np.mean([cagr(S[(r, a)][ix]) - cagr(S[(r, b)][ix]) for a, b in pars])
                    eh = np.mean([cagr(S[("H0", a)][ix]) - cagr(S[("H0", b)][ix]) for a, b in pars])
                    bs.append(er - eh)
                bs = np.asarray(bs)
                out["ranking_x_komponent"][wn][c][r] = {
                    "interaktion_pp": round(100 * d, 3),
                    "ki_lo_pp": round(100 * float(np.percentile(bs, 2.5)), 3),
                    "ki_hi_pp": round(100 * float(np.percentile(bs, 97.5)), 3),
                    "andel_neg": round(float(np.mean(bs < 0)), 3)}

    # ---- MAXIMIN per ranking (regel last i forvag)
    W = list(res["fonster"])
    for r in RANK:
        rows = []
        for e, v, f, t in product(EXP, K5, K6, K7):
            k = key(e, v, f, t)
            cs = [cagr(Sw[w][(r, k)]) for w in W]
            rows.append((k, min(cs), cs[0], cs[1]))
        rows.sort(key=lambda x: -x[1])
        bas = key("E0", "likavikt", "noFR", "inget")
        # Holm over 24 armar, excess mot samma rankings baslinje, svagaste fonstret
        from scipy import stats
        pv = []
        for k, mn, c1, c2 in rows:
            ts = []
            for w in W:
                d = Sw[w][(r, k)] - Sw[w][(r, bas)]
                ts.append(float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))) if d.std(ddof=1) > 0 else 0.0)
            if (c1 - cagr(Sw[W[0]][(r, bas)])) * (c2 - cagr(Sw[W[1]][(r, bas)])) <= 0:
                p = 1.0
            else:
                i = int(np.argmin([abs(x) for x in ts]))
                p = 2 * (1 - stats.t.cdf(abs(ts[i]), len(Sw[W[i]][(r, bas)]) - 1))
            pv.append((k, p))
        o = sorted(pv, key=lambda x: x[1]); prev = 0; holm = {}
        for i, (k, p) in enumerate(o):
            adj = min(1.0, max(prev, (len(o) - i) * p)); prev = adj; holm[k] = round(adj, 4)
        out["maximin"][r] = {
            "vald_arm": rows[0][0], "maximin_cagr": round(100 * rows[0][1], 3),
            "W1_cagr": round(100 * rows[0][2], 3), "W2_cagr": round(100 * rows[0][3], 3),
            "holm_justerat_p": holm[rows[0][0]],
            "topp5": [{"arm": k, "maximin_pp": round(100 * m, 3), "W1": round(100 * a, 3),
                       "W2": round(100 * b, 3), "holm": holm[k]} for k, m, a, b in rows[:5]],
            "H0V3_konfig_arm": key("E1", "invvol1.5", "FR", "legacy"),
            "H0V3_konfig": {w: round(100 * cagr(Sw[w][(r, key("E1", "invvol1.5", "FR", "legacy"))]), 3) for w in W}}

    # ---- arkitekturjamforelse: varje rankings maximin-arm mot H0:s maximin-arm
    h0k = out["maximin"]["H0"]["vald_arm"]
    for r in ("ET", "XGB"):
        rk_ = out["maximin"][r]["vald_arm"]
        d = {}
        for w in W:
            a, b = Sw[w][(r, rk_)], Sw[w][("H0", h0k)]
            bs = np.asarray([cagr(a[ix]) - cagr(b[ix]) for ix in IX[w]])
            d[w] = {"excess_pp": round(100 * (cagr(a) - cagr(b)), 3),
                    "ki_lo_pp": round(100 * float(np.percentile(bs, 2.5)), 3),
                    "ki_hi_pp": round(100 * float(np.percentile(bs, 97.5)), 3),
                    "andel_pos": round(float(np.mean(bs > 0)), 3)}
        out["arkitekturjamforelse"][r] = {"ranking_arm": rk_, "H0_arm": h0k, **d}
    (UT / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "analysis.json")


if __name__ == "__main__":
    main()
