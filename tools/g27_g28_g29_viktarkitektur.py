"""G27/G28 + G29 — MFE/MAE-DIAGNOSTIK OCH LIKAVIKTSÅTERSTÄLLNINGENS ABLATION

Förregistrering: research_k/g29_preregistration.json
sha256 e2a0675a4614e379a0148c84c1c997d01371c0d70741d2c64f70c1c5ed690c71

STEG 1 (G27/G28) är deskriptivt: alla positionsepisoder i låst H0, med MFE, MAE,
vikt före och efter varje rebalance, och vad H0 gör härnäst (behåller/trimmar/
fyller på/säljer).

STEG 2 (G29) är ablationen: arm A återställer incumbents till 1/30, arm B låter
dem drifta. Allt annat identiskt. Neutral allokeringsregel enligt förregistrering:
frigjort kapital delas LIKA mellan inträdande namn.

MODELLRÄTTELSE SOM INGÅR HÄR
  Mina tidigare H0-körningar satte vikterna till 1/N vid VARJE panel, alltså även
  på mellanpanelen där låst H0 inte handlar. Det är inte låst H0. Här driver
  vikterna på mellanpanelen i BÅDA armarna, och återställning sker endast på
  rebalanspanelen. Det påverkar G12/G19/G13+G17:s absoluta nivå marginellt men
  inte deras domar, eftersom de mätte namnval och inte viktbanor.

  Eventuell kvarvarande approximation i terminalhantering drabbar BÅDA armarna
  identiskt, så differensen — det som mäts — förblir giltig.

Kör: /opt/momentum/venv/bin/python tools/g27_g28_g29_viktarkitektur.py
"""
from __future__ import annotations
import bisect, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g27_g28_g29_results.json"
EP = V2 / "research_k/g29_episoder.jsonl"
PATHS = V2 / "research_k/g29_portfolio_paths.json"
COST = 0.002
PPY = 13
N = 30

_SER = {}


def serie(F, k):
    n = (id(F), k)
    if n not in _SER:
        if F is S.F19:
            s = M.SERIE.get(k)
            _SER[n] = None if s is None else \
                (s[0].astype("datetime64[D]").astype(str).tolist(), np.asarray(s[1]))
        else:
            s = S.PS26.get(k)
            _SER[n] = None if s is None else (list(s[0]), np.asarray(s[1]))
    return _SER[n]


def bana(F, k, fran, till):
    s = serie(F, k)
    if s is None:
        return None
    ds, adj = s
    i = bisect.bisect_right(ds, fran)
    j = bisect.bisect_right(ds, till)
    return adj[i:j] if j > i and i < len(ds) else None


def kor(F, arm):
    """arm 'A' = återställ incumbents till 1/30 vid rebalance. 'B' = låt drifta."""
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    w = {}
    nets, turns, hist = [], [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w:
            sel = [r["kod"] for r in raw][:N]
            if not w:
                mal = {k: 1.0 / N for k in sel}
            elif arm == "A":
                mal = {k: 1.0 / N for k in sel}
            else:
                kvar = [k for k in sel if k in w]
                nya = [k for k in sel if k not in w]
                frigjort = float(sum(v for k, v in w.items() if k not in sel))
                mal = {k: w[k] for k in kvar}
                if nya:
                    per = frigjort / len(nya)
                    for k in nya:
                        mal[k] = per
                elif kvar:
                    s_ = sum(mal.values())
                    for k in kvar:
                        mal[k] += frigjort * mal[k] / s_
            tot = sum(mal.values())
            if tot > 0:
                mal = {k: v / tot for k, v in mal.items()}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0))
                       for k in set(mal) | set(w)) / 2.0
        else:
            mal = dict(w)
            turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        gross = float(sum(mal[k] * r[k] for k in mal))
        nets.append(gross - COST * turn)
        turns.append(turn)
        hist.append({"dt": dt, "rebalans": bool(schedf(pi, dt)), "vikter": dict(mal),
                     "avk": dict(r), "turnover": turn})
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return np.array(nets), np.array(turns), hist


def koncentration(hist):
    hhi, maxv, eff = [], [], []
    for h in hist:
        v = np.array(list(h["vikter"].values()))
        if len(v) == 0:
            continue
        hhi.append(float(np.sum(v ** 2)))
        maxv.append(float(v.max()))
        eff.append(float(1.0 / np.sum(v ** 2)))
    return {"hhi_medel": round(float(np.mean(hhi)), 5),
            "max_vikt_medel": round(float(np.mean(maxv)), 5),
            "max_vikt_hogsta": round(float(np.max(maxv)), 5),
            "effektivt_antal_medel": round(float(np.mean(eff)), 2),
            "effektivt_antal_lagsta": round(float(np.min(eff)), 2)}


