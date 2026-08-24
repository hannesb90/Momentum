"""TRE FRÅGOR: TIDIG DETEKTION, ROTATION TILL BEFINTLIGT, OCH UTDELNING

1. Hur snabbt syns det att ett innehav inte kommer prestera?
   Mäter hur väl de första panelernas avkastning förutsäger resten av
   innehavet, och hur utfallet ser ut betingat på ett svagt första utfall.

2. Går det att rotera från svag till redan ägd position i stället för att
   byta ut namnet? Testar att vid ombalansering flytta vikt från innehav med
   svagt hittills-utfall till dem med starkt, i stället för invers vol.

3. Hanteras utdelning korrekt?
   Verifierar att adjusted_close är totalavkastningsjusterad genom att jämföra
   adj-avkastning mot close-avkastning plus utdelning på X-dagar.

Kör: /opt/momentum/venv/bin/python tools/tidig_detektion_och_utdelning.py
"""
from __future__ import annotations
import gzip, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/tidig_detektion_och_utdelning_results.json"
COST = 0.002


def innehavsbanor(F):
    """Alla innehavsperioder i STACK_H med avkastning per panel."""
    dts, ret = F["eval_dates"], F["returns_map"]
    smaf, schedf = F["sma_fn"], F["sched_fn"]
    prev, oppna, spells = [], {}, []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]; elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if schedf(pi, dt) or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= 35 and k in elig]
            sel0 = (keep + [r["kod"] for r in raw if r["kod"] not in keep])[:30]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < 30:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
        for k in prev:
            if k not in sel0 and k in oppna:
                spells.append(oppna.pop(k))
        for k in sel0:
            oppna.setdefault(k, {"kod": k, "avk": []})
            oppna[k]["avk"].append(ret.get((k, dt), 0.0))
        prev = sel0
    spells.extend(oppna.values())
    return [s for s in spells if len(s["avk"]) >= 3]


def del1_detektion(F, namn):
    sp = innehavsbanor(F)
    ut = {"n_spells": len(sp)}
    for k in (1, 2, 3):
        par = [(float(np.prod([1 + x for x in s["avk"][:k]]) - 1),
                float(np.prod([1 + x for x in s["avk"][k:]]) - 1))
               for s in sp if len(s["avk"]) > k]
        if len(par) < 20:
            continue
        x = np.array([p[0] for p in par]); y = np.array([p[1] for p in par])
        r = float(np.corrcoef(x, y)[0, 1])
        svaga = y[x < 0]; starka = y[x >= 0]
        ut[f"efter_{k}_paneler"] = {
            "n": len(par), "korrelation_mot_resten": round(r, 4),
            "t": round(float(r * math.sqrt((len(x) - 2) / max(1e-12, 1 - r ** 2))), 2),
            "resten_om_svag_start": round(float(svaga.mean()), 4) if len(svaga) else None,
            "resten_om_stark_start": round(float(starka.mean()), 4) if len(starka) else None,
            "andel_svag_start": round(float(np.mean(x < 0)), 3),
            "andel_svaga_som_slutar_minus": round(float(np.mean(svaga < 0)), 3) if len(svaga) else None,
            "andel_starka_som_slutar_minus": round(float(np.mean(starka < 0)), 3) if len(starka) else None}
    print(f"\n  {namn}: {len(sp)} innehavsperioder")
    for k in (1, 2, 3):
        d = ut.get(f"efter_{k}_paneler")
        if not d:
            continue
        print(f"    efter {k} panel(er): korr mot resten {d['korrelation_mot_resten']:+.3f} "
              f"(t {d['t']:+.2f})")
        print(f"       svag start -> resten {d['resten_om_svag_start']:+.2%} | "
              f"stark start -> resten {d['resten_om_stark_start']:+.2%}")
        print(f"       av de svaga slutar {d['andel_svaga_som_slutar_minus']:.0%} på minus, "
              f"av de starka {d['andel_starka_som_slutar_minus']:.0%}")
    return ut


def del2_rotera(F, tilt):
    """Vid ombalansering: flytta vikt mot innehav med starkt hittills-utfall."""
    dts, ret = F["eval_dates"], F["returns_map"]
    volf, smaf, conff, schedf = F["vol_fn"], F["sma_fn"], F["conf_fn"], F["sched_fn"]
    prev, prevw, nets, hittills = [], {}, [], defaultdict(float)
    for pi, dt in enumerate(dts):
        sched = schedf(pi, dt)
        raw = F["rankings"][dt]; elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if sched or not prev:
            keep = [k for k in (prev or []) if rm.get(k, 999) <= 35 and k in elig]
            sel0 = (keep + [r["kod"] for r in raw if r["kod"] not in keep])[:30]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < 30:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
        for k in prev:
            if k not in sel0:
                hittills.pop(k, None)
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev, prevw = sel0, {}; continue
        ts = n / 30
        inv = 1.0 / (np.maximum(np.array([volf(k, dt) for k in sel]), 0.05) ** 1.5)
        w = inv / np.sum(inv) * ts
        if sched and tilt:
            h = np.array([hittills.get(k, 0.0) for k in sel])
            faktor = np.exp(tilt * np.clip(h, -0.5, 0.5))
            w = w * faktor; w = w / np.sum(w) * ts
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * ts
        if prevw:
            w = np.array([prevw.get(k, 0.0) if (abs(w[i] - prevw.get(k, 0.0)) < 0.005
                                                and prevw.get(k, 0.0) > 0) else w[i]
                          for i, k in enumerate(sel)])
            w = w / np.sum(w) * ts
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not prev else \
            sum(abs(curr.get(k, 0.0) - prevw.get(k, 0.0)) for k in set(prevw) | set(curr)) / 2.0
        rets = np.array([ret.get((k, dt), 0.0) for k in sel])
        for k, r_ in zip(sel, rets):
            hittills[k] = (1 + hittills[k]) * (1 + r_) - 1
        nets.append(float(np.sum(w * rets)) - COST * turn)
        prev, prevw = sel0, curr
    return np.array(nets)


