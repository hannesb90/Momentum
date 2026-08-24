"""G83 INVERS-VOL-VIKTNING och G97 LÅGRISKANOMALIN PÅ LOCKED H0

Förregistrering: research_k/g83_g97_preregistration.json
sha256 df3bc9272dcf055c00c94cb864c5fc01febe25c3d3d88b05a9fbb0bd112c7c71

G83 är en VIKTablation (typ B): samma namn, samma paneler, samma exekvering,
samma kostnad. Enda skillnaden är vikten vid rebalans — 1/30 mot invers
volatilitet. Regeln byter inga namn och kräver därför ingen matched-random
placebo.

  exponent 1,0 (ren invers vol, inte ERC:s 1,5)
  volatilitet: befintlig vol_fn, 60 dagar, oförändrad
  golv max(vol, 0,05); INGET viktak — locked H0 har inga tak, och att lägga till
  dem vore en andra ändring. Koncentrationsmått redovisas i stället.

G97 är ett INFORMATIONStest (typ A): predicerar lägre vol_52w framtida
avkastning inkrementellt inom topp-30, efter kontroll för aktuell H0-score?
Regel 6 tillämpas: endast h=1 är icke-överlappande och utgör primärbeviset.

Kör: /opt/momentum/venv/bin/python tools/g83_g97_riskviktning.py
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

OUT = V2 / "research_k/g83_g97_results.json"
PANEL = V2 / "research_k/g83_g97_paneldata.jsonl"
COST = 0.002
PPY = 13
N = 30
HOR = [(1, "4v"), (2, "8v"), (3, "12v"), (6, "24v")]
MIN_VECKOR = 45


# ------------------------------------------------------------------ G83
def kor(F, arm):
    """arm 'A' = lika vikt 1/30 vid rebalans. 'B' = invers volatilitet."""
    dts, ret, schedf, volf = F["eval_dates"], F["returns_map"], F["sched_fn"], F["vol_fn"]
    w, nets, turns, hist = {}, [], [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w:
            sel = [r["kod"] for r in raw][:N]
            if arm == "A":
                mal = {k: 1.0 / N for k in sel}
            else:
                inv = np.array([1.0 / max(volf(k, dt), 0.05) for k in sel])
                mal = dict(zip(sel, inv / inv.sum()))
            t_ = sum(mal.values())
            mal = {k: v / t_ for k, v in mal.items()} if t_ > 0 else {}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0)) for k in set(mal) | set(w)) / 2.0
        else:
            mal = dict(w)
            turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        g = float(sum(mal[k] * r[k] for k in mal))
        nets.append(g - COST * turn)
        turns.append(turn)
        hist.append({"dt": dt, "vikter": dict(mal), "avk": dict(r)})
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return np.array(nets), np.array(turns), hist


def konc(hist):
    hhi, mx, eff = [], [], []
    for h in hist:
        v = np.array(list(h["vikter"].values()))
        if not len(v):
            continue
        hhi.append(float((v ** 2).sum())); mx.append(float(v.max()))
        eff.append(float(1 / (v ** 2).sum()))
    return {"hhi": round(float(np.mean(hhi)), 5),
            "max_vikt_medel": round(float(np.mean(mx)), 5),
            "max_vikt_hogsta": round(float(np.max(mx)), 5),
            "eff_antal_medel": round(float(np.mean(eff)), 2),
            "eff_antal_lagsta": round(float(np.min(eff)), 2)}


# ------------------------------------------------------------------ G97
_D, _V = {}, {}


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


def veckoserie(F, k):
    n = (id(F), k)
    if n in _V:
        return _V[n]
    s = dagsserie(F, k)
    if s is None:
        _V[n] = None
        return None
    ds, adj = s
    sista = {}
    for i, d in enumerate(ds):
        y, wk, _ = date.fromisoformat(d).isocalendar()
        sista[(y, wk)] = i
    idx = [sista[x] for x in sorted(sista)]
    _V[n] = ([ds[i] for i in idx], adj[idx])
    return _V[n]


def vol52(F, k, dt):
    v = veckoserie(F, k)
    if v is None:
        return None
    wd, wp = v
    j = bisect.bisect_right(wd, dt)
    fon = wp[max(0, j - 53):j]
    if len(fon) < MIN_VECKOR + 1:
        return None
    r = fon[1:] / fon[:-1] - 1
    return float(np.std(r, ddof=1))


def spearman(x, y):
    if len(x) < 10:
        return None
    def rk(a):
        o = sorted(range(len(a)), key=lambda i: a[i]); r = [0.0] * len(a); i = 0
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


def g97(F, namn, rader):
    dts = F["eval_dates"]
    ic, ric, kv, tmb = defaultdict(list), defaultdict(list), defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        top = [r["kod"] for r in raw][:N]
        sc = {r["kod"]: r["score"] for r in raw}
        rows = [(k, vol52(F, k, dt), sc[k]) for k in top]
        rows = [(k, v, s) for k, v, s in rows if v is not None]
        if len(rows) < 20:
            continue
        koder = [r[0] for r in rows]
        mv = np.array([r[1] for r in rows]); sv = np.array([r[2] for r in rows])
        for k, v in zip(koder, mv):
            rader.append({"fonster": namn, "dt": dt, "kod": k, "vol52": round(float(v), 5)})
        y = np.argsort(np.argsort(mv)).astype(float)
        X = np.column_stack([np.ones(len(y)), np.argsort(np.argsort(sv)).astype(float)])
        res = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
        for h, e in HOR:
            fw = [framat(F, k, pi, h) for k in koder]
            m = [i for i, x in enumerate(fw) if x is not None]
            if len(m) < 20:
                continue
            yy = [fw[i] for i in m]
            a = spearman([mv[i] for i in m], yy)
            b = spearman([res[i] for i in m], yy)
            if a is not None:
                ic[e].append(a)
            if b is not None:
                ric[e].append(b)
            ordn = sorted(m, key=lambda i: mv[i])      # Q1 = LÄGST volatilitet
            q = max(3, len(ordn) // 5)
            for qi in range(5):
                seg = ordn[qi * q:(qi + 1) * q] if qi < 4 else ordn[4 * q:]
                if seg:
                    kv[e][qi].append(float(np.mean([fw[i] for i in seg])))
            tmb[e].append(float(np.mean([fw[i] for i in ordn[:q]]) -
                                np.mean([fw[i] for i in ordn[-q:]])))
    print(f"\n  {namn}   paneler: {len(ic['4v'])}")
    print(f"    {'horisont':<9}{'IC(vol)':>10}{'t naiv':>8}{'residual':>11}{'t naiv':>8}"
          f"{'t just':>8}{'lag−hog':>10}{'t just':>8}  kvintiler lågvol→högvol")
    ut = {}
    for h, e in HOR:
        if len(ic[e]) < 8:
            continue
        a1 = np.array(ic[e]); a2 = np.array(ric[e]); a3 = np.array(tmb[e])
        f_ = lambda x: float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))
        q = [float(np.mean(kv[e][i])) for i in range(5) if kv[e][i]]
        ut[e] = {"ic_vol": round(float(a1.mean()), 4), "t_ic": round(f_(a1), 2),
                 "residual_ic": round(float(a2.mean()), 4), "t_residual": round(f_(a2), 2),
                 "t_residual_just": round(f_(a2) / math.sqrt(h), 2),
                 "lag_minus_hog": round(float(a3.mean()), 5),
                 "t_lmh_just": round(f_(a3) / math.sqrt(h), 2),
                 "kvintiler": [round(x, 5) for x in q], "n_paneler": len(a1), "h": h}
        print(f"    {e:<9}{a1.mean():>+10.4f}{f_(a1):>8.2f}{a2.mean():>+11.4f}{f_(a2):>8.2f}"
              f"{f_(a2)/math.sqrt(h):>+8.2f}{a3.mean():>+10.2%}{f_(a3)/math.sqrt(h):>+8.2f}  "
              f"{' '.join(f'{x:+.1%}' for x in q)}")
    return ut


def main():
    ut = {"version": "G83_G97_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": "df3bc9272dcf055c00c94cb864c5fc01febe25c3d3d88b05a9fbb0bd112c7c71",
          "G83": {}, "G97": {}}

    print(f"{'='*80}\nG83 — INVERS-VOL-VIKTNING PÅ LOCKED H0 (viktablation, byter inga namn)")
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        nA, tA, hA = kor(F, "A")
        nB, tB, hB = kor(F, "B")
        avvik = sum(1 for a, b in zip(hA, hB) if set(a["vikter"]) != set(b["vikter"]))
        sA, sB = S.stat(nA), S.stat(nB)
        kA, kB = konc(hA), konc(hB)
        bo = S.boot(nB, nA)
        print(f"\n  {namn}   INVARIANT namnuppsättning: {avvik} avvikelser "
              f"{'OK' if avvik == 0 else 'TESTET OGILTIGT'}")
        print(f"  {'':<20}{'A lika vikt':>14}{'B invers vol':>15}{'B − A':>12}")
        for et, a, b, fmt in (("CAGR", sA["cagr"], sB["cagr"], "%"),
                              ("volatilitet", sA["vol"], sB["vol"], "%"),
                              ("maxDD", sA["maxdd"], sB["maxdd"], "%"),
                              ("Sharpe", sA["sharpe"], sB["sharpe"], "f"),
                              ("omsättning/år", tA.mean() * PPY, tB.mean() * PPY, "%"),
                              ("kostnad/år", tA.mean() * PPY * COST, tB.mean() * PPY * COST, "%"),
                              ("max vikt medel", kA["max_vikt_medel"], kB["max_vikt_medel"], "f"),
                              ("max vikt högsta", kA["max_vikt_hogsta"], kB["max_vikt_hogsta"], "f"),
                              ("eff. antal medel", kA["eff_antal_medel"], kB["eff_antal_medel"], "f"),
                              ("eff. antal lägsta", kA["eff_antal_lagsta"], kB["eff_antal_lagsta"], "f")):
            g = "{:>14.2%}{:>15.2%}{:>12.2%}" if fmt == "%" else "{:>14.3f}{:>15.3f}{:>12.3f}"
            print(f"  {et:<20}" + g.format(a, b, b - a))
        print(f"  bootstrap B−A: Δ {bo['delta_cagr']:+.2%}  "
              f"KI [{bo['ki_lo']:+.2%},{bo['ki_hi']:+.2%}]  t {bo['t']:+.2f}")
        ut["G83"][w_] = {"invariant_avvikelser": avvik, "A": {**sA, **kA,
                         "oms_ar": round(float(tA.mean()) * PPY, 4)},
                         "B": {**sB, **kB, "oms_ar": round(float(tB.mean()) * PPY, 4)},
                         "B_minus_A_cagr": round(sB["cagr"] - sA["cagr"], 5), "bootstrap": bo,
                         "netto_A": [round(float(x), 6) for x in nA],
                         "netto_B": [round(float(x), 6) for x in nB]}

    a = ut["G83"]["2020_2026"]["B_minus_A_cagr"]; b = ut["G83"]["2014_2019"]["B_minus_A_cagr"]
    ut["dom_G83"] = ("FÖRBÄTTRAR I BÅDA FÖNSTREN" if a > 0 and b > 0 else
                     "FÖRBÄTTRAR I ETT FÖNSTER" if (a > 0 or b > 0) else
                     "FÖRBÄTTRAR INTE I NÅGOT FÖNSTER")
    print(f"\n  B − A CAGR: {a:+.2%} / {b:+.2%}  →  {ut['dom_G83']}")

    print(f"\n{'='*80}\nG97 — LÅGRISKANOMALIN INOM TOPP-30 (informationstest)")
    print("  IC mäts mot vol_52w. Hypotesen förutsäger NEGATIV IC (lägre vol → högre avkastning).")
    rader = []
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        ut["G97"][w_] = g97(F, namn, rader)
    x = ut["G97"]["2020_2026"]; y = ut["G97"]["2014_2019"]
    gem = [e for e in x if e in y]
    samma = all((x[e]["residual_ic"] > 0) == (y[e]["residual_ic"] > 0) for e in gem)
    h1sig = (abs(x["4v"]["t_residual_just"]) > 1.96 and abs(y["4v"]["t_residual_just"]) > 1.96)
    if samma and h1sig:
        d97 = "REPLICATED INCREMENTAL SIGNAL"
    elif samma and any(abs(x[e]["t_residual_just"]) > 1.96 or abs(y[e]["t_residual_just"]) > 1.96
                       for e in gem):
        d97 = "PROMISING-BUT-UNSTABLE"
    else:
        d97 = "NO INCREMENTAL SIGNAL"
    ut["dom_G97"] = d97
    print(f"\n  DOM G97: {d97}")
    print(f"    (h=1 är den enda icke-överlappande horisonten och utgör primärbeviset)")

    with open(PANEL, "w") as f:
        for r in rader:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\n{'='*80}\nG83: {ut['dom_G83']}\nG97: {d97}")
    print(f"\nSkrivet: {OUT}\nPaneldata: {PANEL} ({len(rader)} observationer)")


if __name__ == "__main__":
    main()
