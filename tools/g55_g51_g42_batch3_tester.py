"""BATCH 3:s LICENSIERADE TESTER — G55/G40, G51/G52, G42

Locked H0 enligt trackh/H0_LOCK.json med G29:s vikträttelse:
topp-30, lika vikt 1/30, ombalans var andra panel, drift på mellanpanel,
20 bp enkelsidigt. Referens: 7,20 % (2020-2026) och 31,56 % (2014-2019).

STEG 1  G55/G40 — koncentration och höger-svansberoende
STEG 2  G51/G52 — accelerationens INKREMENTELLA signalvärde utöver H0-rank
STEG 3  G51/G52 — portföljvärde, ENDAST om steg 2 ger REPLICATED INCREMENTAL
STEG 4  G42     — SMA200 som absolut trendvillkor

ACCELERATIONSDEFINITION — återanvänd oförändrad från
tools/granskning_statisk_vs_dynamisk.py::lutning:
    acceleration(k, panel_i) = H0_score(k, panel_i) − H0_score(k, panel_i−3)
Ingen ny lookback, ingen ny transformation.

SMA-DEFINITION — återanvänd oförändrad: stack_h_motor.sma26 respektive
h1419_motor.sma_ok, båda pris mot 200-dagars medel.

Fem evidensnivåer hålls isär: deskriptiv mekanism, prediction skill,
INKREMENTELL prediction skill, decision skill, portfolio value.

Kör: /opt/momentum/venv/bin/python tools/g55_g51_g42_batch3_tester.py
"""
from __future__ import annotations
import json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g55_g51_g42_results.json"
PANELDATA = V2 / "research_k/g55_g51_g42_paneldata.jsonl"
COST = 0.002
PPY = 13
N = 30
HOR = [(1, "4v"), (2, "8v"), (3, "12v"), (6, "24v")]


def h0(F, uteslut=None, ersatt_regel=None, ersatt_data=None, andel=0.20):
    """Locked H0. uteslut: koder som tas bort ur universumet (diagnostik).
       ersatt_regel: None | 'acc' | 'sma' — ersätter namn i topp-30."""
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    ute = set(uteslut or [])
    w, nets, turns, bidrag, hist = {}, [], [], defaultdict(float), []
    for pi, dt in enumerate(dts):
        raw = [r for r in F["rankings"][dt] if r["kod"] not in ute]
        if schedf(pi, dt) or not w:
            sel = [r["kod"] for r in raw][:N]
            if ersatt_regel:
                kand = [r["kod"] for r in raw[N:]]
                if ersatt_regel == "acc":
                    v = {k: ersatt_data.get((k, pi)) for k in sel}
                    giltiga = {k: x for k, x in v.items() if x is not None}
                    m = int(round(andel * len(sel)))
                    if len(giltiga) >= 10 and m > 0:
                        bort = sorted(giltiga, key=lambda k: giltiga[k])[:m]
                        ers = [k for k in kand if ersatt_data.get((k, pi)) is not None][:len(bort)]
                        sel = [k for k in sel if k not in bort] + ers
                else:
                    ok = [k for k in sel if ersatt_data(k, dt)]
                    behov = len(sel) - len(ok)
                    ers = [k for k in kand if ersatt_data(k, dt)][:behov]
                    sel = ok + ers
                sel = sel[:N]
            mal = {k: 1.0 / N for k in sel}
            tot = sum(mal.values())
            mal = {k: v / tot for k, v in mal.items()} if tot > 0 else {}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0)) for k in set(mal) | set(w)) / 2.0
        else:
            mal = dict(w)
            turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        gross = float(sum(mal[k] * r[k] for k in mal))
        nets.append(gross - COST * turn)
        turns.append(turn)
        for k in mal:
            bidrag[k] += mal[k] * r[k]
        hist.append({"dt": dt, "sel": list(mal), "vikter": dict(mal), "avk": dict(r)})
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return np.array(nets), np.array(turns), dict(bidrag), hist


