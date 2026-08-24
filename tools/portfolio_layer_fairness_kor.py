"""PORTFOLIO_LAYER_FAIRNESS_RACE — samma faktoriella portfoljdesign pa tre rankingar.

Forregistrering: research_k/portfolio_layer_fairness/preregistration.json
INGA MODELLER TRANAS. De frysta F0-prediktionerna aateranvands ordagrant.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/portfolio_layer_fairness"; RACE = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
COST, PPY, RF, N, POOL = 0.002, 13.0, 0.0224, 20, 30
BLOCK, DRAWS, SEED = 13, 2000, 20260815
EXP, K5, K6, K7 = ("E0", "E1", "E2"), ("likavikt", "invvol1.5"), ("noFR", "FR"), ("inget", "legacy")
key = lambda e, v, f, t: f"{e}|{v}|{f}|{t}"


def stat(x):
    x = np.asarray(x, float); w = np.cumprod(1 + x)
    c = float(w[-1] ** (PPY / len(x)) - 1); v = float(x.std(ddof=1) * math.sqrt(PPY))
    return {"cagr": round(c, 4), "sharpe": round((c - RF) / v, 4) if v else 0.0,
            "vol": round(v, 4), "maxdd": round(float((w / np.maximum.accumulate(w) - 1).min()), 4)}


def boot_idx(n, rng):
    out = []
    while len(out) < n:
        s = rng.integers(0, max(1, n - BLOCK + 1)); out.extend(range(s, min(s + BLOCK, n)))
    return np.array(out[:n])


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "PORTFOLIO_LAYER_FAIRNESS_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"), "ingen_traning": True, "fonster": {}}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, rm, ser, idx = W["rankings"], W["retmap"], W["serie"], W["idx"]
        preds = {m: json.loads((RACE / f"preds_{wn}_{m}_F0.json").read_text())
                 for m in ("EXTRATREES", "XGBOOST")}
        dagar = sorted(preds["EXTRATREES"]); fe = W["paneler"].index(dagar[0]); nev = len(dagar)

        def sma_ok(k, d):
            i = idx(k, d)
            if i is None or i < 200: return True
            _, v = ser[k]; return v[i] >= float(np.mean(v[i - 200:i]))

        def bekr(k, d):
            i = idx(k, d)
            if i is None or i < 120: return False
            _, v = ser[k]; ma = float(np.mean(v[i - 120:i])); r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            return bool(v[i] >= ma and float(np.std(r) * math.sqrt(252)) < 0.35)

        def vol(k, d):
            i = idx(k, d)
            if i is None or i < 61: return 0.25
            _, v = ser[k]; r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            return float(np.std(r) * math.sqrt(252))

        pool = lambda d: [r["kod"] for r in rk[d]][:POOL]
        ORD = {"H0": lambda d: pool(d),
               "ET": lambda d: sorted(pool(d), key=lambda k: (-preds["EXTRATREES"].get(d, {}).get(k, -1e18), k)),
               "XGB": lambda d: sorted(pool(d), key=lambda k: (-preds["XGBOOST"].get(d, {}).get(k, -1e18), k))}

        def kor(of, e, v_, f_, t_):
            prev, nets, kassa, antal, oms = [], [], [], [], []
            for i, d in enumerate(W["paneler"]):
                if i % 2 == 0 or not prev:
                    cur = of(d)[:N]; turn = len(set(cur) - set(prev)) / max(1, N) if prev else 0.0; prev = cur
                else: turn = 0.0
                if i < fe: continue
                sel = [k for k in prev if sma_ok(k, d)] if e in ("E1", "E2") else list(prev)
                n = len(sel); antal.append(n); oms.append(turn)
                if n == 0:
                    nets.append(0.0); kassa.append(1.0); continue
                ts = n / N if e == "E1" else 1.0
                kassa.append(1.0 - ts)
                if v_ == "invvol1.5":
                    inv = 1.0 / (np.maximum(np.array([vol(k, d) for k in sel]), 0.05) ** 1.5)
                    w = inv / np.sum(inv) * ts
                else: w = np.full(n, ts / n)
                if f_ == "FR": w = w * np.array([1.0 if bekr(k, d) else 0.75 for k in sel])
                if t_ == "legacy":
                    w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * ts
                else: w = w / np.sum(w) * ts
                nets.append(float(np.sum(w * np.array([rm.get((k, d), 0.) for k in sel]))) - COST * turn)
            return (np.asarray(nets), float(np.mean(kassa)), float(np.mean(antal)), float(np.sum(oms)))

        S, tab = {}, {}
        for rn, of in ORD.items():
            tab[rn] = {}
            for e, v_, f_, t_ in product(EXP, K5, K6, K7):
                nets, ka, an, om = kor(of, e, v_, f_, t_)
                kk = key(e, v_, f_, t_); S[(rn, kk)] = nets
                tab[rn][kk] = {**stat(nets), "mean_kassa": round(ka, 4), "mean_exposure": round(1 - ka, 4),
                               "mean_innehav": round(an, 2), "turnover_total": round(om, 4),
                               "mean_turnover": round(om / nev, 4),
                               "kostnad_total": round(COST * om, 5)}
            print(f"{wn} {rn}: 24 armar klara", flush=True)
        ut["fonster"][wn] = {"n_eval_paneler": nev, "forsta": dagar[0], "sista": dagar[-1], "tabell": tab}
        for (rn, kk), v in S.items():
            np.save(UT / f"nets_{wn}_{rn}_{kk.replace('|','_').replace('.','p')}.npy", v)
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
