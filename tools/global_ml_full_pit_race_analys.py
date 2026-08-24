"""Analys av GLOBAL_ML_FULL_PIT_FEATURE_RACE. Ingen ny traning, ingen ny simulering."""
from __future__ import annotations
import importlib.util, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/global_ml_full_pit_race"
_s = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_s); _s.loader.exec_module(G)
R = G.R
MODELS, ARMS = G.MODELS, ("F0", "F1", "F2")
PPY, BLOCK, DRAWS, SEED = 13.0, 13, 2000, 20260815


def boot_delta(a, b):
    rng = np.random.default_rng(SEED); n = len(a); out = []
    for _ in range(DRAWS):
        idx = []
        while len(idx) < n:
            s = rng.integers(0, max(1, n - BLOCK + 1)); idx.extend(range(s, min(s + BLOCK, n)))
        idx = np.array(idx[:n])
        out.append(np.prod(1 + a[idx]) ** (PPY / n) - np.prod(1 + b[idx]) ** (PPY / n))
    out = np.asarray(out); d = a - b
    t = float(d.mean() / (d.std(ddof=1) / math.sqrt(n))) if d.std(ddof=1) > 0 else 0.0
    return {"delta_pp": round(100 * float(np.prod(1 + a) ** (PPY / n) - np.prod(1 + b) ** (PPY / n)), 3),
            "ki_lo_pp": round(100 * float(np.percentile(out, 2.5)), 3),
            "ki_hi_pp": round(100 * float(np.percentile(out, 97.5)), 3),
            "t": round(t, 3), "andel_pos": round(float(np.mean(out > 0)), 3)}


def holm(pv):
    o = sorted(pv, key=lambda x: x[1]); k = len(o); prev = 0; out = {}
    for i, (nm, p) in enumerate(o):
        adj = min(1.0, max(prev, (k - i) * p)); prev = adj; out[nm] = round(adj, 4)
    return out


def confound(wn):
    """Fordelningar i modellens Topp-30 mot (1) hela universumet (2) H0:s Topp-30."""
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    W = R.load_window(wn); rk, ser, idx = W["rankings"], W["serie"], W["idx"]
    isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()

    def mcap(k, d):
        r = G.nasdaq_rad(k, isin.get(k), d)
        return float(r["market_cap"]) if r and r.get("market_cap") else np.nan

    def spread(k, d):
        r = G.nasdaq_rad(k, isin.get(k), d)
        return float(r["avg_closing_spread"]) if r and r.get("avg_closing_spread") else np.nan

    def velo(k, d):
        r = G.nasdaq_rad(k, isin.get(k), d)
        return float(r["turnover_velocity"]) if r and r.get("turnover_velocity") else np.nan

    def ind(k, d):
        r = G.nasdaq_rad(k, isin.get(k), d)
        return r.get("industry") if r else None

    def vol60(k, d):
        i = idx(k, d)
        if i is None or i < 61: return np.nan
        _, v = ser[k]; rr = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
        return float(np.std(rr) * math.sqrt(252))

    out = {}
    for mod in MODELS:
        out[mod] = {}
        for arm in ARMS:
            p = UT / f"preds_{wn}_{mod}_{arm}.json"
            if not p.exists(): continue
            pr = json.loads(p.read_text())
            acc = defaultdict(list); hacc = defaultdict(list); uacc = defaultdict(list)
            indm = defaultdict(int); indh = defaultdict(int); n = 0
            for d, s in pr.items():
                if d not in rk: continue
                univ = [r["kod"] for r in rk[d]]
                mc = {k: mcap(k, d) for k in univ}
                fin = [v for v in mc.values() if np.isfinite(v)]
                if len(fin) < 20: continue
                pct = {k: float(stats.percentileofscore(fin, v)) if np.isfinite(v) else np.nan
                       for k, v in mc.items()}
                t30 = [k for k, _ in sorted(s.items(), key=lambda x: (-x[1], x[0])) if k in pct][:30]
                h30 = univ[:30]; n += 1
                for grp, tgt, ic in ((t30, acc, indm), (h30, hacc, indh), (univ, uacc, None)):
                    tgt["mcap_pct"] += [pct[k] for k in grp if np.isfinite(pct.get(k, np.nan))]
                    tgt["spread"] += [x for x in (spread(k, d) for k in grp) if np.isfinite(x)]
                    tgt["velocity"] += [x for x in (velo(k, d) for k in grp) if np.isfinite(x)]
                    tgt["vol60"] += [x for x in (vol60(k, d) for k in grp) if np.isfinite(x)]
                    if ic is not None:
                        for k in grp:
                            b = ind(k, d)
                            if b: ic[b] += 1
            f = lambda L: round(float(np.median(L)), 5) if L else None
            tot = sum(indm.values()) or 1; toth = sum(indh.values()) or 1
            out[mod][arm] = {
                "modell_top30": {k: f(v) for k, v in acc.items()},
                "H0_top30": {k: f(v) for k, v in hacc.items()},
                "universum": {k: f(v) for k, v in uacc.items()},
                "hhi_industry_modell": round(sum((v / tot) ** 2 for v in indm.values()), 4),
                "hhi_industry_H0": round(sum((v / toth) ** 2 for v in indh.values()), 4),
                "storsta_industry_modell": max(indm.items(), key=lambda x: x[1])[0] if indm else None,
                "storsta_industry_andel": round(max(indm.values()) / tot, 4) if indm else None,
                "n_paneler": n}
    return out