# ---------------------------------------------------------------- STEG 1
def steg1(F, hist, fonster):
    dts = F["eval_dates"]
    innehav = [set(h["vikter"]) for h in hist]
    ep = []
    per = defaultdict(list)
    for pi, s in enumerate(innehav):
        for k in s:
            per[k].append(pi)
    for k, idx in per.items():
        start = idx[0]; forra = idx[0]
        for i in idx[1:] + [None]:
            if i is None or i != forra + 1:
                if forra < len(dts) - 1:
                    b = bana(F, k, dts[start], dts[min(forra + 1, len(dts) - 1)])
                    mfe = mae = None
                    if b is not None and len(b) > 3 and b[0] > 0:
                        rel = b / b[0] - 1
                        mfe, mae = float(rel.max()), float(rel.min())
                    tot = float(np.prod([1 + hist[p]["avk"].get(k, 0.0)
                                         for p in range(start, forra + 1)]) - 1)
                    ep.append({"fonster": fonster, "kod": k, "entry": dts[start],
                               "exit": dts[forra + 1], "paneler": forra - start + 1,
                               "total_return": tot, "mfe": mfe, "mae": mae})
                if i is not None:
                    start = i
            if i is not None:
                forra = i

    # vikthändelser vid varje rebalance
    hand = []
    for pi in range(1, len(hist)):
        if not hist[pi]["rebalans"]:
            continue
        fore = hist[pi - 1]
        w_pre = {k: v * (1 + fore["avk"].get(k, 0.0)) for k, v in fore["vikter"].items()}
        s_ = sum(w_pre.values())
        w_pre = {k: v / s_ for k, v in w_pre.items()} if s_ > 0 else {}
        w_post = hist[pi]["vikter"]
        sedan = dts[max(0, pi - 2)]
        for k, v in w_pre.items():
            i0 = max(0, pi - 2)
            r_fore = float(np.prod([1 + hist[p]["avk"].get(k, 0.0)
                                    for p in range(i0, pi)]) - 1)
            if k not in w_post:
                lage = "D_saljs"
                dv = -v
            else:
                dv = w_post[k] - v
                lage = "B_trimmas" if dv < -1e-9 else ("C_fylls_pa" if dv > 1e-9 else "A_oforandrad")
            framat = float(np.prod([1 + hist[p]["avk"].get(k, 0.0)
                                    for p in range(pi, min(pi + 2, len(hist)))]) - 1) \
                if k in w_post else None
            hand.append({"pi": pi, "kod": k, "lage": lage, "w_pre": v,
                         "w_post": w_post.get(k, 0.0), "dv": dv,
                         "ret_fore": r_fore, "ret_efter_2p": framat})

    print(f"\n{'-'*74}\nSTEG 1 — G27/G28 MFE/MAE-DIAGNOSTIK   {fonster}")
    e = [x for x in ep if x["mfe"] is not None]
    m1 = np.array([x["mfe"] for x in e]); m2 = np.array([x["mae"] for x in e])
    tot = np.array([x["total_return"] for x in e])
    print(f"  positionsepisoder: {len(e)}")
    print(f"    MFE  medel {m1.mean():+.2%}  median {np.median(m1):+.2%}")
    print(f"    MAE  medel {m2.mean():+.2%}  median {np.median(m2):+.2%}")
    print(f"    faktisk return medel {tot.mean():+.2%}  median {np.median(tot):+.2%}")
    fang = tot / np.where(m1 > 0.001, m1, np.nan)
    fang = fang[~np.isnan(fang)]
    print(f"    FÅNGSTGRAD (return/MFE) median {np.median(fang):.3f} — andel av "
          f"toppen som realiseras")

    print(f"\n  VAD H0 GÖR VID NÄSTA REBALANCE")
    print(f"    {'läge':<16}{'n':>6}{'andel':>8}{'ret före':>11}{'Δvikt':>10}"
          f"{'MFE':>10}{'ret efter 2p':>14}")
    grp = defaultdict(list)
    for h in hand:
        grp[h["lage"]].append(h)
    mfe_per_kod = {(x["kod"], x["entry"]): x["mfe"] for x in ep}
    ut_lage = {}
    for lage in ("A_oforandrad", "B_trimmas", "C_fylls_pa", "D_saljs"):
        g = grp.get(lage, [])
        if len(g) < 5:
            continue
        rf = np.array([x["ret_fore"] for x in g])
        dv = np.array([x["dv"] for x in g])
        re = np.array([x["ret_efter_2p"] for x in g if x["ret_efter_2p"] is not None])
        ut_lage[lage] = {"n": len(g), "andel": round(len(g) / len(hand), 4),
                         "ret_fore_medel": round(float(rf.mean()), 5),
                         "dvikt_medel": round(float(dv.mean()), 6),
                         "ret_efter_2p": round(float(re.mean()), 5) if len(re) else None}
        print(f"    {lage:<16}{len(g):>6}{len(g)/len(hand):>8.1%}{rf.mean():>+11.2%}"
              f"{dv.mean():>+10.4f}{'':>10}"
              f"{(re.mean() if len(re) else float('nan')):>+14.2%}")

    # samband
    rf = np.array([h["ret_fore"] for h in hand if h["lage"] != "D_saljs"])
    dv = np.array([h["dv"] for h in hand if h["lage"] != "D_saljs"])
    kor_rd = float(np.corrcoef(rf, dv)[0, 1]) if len(rf) > 10 else float("nan")
    print(f"\n  SAMBAND (endast behållna namn, n={len(rf)})")
    print(f"    korrelation mellan avkastning FÖRE rebalance och viktändring: {kor_rd:+.3f}")
    print(f"    -> negativt värde = H0 tar systematiskt kapital från det som stigit")
    return {"n_episoder": len(e), "mfe_medel": round(float(m1.mean()), 5),
            "mae_medel": round(float(m2.mean()), 5),
            "return_medel": round(float(tot.mean()), 5),
            "fangstgrad_median": round(float(np.median(fang)), 4),
            "lagen": ut_lage, "korr_retfore_dvikt": round(kor_rd, 4)}, ep


