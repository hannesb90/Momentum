"""G97-P — HIGH-VOL TAIL EXCLUSION PÅ LOCKED H0

Förregistrerad i ledgern efter G97. SEX namn är låst (6/30 = 20 % = den högsta
volatilitetskvintilen som motiverade testet). Ingen alternativ kvantil, ingen
voltröskel, ingen viktvariant, ingen parameterrobusthet kring sex.

REGELN
  1. H0:s ordinarie topp-30 enligt locked H0.
  2. PIT vol_52w, exakt G97:s definition (ISO-veckor, oberoende
     veckorekonstruktion, minst 45 av 52 veckoavkastningar).
  3. De SEX med högst vol_52w exkluderas.
  4. Ersätts av de nästa H0-rankade kandidaterna — rank 31 till 36 — valda
     ENBART på H0-rank. Ingen vol-optimering bland ersättarna.
  5. Allt annat identiskt med canonical locked H0.

KONSEKVENS FÖR PLACEBOT
  Eftersom ersättarna alltid är rank 31-36 är regelns ENDA val vilka sex som
  kastas ut. Placebot behöver därför bara slumpa den delen, med exakt samma
  ersättarpool. Det ger en ovanligt ren matchning: ingen kandidatpool att
  approximera, inget rankdjup att gissa.

KEDJAN SOM PRÖVAS
  replikerad inkrementell prediction skill (G97, klar)
  -> decision skill (steg 3)
  -> matched-random selection skill (steg 2)
  -> portfolio value (steg 1)

Kör: /opt/momentum/venv/bin/python tools/g97p_hogvolsvans.py
"""
from __future__ import annotations
import bisect, json, math, sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g97p_results.json"
LEDGER = V2 / "research_k/g97p_panelledger.jsonl"
COST = 0.002
PPY = 13
N = 30
K = 6                      # LÅST
DRAG = 1000
SEED = 20260817
HOR = [(1, "4v"), (2, "8v"), (3, "12v"), (6, "24v")]
MIN_VECKOR = 45

_D, _V, _VOL = {}, {}, {}


def dagsserie(F, k):
    n = (id(F), k)
    if n not in _D:
        if F is S.F19:
            s = M.SERIE.get(k)
            _D[n] = None if s is None else \
                (s[0].astype("datetime64[D]").astype(str).tolist(), np.asarray(s[1]))
        else:
            s = S.PS26.get(k)
            _D[n] = None if s is None else (list(s[0]), np.asarray(s[1]))
    return _D[n]


def veckoserie(F, k):
    n = (id(F), k)
    if n in _V:
        return _V[n]
    s = dagsserie(F, k)
    if s is None:
        _V[n] = None
        return None
    ds, adj = s
    sista = {}
    for i, d in enumerate(ds):
        y, wk, _ = date.fromisoformat(d).isocalendar()
        sista[(y, wk)] = i
    idx = [sista[x] for x in sorted(sista)]
    _V[n] = ([ds[i] for i in idx], adj[idx])
    return _V[n]


def vol52(F, k, dt):
    n = (id(F), k, dt)
    if n in _VOL:
        return _VOL[n]
    v = veckoserie(F, k)
    r = None
    if v is not None:
        wd, wp = v
        j = bisect.bisect_right(wd, dt)          # PIT: endast t.o.m. paneldatum
        fon = wp[max(0, j - 53):j]
        if len(fon) >= MIN_VECKOR + 1:
            ret = fon[1:] / fon[:-1] - 1
            r = float(np.std(ret, ddof=1))
    _VOL[n] = r
    return r


