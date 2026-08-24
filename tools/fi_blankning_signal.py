"""BLANKNINGSSIGNAL UR FI:S REGISTER — MOT STACK_H I BÅDA FÖNSTREN

Första nya datakällan i hela programmet som har historik i BÅDA fönstren
(2012-2026), och därmed den första som kan prövas mot tvåfönsterkriteriet.

REKONSTRUKTION AV TILLSTÅND
  Registret är en händelselogg, inte en tidsserie. Varje rad är en rapport från
  EN innehavare om EN emittent vid ETT datum. En position gäller tills samma
  innehavare rapporterar en ny siffra. "<0,5" betyder att innehavaren gått under
  publiceringströskeln — positionen sätts då till noll.
  Aggregerad blankning för ett bolag vid datum D = summan av varje innehavares
  senast rapporterade position <= D.

  Detta UNDERSKATTAR systematiskt: positioner under 0,5 % syns aldrig. Signalen
  är alltså "rapporterad synlig blankning", inte total blankning.

PUNKT-I-TID
  FI publicerar positionsdatum, och publiceringen sker dagen efter kl 15:30.
  Vi lägger på LAGG_DAGAR marginal ovanpå det, så inget datum som ännu inte var
  publicerat kan påverka ett beslut.

VAD SOM PRÖVAS
  N1  nivå som uteslutning: namn med aggregerad blankning över tröskel plockas bort
  N2  nivå som viktstraff: behåll namnet men skala ned vikten
  N3  nivå som rankningsjustering: dra av från poängen, mjukare än hård uteslutning
  F1  FÖRÄNDRING: stigande blankning senaste 3 månaderna som säljsignal
  F2  FÖRÄNDRING: fallande blankning (täckningsköp) som köpsignal
  K1  KONTRÄR: hög blankning som squeeze-kandidat, alltså tvärtom mot N1

PLACEBO
  Varje regel som byter ut vilka namn som ägs jämförs mot slumpmässig
  uteslutning av lika många namn per panel, samma antal utfall som regeln ger.

Kör: /opt/momentum/venv/bin/python tools/fi_blankning_signal.py
"""
from __future__ import annotations
import json, math, sys
from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/fi_blankning_signal_results.json"
DATA = V2 / "validated/fi_blankning/fi_blankning_normaliserad.jsonl"
COST = 0.002
LAGG_DAGAR = 4          # publiceringsfördröjning + marginal
RNG = np.random.default_rng(20260816)


# ---------------------------------------------------------------- tillstånd
def ladda():
    """-> {ticker: [(datum, innehavare, position_pct), ...]} sorterat."""
    per = defaultdict(list)
    with open(DATA) as f:
        for rad in f:
            r = json.loads(rad)
            if not r.get("ticker") or r.get("position_pct") is None:
                continue
            per[r["ticker"]].append((r["datum"], r["innehavare"].strip(), r["position_pct"]))
    for k in per:
        per[k].sort()
    return dict(per)


HAND = ladda()


def aggregat(ticker, dt):
    """Summan av varje innehavares senast rapporterade position vid dt minus lagg."""
    h = HAND.get(ticker)
    if not h:
        return 0.0
    grans = (date.fromisoformat(dt) - timedelta(days=LAGG_DAGAR)).isoformat()
    senast = {}
    for d, inn, p in h:
        if d > grans:
            break
        senast[inn] = p
    return float(sum(senast.values()))


def bygg_cache(F):
    """{(kod, dt): aggregerad blankning i procent}."""
    c = {}
    for dt in F["eval_dates"]:
        for r in F["rankings"][dt]:
            c[(r["kod"], dt)] = aggregat(r["kod"], dt)
    return c