def main():
    res = json.loads((UT / "results.json").read_text())
    out = {"version": "GLOBAL_ML_FULL_PIT_RACE_ANALYS_V1", "prereg_sha256": res["prereg_sha256"],
           "armkontraster": {}, "holm": {}, "confounders": {}}
    nets = {}
    for wn in res["celler"]:
        for mod in MODELS:
            for arm in ARMS:
                f = UT / f"nets_{wn}_{mod}_{arm}.npy"
                if f.exists(): nets[(wn, mod, arm)] = np.load(f)
    for wn in res["celler"]:
        out["armkontraster"][wn] = {}
        for mod in MODELS:
            c = {}
            for a, b in (("F1", "F0"), ("F2", "F1"), ("F2", "F0")):
                if (wn, mod, a) in nets and (wn, mod, b) in nets:
                    c[f"{a}-{b}"] = boot_delta(nets[(wn, mod, a)], nets[(wn, mod, b)])
            # Holm inom familj over de tre kontrasterna
            pv = [(k, 2 * (1 - stats.t.cdf(abs(v["t"]), len(nets[(wn, mod, "F0")]) - 1))) for k, v in c.items()]
            c["holm_inom_familj"] = holm(pv)
            out["armkontraster"][wn][mod] = c
    # Holm over familjer: basta arm per familj, svagaste fonster
    W = list(res["celler"])
    fam = {}
    for mod in MODELS:
        best, bp = None, 1.0
        for arm in ARMS:
            ts = []
            for wn in W:
                v = res["celler"][wn]["modeller"].get(mod, {}).get(arm)
                if v: ts.append((v["vs_h0_ew"]["delta_cagr"], v["vs_h0_ew"]["t"], len(nets[(wn, mod, arm)])))
            if len(ts) < 2: continue
            if ts[0][0] * ts[1][0] <= 0: p = 1.0
            else:
                i = int(np.argmin([abs(x[1]) for x in ts])
                        ) if abs(ts[0][1]) != abs(ts[1][1]) else 0
                p = 2 * (1 - stats.t.cdf(min(abs(ts[0][1]), abs(ts[1][1])), ts[i][2] - 1))
            if p < bp: bp, best = p, arm
        fam[mod] = {"basta_arm": best, "p_svagaste_fonster": round(bp, 4)}
    out["holm"] = {"per_familj": fam,
                   "holm_justerat": holm([(m, v["p_svagaste_fonster"]) for m, v in fam.items()])}
    for wn in res["celler"]:
        out["confounders"][wn] = confound(wn)
    (UT / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "analysis.json")


if __name__ == "__main__":
    main()