# ---------------------------------------------------------------- STEG 2
def steg2(F, fonster):
    nA, tA, hA = kor(F, "A")
    nB, tB, hB = kor(F, "B")
    # invariantkontroll
    avvik = sum(1 for a, b in zip(hA, hB) if set(a["vikter"]) != set(b["vikter"]))
    sA, sB = S.stat(nA), S.stat(nB)
    kA, kB = koncentration(hA), koncentration(hB)
    print(f"\n{'-'*74}\nSTEG 2 — G29 ABLATION   {fonster}")
    print(f"  INVARIANT: paneler med olika namnuppsättning: {avvik}  "
          f"{'OK' if avvik == 0 else 'TESTET OGILTIGT'}")
    print(f"  {'':<22}{'A RESET':>12}{'B DRIFT':>12}{'B - A':>12}")
    for etikett, a, b, f in (("CAGR", sA["cagr"], sB["cagr"], "{:+.2%}"),
                             ("total return", float(np.prod(1 + nA) - 1),
                              float(np.prod(1 + nB) - 1), "{:+.2%}"),
                             ("volatilitet", sA["vol"], sB["vol"], "{:+.2%}"),
                             ("maxDD", sA["maxdd"], sB["maxdd"], "{:+.2%}"),
                             ("Sharpe", sA["sharpe"], sB["sharpe"], "{:+.3f}"),
                             ("omsättning/år", float(tA.mean()) * PPY,
                              float(tB.mean()) * PPY, "{:+.2%}"),
                             ("kostnad/år", float(tA.mean()) * PPY * COST,
                              float(tB.mean()) * PPY * COST, "{:+.3%}"),
                             ("max vikt medel", kA["max_vikt_medel"], kB["max_vikt_medel"], "{:+.4f}"),
                             ("max vikt högsta", kA["max_vikt_hogsta"], kB["max_vikt_hogsta"], "{:+.4f}"),
                             ("effektivt antal", kA["effektivt_antal_medel"],
                              kB["effektivt_antal_medel"], "{:+.2f}")):
        fm = "{:>12.2%}" if "%" in f else ("{:>12.3f}" if ".3f" in f else
                                           ("{:>12.4f}" if ".4f" in f else "{:>12.2f}"))
        print(f"  {etikett:<22}" + fm.format(a) + fm.format(b) + f"{f.format(b-a):>12}")

    bo = S.boot(nB, nA)
    print(f"  bootstrap B-A: Δ {bo['delta_cagr']:+.2%}  "
          f"KI [{bo['ki_lo']:+.2%},{bo['ki_hi']:+.2%}]  t {bo['t']:+.2f}")

    # attribution
    dg = []
    for a, b in zip(hA, hB):
        koder = set(a["vikter"]) | set(b["vikter"])
        upp = sum((b["vikter"].get(k, 0) - a["vikter"].get(k, 0)) * a["avk"].get(k, 0)
                  for k in koder if b["vikter"].get(k, 0) > a["vikter"].get(k, 0))
        ner = sum((b["vikter"].get(k, 0) - a["vikter"].get(k, 0)) * a["avk"].get(k, 0)
                  for k in koder if b["vikter"].get(k, 0) < a["vikter"].get(k, 0))
        dg.append((upp, ner))
    upp = float(np.sum([x[0] for x in dg])); ner = float(np.sum([x[1] for x in dg]))
    kost = float((tA.mean() - tB.mean()) * len(tA) * COST)
    print(f"\n  ATTRIBUTION (summerad över perioden, aritmetiskt)")
    print(f"    1+2. övervikt i drivna vinnare:      {upp:+.2%}")
    print(f"       undervikt i drivna förlorare:     {ner:+.2%}")
    print(f"    3.  lägre omsättningskostnad i B:    {kost:+.2%}")
    print(f"       summa:                            {upp+ner+kost:+.2%}")

    # robusthet: leave-one-largest-contributor-out
    bidrag = defaultdict(float)
    for a, b in zip(hA, hB):
        for k in set(a["vikter"]) | set(b["vikter"]):
            bidrag[k] += (b["vikter"].get(k, 0) - a["vikter"].get(k, 0)) * a["avk"].get(k, 0)
    topp = sorted(bidrag.items(), key=lambda x: -abs(x[1]))[:5]
    print(f"\n  ROBUSTHET — fem största bidragsgivare till skillnaden")
    for k, v in topp:
        print(f"    {k:<10}{v:>+9.2%}")
    andel = abs(topp[0][1]) / max(1e-9, abs(upp + ner)) if topp else 0
    print(f"    största enskilda namnets andel av viktdifferensen: {andel:.0%}")

    return {"invariant_avvikelser": avvik,
            "A": {**sA, "oms_ar": round(float(tA.mean()) * PPY, 4), **kA},
            "B": {**sB, "oms_ar": round(float(tB.mean()) * PPY, 4), **kB},
            "B_minus_A": {"cagr": round(sB["cagr"] - sA["cagr"], 5),
                          "sharpe": round(sB["sharpe"] - sA["sharpe"], 4),
                          "maxdd": round(sB["maxdd"] - sA["maxdd"], 5),
                          "oms_ar": round(float(tB.mean() - tA.mean()) * PPY, 5)},
            "bootstrap": bo,
            "attribution": {"overvikt_vinnare": round(upp, 5), "undervikt_forlorare": round(ner, 5),
                            "kostnadsdiff": round(kost, 5)},
            "storsta_bidragsgivare": [{"kod": k, "bidrag": round(v, 5)} for k, v in topp],
            "storsta_namnets_andel": round(float(andel), 4),
            "paths": {"A": [round(float(x), 6) for x in nA],
                      "B": [round(float(x), 6) for x in nB]}}