# ---------------------------------------------------------------- STEG 1
def steg1(F, namn):
    nets, turns, bidrag, hist = h0(F)
    bas = S.stat(nets)
    b = sorted(bidrag.items(), key=lambda x: -x[1])
    pos = sum(v for _, v in b if v > 0)
    print(f"\n{'='*76}\nSTEG 1 — G55/G40 KONCENTRATION   {namn}")
    print(f"  locked H0: CAGR {bas['cagr']:.2%}  (referens "
          f"{'7,20 %' if F is S.F26 else '31,56 %'})")
    print(f"  antal namn med bidrag: {len(bidrag)}   summa positiva bidrag {pos:.2%}")
    for n_ in (1, 3, 5, 10):
        andel = sum(v for _, v in b[:n_]) / pos if pos else 0
        print(f"    topp-{n_:<2} andel av total vinst: {andel:>7.1%}   "
              f"{', '.join(k for k, _ in b[:n_][:5])}")
    hhi = sum((v / pos) ** 2 for _, v in b if v > 0) if pos else 0
    print(f"    HHI på positiva bidrag: {hhi:.4f}  (effektivt antal bidragsgivare "
          f"{1/hhi:.1f})")

    rad = {"cagr_alla": bas["cagr"], "n_bidragsgivare": len(bidrag),
           "hhi_positiva": round(hhi, 5),
           "andelar": {}, "leave_out": {}, "leave_one": {}}
    for n_ in (1, 3, 5, 10):
        rad["andelar"][f"topp{n_}"] = round(sum(v for _, v in b[:n_]) / pos, 4) if pos else None
    print(f"\n  CAGR efter att namnen tas bort ur universumet (diagnostik, ej strategi)")
    print(f"    {'variant':<26}{'CAGR':>9}{'Δ mot alla':>13}")
    print(f"    {'alla namn':<26}{bas['cagr']:>9.2%}{'—':>13}")
    for n_ in (1, 3, 5):
        koder = [k for k, _ in b[:n_]]
        c = S.stat(h0(F, uteslut=koder)[0])["cagr"]
        rad["leave_out"][f"topp{n_}"] = {"cagr": round(c, 5), "delta": round(c - bas["cagr"], 5),
                                          "koder": koder}
        print(f"    {'utan topp-' + str(n_):<26}{c:>9.2%}{c - bas['cagr']:>+13.2%}")

    print(f"\n  LEAVE-ONE-STOCK-OUT (tio största bidragsgivarna)")
    varsta = None
    for k, v in b[:10]:
        c = S.stat(h0(F, uteslut=[k])[0])["cagr"]
        rad["leave_one"][k] = {"cagr": round(c, 5), "delta": round(c - bas["cagr"], 5),
                               "bidrag": round(v, 5)}
        if varsta is None or c < varsta[1]:
            varsta = (k, c)
    for k, x in sorted(rad["leave_one"].items(), key=lambda y: y[1]["delta"])[:5]:
        print(f"    utan {k:<10}{x['cagr']:>9.2%}{x['delta']:>+13.2%}")
    print(f"    sämsta leave-one-out: {varsta[0]} → {varsta[1]:.2%}")

    # trimmad bidragsserie: vinsorisera panelbidrag på 1:a/99:e percentilen
    alla = [v for h in hist for v in
            [h["vikter"][k] * h["avk"].get(k, 0.0) for k in h["vikter"]]]
    lo, hi = np.percentile(alla, [1, 99])
    trimmade = []
    for h in hist:
        s_ = sum(float(np.clip(h["vikter"][k] * h["avk"].get(k, 0.0), lo, hi))
                 for k in h["vikter"])
        trimmade.append(s_)
    ct = S.stat(np.array(trimmade))["cagr"]
    rad["trimmad_cagr_1_99"] = round(ct, 5)
    print(f"\n  Trimmat bidrag (panelbidrag vinsoriserade 1:a/99:e percentilen, brutto): "
          f"{ct:.2%}")

    d3 = rad["leave_out"]["topp3"]["delta"]
    rad["hypotesen_haller"] = bool(abs(d3) < 0.08)
    rad["klassificering"] = ("ROBUST" if abs(d3) < 0.04 else
                             "MODERATELY CONCENTRATED" if abs(d3) < 0.08 else
                             "RIGHT-TAIL DEPENDENT")
    print(f"\n  Δ vid borttagning av topp-3: {d3:+.2%}  →  {rad['klassificering']}")
    return rad, hist


