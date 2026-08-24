"""LÖNSAMHET SOM POÄNGFAKTOR OCH SOM PORTFÖLJKVOT

Grinden föll (0 av 7). Men grinden är den trubbigaste möjliga formen: den läser
bara TECKNET på marginalen och kastar bort allt annat. Diagnostiken mätte
kvintilspread, alltså MAGNITUD. Två former som faktiskt använder magnituden är
oprövade:

  A. POÄNGFAKTOR
     poäng_ny = (1-w) x H0-poäng + w x percentilrank(marginal)
     H0-poängen är redan i percentilenheter, så skalorna är jämförbara utan
     omräkning. Namn utan marginaldata får medianpercentilen 0,5 — neutralt,
     samma logik som grindens "saknat värde utesluter inte".
     Svep w = 0,05 till 0,50.

  B. PORTFÖLJKVOT
     Portföljen måste innehålla minst q lönsamma namn av 30. Räcker inte
     topp-30 byts de lägst rankade olönsamma mot nästa rankade lönsamma
     kandidat. Detta är en KONSTRUKTIONSregel, inte ett urvalsfilter: den
     släpper in olönsamma namn så länge de är få nog.

     q=30 är per definition identisk med grinden, så svepet spänner hela vägen
     från obunden till grind och visar var kostnaden uppstår.

  C. KVOT PÅ HÖG LÖNSAMHET (den dynamiska formen)
     Kvot på "positiv marginal" binder knappt — 89 % av topp-30 är redan
     lönsamma. Kvot på "översta tredjedelen av marginalfördelningen DENNA panel"
     är tvärsnittlig och binder på riktigt.

Mot STACK_H och mot den bara modellen, båda fönstren.

Kör: /opt/momentum/venv/bin/python tools/lonsamhet_poangfaktor_och_kvot.py
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import lonsamhetstilt_mot_stack_h as L

OUT = V2 / "research_k/lonsamhet_poangfaktor_och_kvot_results.json"
COST = 0.002


def marginalbild(F, dt, koder):
    """-> (percentilrank per kod, mängd lönsamma, mängd i översta tredjedelen)"""
    v = {k: L.pit(L.MARGINAL, k, dt) for k in koder}
    med = sorted((x, k) for k, x in v.items() if x is not None)
    n = len(med)
    if n < 30:
        return {k: 0.5 for k in koder}, set(), set()
    pct = {k: (i + 0.5) / n for i, (_, k) in enumerate(med)}
    pct = {k: pct.get(k, 0.5) for k in koder}
    lonsam = {k for k, x in v.items() if x is not None and x > 0}
    grans = float(np.quantile([x for x, _ in med], 2 / 3))
    hog = {k for k, x in v.items() if x is not None and x >= grans}
    return pct, lonsam, hog


def sim(F, w=None, kvot=None, kvot_typ="lonsam", N=30, hyst_rank=35, bar=False):
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    previous, prev_weights, nets, bind = [], {}, [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        koder = [r["kod"] for r in raw]
        pct, lonsam, hog = marginalbild(F, dt, koder)
        onskad = lonsam if kvot_typ == "lonsam" else hog

        if w is not None and len(lonsam) > 0:
            arbets = sorted(({"kod": r["kod"], "score": (1 - w) * r["score"] + w * pct[r["kod"]]}
                             for r in raw), key=lambda x: (x["score"], x["kod"]), reverse=True)
        else:
            arbets = raw
        elig = {r["kod"] for r in arbets}
        rm = {r["kod"]: i + 1 for i, r in enumerate(arbets)}

        if schedf(pi, dt) or not previous:
            if bar:
                sel0 = [r["kod"] for r in arbets][:N]
            else:
                keep = [k for k in previous if rm.get(k, 999) <= hyst_rank and k in elig]
                sel0 = (keep + [r["kod"] for r in arbets if r["kod"] not in keep])[:N]
        else:
            sel0 = [k for k in previous if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in arbets if r["kod"] not in sel0][: N - len(sel0)]

        n_bytt = 0
        if kvot is not None and len(lonsam) >= 30:
            har = sum(1 for k in sel0 if k in onskad)
            if har < kvot:
                brist = kvot - har
                kand = [r["kod"] for r in arbets if r["kod"] in onskad and r["kod"] not in sel0]
                # lägst rankade icke-önskade åker ut först
                ut_i = [i for i in range(len(sel0) - 1, -1, -1) if sel0[i] not in onskad]
                for i in ut_i[:brist]:
                    if not kand:
                        break
                    sel0[i] = kand.pop(0)
                    n_bytt += 1
        bind.append(n_bytt)

        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); previous, prev_weights = sel0, {}; continue
        vols = np.array([volf(k, dt) for k in sel], dtype=float)
        inv = 1.0 / (np.maximum(vols, 0.05) ** (1.0 if bar else 1.5))
        wt = inv / np.sum(inv) * (n / N)
        if not bar:
            wt = wt * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        wt = np.clip(wt, 0.01, 0.06); wt = wt / np.sum(wt) * (n / N)
        if prev_weights and not bar:
            wt = np.array([prev_weights.get(k, 0.0)
                           if (abs(wt[i] - prev_weights.get(k, 0.0)) < 0.005
                               and prev_weights.get(k, 0.0) > 0) else wt[i]
                           for i, k in enumerate(sel)])
            wt = wt / np.sum(wt) * (n / N)
        curr = dict(zip(sel, wt))
        turn = float(np.sum(wt)) if not previous else \
            sum(abs(curr.get(k, 0.0) - prev_weights.get(k, 0.0))
                for k in set(prev_weights) | set(curr)) / 2.0
        nets.append(float(np.sum(wt * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        previous, prev_weights = sel0, curr
    return np.array(nets), float(np.mean(bind))


def main():
    bas = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}
    barkw = dict(use_erc=False, use_fr=False, use_hysteresis=False, use_ntz=False)
    barbas = {"26": S.kor(**{**S.F26, **barkw})[0], "19": S.kor(**{**S.F19, **barkw})[0]}
    print(f"baslinjekontroll STACK_H {S.stat(bas['26'])['cagr']:.2%} / {S.stat(bas['19'])['cagr']:.2%}")
    k = sim(S.F26)[0]
    print(f"motorkontroll (allt av): {S.stat(k)['cagr']:.2%} "
          f"{'OK' if abs(S.stat(k)['cagr'] - S.stat(bas['26'])['cagr']) < 0.0005 else 'AVVIKER'}")

    # hur mycket finns det att binda på?
    print("\nHUR MYCKET RUM FINNS DET?")
    for w_, F, namn in (("26", S.F26, "2020-2026"), ("19", S.F19, "2014-2019")):
        a, b = [], []
        for dt in F["eval_dates"]:
            raw = F["rankings"][dt]
            pct, lon, hog = marginalbild(F, dt, [r["kod"] for r in raw])
            if not lon:
                continue
            t30 = [r["kod"] for r in raw[:30]]
            a.append(sum(1 for k in t30 if k in lon))
            b.append(sum(1 for k in t30 if k in hog))
        print(f"  {namn}: av topp-30 är {np.mean(a):.1f} lönsamma och "
              f"{np.mean(b):.1f} i översta marginaltredjedelen")

    ut = {"version": "LONSAMHET_POANGFAKTOR_OCH_KVOT_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "resultat": {}}
    varianter = [(f"A poängfaktor w={x:.2f}", dict(w=x)) for x in (0.05, 0.10, 0.20, 0.30, 0.50)]
    varianter += [(f"B kvot: minst {q} lönsamma av 30", dict(kvot=q)) for q in (27, 28, 29, 30)]
    varianter += [(f"C kvot: minst {q} i toppmarginaltredjedel", dict(kvot=q, kvot_typ="hog"))
                  for q in (10, 15, 20)]

    for bl, bser, barflagga in (("STACK_H", bas, False), ("BAR", barbas, True)):
        print(f"\nMOT {bl}")
        print(f"  {'variant':<40}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}"
              f"{'byten':>8}{'maxDD26':>9}  repl")
        for namn, kw in varianter:
            a26, b26 = sim(S.F26, **kw, bar=barflagga)
            a19, b19 = sim(S.F19, **kw, bar=barflagga)
            d26, d19 = S.boot(a26, bser["26"]), S.boot(a19, bser["19"])
            rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
            ut["resultat"].setdefault(namn, {})[bl] = {
                "f2020_2026": {**S.stat(a26), **d26, "byten_per_panel": round(b26, 2)},
                "f2014_2019": {**S.stat(a19), **d19, "byten_per_panel": round(b19, 2)},
                "bada_positiva": bool(rep),
                "maxdd_delta_26": round(S.stat(a26)["maxdd"] - S.stat(bser["26"])["maxdd"], 4),
                "maxdd_delta_19": round(S.stat(a19)["maxdd"] - S.stat(bser["19"])["maxdd"], 4)}
            print(f"  {namn:<40}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
                  f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
                  f"{b26:>4.1f}/{b19:<3.1f}"
                  f"{S.stat(a26)['maxdd'] - S.stat(bser['26'])['maxdd']:>+9.2%}"
                  f"  {'JA' if rep else '-'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    n = sum(1 for v in ut["resultat"].values() if v["STACK_H"]["bada_positiva"])
    print(f"\nPositiva i båda fönstren mot STACK_H: {n} av {len(ut['resultat'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