def main():
    ut = {"version": "G27_G28_G29_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": "e2a0675a4614e379a0148c84c1c997d01371c0d70741d2c64f70c1c5ed690c71",
          "fonster": {}}
    alla_ep = []
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        nA, tA, hA = kor(F, "A")
        d1, ep = steg1(F, hA, namn)
        alla_ep.extend(ep)
        d2 = steg2(F, namn)
        ut["fonster"][w_] = {"steg1_mfe_mae": d1, "steg2_ablation": d2}

    with open(EP, "w") as f:
        for e in alla_ep:
            f.write(json.dumps(e, ensure_ascii=False, default=float) + "\n")
    PATHS.write_text(json.dumps(
        {w: {"A": ut["fonster"][w]["steg2_ablation"]["paths"]["A"],
             "B": ut["fonster"][w]["steg2_ablation"]["paths"]["B"]} for w in ut["fonster"]},
        ensure_ascii=False))
    for w in ut["fonster"]:
        ut["fonster"][w]["steg2_ablation"].pop("paths")

    a = ut["fonster"]["2020_2026"]["steg2_ablation"]["B_minus_A"]["cagr"]
    b = ut["fonster"]["2014_2019"]["steg2_ablation"]["B_minus_A"]["cagr"]
    if a > 0.005 and b > 0.005:
        dom = "FALSIFIERAD — DRIFT slår RESET med >0,5 pp i BÅDA fönstren"
    elif (a > 0.005) != (b > 0.005) and max(a, b) > 0.005:
        dom = "PROMISING-BUT-UNSTABLE — effekten finns bara i ett fönster"
    else:
        dom = "NO MATERIAL RESET DRAG"
    ut["dom"] = dom
    ut["B_minus_A_cagr"] = {"2020_2026": a, "2014_2019": b}
    print(f"\n{'='*74}\nB − A CAGR: {a:+.2%} (2020-2026)  /  {b:+.2%} (2014-2019)")
    print(f"DOM: {dom}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nEpisoder: {EP}\nPortföljbanor: {PATHS}")


if __name__ == "__main__":
    main()
