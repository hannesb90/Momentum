"""G13+G17 — PREMATURE EXIT & TREND RESUMPTION AUDIT FÖR FRYST H0

G19 visade att korta innehav har svag avkastning UNDER innehavstiden, men det
måttet är betingat på H0:s egen exitregel och duger inte som bevis. Detta test
mäter enbart vad som händer EFTER försäljningen — en period som inte ingår i
beslutet att sälja.

POPULATION
  Alla H0-innehav som säljs efter <= 2 paneler. Eftersom H0 ombalanserar varannan
  panel är detta exakt liktydigt med "såldes vid nästa ombalansering".

ERSÄTTARE
  De namn som kom IN vid samma ombalansering, likaviktade. I en likaviktad
  portfölj är det ekonomiskt exakt dit det frigjorda kapitalet gick.

HORISONTER
  +1, +2, +3, +4, +6 och +13 paneler. Panelen är 28 dagar, så 13 paneler är
  exakt 52 veckor och 6 paneler är 24 veckor. **26 veckor finns inte på det
  frusna beslutsrutnätet** och approximeras av 6 paneler; det redovisas som 24 v.
  Ingen daglig universumbenchmark existerar i det frysta lagret, så excess mäts
  på panelnivå. MAE/MFE och drawdown mäts på DAGLIGA priser, där ingen benchmark
  behövs.

EKONOMISK DEFINITION AV PREMATURE EXIT
  En exit är potentiellt undvikbar endast om ALLA tre gäller:
    1. den sålda aktien stiger absolut över horisonten
    2. den slår H0:s faktiska ersättare över samma horisont
    3. mellanperiodens nedgång gör inte exiten uppenbart rationell
       (operationaliserat: max adverse excursion efter exit är inte värre än -20 %)

  Enbart "aktien steg efter försäljning" räknas alltså INTE.

INGEN REGEL TESTAS. Ingen hysteres, inget band, ingen tuning.

Kör: /opt/momentum/venv/bin/python tools/g13_g17_premature_exit_audit.py
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

OUT = V2 / "research_k/g13_g17_premature_exit_results.json"
EVENTS = V2 / "research_k/g13_g17_premature_exit_events.jsonl"
COST = 0.002
N = 30
HOR = [1, 2, 3, 4, 6, 13]
HOR_ETIKETT = {1: "+1 panel (4v)", 2: "+2 (8v)", 3: "+3 (12v)", 4: "+4 (16v)",
               6: "+6 (24v)", 13: "+13 (52v)"}
PRIMAR = 4


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


def dagsbana(F, k, fran, till):
    """Dagliga justerade priser i (fran, till]. Första punkt = första handelsdag
    strikt efter fran, vilket är H0:s exekveringsdag."""
    s = serie(F, k)
    if s is None:
        return None, None
    ds, adj = s
    i = bisect.bisect_right(ds, fran)
    j = bisect.bisect_right(ds, till)
    if i >= len(ds) or j <= i:
        return None, None
    return ds[i:j], adj[i:j]


def kor_h0(F):
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    prev, urval = [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        elig = {r["kod"] for r in raw}
        if schedf(pi, dt) or not prev:
            sel = [r["kod"] for r in raw][:N]
        else:
            sel = [k for k in prev if k in elig]
            if len(sel) < N:
                sel += [r["kod"] for r in raw if r["kod"] not in sel][: N - len(sel)]
        urval.append(sel)
        prev = sel
    return urval


def kum(F, k, fran_pi, h):
    """Geometrisk avkastning för k över panelerna fran_pi .. fran_pi+h-1."""
    dts, ret = F["eval_dates"], F["returns_map"]
    if fran_pi + h > len(dts):
        return None
    p = 1.0
    for i in range(fran_pi, fran_pi + h):
        v = ret.get((k, dts[i]))
        if v is None:
            return None
        p *= (1 + v)
    return p - 1


def bygg(F, fonster):
    dts = F["eval_dates"]
    urval = kor_h0(F)
    univ = np.array([float(np.mean([F["returns_map"].get((r["kod"], dt), 0.0)
                                    for r in F["rankings"][dt]])) for dt in dts])

    # spelllängder
    per = defaultdict(list)
    for pi, sel in enumerate(urval):
        for k in sel:
            per[k].append(pi)
    korta = []          # (kod, start_pi, exit_pi)
    for k, idx in per.items():
        start = idx[0]; forra = idx[0]
        for i in idx[1:] + [None]:
            if i is None or i != forra + 1:
                langd = forra - start + 1
                exit_pi = forra + 1
                if langd <= 2 and exit_pi < len(dts):
                    korta.append((k, start, exit_pi))
                if i is not None:
                    start = i
            if i is not None:
                forra = i

    # inträden per panel = ersättarkorgen
    intraden = {}
    for pi in range(1, len(urval)):
        intraden[pi] = [k for k in urval[pi] if k not in urval[pi - 1]]

    ev = []
    for k, start_pi, exit_pi in korta:
        e = {"fonster": fonster, "kod": k, "exit_panel": dts[exit_pi],
             "exit_pi": exit_pi, "spelllangd": exit_pi - start_pi,
             "n_ersattare": len(intraden.get(exit_pi, []))}
        ers = intraden.get(exit_pi, [])
        for h in HOR:
            r = kum(F, k, exit_pi, h)
            u = float(np.prod(1 + univ[exit_pi:exit_pi + h]) - 1) if exit_pi + h <= len(dts) else None
            if ers and exit_pi + h <= len(dts):
                rr = [kum(F, x, exit_pi, h) for x in ers]
                rr = [x for x in rr if x is not None]
                er = float(np.mean(rr)) if rr else None
            else:
                er = None
            e[f"ret_{h}"] = r
            e[f"univ_{h}"] = u
            e[f"excess_{h}"] = (1 + r) / (1 + u) - 1 if (r is not None and u is not None) else None
            e[f"ersattare_{h}"] = er
            e[f"opp_cost_{h}"] = r - er if (r is not None and er is not None) else None

        # daglig bana för MAE/MFE och drawdown före återhämtning
        slut_pi = min(exit_pi + 13, len(dts) - 1)
        ds, adj = dagsbana(F, k, dts[exit_pi], dts[slut_pi])
        if ds is not None and len(adj) > 5:
            p0 = float(adj[0])
            rel = adj / p0 - 1
            e["mfe"] = float(np.max(rel)); e["mae"] = float(np.min(rel))
            over = np.where(adj > p0)[0]
            forsta_over = int(over[0]) if len(over) else None
            e["dd_fore_aterhamtning"] = float(np.min(rel[:forsta_over + 1])) if forsta_over else \
                float(np.min(rel))
            e["aterhamtade_till_exitpris"] = forsta_over is not None
            e["dagar_till_exitpris"] = forsta_over
        else:
            e["mfe"] = e["mae"] = e["dd_fore_aterhamtning"] = None
            e["aterhamtade_till_exitpris"] = None; e["dagar_till_exitpris"] = None

        # återinträde i H0
        ater = None
        for pj in range(exit_pi + 1, len(urval)):
            if k in urval[pj]:
                ater = pj; break
        e["aterintrade_pi"] = ater
        e["paneler_till_aterintrade"] = (ater - exit_pi) if ater is not None else None
        if ater is not None:
            _, a1 = dagsbana(F, k, dts[exit_pi], dts[min(exit_pi + 1, len(dts) - 1)])
            _, a2 = dagsbana(F, k, dts[ater], dts[min(ater + 1, len(dts) - 1)])
            if a1 is not None and a2 is not None and len(a1) and len(a2) and a1[0] > 0:
                e["pris_exit_till_ater"] = float(a2[0] / a1[0] - 1)
            else:
                e["pris_exit_till_ater"] = None
        else:
            e["pris_exit_till_ater"] = None
        ev.append(e)
    return ev


def sammanfatta(ev, etikett):
    print(f"\n{'='*78}\n{etikett}   n = {len(ev)} korta exits")
    ut = {"n_exits": len(ev)}

    print(f"\n  EFTER EXIT — absolut, mot universum, mot faktisk ersättare")
    print(f"  {'horisont':<16}{'n':>5}{'absolut':>10}{'excess':>10}{'ersättare':>11}"
          f"{'opp.cost':>10}{'t opp':>8}{'slår ers.':>10}")
    per_h = {}
    for h in HOR:
        r = np.array([e[f"ret_{h}"] for e in ev if e.get(f"ret_{h}") is not None])
        x = np.array([e[f"excess_{h}"] for e in ev if e.get(f"excess_{h}") is not None])
        o = np.array([e[f"opp_cost_{h}"] for e in ev if e.get(f"opp_cost_{h}") is not None])
        er = np.array([e[f"ersattare_{h}"] for e in ev if e.get(f"ersattare_{h}") is not None])
        if len(o) < 5:
            continue
        t = float(o.mean() / (o.std(ddof=1) / math.sqrt(len(o))))
        andel = float((o > 0).mean())
        per_h[h] = {"n": len(o), "absolut": round(float(r.mean()), 5),
                    "excess": round(float(x.mean()), 5), "ersattare": round(float(er.mean()), 5),
                    "opp_cost": round(float(o.mean()), 5), "t_opp": round(t, 2),
                    "andel_slar_ersattare": round(andel, 4)}
        print(f"  {HOR_ETIKETT[h]:<16}{len(o):>5}{r.mean():>+10.2%}{x.mean():>+10.2%}"
              f"{er.mean():>+11.2%}{o.mean():>+10.2%}{t:>8.2f}{andel:>10.1%}")
    ut["per_horisont"] = per_h

    # bana efter exit
    mae = np.array([e["mae"] for e in ev if e.get("mae") is not None])
    mfe = np.array([e["mfe"] for e in ev if e.get("mfe") is not None])
    dd = np.array([e["dd_fore_aterhamtning"] for e in ev if e.get("dd_fore_aterhamtning") is not None])
    ah = [e["aterhamtade_till_exitpris"] for e in ev if e.get("aterhamtade_till_exitpris") is not None]
    print(f"\n  BANAN EFTER EXIT (dagliga priser, 52 v)")
    print(f"    MAE medel {mae.mean():+.2%}  median {np.median(mae):+.2%}")
    print(f"    MFE medel {mfe.mean():+.2%}  median {np.median(mfe):+.2%}")
    print(f"    drawdown före återhämtning, medel {dd.mean():+.2%}")
    print(f"    andel som återhämtar till exitpriset inom 52 v: {np.mean(ah):.1%}")
    ut["bana"] = {"mae_medel": round(float(mae.mean()), 5), "mfe_medel": round(float(mfe.mean()), 5),
                  "dd_fore_aterhamtning": round(float(dd.mean()), 5),
                  "andel_aterhamtar": round(float(np.mean(ah)), 4)}

    # återinträden
    ater = [e for e in ev if e.get("aterintrade_pi") is not None]
    pris = np.array([e["pris_exit_till_ater"] for e in ater if e.get("pris_exit_till_ater") is not None])
    pan = np.array([e["paneler_till_aterintrade"] for e in ater if e.get("paneler_till_aterintrade")])
    print(f"\n  ÅTERINTRÄDEN")
    print(f"    andel som återvänder till H0: {len(ater)/len(ev):.1%}  (n={len(ater)})")
    if len(pan):
        print(f"    tid till återinträde: median {np.median(pan):.0f} paneler, "
              f"medel {pan.mean():.1f}")
    if len(pris):
        print(f"    pris exit->återinträde: medel {pris.mean():+.2%}, median {np.median(pris):+.2%}")
        for tr in (0.0, 0.10, 0.20, 0.30):
            a = float((pris > tr).mean())
            print(f"      återköpt mer än {tr:.0%} dyrare: {a:.1%}  "
                  f"({int((pris>tr).sum())} st)")
    ut["aterintraden"] = {
        "andel": round(len(ater) / len(ev), 4), "n": len(ater),
        "median_paneler": float(np.median(pan)) if len(pan) else None,
        "pris_medel": round(float(pris.mean()), 5) if len(pris) else None,
        "pris_median": round(float(np.median(pris)), 5) if len(pris) else None,
        "andel_dyrare": {f">{int(t*100)}%": round(float((pris > t).mean()), 4)
                         for t in (0.0, 0.10, 0.20, 0.30)} if len(pris) else None}

    # delpopulationer
    print(f"\n  DELPOPULATIONER (horisont {HOR_ETIKETT[PRIMAR]})")
    def har(e):
        return e.get(f"ret_{PRIMAR}") is not None and e.get(f"opp_cost_{PRIMAR}") is not None
    bas = [e for e in ev if har(e)]
    grupper = {
        "fortsatt förlorare (excess<0)": [e for e in bas if e[f"excess_{PRIMAR}"] < 0],
        "snabb trendresumption (+1 och +2 positiv)":
            [e for e in bas if (e.get("ret_1") or -1) > 0 and (e.get("ret_2") or -1) > 0],
        "återköpt billigare": [e for e in bas if (e.get("pris_exit_till_ater") or 1) < 0],
        "återköpt dyrare": [e for e in bas if (e.get("pris_exit_till_ater") or -1) > 0],
        "återköpt >10 % dyrare": [e for e in bas if (e.get("pris_exit_till_ater") or -1) > 0.10],
        "återköpt >20 % dyrare": [e for e in bas if (e.get("pris_exit_till_ater") or -1) > 0.20],
        "återköpt >30 % dyrare": [e for e in bas if (e.get("pris_exit_till_ater") or -1) > 0.30],
    }
    print(f"    {'grupp':<44}{'n':>5}{'andel':>8}{'opp.cost':>11}{'slår ers.':>10}")
    ut["delpopulationer"] = {}
    for g, lst in grupper.items():
        if len(lst) < 3:
            continue
        o = np.array([e[f"opp_cost_{PRIMAR}"] for e in lst])
        ut["delpopulationer"][g] = {"n": len(lst), "andel": round(len(lst) / len(bas), 4),
                                    "opp_cost": round(float(o.mean()), 5),
                                    "andel_slar": round(float((o > 0).mean()), 4)}
        print(f"    {g:<44}{len(lst):>5}{len(lst)/len(bas):>8.1%}{o.mean():>+11.2%}"
              f"{(o>0).mean():>10.1%}")

    # den ekonomiska definitionen
    print(f"\n  EKONOMISKT UNDVIKBARA EXITS (alla tre villkoren, horisont {HOR_ETIKETT[PRIMAR]})")
    und = [e for e in bas
           if e[f"ret_{PRIMAR}"] > 0 and e[f"opp_cost_{PRIMAR}"] > 0
           and (e.get("mae") is None or e["mae"] > -0.20)]
    o = np.array([e[f"opp_cost_{PRIMAR}"] for e in und]) if und else np.array([0.0])
    andel = len(und) / len(bas)
    print(f"    antal {len(und)} av {len(bas)} = {andel:.1%}")
    print(f"    deras genomsnittliga opportunity cost: {o.mean():+.2%}")
    print(f"    aggregerat bidrag: {andel * o.mean():+.2%} per exit-tillfälle i snitt")
    ut["ekonomiskt_undvikbara"] = {"n": len(und), "andel": round(andel, 4),
                                   "opp_cost_medel": round(float(o.mean()), 5),
                                   "aggregerat": round(float(andel * o.mean()), 5)}
    return ut


def main():
    ut = {"version": "G13_G17_PREMATURE_EXIT_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "status": "FÖRREGISTRERAD DIAGNOSTIK — ingen regel testad",
          "ersattardefinition": "likaviktad korg av de namn som kom in vid samma ombalansering",
          "horisontforbehall": "26 veckor finns inte på det frusna 28-dagarsrutnätet; "
                               "6 paneler = 24 veckor redovisas i stället. 13 paneler = 52 v exakt.",
          "fonster": {}}
    alla = []
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        ev = bygg(F, namn)
        alla.extend(ev)
        ut["fonster"][w_] = sammanfatta(ev, namn)
    ut["poolat"] = sammanfatta(alla, "POOLAT — båda fönstren")

    with open(EVENTS, "w") as f:
        for e in alla:
            f.write(json.dumps(e, ensure_ascii=False, default=float) + "\n")

    # beslutsregel
    a = ut["fonster"]["2020_2026"]; b = ut["fonster"]["2014_2019"]
    oa = a["per_horisont"].get(PRIMAR, {}); ob = b["per_horisont"].get(PRIMAR, {})
    gen_pos = oa.get("opp_cost", 0) > 0 and ob.get("opp_cost", 0) > 0
    sig = oa.get("t_opp", 0) > 1.96 and ob.get("t_opp", 0) > 1.96
    delpop = None
    for g in ut["fonster"]["2020_2026"]["delpopulationer"]:
        if g in ut["fonster"]["2014_2019"]["delpopulationer"]:
            x = ut["fonster"]["2020_2026"]["delpopulationer"][g]
            y = ut["fonster"]["2014_2019"]["delpopulationer"][g]
            if x["opp_cost"] > 0 and y["opp_cost"] > 0 and x["andel"] > 0.05 and y["andel"] > 0.05:
                delpop = g
    if gen_pos and sig:
        dom = "PREMATURE-EXIT PROBLEM SUPPORTED"
    elif delpop:
        dom = f"MIXED / CONDITIONAL — delpopulation: {delpop}"
    else:
        dom = "NO PREMATURE-EXIT PROBLEM"
    ut["dom"] = dom
    ut["licensierar_G1_G2_G6"] = dom != "NO PREMATURE-EXIT PROBLEM"
    print(f"\n{'='*78}\nBESLUT: {dom}")
    print(f"Licensierar G1/G2/G6: {'JA' if ut['licensierar_G1_G2_G6'] else 'NEJ'}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nEventnivå: {EVENTS} ({len(alla)} rader)")


if __name__ == "__main__":
    main()
