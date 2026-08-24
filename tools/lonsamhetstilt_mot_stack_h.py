"""LÖNSAMHET SOM PORTFÖLJREGEL — BÅDA FÖNSTREN, TVÅ BASLINJER

Segmentdiagnostiken 2026-08-16 visade att lönsamma bolag har nästan identisk
kvintilspread i båda fönstren (+16,0 % respektive +16,4 %/år, t 2,04 och 2,43),
medan olönsamma är brus och stora bolag inte rangordnas alls. Det är programmets
starkaste replikation av någon segmentindelning.

Frågan här: bär det över till en portföljregel?

VAD SOM SKILJER DETTA FRÅN K8
  K8 (2026-08-13) prövade en grind på ABSOLUT rörelseresultat (KPI 55 > 0) mot
  VA_RETURN_CHALLENGER i ENDAST 2020-2026. Utfall: CAGR +0,10 pp, maxDD +2,09 pp,
  t_paired -0,10, klassad SVAGT STÖD.

  Detta skript ändrar fyra saker:
    1. MARGINAL i stället för nivå (KPI 29, rörelsemarginal) — skalfri, och det
       är måttet diagnostiken faktiskt mätte
    2. BÅDA fönstren, inte ett
    3. Mot STACK_H OCH mot den bara modellen — L1-granskningen visade att FR-
       overlayen redan nedviktar obekräftade namn med 0,75, alltså en svag form
       av samma sak. Utan barmodellen går redundansen inte att skilja från
       verkningslöshet.
    4. Både GRIND, VIKTTILT och RANKTILT, samt tvärsnittlig tröskel

SAMMA SAKNAD-DATA-REGEL SOM K8
  Saknat värde vid T betyder INTE utesluten. Grinden får bara ta bort på positivt
  bevis om förlust. Att utesluta på frånvaro skulle tyst rensa bort hela den
  avnoteringsnära populationen.

TÄCKNING
  KPI-historiken börjar 2017. Det sena fönstret har i praktiken full täckning,
  det tidiga ungefär halva. Där data saknas ligger regeln stilla och utfallet
  späds ut. Därför rapporteras deltat BÅDE över hela fönstret OCH begränsat till
  de paneler som faktiskt har täckning.

Kör: /opt/momentum/venv/bin/python tools/lonsamhetstilt_mot_stack_h.py
"""
from __future__ import annotations
import bisect, json, sys
from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/lonsamhetstilt_mot_stack_h_results.json"
KPI = V2 / "validated/kpi_pit"
COST = 0.002
LAGG = 5


def ladda(fil):
    per = defaultdict(list)
    for r in json.loads((KPI / f"{fil}.json").read_text()):
        if r.get("report_date") and r.get("v") is not None:
            per[r["kod"]].append((r["report_date"], float(r["v"])))
    for k in per:
        per[k].sort()
    return {k: (np.array([x[0] for x in v]), np.array([x[1] for x in v])) for k, v in per.items()}


MARGINAL = ladda("29_Rorelsemarginal_r12")
FCF = ladda("24_FCF_Marginal_r12")


def pit(d, k, dt):
    h = d.get(k)
    if h is None:
        return None
    g = (date.fromisoformat(dt) - timedelta(days=LAGG)).isoformat()
    i = int(np.searchsorted(h[0], g, side="right")) - 1
    return float(h[1][i]) if i >= 0 else None


def sim(F, kalla=MARGINAL, lage=None, trosk=0.0, tilt=0.75, kvantil=None,
        N=30, hyst_rank=35, bar=False):
    """lage: None | 'grind' | 'vikt' | 'rank'
       kvantil: om satt används tvärsnittlig tröskel i stället för absolut"""
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    previous, prev_weights, nets, tackn, traff = [], {}, [], [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        v = {r["kod"]: pit(kalla, r["kod"], dt) for r in raw}
        med = [x for x in v.values() if x is not None]
        tackn.append(len(med))
        g = float(np.quantile(med, kvantil)) if (kvantil is not None and len(med) >= 30) else trosk
        # positivt bevis om förlust krävs; saknat värde = ej utesluten
        dalig = {k for k, x in v.items() if x is not None and x <= g}
        traff.append(len(dalig & set(previous)) if previous else 0)

        arbets = raw
        if lage == "grind" and len(med) >= 30:
            arbets = [r for r in raw if r["kod"] not in dalig] or raw
        elif lage == "rank" and len(med) >= 30:
            arbets = sorted(raw, key=lambda r: -(r["score"] - (0.05 if r["kod"] in dalig else 0)))
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

        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); previous, prev_weights = sel0, {}; continue
        vols = np.array([volf(k, dt) for k in sel], dtype=float)
        p = 1.0 if bar else 1.5
        inv = 1.0 / (np.maximum(vols, 0.05) ** p)
        w = inv / np.sum(inv) * (n / N)
        if not bar:
            w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        if lage == "vikt" and len(med) >= 30:
            w = w * np.array([tilt if k in dalig else 1.0 for k in sel])
        w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * (n / N)
        if prev_weights and not bar:
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
        previous, prev_weights = sel0, curr
    return np.array(nets), np.array(tackn), float(np.mean(traff))