# ---------------------------------------------------------------- motor
def sim(F, blank, regel=None, trosk=1.0, straff=0.5, N=30, hyst_rank=35,
        forandring=None, slump_n=None):
    """regel: None | 'uteslut' | 'vikt' | 'rank' | 'kontrar' | 'slump'
       forandring: None | 'stigande' | 'fallande'  (använder delta mot 3 paneler bak)"""
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets, n_traffar = [], {}, [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        b = {r["kod"]: blank.get((r["kod"], dt), 0.0) for r in raw}
        if forandring:
            bak = dts[max(0, pi - 3)]
            d3 = {k: b[k] - blank.get((k, bak), 0.0) for k in b}

        # vilka namn regeln pekar ut
        if regel == "uteslut":
            flagg = {k for k, v in b.items() if v >= trosk}
        elif regel == "kontrar":
            flagg = set()
        elif regel == "slump":
            kandidater = [r["kod"] for r in raw[:60]]
            m = min(slump_n or 0, len(kandidater))
            flagg = set(RNG.choice(kandidater, size=m, replace=False)) if m else set()
        elif forandring == "stigande":
            flagg = {k for k, v in d3.items() if v >= trosk}
        elif forandring == "fallande":
            flagg = {k for k, v in d3.items() if v <= -trosk}
        else:
            flagg = set()
        n_traffar.append(len(flagg & {r["kod"] for r in raw[:N]}))

        # rangordning, ev. justerad
        if regel == "rank":
            just = sorted(raw, key=lambda r: -(r["score"] - straff * min(b[r["kod"]], 5.0) / 100.0))
        elif regel == "kontrar":
            just = sorted(raw, key=lambda r: -(r["score"] + straff * min(b[r["kod"]], 5.0) / 100.0))
        elif forandring == "fallande":
            just = sorted(raw, key=lambda r: -(r["score"] + (straff / 100.0 if r["kod"] in flagg else 0)))
        else:
            just = raw
        if regel in ("uteslut", "slump") or forandring == "stigande":
            just = [r for r in just if r["kod"] not in flagg] or raw

        elig = {r["kod"] for r in just}
        rm = {r["kod"]: i + 1 for i, r in enumerate(just)}
        if schedf(pi, dt) or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= hyst_rank and k in elig]
            sel0 = (keep + [r["kod"] for r in just if r["kod"] not in keep])[:N]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in just if r["kod"] not in sel0][: N - len(sel0)]
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev, prevw = sel0, {}; continue
        ts = n / N
        inv = 1.0 / (np.maximum(np.array([volf(k, dt) for k in sel]), 0.05) ** 1.5)
        w = inv / np.sum(inv) * ts
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        if regel == "vikt":
            w = w * np.array([straff if b[k] >= trosk else 1.0 for k in sel])
        w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * ts
        if prevw:
            w = np.array([prevw.get(k, 0.0) if (abs(w[i] - prevw.get(k, 0.0)) < 0.005
                                                and prevw.get(k, 0.0) > 0) else w[i]
                          for i, k in enumerate(sel)])
            w = w / np.sum(w) * ts
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not prev else \
            sum(abs(curr.get(k, 0.0) - prevw.get(k, 0.0)) for k in set(prevw) | set(curr)) / 2.0
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev, prevw = sel0, curr
    return np.array(nets), float(np.mean(n_traffar))


