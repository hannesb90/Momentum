"""A4 — OPPORTUNITY-COST-BYTE (legacy `swap_10`, aldrig replikerad i v2)

Legacys starkaste enskilda fynd. Rättelseposten 2026-08-05:

  "swap_10 är den enda mekanism i hela sessionen som klarar BÅDA kontrollerna
   — placebo (percentil 100 på båda fönstren) och lotteri (över SE i båda
   fönstren). Ingen annan mekanism, konfiguration eller insättningsregel har
   gjort det."

Mätt mot LambdaRank/LSTM-modellen, alltså ett annat urval. Det gör den till en
hypotes med känd riktning, inte ett resultat för STACK_H.

MEKANISMEN
  STACK_H har hysteres — den säger när ett innehav FÅR BEHÅLLAS (rank <= 35).
  Den har ingen regel för när ett byte är VÄRT ATT GÖRA. Swap fyller det hålet:

    byt ut ett innehav om
      (1) det underpresterar mot universumet sedan köptillfället med mer än U, OCH
      (2) bästa icke-ägda kandidat har en poäng som överstiger innehavets med
          mer än G

  Legacy komponentanalys 2026-08-04: "underprestationsvillkoret bär effekten,
  inte streckkravet". Därför svepas U och G separat, inte som ett rutnät med
  ett enda valt hörn.

  Bytet får ske på VARJE panel, även icke-rebalanspaneler. Det är hela poängen:
  en möjlighet som uppstår vecka 3 av 8 ska inte behöva vänta.

F1-FÖRFININGEN
  Legacy 2026-08-04 fann att en tilläggsregel förbättrade allt: vägra byta IN
  ett namn som ligger mer än -10 % under sin egen 52v-topp. Prövas separat.

  Men samma logg visar att varje efterföljande "förbättring" sänkte
  framåteffekten monotont (+2,61 -> +1,27 -> +0,30 pp), eftersom optimeringarna
  valdes på en enskild kalender. Därför rapporteras grundmekanismen först och
  förfiningen som ett separat, efterställt utfall.

PLACEBO
  Regeln byter namn, alltså jämförs den mot slumpmässigt byte av lika många
  namn per panel.

Kör: /opt/momentum/venv/bin/python tools/a4_opportunity_cost_swap.py
"""
from __future__ import annotations
import bisect, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/a4_opportunity_cost_swap_results.json"
COST = 0.002
RNG = np.random.default_rng(20260816)


def under_egen_topp(F, k, dt):
    """Hur långt under sin egen 52v-topp namnet ligger. None om okänt."""
    if F is S.F19:
        s = M.SERIE.get(k)
        if s is None:
            return None
        ds, v = s
        now = np.datetime64(dt)
        i = int(np.searchsorted(ds, now, side="right")) - 1
        if i < 20:
            return None
        j = max(0, i - 252)
        topp = float(np.max(v[j:i + 1]))
        return float(v[i] / topp - 1) if topp > 0 else None
    s = S.PS26.get(k)
    if s is None:
        return None
    ds, adj = s
    i = bisect.bisect_right(ds, dt) - 1
    if i < 20:
        return None
    j = max(0, i - 252)
    topp = float(np.max(adj[j:i + 1]))
    return float(adj[i] / topp - 1) if topp > 0 else None


