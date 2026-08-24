"""GRANSKNING: VAR TRÖSKLARNA STATISKA NÄR DE BORDE VARIT RELATIVA?

Nästan varje regel i programmet använder ett FAST tal som gäller identiskt
2014-2026: "blankning över 1 %", "underpresterar med 10 %", "momentum vid sin
6-panelstopp", "rank under 40".

Ett fast tal betyder olika saker i olika perioder. Blankningstäckningen gick
från 3,7 % av universumet till 13,7 %; en 1 %-tröskel träffar därför ett namn
vartannat beslut 2015 och tre namn per beslut 2025. Volatiliteten fördubblades
under 2020; en 10 %-tröskel för underprestation är en helt annan händelse i ett
lugnt än i ett stökigt kvartal.

Den relativa formen är immun mot detta: "de 10 % mest blankade DENNA panel",
"det svagaste innehavet DENNA panel". Tröskeln flyttar med fördelningen.

TRE REGLER OMBYGGDA FRÅN ABSOLUT TILL RELATIV FORM

  D1  swap: offret väljs som de q sämsta innehaven denna panel, inte de som
      underpresterar med mer än U procent
  D2  momentumkurvan: lutning mätt som tvärsnittspercentil denna panel, inte
      som absolut jämförelse mot eget 6-panelsfönster
  D3  blankning: de q mest blankade denna panel, inte de över X procent

FJÄRDE DIMENSIONEN — REGIMBETINGNING
  Legacy 2026-08-06: "grinden är kalibrerad för fel regim". Varje regel körs
  också i en variant som bara är aktiv när universumets 12m-avkastning är
  negativ, respektive bara när den är positiv.

Kör: /opt/momentum/venv/bin/python tools/granskning_statisk_vs_dynamisk.py
"""
from __future__ import annotations
import bisect, json, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/granskning_statisk_vs_dynamisk_results.json"
COST = 0.002
BLANK = V2 / "validated/fi_blankning/fi_blankning_normaliserad.jsonl"


# ---------------------------------------------------------- hjälpdata
def ladda_blankning():
    per = defaultdict(list)
    with open(BLANK) as f:
        for rad in f:
            r = json.loads(rad)
            if r.get("ticker") and r.get("position_pct") is not None:
                per[r["ticker"]].append((r["datum"], r["innehavare"].strip(), r["position_pct"]))
    for k in per:
        per[k].sort()
    return dict(per)


HAND = ladda_blankning()


def blank_niva(k, dt):
    h = HAND.get(k)
    if not h:
        return 0.0
    from datetime import date, timedelta
    g = (date.fromisoformat(dt) - timedelta(days=4)).isoformat()
    senast = {}
    for d, inn, p in h:
        if d > g:
            break
        senast[inn] = p
    return float(sum(senast.values()))


def regim(F):
    """Universumets rullande 12-panelsavkastning, per panel. Endast historik."""
    dts, ret = F["eval_dates"], F["returns_map"]
    u = [float(np.mean([ret.get((r["kod"], dt), 0.0) for r in F["rankings"][dt]])) for dt in dts]
    ut = {}
    for i, dt in enumerate(dts):
        j = max(0, i - 12)
        ut[dt] = float(np.prod([1 + x for x in u[j:i]]) - 1) if i > j else 0.0
    return ut


def lutning(F, k, dt, pi):
    """Poängförändring över 3 paneler — samma information som momentumkurvans
    lutning, men beräknad ur rankningens egen poäng."""
    dts = F["eval_dates"]
    if pi < 3:
        return None
    bak = dts[pi - 3]
    a = _SC[id(F)].get((k, dt))
    b = _SC[id(F)].get((k, bak))
    return None if a is None or b is None else a - b


_SC = {}


def bygg_sc(F):
    _SC[id(F)] = {(r["kod"], dt): r["score"] for dt in F["eval_dates"] for r in F["rankings"][dt]}


