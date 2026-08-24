"""STATISK -> DYNAMISK, DEL 2: DE KONVERTERINGAR SOM ÅTERSTOD

Del 1 konverterade tre regler (swap, lutning, blankning). Det var tre av tio
familjer. Resten av programmet vilar fortfarande på fasta tal. De fyra viktigaste
kvarvarande, och varför den statiska formen kan ha dödat dem:

  D4  DRAWDOWN-EXIT VOL-NORMALISERAD
      DD20 (Batch 2, INGET STÖD) säljer vid -20 % från egen topp. Samma tröskel
      för ett kraftbolag med 18 % årsvol som för ett förhoppningsbolag med 65 %.
      För det första är -20 % en trestandardavvikelsers händelse, för det andra
      knappt en. Regeln mäter alltså volatilitet, inte tesbrott.
      Dynamisk form: sälj vid -k gånger namnets EGEN volatilitet.

  D5  HYSTERESEN SOM PERCENTIL I STÄLLET FÖR RANKPLATS
      "Behåll medan rank <= 35" är fast i ANTAL. Universumet växer och krymper,
      och rank 35 av 290 är en annan sak än rank 35 av 420. Dynamisk form:
      behåll medan poängen ligger över den p:te percentilen den panelen.

  D6  KÖPBANDET PÅ POÄNGGAP I STÄLLET FÖR RANKPLATS
      "Rekrytera från rank 11-40" är fast i antal platser. Men rankningen är
      platt — 0,1055 percentilenheter mellan rank 1 och 30 — och plattheten
      varierar panel för panel. Dynamisk form: rekrytera alla vars poäng ligger
      inom g poängenheter från toppen.

  D7  UTJÄMNING MED ADAPTIV SPAN
      A3 föll för fast EMA-span. Men hur mycket utjämning som behövs beror på
      hur brusig rankningen är just då. Dynamisk form: span som växer när
      rankomsättningen i toppen ökar.

Kör: /opt/momentum/venv/bin/python tools/granskning_statisk_vs_dynamisk_del2.py
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

OUT = V2 / "research_k/granskning_statisk_vs_dynamisk_del2_results.json"
COST = 0.002


def rankomsattning(F):
    """Andel av topp-30 som byts ut mot förra panelen. Endast historik."""
    dts, ut, forra = F["eval_dates"], {}, None
    for dt in dts:
        t = {r["kod"] for r in F["rankings"][dt][:30]}
        ut[dt] = 1.0 if forra is None else 1.0 - len(t & forra) / 30.0
        forra = t
    return ut


def utjamna_adaptiv(F, span_lo=1.0, span_hi=4.0):
    """EMA vars span växer med rankomsättningen. Omsättningen normaliseras mot
    ett EXPANDERANDE medelvärde, aldrig mot hela stickprovet."""
    oms = rankomsattning(F)
    dts = F["eval_dates"]
    ema, ut, hist = {}, {}, []
    for dt in dts:
        hist.append(oms[dt])
        m = float(np.mean(hist))
        kvot = oms[dt] / m if m > 0 else 1.0
        span = float(np.clip(span_lo + (span_hi - span_lo) * (kvot - 0.5), span_lo, span_hi))
        a = 2.0 / (span + 1.0)
        nya = []
        for r in F["rankings"][dt]:
            k, sc = r["kod"], r["score"]
            ema[k] = sc if k not in ema else a * sc + (1 - a) * ema[k]
            nya.append({"kod": k, "score": float(ema[k])})
        nya.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = nya
    return ut


def sim(F, N=30, hyst_rank=35, hyst_pct=None, dd_k=None, kopband_gap=None,
        rankings=None, dd_fast=None):
    """Kanonisk STACK_H-motor plus en av de dynamiska konverteringarna.
       hyst_pct  : behåll medan poäng >= (1-p)-kvantilen denna panel
       dd_k      : sälj vid drawdown från egen topp sedan köp < -dd_k * årsvol
       dd_fast   : samma men fast tröskel (DD20-replikering, för jämförelse)
       kopband_gap: rekrytera endast namn inom g poängenheter från toppen"""
    R = rankings if rankings is not None else F["rankings"]
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    previous, prev_weights, nets, hand = [], {}, [], []
    kurva = {}          # kod -> (kumulativ avkastning sedan köp, toppnivå)
    for pi, dt in enumerate(dts):
        raw = R[dt]
        elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        sc = {r["kod"]: r["score"] for r in raw}

        # --- drawdown-exit, prövas FÖRE urvalet ---
        tvang_ut = set()
        if (dd_k is not None or dd_fast is not None) and previous:
            for k in previous:
                if k not in kurva:
                    continue
                niva, topp = kurva[k]
                dd = niva / topp - 1 if topp > 0 else 0.0
                grans = -dd_fast if dd_fast is not None else -dd_k * max(volf(k, dt), 0.05)
                if dd < grans:
                    tvang_ut.add(k)
        hand.append(len(tvang_ut))
        kvar = [k for k in previous if k not in tvang_ut]

        if schedf(pi, dt) or not previous:
            if hyst_pct is not None:
                varden = [r["score"] for r in raw]
                g = float(np.quantile(varden, 1 - hyst_pct)) if varden else 0.0
                keep = [k for k in kvar if sc.get(k, -9) >= g and k in elig]
            else:
                keep = [k for k in kvar if rm.get(k, 999) <= hyst_rank and k in elig]
            if kopband_gap is not None and raw:
                topp = raw[0]["score"]
                pool = [r["kod"] for r in raw if topp - r["score"] <= kopband_gap]
                if len(pool) < N:
                    pool = [r["kod"] for r in raw[:N]]
            else:
                pool = [r["kod"] for r in raw]
            sel0 = (keep + [k for k in pool if k not in keep])[:N]
        else:
            sel0 = [k for k in kvar if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]

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
        rets = np.array([ret.get((k, dt), 0.0) for k in sel])
        nets.append(float(np.sum(w * rets)) - COST * turn)

        nya = set(sel0) - set(previous)
        for k in list(kurva):
            if k not in sel0:
                kurva.pop(k)
        for k in sel0:
            r_ = ret.get((k, dt), 0.0)
            if k in nya:
                kurva[k] = (1.0 + r_, max(1.0, 1.0 + r_))
            else:
                niva, topp = kurva.get(k, (1.0, 1.0))
                niva *= (1 + r_)
                kurva[k] = (niva, max(topp, niva))
        previous, prev_weights = sel0, curr
    return np.array(nets), float(np.mean(hand))


def main():
    bas26, bas19 = S.kor(**S.F26)[0], S.kor(**S.F19)[0]
    print(f"baslinjekontroll: {S.stat(bas26)['cagr']:.2%} / {S.stat(bas19)['cagr']:.2%}")
    k = sim(S.F26)[0]
    print(f"motorkontroll (allt av): {S.stat(k)['cagr']:.2%} "
          f"{'OK' if abs(S.stat(k)['cagr'] - S.stat(bas26)['cagr']) < 0.0005 else 'AVVIKER'}")

    ut = {"version": "GRANSKNING_STATISK_VS_DYNAMISK_DEL2_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "resultat": {}}

    varianter = []
    # D4 — drawdown, statisk referens och dynamisk form
    for x in (0.20, 0.30):
        varianter.append((f"D4 STATISK: sälj vid -{x:.0%} från egen topp", dict(dd_fast=x)))
    for kk in (0.5, 0.75, 1.0, 1.5):
        varianter.append((f"D4 DYNAMISK: sälj vid -{kk:g} x egen årsvol", dict(dd_k=kk)))
    # D5 — hysteres som percentil
    for p in (0.05, 0.10, 0.15, 0.25):
        varianter.append((f"D5 hysteres: behåll över topp {p:.0%}", dict(hyst_pct=p)))
    # D6 — köpband på poänggap
    for g in (0.05, 0.10, 0.20):
        varianter.append((f"D6 köpband: inom {g:.2f} poäng från toppen", dict(kopband_gap=g)))

    print(f"\n  {'variant':<42}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}{'exits':>9}  repl")
    print(f"  {'STACK_H':<42}{S.stat(bas26)['cagr']:>8.2%}{'—':>9}"
          f"{S.stat(bas19)['cagr']:>9.2%}{'—':>9}")
    for namn, kw in varianter:
        a26, h26 = sim(S.F26, **kw)
        a19, h19 = sim(S.F19, **kw)
        d26, d19 = S.boot(a26, bas26), S.boot(a19, bas19)
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["resultat"][namn] = {"f2020_2026": {**S.stat(a26), **d26, "exits_per_panel": round(h26, 2)},
                                "f2014_2019": {**S.stat(a19), **d19, "exits_per_panel": round(h19, 2)},
                                "bada_positiva": bool(rep)}
        print(f"  {namn:<42}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
              f"{h26:>5.1f}/{h19:<4.1f}  {'JA' if rep else '-'}")

    # D7 — adaptiv utjämning, separat eftersom den bygger om rankningen
    print(f"\n  {'D7 adaptiv utjämning':<42}")
    for lo, hi in ((1.0, 3.0), (1.0, 5.0), (2.0, 6.0)):
        namn = f"D7 EMA-span {lo:g}-{hi:g} styrd av rankomsättning"
        a26 = sim(S.F26, rankings=utjamna_adaptiv(S.F26, lo, hi))[0]
        a19 = sim(S.F19, rankings=utjamna_adaptiv(S.F19, lo, hi))[0]
        d26, d19 = S.boot(a26, bas26), S.boot(a19, bas19)
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["resultat"][namn] = {"f2020_2026": {**S.stat(a26), **d26},
                                "f2014_2019": {**S.stat(a19), **d19}, "bada_positiva": bool(rep)}
        print(f"  {namn:<42}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
              f"{'':>10}  {'JA' if rep else '-'}")

    print("\nSTATISK MOT DYNAMISK — samma mekanism, båda formerna")
    par = [("drawdown-exit", "D4 STATISK: sälj vid -20% från egen topp",
            "D4 DYNAMISK: sälj vid -1 x egen årsvol")]
    for etikett, s_, d_ in par:
        if s_ in ut["resultat"] and d_ in ut["resultat"]:
            a, b = ut["resultat"][s_], ut["resultat"][d_]
            print(f"  {etikett}: statisk {a['f2020_2026']['delta_cagr']:+.2%}/"
                  f"{a['f2014_2019']['delta_cagr']:+.2%}   dynamisk "
                  f"{b['f2020_2026']['delta_cagr']:+.2%}/{b['f2014_2019']['delta_cagr']:+.2%}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    n = sum(1 for v in ut["resultat"].values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n} av {len(ut['resultat'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