def del3_utdelning():
    """Verifiera att adjusted_close bär utdelningen."""
    fall = []
    for kod in ("VOLV-B", "SEB-A", "TELIA", "HM-B", "SHB-A"):
        rows = divs = None
        for kat in ("active", "delisted"):
            p = EOD / kat / "eod" / f"{kod}.json.gz"
            if p.exists():
                with gzip.open(p, "rt") as f:
                    rows = json.load(f)
                with gzip.open(EOD / kat / "div" / f"{kod}.json.gz", "rt") as f:
                    divs = json.load(f)
                break
        if not rows or not divs:
            continue
        idx = {r["date"]: i for i, r in enumerate(rows)}
        for dv in divs:
            d, v = dv.get("date"), dv.get("unadjustedValue") or dv.get("value")
            if not d or d not in idx or idx[d] == 0 or not v or d < "2020-01-01":
                continue
            i = idx[d]
            c0, c1 = rows[i - 1]["close"], rows[i]["close"]
            a0, a1 = rows[i - 1]["adjusted_close"], rows[i]["adjusted_close"]
            if not all((c0, c1, a0, a1)) or c0 <= 0 or a0 <= 0:
                continue
            fall.append({"kod": kod, "xdag": d, "utdelning": round(float(v), 3),
                         "ret_close": round(c1 / c0 - 1, 4),
                         "ret_adj": round(a1 / a0 - 1, 4),
                         "ret_close_plus_utd": round((c1 + float(v)) / c0 - 1, 4),
                         "avvikelse_adj_mot_TR": round((a1 / a0) - ((c1 + float(v)) / c0), 5)})
            if len([f for f in fall if f["kod"] == kod]) >= 3:
                break
    av = [abs(f["avvikelse_adj_mot_TR"]) for f in fall]
    return {"n_xdagar": len(fall), "median_absolut_avvikelse": round(float(np.median(av)), 6) if av else None,
            "max_absolut_avvikelse": round(float(max(av)), 6) if av else None,
            "slutsats": "adjusted_close ÄR totalavkastningsjusterad — utdelningen ligger i serien"
                        if av and max(av) < 0.005 else "AVVIKER — kontrollera",
            "exempel": fall[:8]}


def main():
    ut = {"version": "TIDIG_DETEKTION_OCH_UTDELNING_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    print("1. HUR SNABBT SYNS DET ATT ETT INNEHAV INTE PRESTERAR?")
    ut["detektion"] = {"2020_2026": del1_detektion(S.F26, "2020-2026"),
                       "2014_2019": del1_detektion(S.F19, "2014-2019")}
    print("\n2. ROTERA VIKT MOT STARKA INNEHAV I STÄLLET FÖR BYTE")
    bas26, bas19 = S.kor(**S.F26)[0], S.kor(**S.F19)[0]
    ut["rotation"] = {}
    print(f"  {'tilt':<22}{'Δ 20-26':>9}{'Δ 14-19':>9}")
    for t in (0.5, 1.0, 2.0, -1.0):
        a26, a19 = del2_rotera(S.F26, t), del2_rotera(S.F19, t)
        d26, d19 = S.boot(a26, bas26), S.boot(a19, bas19)
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["rotation"][f"tilt_{t}"] = {"f2020_2026": {**S.stat(a26), **d26},
                                       "f2014_2019": {**S.stat(a19), **d19},
                                       "bada_positiva": bool(rep)}
        print(f"  vikttilt {t:+.1f}{'':<10}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
              f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")
    print("\n3. UTDELNINGSHANTERING")
    ut["utdelning"] = del3_utdelning()
    u = ut["utdelning"]
    print(f"  {u['n_xdagar']} X-dagar prövade, median absolut avvikelse "
          f"{u['median_absolut_avvikelse']}, max {u['max_absolut_avvikelse']}")
    print(f"  {u['slutsats']}")
    for f in u["exempel"][:4]:
        print(f"    {f['kod']:<8} {f['xdag']}  utd {f['utdelning']:>6}  "
              f"close {f['ret_close']:+.2%}  adj {f['ret_adj']:+.2%}  "
              f"close+utd {f['ret_close_plus_utd']:+.2%}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