def main():
    bas = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}
    barbas = {"26": S.kor(**{**S.F26, "use_erc": False, "use_fr": False,
                             "use_hysteresis": False, "use_ntz": False})[0],
              "19": S.kor(**{**S.F19, "use_erc": False, "use_fr": False,
                             "use_hysteresis": False, "use_ntz": False})[0]}
    print(f"baslinjekontroll STACK_H {S.stat(bas['26'])['cagr']:.2%} / {S.stat(bas['19'])['cagr']:.2%}")
    print(f"baslinje BAR             {S.stat(barbas['26'])['cagr']:.2%} / "
          f"{S.stat(barbas['19'])['cagr']:.2%}")
    k = sim(S.F26)[0]
    print(f"motorkontroll (regel av): {S.stat(k)['cagr']:.2%} "
          f"{'OK' if abs(S.stat(k)['cagr'] - S.stat(bas['26'])['cagr']) < 0.0005 else 'AVVIKER'}")
    kb = sim(S.F26, bar=True)[0]
    print(f"motorkontroll BAR:        {S.stat(kb)['cagr']:.2%} "
          f"{'OK' if abs(S.stat(kb)['cagr'] - S.stat(barbas['26'])['cagr']) < 0.004 else 'AVVIKER'}")

    ut = {"version": "LONSAMHETSTILT_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "skiljer_fran_K8": "marginal i stället för nivå, båda fönstren, två baslinjer, "
                             "grind + vikttilt + ranktilt, tvärsnittlig tröskel",
          "resultat": {}}

    varianter = [
        ("grind: rörelsemarginal <= 0 bort", dict(lage="grind", trosk=0.0)),
        ("grind: rörelsemarginal <= 5 % bort", dict(lage="grind", trosk=5.0)),
        ("grind: nedersta tredjedelen bort", dict(lage="grind", kvantil=1 / 3)),
        ("grind: FCF-marginal <= 0 bort", dict(lage="grind", trosk=0.0, kalla=FCF)),
        ("vikt x0,75 vid marginal <= 0", dict(lage="vikt", trosk=0.0, tilt=0.75)),
        ("vikt x0,50 vid marginal <= 0", dict(lage="vikt", trosk=0.0, tilt=0.50)),
        ("ranktilt vid marginal <= 0", dict(lage="rank", trosk=0.0)),
    ]

    for bl, basserie, barflagga in (("STACK_H", bas, False), ("BAR", barbas, True)):
        print(f"\nMOT {bl}")
        print(f"  {'variant':<36}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}"
              f"{'Δ19 täckt':>11}{'maxDD26':>9}  repl")
        for namn, kw in varianter:
            a26, t26, tr26 = sim(S.F26, **kw, bar=barflagga)
            a19, t19, tr19 = sim(S.F19, **kw, bar=barflagga)
            d26 = S.boot(a26, basserie["26"]); d19 = S.boot(a19, basserie["19"])
            m19 = t19 >= 30
            if m19.sum() >= 20:
                dt19 = S.boot(a19[m19], basserie["19"][m19])["delta_cagr"]
            else:
                dt19 = None
            rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
            ut["resultat"].setdefault(namn, {})[bl] = {
                "f2020_2026": {**S.stat(a26), **d26, "traffar": round(tr26, 2)},
                "f2014_2019": {**S.stat(a19), **d19, "traffar": round(tr19, 2),
                               "delta_endast_tackta_paneler": dt19,
                               "n_tackta_paneler": int(m19.sum())},
                "bada_positiva": bool(rep),
                "maxdd_delta_26": round(S.stat(a26)["maxdd"] - S.stat(basserie["26"])["maxdd"], 4),
                "maxdd_delta_19": round(S.stat(a19)["maxdd"] - S.stat(basserie["19"])["maxdd"], 4)}
            print(f"  {namn:<36}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
                  f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
                  f"{(f'{dt19:+.2%}' if dt19 is not None else '—'):>11}"
                  f"{S.stat(a26)['maxdd'] - S.stat(basserie['26'])['maxdd']:>+9.2%}"
                  f"  {'JA' if rep else '-'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    n = sum(1 for v in ut["resultat"].values() if v.get("STACK_H", {}).get("bada_positiva"))
    print(f"\nPositiva i båda fönstren mot STACK_H: {n} av {len(ut['resultat'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