# ---------------------------------------------------------- motor
def sim(F, regel=None, q=0.20, riktning="ta_bort", bara_regim=None, N=30, hyst_rank=35):
    """regel: None | 'swap_rel' | 'lutning_rel' | 'blank_rel'
       q: andel av panelen som regeln träffar (relativ tröskel)
       bara_regim: None | 'bear' | 'bull'"""
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    R = _REG[id(F)]
    previous, prev_weights, nets, traff = [], {}, [], []
    rel = {}
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        aktiv = True
        if bara_regim == "bear":
            aktiv = R[dt] < 0
        elif bara_regim == "bull":
            aktiv = R[dt] >= 0

        if schedf(pi, dt) or not previous:
            keep = [k for k in previous if rm.get(k, 999) <= hyst_rank and k in elig]
            sel0 = (keep + [r["kod"] for r in raw if r["kod"] not in keep])[:N]
        else:
            sel0 = [k for k in previous if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]

        n_tr = 0
        if regel and aktiv and previous:
            kand = [r["kod"] for r in raw if r["kod"] not in sel0]
            if regel == "swap_rel":
                # de q sämsta innehaven denna panel, mätt relativt
                m = max(1, int(round(q * len(sel0))))
                ordn = sorted(sel0, key=lambda k: rel.get(k, 0.0))[:m]
                for i, k in enumerate(list(sel0)):
                    if k in ordn and i < len(sel0) and n_tr < len(kand):
                        sel0[sel0.index(k)] = kand[n_tr]
                        n_tr += 1
            elif regel in ("lutning_rel", "blank_rel"):
                if regel == "lutning_rel":
                    v = {r["kod"]: lutning(F, r["kod"], dt, pi) for r in raw}
                else:
                    v = {r["kod"]: blank_niva(r["kod"], dt) for r in raw}
                giltiga = {k: x for k, x in v.items() if x is not None}
                if len(giltiga) > 20:
                    if regel == "lutning_rel":
                        grans = float(np.quantile(list(giltiga.values()), q))
                        flagg = {k for k, x in giltiga.items() if x <= grans}
                    else:
                        grans = float(np.quantile(list(giltiga.values()), 1 - q))
                        flagg = {k for k, x in giltiga.items() if x >= grans and x > 0}
                    if riktning == "ta_bort":
                        rensad = [r for r in raw if r["kod"] not in flagg] or raw
                    else:
                        rensad = sorted(raw, key=lambda r: -(r["score"] +
                                                             (0.05 if r["kod"] in flagg else 0)))
                    n_tr = len(flagg & set(sel0))
                    rm2 = {r["kod"]: i + 1 for i, r in enumerate(rensad)}
                    e2 = {r["kod"] for r in rensad}
                    if schedf(pi, dt):
                        keep = [k for k in previous if rm2.get(k, 999) <= hyst_rank and k in e2]
                        sel0 = (keep + [r["kod"] for r in rensad if r["kod"] not in keep])[:N]
                    else:
                        sel0 = [k for k in previous if k in e2]
                        if len(sel0) < N:
                            sel0 += [r["kod"] for r in rensad if r["kod"] not in sel0][: N - len(sel0)]
        traff.append(n_tr)

        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); previous, prev_weights = sel0, {}; continue
        vols = np.array([volf(k, dt) for k in sel], dtype=float)
        inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
        w = inv / np.sum(inv) * (n / N)
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * (n / N)
        if prev_weights:
            w = np.array([prev_weights.get(k, 0.0)
                          if (abs(w[i] - prev_weights.get(k, 0.0)) < 0.005
                              and prev_weights.get(k, 0.0) > 0) else w[i]
                          for i, k in enumerate(sel)])
            w = w / np.sum(w) * (n / N)
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not previous else \
            sum(abs(curr.get(k, 0.0) - prev_weights.get(k, 0.0))
                for k in set(prev_weights) | set(curr)) / 2.0
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        univ = float(np.mean([ret.get((r["kod"], dt), 0.0) for r in raw]))
        nya = set(sel0) - set(previous)
        for k in list(rel):
            if k not in sel0:
                rel.pop(k)
        for k in sel0:
            rel[k] = 0.0 if k in nya else \
                (1 + rel.get(k, 0.0)) * (1 + ret.get((k, dt), 0.0)) / (1 + univ) - 1
        previous, prev_weights = sel0, curr
    return np.array(nets), float(np.mean(traff))


_REG = {}


def main():
    for F in (S.F26, S.F19):
        bygg_sc(F); _REG[id(F)] = regim(F)
    bas26, bas19 = S.kor(**S.F26)[0], S.kor(**S.F19)[0]
    print(f"baslinjekontroll: {S.stat(bas26)['cagr']:.2%} / {S.stat(bas19)['cagr']:.2%}")
    k = sim(S.F26)[0]
    print(f"motorkontroll (regel av): {S.stat(k)['cagr']:.2%} "
          f"{'OK' if abs(S.stat(k)['cagr'] - S.stat(bas26)['cagr']) < 0.0005 else 'AVVIKER'}")

    ut = {"version": "GRANSKNING_STATISK_VS_DYNAMISK_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "resultat": {}}
    varianter = []
    for q in (0.10, 0.20):
        varianter.append((f"D1 swap: {q:.0%} sämsta innehaven", dict(regel="swap_rel", q=q)))
    for q in (0.10, 0.20, 0.33):
        varianter.append((f"D2 lutning: bort med {q:.0%} lägsta", dict(regel="lutning_rel", q=q)))
    for q in (0.05, 0.10, 0.20):
        varianter.append((f"D3 blankning: bort med {q:.0%} mest", dict(regel="blank_rel", q=q)))
    for r in ("bear", "bull"):
        varianter.append((f"D2 lutning 20 % endast i {r}",
                          dict(regel="lutning_rel", q=0.20, bara_regim=r)))
        varianter.append((f"D1 swap 20 % endast i {r}",
                          dict(regel="swap_rel", q=0.20, bara_regim=r)))

    print(f"\n  {'variant':<38}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}{'träff':>9}  repl")
    print(f"  {'STACK_H':<38}{S.stat(bas26)['cagr']:>8.2%}{'—':>9}{S.stat(bas19)['cagr']:>9.2%}{'—':>9}")
    for namn, kw in varianter:
        a26, t26 = sim(S.F26, **kw)
        a19, t19 = sim(S.F19, **kw)
        d26, d19 = S.boot(a26, bas26), S.boot(a19, bas19)
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["resultat"][namn] = {"f2020_2026": {**S.stat(a26), **d26, "traff": round(t26, 2)},
                                "f2014_2019": {**S.stat(a19), **d19, "traff": round(t19, 2)},
                                "bada_positiva": bool(rep)}
        print(f"  {namn:<38}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
              f"{t26:>5.1f}/{t19:<4.1f}  {'JA' if rep else '-'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    n = sum(1 for v in ut["resultat"].values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n} av {len(ut['resultat'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