def main():
    ut = {"version": "FI_BLANKNING_SIGNAL_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "kalla": "FI blankningsregistret, historik 2012-2026",
          "lagg_dagar": LAGG_DAGAR}

    B = {}
    for w_, F in (("26", S.F26), ("19", S.F19)):
        B[w_] = bygg_cache(F)

    # ---- STEG 1: hur mycket kan signalen ens röra?
    print("STEG 1. TÄCKNING — hur många namn kan regeln överhuvudtaget röra?")
    ut["tackning"] = {}
    for w_, F, namn in (("26", S.F26, "2020-2026"), ("19", S.F19, "2014-2019")):
        blank = B[w_]
        rader = []
        for dt in F["eval_dates"]:
            t30 = [r["kod"] for r in F["rankings"][dt][:30]]
            v = [blank.get((k, dt), 0.0) for k in t30]
            rader.append((sum(1 for x in v if x > 0), sum(1 for x in v if x >= 1.0),
                          sum(1 for x in v if x >= 2.0), float(np.mean(v))))
        a = np.array(rader)
        alla = [blank.get((r["kod"], dt), 0.0) for dt in F["eval_dates"] for r in F["rankings"][dt]]
        print(f"  {namn}: av topp-30 per panel har i snitt {a[:,0].mean():.1f} namn "
              f"någon blankning, {a[:,1].mean():.1f} över 1 %, {a[:,2].mean():.1f} över 2 %")
        print(f"     medelblankning i topp-30 {a[:,3].mean():.3f} %, "
              f"i hela universumet {np.mean(alla):.3f} %, "
              f"andel av universumet med position {np.mean(np.array(alla) > 0):.1%}")
        ut["tackning"][namn] = {"topp30_med_position": round(float(a[:, 0].mean()), 2),
                                "topp30_over_1pct": round(float(a[:, 1].mean()), 2),
                                "topp30_over_2pct": round(float(a[:, 2].mean()), 2),
                                "medel_topp30_pct": round(float(a[:, 3].mean()), 4),
                                "medel_universum_pct": round(float(np.mean(alla)), 4),
                                "andel_universum_med_position": round(float(np.mean(np.array(alla) > 0)), 4)}

    # ---- STEG 2: är blankning kopplad till framtida avkastning alls?
    print("\nSTEG 2. RÅ SAMBAND — blankning mot NÄSTA PANELS avkastning, hela universumet")
    ut["samband"] = {}
    for w_, F, namn in (("26", S.F26, "2020-2026"), ("19", S.F19, "2014-2019")):
        blank, ret = B[w_], F["returns_map"]
        med, utan = [], []
        for dt in F["eval_dates"]:
            for r in F["rankings"][dt]:
                v = ret.get((r["kod"], dt))
                if v is None:
                    continue
                (med if blank.get((r["kod"], dt), 0.0) >= 1.0 else utan).append(v)
        m, u = np.array(med), np.array(utan)
        if len(m) > 10:
            se = math.sqrt(m.var(ddof=1) / len(m) + u.var(ddof=1) / len(u))
            t = (m.mean() - u.mean()) / se
        else:
            t = float("nan")
        print(f"  {namn}: blankade >=1 % n={len(m)} avk {m.mean():+.3%} | "
              f"övriga n={len(u)} avk {u.mean():+.3%} | skillnad {m.mean()-u.mean():+.3%} (t {t:+.2f})")
        ut["samband"][namn] = {"n_blankade": len(m), "avk_blankade": round(float(m.mean()), 5),
                               "n_ovriga": len(u), "avk_ovriga": round(float(u.mean()), 5),
                               "skillnad": round(float(m.mean() - u.mean()), 5), "t": round(float(t), 2)}

    # ---- STEG 3: som regel mot STACK_H
    BAS = {"26": S.kor(**S.F26)[0], "19": S.kor(**S.F19)[0]}
    print(f"\n  baslinjekontroll: STACK_H {S.stat(BAS['26'])['cagr']:.2%} / "
          f"{S.stat(BAS['19'])['cagr']:.2%}  (registret: 13,56 %)")

    print("\nSTEG 3. SOM REGEL MOT STACK_H")
    print(f"  {'variant':<38}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}{'träffar':>9}  repl")
    ut["regler"] = {}
    varianter = [
        ("N1 uteslut blankning >= 0,5 %", dict(regel="uteslut", trosk=0.5)),
        ("N1 uteslut blankning >= 1 %", dict(regel="uteslut", trosk=1.0)),
        ("N1 uteslut blankning >= 2 %", dict(regel="uteslut", trosk=2.0)),
        ("N2 halverad vikt vid >= 1 %", dict(regel="vikt", trosk=1.0, straff=0.5)),
        ("N2 vikt x0,75 vid >= 1 %", dict(regel="vikt", trosk=1.0, straff=0.75)),
        ("N3 rankstraff, skala 0,5", dict(regel="rank", straff=0.5)),
        ("N3 rankstraff, skala 2,0", dict(regel="rank", straff=2.0)),
        ("F1 uteslut stigande >= +0,5 pp/3 pan", dict(forandring="stigande", trosk=0.5)),
        ("F1 uteslut stigande >= +1 pp/3 pan", dict(forandring="stigande", trosk=1.0)),
        ("F2 bonus vid fallande >= 0,5 pp", dict(forandring="fallande", trosk=0.5, straff=1.0)),
        ("K1 kontrar: blankning som plus 0,5", dict(regel="kontrar", straff=0.5)),
        ("K1 kontrar: blankning som plus 2,0", dict(regel="kontrar", straff=2.0)),
    ]
    for namn, kw in varianter:
        a26, tr26 = sim(S.F26, B["26"], **kw)
        a19, tr19 = sim(S.F19, B["19"], **kw)
        d26, d19 = S.boot(a26, BAS["26"]), S.boot(a19, BAS["19"])
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["regler"][namn] = {"f2020_2026": {**S.stat(a26), **d26, "traffar_per_panel": round(tr26, 2)},
                              "f2014_2019": {**S.stat(a19), **d19, "traffar_per_panel": round(tr19, 2)},
                              "bada_positiva": bool(rep)}
        print(f"  {namn:<38}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
              f"{tr26:>5.1f}/{tr19:<4.1f}  {'JA' if rep else '-'}")

    # ---- STEG 4: placebo för uteslutningsreglerna
    print("\nSTEG 4. PLACEBO — slumpmässig uteslutning av lika många namn, 60 dragningar")
    ut["placebo"] = {}
    for nyckel in ("N1 uteslut blankning >= 1 %", "N1 uteslut blankning >= 0,5 %",
                   "F1 uteslut stigande >= +0,5 pp/3 pan"):
        rad = {}
        for w_, F, namn in (("26", S.F26, "2020-2026"), ("19", S.F19, "2014-2019")):
            f = f"f{'2020_2026' if w_ == '26' else '2014_2019'}"
            nn = ut["regler"][nyckel][f]["traffar_per_panel"]
            d = np.array([S.boot(sim(F, B[w_], regel="slump", slump_n=max(1, round(nn)))[0],
                                 BAS[w_])["delta_cagr"] for _ in range(60)])
            rad[namn] = {"n_uteslutna_per_panel": nn, "medel": round(float(d.mean()), 5),
                         "sd": round(float(d.std(ddof=1)), 5),
                         "band_2sd": [round(float(d.mean() - 2 * d.std(ddof=1)), 4),
                                      round(float(d.mean() + 2 * d.std(ddof=1)), 4)],
                         "regelns_delta": ut["regler"][nyckel][f]["delta_cagr"]}
            reg = ut["regler"][nyckel][f]["delta_cagr"]
            innanfor = abs(reg - d.mean()) <= 2 * d.std(ddof=1)
            rad[namn]["inom_placebobandet"] = bool(innanfor)
            print(f"  {nyckel[:34]:<34} {namn}: placebo {d.mean():+.2%} sd {d.std(ddof=1):.2%} "
                  f"band [{d.mean()-2*d.std(ddof=1):+.2%},{d.mean()+2*d.std(ddof=1):+.2%}] "
                  f"regel {reg:+.2%} → {'INOM (= slump)' if innanfor else 'UTANFÖR'}")
        ut["placebo"][nyckel] = rad

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    n = sum(1 for v in ut["regler"].values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n} av {len(ut['regler'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