# ---------------------------------------------------------------- hjälp
def spearman(x, y):
    if len(x) < 8:
        return None
    def rk(a):
        o = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a); i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and a[o[j + 1]] == a[o[i]]:
                j += 1
            m = (i + j) / 2 + 1
            for t in range(i, j + 1):
                r[o[t]] = m
            i = j + 1
        return np.array(r)
    a, b = rk(x), rk(y)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


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


# ---------------------------------------------------------------- STEG 2
def steg2(F, namn, acc):
    dts = F["eval_dates"]
    ic = defaultdict(list); ric = defaultdict(list); kvint = defaultdict(lambda: defaultdict(list))
    tmb = defaultdict(list)
    for pi, dt in enumerate(dts):
        top = [r["kod"] for r in F["rankings"][dt]][:N]
        a = [(k, acc.get((k, pi))) for k in top]
        a = [(k, x) for k, x in a if x is not None]
        if len(a) < 20:
            continue
        sc = {r["kod"]: r["score"] for r in F["rankings"][dt]}
        koder = [k for k, _ in a]
        av = np.array([x for _, x in a])
        sv = np.array([sc[k] for k in koder])
        # residual acceleration efter kontroll för aktuell H0-score (rangbaserat)
        ra = np.argsort(np.argsort(av)).astype(float)
        rs = np.argsort(np.argsort(sv)).astype(float)
        if rs.std() > 0:
            beta = np.cov(ra, rs)[0, 1] / np.var(rs)
            res = ra - beta * (rs - rs.mean())
        else:
            res = ra
        for h, etikett in HOR:
            fw = [framat(F, k, pi, h) for k in koder]
            m = [i for i, x in enumerate(fw) if x is not None]
            if len(m) < 20:
                continue
            y = [fw[i] for i in m]
            v1 = spearman([av[i] for i in m], y)
            v2 = spearman([res[i] for i in m], y)
            if v1 is not None:
                ic[etikett].append(v1)
            if v2 is not None:
                ric[etikett].append(v2)
            ordn = sorted(m, key=lambda i: av[i])
            q = max(3, len(ordn) // 5)
            kvint[etikett]["Q1_lagst"].append(float(np.mean([fw[i] for i in ordn[:q]])))
            kvint[etikett]["Q5_hogst"].append(float(np.mean([fw[i] for i in ordn[-q:]])))
            tmb[etikett].append(float(np.mean([fw[i] for i in ordn[-q:]]) -
                                     np.mean([fw[i] for i in ordn[:q]])))
    print(f"\n{'='*76}\nSTEG 2 — G51/G52 ACCELERATIONENS INKREMENTELLA SIGNAL   {namn}")
    print(f"  population: H0 topp-30 vid beslutstidpunkten, {len(ic['4v'])} paneler")
    print(f"  {'horisont':<10}{'rank-IC':>10}{'t':>7}{'residual-IC':>14}{'t':>7}"
          f"{'topp−botten':>13}{'t':>7}")
    rad = {}
    for h, e in HOR:
        if not ic[e]:
            continue
        a1 = np.array(ic[e]); a2 = np.array(ric[e]); a3 = np.array(tmb[e])
        t1 = a1.mean() / (a1.std(ddof=1) / math.sqrt(len(a1)))
        t2 = a2.mean() / (a2.std(ddof=1) / math.sqrt(len(a2)))
        t3 = a3.mean() / (a3.std(ddof=1) / math.sqrt(len(a3)))
        rad[e] = {"ic": round(float(a1.mean()), 4), "t_ic": round(float(t1), 2),
                  "residual_ic": round(float(a2.mean()), 4), "t_residual": round(float(t2), 2),
                  "topp_minus_botten": round(float(a3.mean()), 5), "t_tmb": round(float(t3), 2),
                  "Q1": round(float(np.mean(kvint[e]["Q1_lagst"])), 5),
                  "Q5": round(float(np.mean(kvint[e]["Q5_hogst"])), 5), "n_paneler": len(a1)}
        print(f"  {e:<10}{a1.mean():>+10.4f}{t1:>7.2f}{a2.mean():>+14.4f}{t2:>7.2f}"
              f"{a3.mean():>+13.2%}{t3:>7.2f}")
    return rad


# ---------------------------------------------------------------- STEG 4 diag
def steg4_diag(F, namn, smaf):
    dts = F["eval_dates"]
    over, under, ric = defaultdict(list), defaultdict(list), defaultdict(list)
    for pi, dt in enumerate(dts):
        top = [r["kod"] for r in F["rankings"][dt]][:N]
        flagga = {k: bool(smaf(k, dt)) for k in top}
        sc = {r["kod"]: r["score"] for r in F["rankings"][dt]}
        for h, e in HOR:
            fw = {k: framat(F, k, pi, h) for k in top}
            a = [fw[k] for k in top if fw[k] is not None and flagga[k]]
            b = [fw[k] for k in top if fw[k] is not None and not flagga[k]]
            if len(a) >= 5 and len(b) >= 3:
                over[e].append(float(np.mean(a))); under[e].append(float(np.mean(b)))
            koder = [k for k in top if fw[k] is not None]
            if len(koder) >= 20:
                rs = np.argsort(np.argsort([sc[k] for k in koder])).astype(float)
                fv = np.array([1.0 if flagga[k] else 0.0 for k in koder])
                if rs.std() > 0:
                    beta = np.cov(fv, rs)[0, 1] / np.var(rs)
                    res = fv - beta * (rs - rs.mean())
                else:
                    res = fv
                v = spearman(list(res), [fw[k] for k in koder])
                if v is not None:
                    ric[e].append(v)
    print(f"\n{'='*76}\nSTEG 4 — G42 SMA200 DIAGNOSTIK   {namn}")
    print(f"  {'horisont':<10}{'över SMA200':>14}{'under':>11}{'skillnad':>11}{'t':>7}"
          f"{'residual-IC':>14}{'t':>7}")
    rad = {}
    for h, e in HOR:
        if len(over[e]) < 8:
            continue
        a, b = np.array(over[e]), np.array(under[e])
        d = a - b
        t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))
        r_ = np.array(ric[e]) if ric[e] else np.array([0.0])
        tr = r_.mean() / (r_.std(ddof=1) / math.sqrt(len(r_))) if len(r_) > 3 else float("nan")
        rad[e] = {"over": round(float(a.mean()), 5), "under": round(float(b.mean()), 5),
                  "skillnad": round(float(d.mean()), 5), "t": round(float(t), 2),
                  "residual_ic": round(float(r_.mean()), 4), "t_residual": round(float(tr), 2),
                  "n_paneler": len(a)}
        print(f"  {e:<10}{a.mean():>+14.2%}{b.mean():>+11.2%}{d.mean():>+11.2%}{t:>7.2f}"
              f"{r_.mean():>+14.4f}{tr:>7.2f}")
    return rad


