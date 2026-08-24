"""ICB_IDENTIFIABILITY_ASSESSMENT — designstudie. INGA avkastningsberak ningar.

Raknar nodstorlekar och avgor vilka splits som ar statistiskt identifierbara.
MDE harleds ur REDAN PUBLICERADE statistikor (cross_model_arch_b), inte ur nya test.
"""
from __future__ import annotations
import importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/icb_identifiability"; UT.mkdir(exist_ok=True)
_g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R

# ---- EX ANTE-LASTA REGLER ----
MERE = 4.0                 # minsta ekonomiskt relevanta effekt, pp/ar
MDE_REF, M_REF, N_REF = 10.57, 30, 52
MIN_CHILD = 8              # minst 8 unika instrument per panel i noden
TIDSSTABIL = 0.80          # support i minst 80 % av panelerna i BADA fonstren
BALANS = 0.25              # minsta barn >= 25 % av storsta barnets median
KONC_TAK = 0.20            # inget enskilt instrument > 20 % av nodens obs


def mde(m, n):
    if m <= 0 or n <= 0: return float("inf")
    return MDE_REF * math.sqrt(M_REF / m) * math.sqrt(N_REF / n)


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    ut = {"version": "ICB_IDENTIFIABILITY_ASSESSMENT_V1", "typ": "DESIGNSTUDIE",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "inga_avkastningstest": True,
          "ex_ante_regler": {"MERE_pp_per_ar": MERE, "MDE_formel": f"{MDE_REF}*sqrt(30/m)*sqrt(52/n)",
                             "min_child_instrument_per_panel": MIN_CHILD,
                             "tidsstabilitet": TIDSSTABIL, "balanskrav": BALANS, "koncentrationstak": KONC_TAK},
          "fonster": {}}
    DATA = {}
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk = W["rankings"]
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        preds = json.loads((V2 / f"research_k/global_ml_full_pit_race/preds_{wn}_EXTRATREES_F0.json").read_text())
        dagar = [d for d in sorted(preds) if d in rk]

        def meta(k, d):
            r_ = G.nasdaq_rad(k, isin.get(k), d)
            if not r_: return None, None, None
            return r_.get("industry"), r_.get("supersector"), (float(r_["market_cap"]) if r_.get("market_cap") else None)

        rows = []
        for pi, d in enumerate(dagar):
            u = [r["kod"] for r in rk[d]]
            pool = set(u[:30])
            mc = {}
            rec = []
            for k in u:
                ind, sup, m_ = meta(k, d)
                rec.append({"k": k, "ind": ind, "sup": sup, "mc": m_, "pool": k in pool})
                if m_: mc[k] = m_
            order = sorted(mc, key=lambda k: mc[k])
            terc = {}
            for i, k in enumerate(order):
                terc[k] = "liten" if i < len(order) / 3 else ("mellan" if i < 2 * len(order) / 3 else "stor")
            for r_ in rec: r_["terc"] = terc.get(r_["k"])
            rows.append({"p": pi, "rec": rec})
        DATA[wn] = (rows, len(dagar))

        # ---- nodstorlekar
        def nod(popfilt, key):
            per = defaultdict(list)   # nodnamn -> [antal per panel]
            inst = defaultdict(set); obs = defaultdict(lambda: defaultdict(int))
            for pr in rows:
                c = defaultdict(int)
                for r_ in pr["rec"]:
                    if not popfilt(r_): continue
                    v = key(r_)
                    if v is None: continue
                    c[v] += 1; inst[v].add(r_["k"]); obs[v][r_["k"]] += 1
                for v, n in c.items(): per[v].append(n)
                for v in per:
                    if v not in c: per[v].append(0)
            out = {}
            for v, L in per.items():
                a = np.array(L, float)
                tot = sum(obs[v].values())
                out[v] = {"median": float(np.median(a)), "p10": float(np.percentile(a, 10)),
                          "min": float(a.min()), "max": float(a.max()),
                          "andel_paneler_med_support": float(np.mean(a >= MIN_CHILD)),
                          "n_unika_instrument": len(inst[v]), "n_obs": int(tot),
                          "max_instrument_andel": round(max(obs[v].values()) / tot, 3) if tot else None}
            return out

        POP = {"FULL": lambda r: True, "H0POOL": lambda r: r["pool"]}
        KEY = {"ICB_industry": lambda r: r["ind"], "ICB_supersector": lambda r: r["sup"],
               "SIZE_tercil": lambda r: r["terc"]}
        res = {"n_paneler": len(dagar)}
        res["ROOT"] = {p: {"median_instrument": float(np.median([sum(1 for r_ in pr["rec"] if POP[p](r_)) for pr in rows])),
                           "n_unika": len({r_["k"] for pr in rows for r_ in pr["rec"] if POP[p](r_)})} for p in POP}
        for p in POP:
            for kn in KEY:
                res[f"{p}|{kn}"] = nod(POP[p], KEY[kn])
        ut["fonster"][wn] = res
        print(f"{wn}: {len(dagar)} paneler klart", flush=True)

    # ---- identifiability map
    W1, W2 = "W1_2014_2019", "W2_2020_2026"
    n1, n2 = ut["fonster"][W1]["n_paneler"], ut["fonster"][W2]["n_paneler"]
    karta = []
    for pop in ("FULL", "H0POOL"):
        m1 = ut["fonster"][W1]["ROOT"][pop]["median_instrument"]
        m2 = ut["fonster"][W2]["ROOT"][pop]["median_instrument"]
        karta.append({"NODE": "ROOT", "POPULATION": pop, "SPLIT": "(ingen — nodens egen kraft)",
                      "m_W1": m1, "m_W2": m2, "MDE_W1": round(mde(m1, n1), 2), "MDE_W2": round(mde(m2, n2), 2),
                      "W1_ID": mde(m1, n1) <= MERE, "W2_ID": mde(m2, n2) <= MERE,
                      "BADA": mde(m1, n1) <= MERE and mde(m2, n2) <= MERE})
        for kn in ("ICB_industry", "ICB_supersector", "SIZE_tercil"):
            a = ut["fonster"][W1][f"{pop}|{kn}"]; b = ut["fonster"][W2][f"{pop}|{kn}"]
            gem = sorted(set(a) & set(b))
            barn = []
            for v in gem:
                s1, s2 = a[v], b[v]
                ok = (s1["andel_paneler_med_support"] >= TIDSSTABIL and s2["andel_paneler_med_support"] >= TIDSSTABIL
                      and mde(s1["median"], n1) <= MERE and mde(s2["median"], n2) <= MERE)
                barn.append({"barn": v, "median_W1": s1["median"], "median_W2": s2["median"],
                             "stabil_W1": round(s1["andel_paneler_med_support"], 3),
                             "stabil_W2": round(s2["andel_paneler_med_support"], 3),
                             "MDE_W1": round(mde(s1["median"], n1), 1), "MDE_W2": round(mde(s2["median"], n2), 1),
                             "max_instr_andel_W1": s1["max_instrument_andel"], "IDENTIFIERBAR": ok})
            karta.append({"NODE": "ROOT", "POPULATION": pop, "SPLIT": kn,
                          "n_barn_gemensamma": len(gem), "n_barn_identifierbara": sum(1 for x in barn if x["IDENTIFIERBAR"]),
                          "barn": barn,
                          "LICENS": "JA" if sum(1 for x in barn if x["IDENTIFIERBAR"]) >= 2 else "NEJ",
                          "STOP": sum(1 for x in barn if x["IDENTIFIERBAR"]) < 2})
    ut["identifiability_map"] = karta
    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