def kor(F, regel=None, rng=None, samla=False):
    """regel: None = locked H0. 'g97p' = exkludera sex högsta vol.
       'placebo' = exkludera sex slumpmässiga. Ersättare alltid rank 31-36."""
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    w, nets, turns, hist, inv = {}, [], [], [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        koder = [r["kod"] for r in raw]
        if schedf(pi, dt) or not w:
            top = koder[:N]
            bort, ers, n_data = [], [], None
            if regel:
                v = {k: vol52(F, k, dt) for k in top}
                med = {k: x for k, x in v.items() if x is not None}
                n_data = len(med)
                if n_data >= 20 and len(koder) >= N + K:
                    if regel == "g97p":
                        bort = sorted(med, key=lambda k: -med[k])[:K]
                    else:
                        bort = list(rng.choice(top, size=K, replace=False))
                    ers = koder[N:N + K]
                    sel = [k for k in top if k not in bort] + ers
                else:
                    sel = top
            else:
                sel = top
            if samla and bort:
                rm = {k: i + 1 for i, k in enumerate(koder)}
                hist.append({"pi": pi, "dt": dt, "n_med_voldata": n_data,
                             "topp30": top, "bort": bort, "ers": ers,
                             "bort_vol": [round(v[k], 5) for k in bort],
                             "bort_rank": [rm[k] for k in bort],
                             "ers_rank": [rm[k] for k in ers],
                             "rankdjup": N + K})
            mal = {k: 1.0 / N for k in sel}
            t_ = sum(mal.values())
            mal = {k: x / t_ for k, x in mal.items()} if t_ > 0 else {}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0)) for k in set(mal) | set(w)) / 2.0
            inv.append({"pi": pi, "n": len(sel), "n_bort": len(bort), "n_ers": len(ers)})
        else:
            mal = dict(w); turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        g = float(sum(mal[k] * r[k] for k in mal))
        nets.append(g - COST * turn)
        turns.append(turn)
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: x / s_ for k, x in ny.items()} if s_ > 0 else {}
    return np.array(nets), np.array(turns), hist, inv


def framat(F, k, pi, h):
    dts, ret = F["eval_dates"], F["returns_map"]
    if pi + h > len(dts):
        return None
    p = 1.0
    for i in range(pi, pi + h):
        v = ret.get((k, dts[i]))
        if v is None:
            return None
        p *= (1 + v)
    return p - 1


def nw_t(x, lag):
    """Newey-West t för medelvärdet av en serie, lag = h-1."""
    x = np.asarray(x, float); n = len(x)
    if n < 5:
        return float("nan")
    e = x - x.mean()
    g0 = float(e @ e) / n
    s = g0
    for L in range(1, min(lag, n - 1) + 1):
        gl = float(e[L:] @ e[:-L]) / n
        s += 2 * (1 - L / (lag + 1)) * gl
    if s <= 0:
        return float("nan")
    return float(x.mean() / math.sqrt(s / n))