def main():
    ut = {"version": "G55_G51_G42_BATCH3_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "locked_h0_referens": {"2020_2026": 0.0720, "2014_2019": 0.3156},
          "accelerationsdefinition": "H0_score(k, panel_i) - H0_score(k, panel_i-3), "
                                     "oforandrad fran granskning_statisk_vs_dynamisk::lutning",
          "fonster": {}}
    paneldata = []

    for w_, F, namn, smaf in (("2020_2026", S.F26, "2020-2026", S.sma26),
                              ("2014_2019", S.F19, "2014-2019", M.sma_ok)):
        r1, hist = steg1(F, namn)
        # acceleration enligt låst definition
        sc = {(r["kod"], pi): r["score"] for pi, dt in enumerate(F["eval_dates"])
              for r in F["rankings"][dt]}
        acc = {}
        for pi in range(len(F["eval_dates"])):
            if pi < 3:
                continue
            for r in F["rankings"][F["eval_dates"][pi]]:
                a, b = sc.get((r["kod"], pi)), sc.get((r["kod"], pi - 3))
                if a is not None and b is not None:
                    acc[(r["kod"], pi)] = a - b
        r2 = steg2(F, namn, acc)
        r4 = steg4_diag(F, namn, smaf)
        ut["fonster"][w_] = {"steg1_koncentration": r1, "steg2_acceleration": r2,
                             "steg4_sma200_diag": r4, "_acc": acc, "_smaf": smaf}
        for h in hist:
            paneldata.append({"fonster": namn, "dt": h["dt"], "sel": h["sel"]})

    # ---- gate steg 2
    a = ut["fonster"]["2020_2026"]["steg2_acceleration"]
    b = ut["fonster"]["2014_2019"]["steg2_acceleration"]
    tecken = [(a[e]["residual_ic"] > 0) == (b[e]["residual_ic"] > 0) for e in a if e in b]
    stark = [abs(a[e]["t_residual"]) > 1.96 and abs(b[e]["t_residual"]) > 1.96 for e in a if e in b]
    if all(tecken) and any(stark):
        dom2 = "REPLICATED INCREMENTAL SIGNAL"
    elif any(tecken) and (any(abs(a[e]["t_residual"]) > 1.96 for e in a) or
                          any(abs(b[e]["t_residual"]) > 1.96 for e in b)):
        dom2 = "PROMISING-BUT-UNSTABLE"
    else:
        dom2 = "NO INCREMENTAL SIGNAL"
    ut["dom_steg2"] = dom2
    print(f"\n{'='*76}\nSTEG 2 DOM: {dom2}")

    if dom2 == "REPLICATED INCREMENTAL SIGNAL":
        print("Steg 3 LICENSIERAT — kör portföljtest")
        ut["steg3"] = {}
        for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
            acc = ut["fonster"][w_]["_acc"]
            nA = h0(F)[0]; nB, tB, _, _ = h0(F, ersatt_regel="acc", ersatt_data=acc)
            ut["steg3"][w_] = {"A": S.stat(nA), "B": S.stat(nB), **S.boot(nB, nA)}
            print(f"  {namn}: A {S.stat(nA)['cagr']:.2%}  B {S.stat(nB)['cagr']:.2%}  "
                  f"Δ {S.stat(nB)['cagr']-S.stat(nA)['cagr']:+.2%}")
    else:
        ut["steg3"] = "EJ LICENSIERAT — steg 2 nådde inte REPLICATED INCREMENTAL SIGNAL"
        print(f"Steg 3 EJ LICENSIERAT: {ut['steg3']}")

    # ---- gate steg 4
    a4 = ut["fonster"]["2020_2026"]["steg4_sma200_diag"]
    b4 = ut["fonster"]["2014_2019"]["steg4_sma200_diag"]
    t4 = [(a4[e]["residual_ic"] > 0) == (b4[e]["residual_ic"] > 0) for e in a4 if e in b4]
    s4 = [abs(a4[e]["t_residual"]) > 1.96 and abs(b4[e]["t_residual"]) > 1.96
          for e in a4 if e in b4]
    if all(t4) and any(s4):
        dom4 = "REPLIKERBAR INKREMENTELL SIGNAL — portföljtest licensierat"
    else:
        dom4 = "INGEN REPLIKERBAR INKREMENTELL SIGNAL — portföljtest ej licensierat"
    ut["dom_steg4_diag"] = dom4
    print(f"\nSTEG 4 DIAGNOSTIKDOM: {dom4}")
    if dom4.startswith("REPLIKERBAR"):
        ut["steg4_portfolj"] = {}
        for w_, F, namn, smaf in (("2020_2026", S.F26, "2020-2026", S.sma26),
                                  ("2014_2019", S.F19, "2014-2019", M.sma_ok)):
            nA = h0(F)[0]; nB = h0(F, ersatt_regel="sma", ersatt_data=smaf)[0]
            ut["steg4_portfolj"][w_] = {"A": S.stat(nA), "B": S.stat(nB), **S.boot(nB, nA)}
            print(f"  {namn}: A {S.stat(nA)['cagr']:.2%}  B {S.stat(nB)['cagr']:.2%}")

    for w_ in ut["fonster"]:
        ut["fonster"][w_].pop("_acc", None); ut["fonster"][w_].pop("_smaf", None)
    with open(PANELDATA, "w") as f:
        for p in paneldata:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nPaneldata: {PANELDATA}")


if __name__ == "__main__":
    main()
