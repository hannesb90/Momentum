"""CANDIDATE_GENERATION_ARCHITECTURE — ar H0:s topp-30 en onodig flaskhals?

Forregistrering: research_k/candidate_generation_architecture/preregistration.json
INGA MODELLER TRANAS. Frysta F0-prediktioner (100 % universumtackning) aateranvands.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/candidate_generation_architecture"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
N, COST, PPY, RF = 20, 0.002, 13.0, 0.0224
BLOCK, DRAWS, SEED = 13, 2000, 20260815
K60 = 60


def stat(x):
    x = np.asarray(x, float); w = np.cumprod(1 + x)
    c = float(w[-1] ** (PPY / len(x)) - 1); v = float(x.std(ddof=1) * math.sqrt(PPY))
    return {"cagr": round(c, 4), "sharpe": round((c - RF) / v, 4) if v else 0.0,
            "vol": round(v, 4), "maxdd": round(float((w / np.maximum.accumulate(w) - 1).min()), 4)}


def boot(a, b):
    rng = np.random.default_rng(SEED); n = len(a); out = []
    for _ in range(DRAWS):
        ix = []
        while len(ix) < n:
            s = rng.integers(0, max(1, n - BLOCK + 1)); ix.extend(range(s, min(s + BLOCK, n)))
        ix = np.array(ix[:n])
        out.append(np.prod(1 + a[ix]) ** (PPY / n) - np.prod(1 + b[ix]) ** (PPY / n))
    out = np.asarray(out)
    return {"delta_pp": round(100 * (np.prod(1 + a) ** (PPY / n) - np.prod(1 + b) ** (PPY / n)), 3),
            "ki_lo_pp": round(100 * float(np.percentile(out, 2.5)), 3),
            "ki_hi_pp": round(100 * float(np.percentile(out, 97.5)), 3),
            "andel_pos": round(float(np.mean(out > 0)), 3)}


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 5 or a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def z(x):
    r = np.argsort(np.argsort(np.asarray(x, float))).astype(float)
    return (r - r.mean()) / (r.std() or 1.0)


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "CANDIDATE_GENERATION_ARCHITECTURE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"), "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm, ser, idx = W["rankings"], W["retmap"], W["serie"], W["idx"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = sorted(preds["EXTRATREES"]); fe = W["paneler"].index(dagar[0]); nev = len(dagar)

        def vol60(k, d):
            i = idx(k, d)
            if i is None or i < 61: return np.nan
            _, v = ser[k]; r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            return float(np.std(r) * math.sqrt(252))

        def nas(k, d, f):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            v = r_.get(f) if r_ else None
            return float(v) if v else np.nan

        def ind(k, d):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            return (r_.get("industry") if r_ else None) or "OKAND"

        univ = lambda d: [r["kod"] for r in rk[d]]
        def mlord(m, cand, d):
            s = preds[m].get(d, {})
            return sorted(cand, key=lambda k: (-s.get(k, -1e18), k))

        ARK = {
            "1_H0_TOP20":        lambda d: univ(d),
            "2_H0TOP30_ET":      lambda d: mlord("EXTRATREES", univ(d)[:30], d),
            "3_H0TOP30_XGB":     lambda d: mlord("XGBOOST",    univ(d)[:30], d),
            "4_FULL_ET":         lambda d: mlord("EXTRATREES", univ(d), d),
            "5_FULL_XGB":        lambda d: mlord("XGBOOST",    univ(d), d),
            "6_H0TOP60_ET":      lambda d: mlord("EXTRATREES", univ(d)[:K60], d),
            "7_H0TOP60_XGB":     lambda d: mlord("XGBOOST",    univ(d)[:K60], d),
        }

        def kor(of, e2=False):
            prev, nets, turns = [], [], []
            for i, d in enumerate(W["paneler"]):
                if i % 2 == 0 or not prev:
                    cur = of(d)[:N]; turn = len(set(cur) - set(prev)) / max(1, N) if prev else 0.0; prev = cur
                else: turn = 0.0
                if i < fe: continue
                turns.append(turn)
                if not e2:
                    nets.append(sum(rm.get((k, d), 0.) for k in prev) / max(1, len(prev)) - COST * turn); continue
                sel = []
                for k in prev:
                    j = idx(k, d)
                    if j is None or j < 200: sel.append(k); continue
                    _, v = ser[k]
                    if v[j] >= float(np.mean(v[j - 200:j])): sel.append(k)
                if not sel: nets.append(0.0); continue
                inv = 1.0 / (np.maximum(np.array([vol60(k, d) if np.isfinite(vol60(k, d)) else .25 for k in sel]), 0.05) ** 1.5)
                w = inv / np.sum(inv)
                nets.append(float(np.sum(w * np.array([rm.get((k, d), 0.) for k in sel]))) - COST * turn)
            return np.asarray(nets), np.asarray(turns)

        S, tab = {}, {}
        for nm, of in ARK.items():
            n1, t1 = kor(of, False); n2, _ = kor(of, True)
            S[nm] = n1
            tab[nm] = {"EW": {**stat(n1), "mean_turnover": round(float(t1.mean()), 4),
                              "cost_40bp": round(float(np.prod(1 + (n1 + COST * t1 - 0.004 * t1)) ** (PPY / nev) - 1), 4)},
                       "E2": stat(n2)}
        for a, b in (("4_FULL_ET", "2_H0TOP30_ET"), ("5_FULL_XGB", "3_H0TOP30_XGB"),
                     ("6_H0TOP60_ET", "2_H0TOP30_ET"), ("7_H0TOP60_XGB", "3_H0TOP30_XGB"),
                     ("2_H0TOP30_ET", "1_H0_TOP20"), ("3_H0TOP30_XGB", "1_H0_TOP20"),
                     ("4_FULL_ET", "1_H0_TOP20"), ("5_FULL_XGB", "1_H0_TOP20")):
            tab[a].setdefault("vs", {})[b] = boot(S[a], S[b])

        # ---------- DEL 5/6/7 diagnostik ----------
        diag = {}
        for m, nm in (("EXTRATREES", "ET"), ("XGBOOST", "XGB")):
            ute, inne, rate, h0rank = [], [], [], []
            ic_ute, ic_ute_res = [], []
            grpA, grpB, grpC = defaultdict(list), defaultdict(list), defaultdict(list)
            for d in dagar:
                if d not in rk: continue
                u = univ(d); h30 = set(u[:30]); pos = {k: i + 1 for i, k in enumerate(u)}
                h0s = {r["kod"]: r["score"] for r in rk[d]}
                full20 = set(mlord(m, u, d)[:N]); pool20 = set(mlord(m, u[:30], d)[:N])
                out = [k for k in full20 if k not in h30]
                rate.append(len(out) / N)
                for k in out:
                    if (k, d) in rm: ute.append(rm[(k, d)]); h0rank.append(pos[k])
                for k in full20 & h30:
                    if (k, d) in rm: inne.append(rm[(k, d)])
                # IC utanfor poolen
                outside = [k for k in u if k not in h30 and (k, d) in rm and k in preds[m].get(d, {})]
                if len(outside) >= 20:
                    ms = [preds[m][d][k] for k in outside]; ret = [rm[(k, d)] for k in outside]
                    hs = [h0s[k] for k in outside]
                    ic_ute.append(sp(ms, ret))
                    a_, b_ = z(ms), z(hs)
                    ic_ute_res.append(sp(a_ - float(np.dot(a_, b_) / np.dot(b_, b_)) * b_, ret))
                # attribution
                for grp, ks in (("A", full20 & pool20), ("B", full20 - pool20), ("C", pool20 - full20)):
                    tgt = {"A": grpA, "B": grpB, "C": grpC}[grp]
                    for k in ks:
                        if (k, d) not in rm: continue
                        tgt["ret"].append(rm[(k, d)]); tgt["h0_rank"].append(pos[k])
                        tgt["ml"].append(preds[m].get(d, {}).get(k, np.nan))
                        tgt["mcap"].append(nas(k, d, "market_cap")); tgt["spread"].append(nas(k, d, "avg_closing_spread"))
                        tgt["velo"].append(nas(k, d, "turnover_velocity")); tgt["vol"].append(vol60(k, d))
                        tgt["ind"].append(ind(k, d))
            f = lambda L: round(float(np.nanmean(L)), 5) if len(L) else None
            g = lambda T: {"n": len(T["ret"]), "medel_ret": f(T["ret"]), "median_H0_rank": (
                round(float(np.median(T["h0_rank"])), 1) if T["h0_rank"] else None),
                "medel_mcap_mdr": (round(float(np.nanmedian(T["mcap"])) / 1e9, 2) if T["mcap"] else None),
                "median_spread": f(T["spread"]), "median_velocity": f(T["velo"]), "median_vol60": f(T["vol"]),
                "storsta_industry": (max(set(T["ind"]), key=T["ind"].count) if T["ind"] else None),
                "storsta_industry_andel": (round(T["ind"].count(max(set(T["ind"]), key=T["ind"].count)) / len(T["ind"]), 3) if T["ind"] else None)}
            diag[nm] = {"utanfor_H0top30_andel_av_topp20": round(float(np.mean(rate)), 4),
                        "medel_ret_valda_UTANFOR": f(ute), "medel_ret_valda_INOM": f(inne),
                        "median_H0_rank_utanfor": round(float(np.median(h0rank)), 1) if h0rank else None,
                        "IC_utanfor_poolen": f(ic_ute), "residual_IC_utanfor_efter_H0": f(ic_ute_res),
                        "attribution": {"A_gemensamma": g(grpA), "B_bara_full_universe": g(grpB), "C_bara_H0pool": g(grpC)}}
        ut["fonster"][wn] = {"n_eval_paneler": nev, "tabell": tab, "diagnostik": diag}
        for k, v in S.items(): np.save(UT / f"nets_{wn}_{k}.npy", v)
        print(f"{wn} klart", flush=True)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