def sim(F, U=None, G=None, f1=False, slump_n=None, N=30, hyst_rank=35):
    """Identisk med stack_h_motor.kor utom att ett bytessteg läggs till efter
    urvalet. U=underprestation mot universumet sedan köp, G=poänggap."""
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    previous, prev_weights, periods = [], {}, []
    rel = {}          # kod -> ackumulerad relativavkastning mot universumet sedan köp
    n_byten = []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        elig = {r["kod"] for r in raw}
        rank_map = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        score = {r["kod"]: r["score"] for r in raw}

        if schedf(pi, dt) or not previous:
            keep = [k for k in previous if rank_map.get(k, 999) <= hyst_rank and k in elig]
            sel0 = (keep + [r["kod"] for r in raw if r["kod"] not in keep])[:N]
        else:
            sel0 = [k for k in previous if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]

        # ---- BYTESSTEGET ----
        byten = 0
        if previous and (U is not None or slump_n is not None):
            kandidater = [r["kod"] for r in raw if r["kod"] not in sel0]
            if f1:
                kandidater = [k for k in kandidater
                              if (x := under_egen_topp(F, k, dt)) is None or x > -0.10]
            if slump_n is not None:
                m = min(slump_n, len(sel0), len(kandidater))
                if m > 0:
                    ut_i = RNG.choice(len(sel0), size=m, replace=False)
                    for j, i in enumerate(sorted(ut_i)):
                        sel0[i] = kandidater[j]
                    byten = m
            else:
                # svagast först: mest underpresterande innehav prövas mot bästa kandidat
                ordning = sorted(range(len(sel0)), key=lambda i: rel.get(sel0[i], 0.0))
                nasta = 0
                for i in ordning:
                    k = sel0[i]
                    if rel.get(k, 0.0) > -U:
                        continue
                    while nasta < len(kandidater) and kandidater[nasta] in sel0:
                        nasta += 1
                    if nasta >= len(kandidater):
                        break
                    c = kandidater[nasta]
                    if G is not None and score.get(c, 0) - score.get(k, 0) <= G:
                        continue
                    sel0[i] = c
                    nasta += 1
                    byten += 1
        n_byten.append(byten)

        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            periods.append({"net": 0.0, "turnover": 0.0}); previous, prev_weights = sel0, {}
            continue
        vols = np.array([volf(k, dt) for k in sel], dtype=float)
        inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
        w = inv / np.sum(inv) * (n / N)
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        w = np.clip(w, 0.01, 0.06)
        w = w / np.sum(w) * (n / N)
        if prev_weights:
            w = np.array([prev_weights.get(k, 0.0)
                          if (abs(w[i] - prev_weights.get(k, 0.0)) < 0.005
                              and prev_weights.get(k, 0.0) > 0) else w[i]
                          for i, k in enumerate(sel)])
            w = w / np.sum(w) * (n / N)
        curr = dict(zip(sel, w))
        if not previous:
            turnover = float(np.sum(w))
        else:
            alla = set(prev_weights) | set(curr)
            turnover = sum(abs(curr.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in alla) / 2.0
        rets = np.array([ret.get((k, dt), 0.0) for k in sel])
        periods.append({"net": float(np.sum(w * rets)) - COST * turnover, "turnover": turnover})

        # uppdatera relativavkastning sedan köp
        univ = float(np.mean([ret.get((r["kod"], dt), 0.0) for r in raw]))
        nya = set(sel0) - set(previous)
        for k in list(rel):
            if k not in sel0:
                rel.pop(k)
        for k in sel0:
            if k in nya:
                rel[k] = 0.0
            else:
                rel[k] = (1 + rel.get(k, 0.0)) * (1 + ret.get((k, dt), 0.0)) / (1 + univ) - 1
        previous, prev_weights = sel0, curr
    return np.array([p["net"] for p in periods]), float(np.mean(n_byten))


def main():
    bas26, bas19 = S.kor(**S.F26)[0], S.kor(**S.F19)[0]
    print(f"baslinjekontroll: STACK_H {S.stat(bas26)['cagr']:.2%} / {S.stat(bas19)['cagr']:.2%}")
    if abs(S.stat(bas26)["cagr"] - 0.1356) > 0.004:
        sys.exit("AVBRYTER: baslinjen reproducerar inte")
    # kontroll: utan bytesregel ska motorn ge baslinjen
    k26 = sim(S.F26)[0]
    print(f"motorkontroll (bytesregel av): {S.stat(k26)['cagr']:.2%} "
          f"{'OK' if abs(S.stat(k26)['cagr'] - S.stat(bas26)['cagr']) < 0.0005 else 'AVVIKER'}")

    ut = {"version": "A4_OPPORTUNITY_COST_SWAP_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "varianter": {}}
    print(f"\n  {'variant':<38}{'CAGR26':>8}{'Δ':>9}{'CAGR19':>9}{'Δ':>9}{'byten':>9}  repl")
    print(f"  {'STACK_H (ingen swap)':<38}{S.stat(bas26)['cagr']:>8.2%}{'—':>9}"
          f"{S.stat(bas19)['cagr']:>9.2%}{'—':>9}")

    varianter = []
    for U in (0.0, 0.05, 0.10, 0.20):
        varianter.append((f"U={U:.0%} underpr., inget poänggap", dict(U=U, G=None)))
    for G in (0.02, 0.05, 0.10):
        varianter.append((f"U=10% + poänggap G={G:.2f}", dict(U=0.10, G=G)))
    varianter.append(("U=10% + F1 (ej -10% under egen topp)", dict(U=0.10, G=None, f1=True)))
    varianter.append(("U=10% + G=0,05 + F1", dict(U=0.10, G=0.05, f1=True)))

    for namn, kw in varianter:
        a26, b26 = sim(S.F26, **kw)
        a19, b19 = sim(S.F19, **kw)
        d26, d19 = S.boot(a26, bas26), S.boot(a19, bas19)
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["varianter"][namn] = {"f2020_2026": {**S.stat(a26), **d26, "byten_per_panel": round(b26, 2)},
                                 "f2014_2019": {**S.stat(a19), **d19, "byten_per_panel": round(b19, 2)},
                                 "bada_positiva": bool(rep)}
        print(f"  {namn:<38}{S.stat(a26)['cagr']:>8.2%}{d26['delta_cagr']:>+9.2%}"
              f"{S.stat(a19)['cagr']:>9.2%}{d19['delta_cagr']:>+9.2%}"
              f"{b26:>5.1f}/{b19:<4.1f}  {'JA' if rep else '-'}")

    b = max(ut["varianter"], key=lambda k: min(ut["varianter"][k]["f2020_2026"]["delta_cagr"],
                                               ut["varianter"][k]["f2014_2019"]["delta_cagr"]))
    print(f"\nPLACEBO för bästa varianten ({b}) — slumpmässiga byten av lika många namn, 40 dragningar")
    ut["placebo"] = {"variant": b}
    for w_, F, bas, namn in (("2020_2026", S.F26, bas26, "2020-2026"),
                             ("2014_2019", S.F19, bas19, "2014-2019")):
        nb = ut["varianter"][b][f"f{w_}"]["byten_per_panel"]
        d = np.array([S.boot(sim(F, slump_n=max(1, round(nb)))[0], bas)["delta_cagr"]
                      for _ in range(40)])
        reg = ut["varianter"][b][f"f{w_}"]["delta_cagr"]
        inom = abs(reg - d.mean()) <= 2 * d.std(ddof=1)
        ut["placebo"][namn] = {"n_byten": nb, "medel": round(float(d.mean()), 5),
                               "sd": round(float(d.std(ddof=1)), 5), "regelns_delta": reg,
                               "inom_placebobandet": bool(inom)}
        print(f"  {namn}: placebo {d.mean():+.2%} sd {d.std(ddof=1):.2%} "
              f"band [{d.mean()-2*d.std(ddof=1):+.2%},{d.mean()+2*d.std(ddof=1):+.2%}] "
              f"regel {reg:+.2%} → {'INOM (= slump)' if inom else 'UTANFÖR'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    n = sum(1 for v in ut["varianter"].values() if v["bada_positiva"])
    print(f"\nPositiva i båda fönstren: {n} av {len(ut['varianter'])}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