def main():
    ut = {"version": "G97P_HOGVOLSVANS_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "K_last": K, "n_placebodragningar": DRAG, "seed": SEED,
          "regel": "exkludera de sex hogsta vol_52w i topp-30, ersatt med rank 31-36",
          "fonster": {}}
    alla_ev = []

    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        nH, tH, _, invH = kor(F)
        nG, tG, hist, invG = kor(F, regel="g97p", samla=True)
        sH, sG = S.stat(nH), S.stat(nG)
        dG = sG["cagr"] - sH["cagr"]

        # ---- A. invarianter
        n30 = all(x["n"] == N for x in invG)
        exakt6 = sum(1 for x in invG if x["n_bort"] == K)
        rebal = len(invG)
        print(f"\n{'='*78}\n{namn}")
        print(f"  A. INVARIANTER")
        print(f"    N=30 varje rebalanspanel: {'JA' if n30 else 'NEJ'}")
        print(f"    exakt sex exkluderingar: {exakt6} av {rebal} rebalanspaneler")
        print(f"    ersattarnas rankdjup: alltid 31-36 (last av regeln)")
        print(f"    voldata tillgänglig for i snitt "
              f"{np.mean([h['n_med_voldata'] for h in hist]):.1f} av 30 namn")

        # ---- B. portföljresultat
        print(f"\n  B. PORTFOLJRESULTAT")
        print(f"    {'':<20}{'locked H0':>13}{'G97-P':>13}{'diff':>12}")
        for et, a, b, f in (("CAGR", sH["cagr"], sG["cagr"], "%"),
                            ("total return", float(np.prod(1 + nH) - 1), float(np.prod(1 + nG) - 1), "%"),
                            ("volatilitet", sH["vol"], sG["vol"], "%"),
                            ("maxDD", sH["maxdd"], sG["maxdd"], "%"),
                            ("Sharpe", sH["sharpe"], sG["sharpe"], "f"),
                            ("omsattning/ar", tH.mean() * PPY, tG.mean() * PPY, "%"),
                            ("kostnad/ar", tH.mean() * PPY * COST, tG.mean() * PPY * COST, "%")):
            g = "{:>13.2%}{:>13.2%}{:>12.2%}" if f == "%" else "{:>13.3f}{:>13.3f}{:>12.3f}"
            print(f"    {et:<20}" + g.format(a, b, b - a))
        bo = S.boot(nG, nH)
        print(f"    bootstrap: Δ {bo['delta_cagr']:+.2%} KI [{bo['ki_lo']:+.2%},{bo['ki_hi']:+.2%}] "
              f"t {bo['t']:+.2f}")
        print(f"    (likavikt => effektivt antal 30, hogsta vikt 1/30, oforandrat)")

        # ---- C. matched-random placebo
        rng = np.random.default_rng(SEED)
        pd_ = np.array([S.stat(kor(F, regel="placebo", rng=rng)[0])["cagr"] - sH["cagr"]
                        for _ in range(DRAG)])
        perc = float((pd_ < dG).mean()); p1 = float((pd_ >= dG).mean())
        print(f"\n  C. MATCHED-RANDOM PLACEBO ({DRAG} dragningar)")
        print(f"    placebo Δ CAGR: medel {pd_.mean():+.2%}  median {np.median(pd_):+.2%}")
        print(f"      p5 {np.percentile(pd_,5):+.2%}   p95 {np.percentile(pd_,95):+.2%}")
        print(f"    G97-P Δ {dG:+.2%}  →  percentil {perc:.1%}   ensidigt p = {p1:.4f}")
        print(f"    andel placebo som slar G97-P: {p1:.1%}")
        klarar = p1 < 0.05
        print(f"    KLARAR PLACEBO: {'JA' if klarar else 'NEJ'}")

        # ---- D. decision skill B − A
        rader = []
        for h in hist:
            for a, b in zip(h["bort"], h["ers"]):
                rad = {"fonster": namn, "dt": h["dt"], "A_bort": a, "B_ers": b}
                for hh, e in HOR:
                    ra, rb = framat(F, a, h["pi"], hh), framat(F, b, h["pi"], hh)
                    rad[f"BmA_{e}"] = (rb - ra) if (ra is not None and rb is not None) else None
                rader.append(rad)
        alla_ev.extend(rader)
        print(f"\n  D. DECISION SKILL — ersattare minus utkastad ({len(rader)} par)")
        print(f"    {'horisont':<9}{'medel':>9}{'median':>9}{'hit':>7}{'trimmat':>10}"
              f"{'t naiv':>8}{'t Regel6':>10}{'t NW':>8}")
        dsk = {}
        for hh, e in HOR:
            v = np.array([r[f"BmA_{e}"] for r in rader if r.get(f"BmA_{e}") is not None])
            if len(v) < 10:
                continue
            per_panel = defaultdict(list)
            for r in rader:
                if r.get(f"BmA_{e}") is not None:
                    per_panel[r["dt"]].append(r[f"BmA_{e}"])
            ps = np.array([np.mean(x) for _, x in sorted(per_panel.items())])
            tn = float(ps.mean() / (ps.std(ddof=1) / math.sqrt(len(ps))))
            lo, hi = np.percentile(v, [1, 99])
            trim = v[(v >= lo) & (v <= hi)]
            dsk[e] = {"medel": round(float(v.mean()), 5), "median": round(float(np.median(v)), 5),
                      "hit_rate": round(float((v > 0).mean()), 4),
                      "trimmat_1_99": round(float(trim.mean()), 5),
                      "t_naiv": round(tn, 2), "t_regel6": round(tn / math.sqrt(hh), 2),
                      "t_newey_west": round(nw_t(ps, hh - 1), 2), "n_par": len(v),
                      "n_paneler": len(ps)}
            print(f"    {e:<9}{v.mean():>+9.2%}{np.median(v):>+9.2%}{(v>0).mean():>7.1%}"
                  f"{trim.mean():>+10.2%}{tn:>8.2f}{tn/math.sqrt(hh):>+10.2f}"
                  f"{dsk[e]['t_newey_west']:>8.2f}")

        # ---- E. robusthet
        print(f"\n  E. ROBUSTHET (horisont 12v)")
        v12 = [(r["A_bort"], r["B_ers"], r.get("BmA_12v")) for r in rader if r.get("BmA_12v") is not None]
        arr = np.array([x[2] for x in v12])
        per_a = defaultdict(list)
        for a, b, x in v12:
            per_a[a].append(x)
        topp = sorted(per_a.items(), key=lambda y: -abs(sum(y[1])))[:3]
        utan = float(np.mean([x for a, b, x in v12 if a != topp[0][0]])) if topp else arr.mean()
        per_dt = defaultdict(list)
        for r in rader:
            if r.get("BmA_12v") is not None:
                per_dt[r["dt"]].append(r["BmA_12v"])
        varsta_panel = max(per_dt.items(), key=lambda y: abs(np.sum(y[1])))
        print(f"    otrimmat {arr.mean():+.2%}   1 %-trimmat "
              f"{np.mean(arr[(arr>=np.percentile(arr,1))&(arr<=np.percentile(arr,99))]):+.2%}")
        print(f"    tre storsta namnbidrag: "
              f"{', '.join(f'{k} ({sum(x):+.1%})' for k, x in topp)}")
        print(f"    utan {topp[0][0]}: {utan:+.2%}")
        print(f"    storsta enskilda panel: {varsta_panel[0]} ({np.sum(varsta_panel[1]):+.1%})")

        ut["fonster"][w_] = {
            "invarianter": {"N30_alla_paneler": bool(n30), "exakt_sex": exakt6,
                            "rebalanspaneler": rebal, "rankdjup": N + K,
                            "voldata_snitt": round(float(np.mean([h["n_med_voldata"] for h in hist])), 1)},
            "h0": sH, "g97p": sG, "delta_cagr": round(dG, 5), "bootstrap": bo,
            "oms_ar": {"h0": round(float(tH.mean()) * PPY, 4), "g97p": round(float(tG.mean()) * PPY, 4)},
            "placebo": {"medel": round(float(pd_.mean()), 5), "median": round(float(np.median(pd_)), 5),
                        "p5": round(float(np.percentile(pd_, 5)), 5),
                        "p95": round(float(np.percentile(pd_, 95)), 5),
                        "g97p_percentil": round(perc, 4), "p_ensidigt": round(p1, 4),
                        "andel_slar_g97p": round(p1, 4), "klarar": bool(klarar)},
            "decision_skill": dsk,
            "robusthet_12v": {"otrimmat": round(float(arr.mean()), 5),
                              "utan_storsta_namn": round(float(utan), 5),
                              "storsta_namn": topp[0][0] if topp else None,
                              "storsta_panel": varsta_panel[0],
                              "storsta_panel_bidrag": round(float(np.sum(varsta_panel[1])), 5)}}
        with open(LEDGER, "a" if w_ != "2020_2026" else "w") as f:
            for h in hist:
                f.write(json.dumps({"fonster": namn, **h}, ensure_ascii=False, default=float) + "\n")

    a = ut["fonster"]["2020_2026"]; b = ut["fonster"]["2014_2019"]
    kl = a["placebo"]["klarar"] and b["placebo"]["klarar"]
    ds_samma = all((a["decision_skill"].get(e, {}).get("medel", 0) > 0) ==
                   (b["decision_skill"].get(e, {}).get("medel", 0) > 0)
                   for e in a["decision_skill"] if e in b["decision_skill"])
    if not kl:
        dom = "REPLICATED PREDICTION SKILL BUT NO REPLICATED PORTFOLIO VALUE"
    elif not ds_samma:
        dom = "PORTFOLIO EFFECT WITHOUT STABLE DECISION MECHANISM"
    else:
        dom = "REPLICATED H0 IMPROVEMENT CANDIDATE"
    ut["slutklassificering"] = dom
    ut["steg4_mekanism"] = ("EJ LICENSIERAD — kravde att placebot klarades i bada fonstren"
                            if not kl else "LICENSIERAD")
    print(f"\n{'='*78}\nΔ CAGR: {a['delta_cagr']:+.2%} / {b['delta_cagr']:+.2%}")
    print(f"Placebo klarad: {a['placebo']['klarar']} / {b['placebo']['klarar']}")
    print(f"SLUTKLASSIFICERING: {dom}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nPanelledger: {LEDGER}")


if __name__ == "__main__":
    main()
