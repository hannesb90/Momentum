"""G101 — REGIMBEROENDE I CANONICAL LOCKED H0

Diagnostiskt. Ingen gate, ingen tradingregel, ingen G97-variant, ingen
parameteroptimering. H0 helt oförändrad.

FRÅGAN: är H0:s överavkastning mot sitt eget likaviktade investerbara universum
materiellt olika mellan ex ante identifierbara marknadsregimer?

REGIMVARIABLER — endast befintliga PIT-features ur featureregistret
  market_regime_trend = index[T] / SMA(index, 26 v) − 1
  market_regime_vol   = std(index veckoavkastningar, 13 v)

  Ingen VIX, ingen ny regimfeature, ingen kombinationsregim.

INDEXPROXY
  Ingen PIT-indexserie finns i det frysta lagret för 2014-2019. Indexet byggs
  därför som den kumulativa likaviktade universumavkastningen per ISO-vecka —
  samma marknadsproxy som i G97-P:s confounderaudit. Det är en dokumenterad
  approximation, inte ett riktigt index.

TERCILER
  Sätts EXPANDERANDE: gränserna för panel i beräknas enbart ur regimvärden
  observerade vid panel 0..i−1. Minst 12 föregående paneler krävs; paneler före
  det redovisas som oklassificerade. Ingen full-sample-kvantil används.

FALSIFIERING (förregistrerad)
  HIGH − LOW > 5 pp annualiserad överavkastning OCH samma riktning separat i
  2014-2019 och 2020-2026. Poolat resultat får aldrig ensamt falsifiera.

TOLKNINGSGRÄNS
  Testet prövar A: "H0 har regimberoende alfa". Det prövar INTE B: "regimtiming
  kan förbättra H0". Även om A visas är B helt oprövat.

Kör: /opt/momentum/venv/bin/python tools/g101_regimberoende.py
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

OUT = V2 / "research_k/g101_regimberoende_results.json"
PANEL = V2 / "research_k/g101_paneldata.jsonl"
COST = 0.002
PPY = 13
N = 30
MIN_HIST = 12
TRENDFON = 26
VOLFON = 13

_D, _W = {}, {}


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


def veckor(F, k):
    n = (id(F), k)
    if n in _W:
        return _W[n]
    s = dagsserie(F, k)
    if s is None:
        _W[n] = None
        return None
    ds, adj = s
    sista = {}
    for i, d in enumerate(ds):
        y, wk, _ = date.fromisoformat(d).isocalendar()
        sista[(y, wk)] = i
    nyck = sorted(sista)
    idx = [sista[x] for x in nyck]
    _W[n] = (nyck, [ds[i] for i in idx], adj[idx])
    return _W[n]


def indexserie(F):
    """Likaviktad universumavkastning per ISO-vecka -> indexnivå från 100."""
    per = defaultdict(list)
    alla = {r["kod"] for dt in F["eval_dates"] for r in F["rankings"][dt]}
    for k in alla:
        w = veckor(F, k)
        if w is None:
            continue
        nyck, wd, wp = w
        r = wp[1:] / wp[:-1] - 1
        for i in range(len(r)):
            if np.isfinite(r[i]) and abs(r[i]) < 3:
                per[nyck[i + 1]].append(float(r[i]))
    nyck = sorted(k for k, v in per.items() if len(v) >= 20)
    ret = [float(np.mean(per[k])) for k in nyck]
    niva, v = [100.0], 100.0
    for r in ret:
        v *= (1 + r)
        niva.append(v)
    # slutdatum per vecka för PIT-uppslag
    slut = {}
    for k in alla:
        w = veckor(F, k)
        if w is None:
            continue
        for kk, dd in zip(w[0], w[1]):
            slut[kk] = max(slut.get(kk, ""), dd)
    datum = [slut.get(k, "") for k in nyck]
    return nyck, datum, np.array(niva[1:]), np.array(ret)


def regimvarden(F):
    """-> {paneldatum: (trend, vol)}, endast information t.o.m. paneldatum."""
    nyck, datum, niva, ret = indexserie(F)
    ut = {}
    for dt in F["eval_dates"]:
        j = bisect.bisect_right(datum, dt)
        if j < max(TRENDFON, VOLFON) + 1:
            ut[dt] = (None, None)
            continue
        sma = float(np.mean(niva[j - TRENDFON:j]))
        trend = float(niva[j - 1] / sma - 1) if sma > 0 else None
        vol = float(np.std(ret[j - VOLFON:j], ddof=1))
        ut[dt] = (trend, vol)
    return ut


def h0(F):
    """Canonical locked H0 + universumavkastning per panel."""
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    w, nets, univ = {}, [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w:
            sel = [r["kod"] for r in raw][:N]
            mal = {k: 1.0 / N for k in sel}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0)) for k in set(mal) | set(w)) / 2.0
        else:
            mal = dict(w); turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        nets.append(float(sum(mal[k] * r[k] for k in mal)) - COST * turn)
        univ.append(float(np.mean([ret.get((x["kod"], dt), 0.0) for x in raw])))
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return np.array(nets), np.array(univ)


def expanderande_tercil(varden):
    """Klassificering enbart på föregående observationer. -1 = oklassificerad."""
    ut = []
    for i, v in enumerate(varden):
        hist = [x for x in varden[:i] if x is not None]
        if v is None or len(hist) < MIN_HIST:
            ut.append(None); continue
        q1, q2 = np.quantile(hist, [1 / 3, 2 / 3])
        ut.append("LOW" if v <= q1 else ("HIGH" if v > q2 else "MID"))
    return ut


def statistik(h, u, mask):
    if mask.sum() < 4:
        return None
    hh, uu = h[mask], u[mask]
    exc = hh - uu
    ann = float((np.prod(1 + hh) / np.prod(1 + uu)) ** (PPY / mask.sum()) - 1)
    v = float(exc.std(ddof=1) * math.sqrt(PPY)) if mask.sum() > 2 else None
    return {"n_paneler": int(mask.sum()), "annualiserad_excess": round(ann, 5),
            "medel_panel_excess": round(float(exc.mean()), 5),
            "median": round(float(np.median(exc)), 5),
            "hit_rate": round(float((exc > 0).mean()), 4),
            "volatilitet_excess": round(v, 5) if v else None,
            "ir": round(float(exc.mean() * PPY / v), 3) if v and v > 0 else None,
            "h0_ann": round(float(np.prod(1 + hh) ** (PPY / mask.sum()) - 1), 5),
            "univ_ann": round(float(np.prod(1 + uu) ** (PPY / mask.sum()) - 1), 5)}


def high_minus_low(h, u, terc):
    a = statistik(h, u, np.array([t == "HIGH" for t in terc]))
    b = statistik(h, u, np.array([t == "LOW" for t in terc]))
    if a is None or b is None:
        return None, a, b
    return a["annualiserad_excess"] - b["annualiserad_excess"], a, b


def block_bootstrap(h, u, terc, draws=2000, block=13, seed=20260817):
    rng = np.random.default_rng(seed)
    n = len(h); nb = int(math.ceil(n / block)); ut = []
    for _ in range(draws):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, max(1, n - block + 1))
            idx.extend(range(s, min(s + block, n)))
        idx = np.array(idx[:n])
        d, _, _ = high_minus_low(h[idx], u[idx], [terc[i] for i in idx])
        if d is not None:
            ut.append(d)
    a = np.array(ut)
    return {"medel": round(float(a.mean()), 5),
            "ki_lo": round(float(np.percentile(a, 2.5)), 5),
            "ki_hi": round(float(np.percentile(a, 97.5)), 5),
            "andel_positiva": round(float((a > 0).mean()), 4), "n_draws": len(a)}


def main():
    ut = {"version": "G101_REGIMBEROENDE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "syfte": "diagnostiskt: har locked H0 regimberoende alfa? Prövar A, inte B.",
          "indexproxy": "kumulativ likaviktad universumavkastning per ISO-vecka; ingen "
                        "PIT-indexserie finns for 2014-2019",
          "tercilmetod": f"expanderande, minst {MIN_HIST} foregaende paneler",
          "falsifiering": "HIGH-LOW > 5 pp annualiserad excess OCH samma riktning i bada fonstren",
          "fonster": {}}
    rader = []
    poolat = {"trend": {"h": [], "u": [], "t": []}, "vol": {"h": [], "u": [], "t": []}}

    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        nets, univ = h0(F)
        rv = regimvarden(F)
        dts = F["eval_dates"]
        tr = [rv[d][0] for d in dts]
        vo = [rv[d][1] for d in dts]
        t_tr = expanderande_tercil(tr)
        t_vo = expanderande_tercil(vo)
        print(f"\n{'='*78}\n{namn}   locked H0 "
              f"{np.prod(1+nets)**(PPY/len(nets))-1:.2%}   universum "
              f"{np.prod(1+univ)**(PPY/len(univ))-1:.2%}")

        # A. invarianter
        print(f"  A. PIT OCH INVARIANTER")
        print(f"    paneler {len(dts)}   H0 reproducerar: "
              f"{'JA' if abs((np.prod(1+nets)**(PPY/len(nets))-1) - (0.0720 if w_=='2020_2026' else 0.3156)) < 0.001 else 'AVVIKER'}")
        print(f"    regimvarden med varde: trend {sum(x is not None for x in tr)}, "
              f"vol {sum(x is not None for x in vo)}")
        print(f"    oklassificerade paneler (expanderande krav): "
              f"trend {sum(t is None for t in t_tr)}, vol {sum(t is None for t in t_vo)}")

        rad = {"h0_ann": round(float(np.prod(1+nets)**(PPY/len(nets))-1), 5),
               "univ_ann": round(float(np.prod(1+univ)**(PPY/len(univ))-1), 5),
               "n_paneler": len(dts)}
        for etikett, terc, varden in (("trend", t_tr, tr), ("vol", t_vo, vo)):
            print(f"\n  {'C' if etikett=='trend' else 'D'}. REGIM: market_regime_{etikett}")
            fordel = {g: sum(1 for t in terc if t == g) for g in ("LOW", "MID", "HIGH")}
            print(f"    fordelning LOW/MID/HIGH: {fordel['LOW']}/{fordel['MID']}/{fordel['HIGH']}"
                  f"   oklassificerade {sum(t is None for t in terc)}")
            print(f"    {'tercil':<8}{'n':>5}{'ann.excess':>12}{'medel':>9}{'median':>9}"
                  f"{'hit':>7}{'IR':>7}{'H0 ann':>10}{'univ ann':>10}")
            per = {}
            for g in ("LOW", "MID", "HIGH"):
                st = statistik(nets, univ, np.array([t == g for t in terc]))
                per[g] = st
                if st:
                    print(f"    {g:<8}{st['n_paneler']:>5}{st['annualiserad_excess']:>+12.2%}"
                          f"{st['medel_panel_excess']:>+9.2%}{st['median']:>+9.2%}"
                          f"{st['hit_rate']:>7.0%}"
                          f"{(st['ir'] if st['ir'] is not None else float('nan')):>7.2f}"
                          f"{st['h0_ann']:>+10.2%}{st['univ_ann']:>+10.2%}")
                else:
                    print(f"    {g:<8}   FOR FA PANELER")
            hml, a, b = high_minus_low(nets, univ, terc)
            bs = block_bootstrap(nets, univ, terc) if hml is not None else None
            mono = None
            if all(per[g] for g in ("LOW", "MID", "HIGH")):
                x = [per[g]["annualiserad_excess"] for g in ("LOW", "MID", "HIGH")]
                mono = "stigande" if x[0] <= x[1] <= x[2] else \
                       ("fallande" if x[0] >= x[1] >= x[2] else "ej monoton")
            print(f"    HIGH − LOW: {hml:+.2%}" if hml is not None else "    HIGH − LOW: n/a")
            if bs:
                print(f"      block-bootstrap KI [{bs['ki_lo']:+.2%}, {bs['ki_hi']:+.2%}]  "
                      f"andel positiva {bs['andel_positiva']:.0%}")
            print(f"      monotonicitet LOW→MID→HIGH: {mono}")

            # F. robusthet
            mHI = np.array([t == "HIGH" for t in terc]); mLO = np.array([t == "LOW" for t in terc])
            rob = {}
            if hml is not None:
                loo = []
                for i in range(len(nets)):
                    kv = np.arange(len(nets)) != i
                    d2, _, _ = high_minus_low(nets[kv], univ[kv], [terc[j] for j in range(len(terc)) if j != i])
                    if d2 is not None:
                        loo.append(d2)
                exc = nets - univ
                gr = np.percentile(np.abs(exc), 95)
                kv = np.abs(exc) <= gr
                d3, _, _ = high_minus_low(nets[kv], univ[kv], [terc[j] for j in range(len(terc)) if kv[j]])
                bidrag = [(dts[i], float(exc[i])) for i in range(len(exc)) if mHI[i] or mLO[i]]
                storst = max(bidrag, key=lambda x: abs(x[1])) if bidrag else None
                rob = {"loo_min": round(float(np.min(loo)), 5), "loo_max": round(float(np.max(loo)), 5),
                       "trimmat_5pct": round(d3, 5) if d3 is not None else None,
                       "storsta_panel": storst[0] if storst else None,
                       "storsta_panel_excess": round(storst[1], 5) if storst else None}
                print(f"      robusthet: leave-one-panel-out [{rob['loo_min']:+.2%}, "
                      f"{rob['loo_max']:+.2%}]   5 %-trimmat "
                      f"{(rob['trimmat_5pct'] if rob['trimmat_5pct'] is not None else float('nan')):+.2%}")
                print(f"      storsta enskilda panel: {rob['storsta_panel']} "
                      f"({rob['storsta_panel_excess']:+.2%})")
            rad[etikett] = {"fordelning": fordel, "per_tercil": per, "high_minus_low": hml,
                            "bootstrap": bs, "monotonicitet": mono, "robusthet": rob}
            poolat[etikett]["h"].extend(nets.tolist())
            poolat[etikett]["u"].extend(univ.tolist())
            poolat[etikett]["t"].extend(terc)
        ut["fonster"][w_] = rad
        for i, dt in enumerate(dts):
            rader.append({"fonster": namn, "dt": dt, "h0": round(float(nets[i]), 6),
                          "univ": round(float(univ[i]), 6), "trend": tr[i], "vol": vo[i],
                          "tercil_trend": t_tr[i], "tercil_vol": t_vo[i]})

    # E. tvåfönsterreplikation + poolat
    print(f"\n{'='*78}\nE. HIGH − LOW, TVÅFÖNSTERREPLIKATION")
    print(f"  {'regim':<8}{'2020-2026':>13}{'2014-2019':>13}{'poolat':>11}"
          f"{'samma tecken':>15}{'>5 pp bada':>12}")
    ut["replikering"] = {}
    for etikett in ("trend", "vol"):
        a = ut["fonster"]["2020_2026"][etikett]["high_minus_low"]
        b = ut["fonster"]["2014_2019"][etikett]["high_minus_low"]
        ph = np.array(poolat[etikett]["h"]); pu = np.array(poolat[etikett]["u"])
        pp, _, _ = high_minus_low(ph, pu, poolat[etikett]["t"])
        samma = (a is not None and b is not None and (a > 0) == (b > 0))
        stor = (a is not None and b is not None and abs(a) > 0.05 and abs(b) > 0.05)
        falsifierad = bool(samma and stor)
        ut["replikering"][etikett] = {"f2020_2026": a, "f2014_2019": b, "poolat": pp,
                                      "samma_tecken": bool(samma),
                                      "over_5pp_bada": bool(stor),
                                      "falsifierar_nollhypotesen": falsifierad}
        print(f"  {etikett:<8}{(a if a is not None else float('nan')):>+13.2%}"
              f"{(b if b is not None else float('nan')):>+13.2%}"
              f"{(pp if pp is not None else float('nan')):>+11.2%}"
              f"{('JA' if samma else 'NEJ'):>15}{('JA' if stor else 'NEJ'):>12}")

    fals = any(v["falsifierar_nollhypotesen"] for v in ut["replikering"].values())
    if not fals:
        dom = "NO REPLICATED MATERIAL REGIME DEPENDENCE"
    else:
        instabil = False
        for et, v in ut["replikering"].items():
            if not v["falsifierar_nollhypotesen"]:
                continue
            for w_ in ("2020_2026", "2014_2019"):
                r = ut["fonster"][w_][et]
                bs = r.get("bootstrap") or {}
                if bs.get("ki_lo", -1) * bs.get("ki_hi", 1) < 0 or r.get("monotonicitet") == "ej monoton":
                    instabil = True
        dom = ("REPLICATED REGIME HETEROGENEITY — UNSTABLE" if instabil
               else "REPLICATED MATERIAL REGIME DEPENDENCE")
    ut["slutklassificering"] = dom
    print(f"\nSLUTKLASSIFICERING: {dom}")
    print("  (Testet provar A: har H0 regimberoende alfa. B: kan regimtiming forbattra H0 "
          "ar HELT OPROVAT.)")

    with open(PANEL, "w") as f:
        for r in rader:
            f.write(json.dumps(r, ensure_ascii=False, default=float) + "\n")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nPaneldata: {PANEL} ({len(rader)} paneler)")


if __name__ == "__main__":
    main()
