"""DYNAMIC_ROUTING_ARCHITECTURE — testar routingPOLICYNS varde, inte varje grens egen alfa.

Forregistrering: research_k/dynamic_routing_architecture/ROUTING_PREREGISTRATION.json
INGA MODELLER TRANAS. Frysta F0-prediktioner aateranvands.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/dynamic_routing_architecture"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "ROUTING_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
N, POOL, COST, PPY, RF = 20, 30, 0.002, 13.0, 0.0224
EMB = 4          # traningspanel j <= i-4 (target 2 paneler + purge/embargo 12 v)
MIN_MED, MIN_PAN = 5, 12
BLOCK, DRAWS, SEED, PL_DRAWS = 13, 2000, 20260815, 1000
ENG = ("H0", "ET", "XGB")


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def stat(x):
    x = np.asarray(x, float); w = np.cumprod(1 + x)
    c = float(w[-1] ** (PPY / len(x)) - 1); v = float(x.std(ddof=1) * math.sqrt(PPY))
    return {"cagr": round(c, 4), "sharpe": round((c - RF) / v, 4) if v else 0.0,
            "maxdd": round(float((w / np.maximum.accumulate(w) - 1).min()), 4)}


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


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "DYNAMIC_ROUTING_ARCHITECTURE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "ROUTING_PREREGISTRATION.json"), "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm = W["rankings"], W["retmap"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = [d for d in sorted(preds["EXTRATREES"]) if d in rk]
        fe = W["paneler"].index(dagar[0])

        def nas(k, d, f):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            v = r_.get(f) if r_ else None
            return float(v) if v else None

        def ind(k, d):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            return (r_.get("industry") if r_ else None) or "OKAND"

        # ---------- panel-data: percentilrangar + noder ----------
        PD = {"FULL": [], "POOL": []}
        for pi, d in enumerate(dagar):
            u = [r["kod"] for r in rk[d] if (r["kod"], d) in rm]
            h0s = {r["kod"]: r["score"] for r in rk[d]}
            for popn, names in (("FULL", u), ("POOL", [k for k in [r["kod"] for r in rk[d]][:POOL] if (k, d) in rm])):
                if len(names) < 10: PD[popn].append(None); continue
                sc = {"H0": {k: h0s[k] for k in names},
                      "ET": {k: preds["EXTRATREES"].get(d, {}).get(k, np.nan) for k in names},
                      "XGB": {k: preds["XGBOOST"].get(d, {}).get(k, np.nan) for k in names}}
                pct = {}
                for e in ENG:
                    v = np.array([sc[e][k] for k in names], float)
                    r_ = np.argsort(np.argsort(v)).astype(float) / max(1, len(v) - 1)
                    pct[e] = dict(zip(names, r_))
                mc = {k: nas(k, d, "market_cap") for k in names}
                ok = [k for k in names if mc[k]]
                order = sorted(ok, key=lambda k: mc[k])
                terc = {}
                for i2, k in enumerate(order):
                    terc[k] = "liten" if i2 < len(order) / 3 else ("mellan" if i2 < 2 * len(order) / 3 else "stor")
                PD[popn].append({"d": d, "names": names, "pct": pct, "ret": {k: rm[(k, d)] for k in names},
                                 "size": {k: terc.get(k, "OKAND") for k in names},
                                 "icb": {k: ind(k, d) for k in names}})

        _ICC = {}

        def ic_hist(pd_, key, upto):
            if (key, upto) in _ICC: return _ICC[(key, upto)]
            """medel-IC per (nod, motor) over traningspaneler <= upto, plus globalt"""
            acc = defaultdict(lambda: defaultdict(list)); cnt = defaultdict(list); glob = defaultdict(list)
            for j in range(0, upto + 1):
                P = pd_[j]
                if P is None: continue
                for e in ENG:
                    glob[e].append(sp([P["pct"][e][k] for k in P["names"]], [P["ret"][k] for k in P["names"]]))
                gs = defaultdict(list)
                for k in P["names"]: gs[P[key][k]].append(k)
                for g, ks in gs.items():
                    if len(ks) < 3: continue
                    cnt[g].append(len(ks))
                    for e in ENG:
                        acc[g][e].append(sp([P["pct"][e][k] for k in ks], [P["ret"][k] for k in ks]))
            gbest = max(ENG, key=lambda e: np.nanmean(glob[e]) if glob[e] else -9)
            val = {}
            for g in acc:
                if len(cnt[g]) < MIN_PAN or np.mean(cnt[g]) < MIN_MED: val[g] = (gbest, "FALLBACK"); continue
                val[g] = (max(ENG, key=lambda e: np.nanmean(acc[g][e]) if acc[g][e] else -9), "LARD")
            _ICC[(key, upto)] = (val, gbest)
            return val, gbest

        def kor(popn, mode, key=None, rng=None, frek=None):
            pd_ = PD[popn]; prev, nets, turns, beslut = [], [], [], []
            for i, P in enumerate(pd_):
                if P is None:
                    nets.append(0.0); turns.append(0.0); continue
                if i % 2 == 0 or not prev:
                    if mode in ENG:
                        sco = {k: P["pct"][mode][k] for k in P["names"]}
                    else:
                        if rng is None:
                            val, gbest = ic_hist(pd_, key, max(-1, i - EMB)) if i - EMB >= 0 else ({}, "H0")
                        else:
                            val, gbest = {}, "H0"
                        # EN motor per NOD (inte per namn), enligt forregistreringen
                        noder = sorted({P[key][k] for k in P["names"]})
                        if rng is not None:
                            idx = rng.choice(3, size=len(noder), p=frek)
                            tilldelning = {g: ENG[idx[j]] for j, g in enumerate(noder)}
                        else:
                            tilldelning = {g: val.get(g, (gbest, "FALLBACK"))[0] for g in noder}
                        sco = {}
                        for k in P["names"]:
                            g = P[key][k]; e = tilldelning[g]
                            sco[k] = P["pct"][e][k]
                            if rng is None: beslut.append((P["d"], g, e, val.get(g, (gbest, "FALLBACK"))[1]))
                    cur = sorted(P["names"], key=lambda k: (-sco[k], k))[:N]
                    turn = len(set(cur) - set(prev)) / max(1, N) if prev else 0.0
                    prev = cur
                else: turn = 0.0
                nets.append(sum(P["ret"][k] for k in prev if k in P["ret"]) / max(1, len(prev)) - COST * turn)
                turns.append(turn)
            return np.asarray(nets), np.asarray(turns), beslut

        res = {"n_paneler": len(dagar), "armar": {}, "routing": {}}
        S = {}
        for popn, pfx in (("FULL", "A"), ("POOL", "B")):
            for e in ENG:
                nets, t, _ = kor(popn, e)
                S[f"{pfx}_{e}"] = nets
                res["armar"][f"{pfx}_static_{e}"] = {**stat(nets), "mean_turnover": round(float(t.mean()), 4)}
            for pol, key in (("R1_size", "size"), ("R2_icb", "icb")):
                nets, t, bes = kor(popn, "ROUTE", key=key)
                S[f"{pfx}_{pol}"] = nets
                fr = defaultdict(int)
                for _, _, e, _ in bes: fr[e] += 1
                tot = sum(fr.values()) or 1
                lard = sum(1 for b in bes if b[3] == "LARD") / max(1, len(bes))
                res["armar"][f"{pfx}_{pol}"] = {**stat(nets), "mean_turnover": round(float(t.mean()), 4),
                    "routingfrekvens": {e: round(fr[e] / tot, 3) for e in ENG},
                    "andel_lard_ej_fallback": round(lard, 3), "n_beslut": len(bes)}
                bäst = max(ENG, key=lambda e: stat(S[f"{pfx}_{e}"])["cagr"])
                res["armar"][f"{pfx}_{pol}"]["basta_statiska"] = f"{pfx}_static_{bäst}"
                res["armar"][f"{pfx}_{pol}"]["vs_basta_statiska"] = boot(nets, S[f"{pfx}_{bäst}"])
                res["armar"][f"{pfx}_{pol}"]["vs_H0"] = boot(nets, S[f"{pfx}_H0"])
                # matchad slumproutning-placebo
                frek = np.array([fr[e] / tot for e in ENG], float); frek = frek / frek.sum()
                pl = []
                rng = np.random.default_rng(SEED)
                for _ in range(PL_DRAWS):
                    nn, _, _ = kor(popn, "ROUTE", key=key, rng=rng, frek=frek)
                    pl.append(float(np.prod(1 + nn) ** (PPY / len(nn)) - 1))
                pl = np.asarray(pl); egen = stat(nets)["cagr"]
                res["armar"][f"{pfx}_{pol}"]["placebo"] = {
                    "median_pp": round(100 * float(np.median(pl)), 3), "p5_pp": round(100 * float(np.percentile(pl, 5)), 3),
                    "p95_pp": round(100 * float(np.percentile(pl, 95)), 3),
                    "policy_percentil": round(float(np.mean(pl < egen)), 3),
                    "over_p95": bool(egen > np.percentile(pl, 95))}
                res["routing"][f"{pfx}_{pol}"] = {}
                per = defaultdict(lambda: defaultdict(int))
                for _, g, e, _ in bes: per[g][e] += 1
                res["routing"][f"{pfx}_{pol}"] = {g: {e: v[e] for e in ENG if e in v} for g, v in per.items()}
        ut["fonster"][wn] = res
        for k, v in S.items(): np.save(UT / f"nets_{wn}_{k}.npy", v)
        print(f"{wn} klart", flush=True)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
