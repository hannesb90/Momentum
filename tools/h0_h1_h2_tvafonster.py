"""H0, H1 OCH H2 I BÅDA FÖNSTREN — VILKEN HÅLLER?

H1 och H2 valdes i Research I Batch 1 på **20 OOS-paneler i ett enda fönster**,
och dokumentet säger uttryckligen att de är "nya challenger-hypoteser, inte
bekräftad alpha". Sedan dess har vi byggt 2014-2019-fönstret och lärt oss att
33 % av alla prövade varianter är positiva i det tidiga fönstret och negativa i
det sena. En challenger validerad på ett fönster är därför svagt bevisad.

Detta skript prövar alla tre i BÅDA fönstren, med Track H:s egen konstruktion —
inte registrets sex invers-vol-modeller.

KONSTRUKTION (enligt docs/H_MODELLCYCLE_DJUPREVISION_2026-08-16.md)
  H0  rank(12m momentum) + rank(18m momentum), 50/50
  H1  50 % H0 + 50 % percentilrank(drawdown-resiliens)
  H2  50 % H0 + 50 % percentilrank(trendstyrka)
  Topp 30, LIKA VIKT 3,33 %
  Beslut var 4:e vecka, nytt urval var 8:e vecka; mellanpanel behåller innehav
  20 bp enkelsidig kostnad

FAKTORDEFINITIONER — hämtade ordagrant ur tools/spari_forward_challengers.py
  drawdown_resilience = -|största nedgång från topp under senaste 364 dagarna|
  trend_strength      = t-värdet för lutningen i regression av log(pris) på tid,
                        samma 364-dagarsfönster
  Minst 200 observationer krävs. Saknad faktor får medianrank, alltså neutral
  behandling — samma regel som djuprevisionens punkt P2 beskriver.

Kör: /opt/momentum/venv/bin/python tools/h0_h1_h2_tvafonster.py
"""
from __future__ import annotations
import bisect, json, math, sys
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/h0_h1_h2_tvafonster_results.json"
COST = 0.002
PPY = 13


_SER = {}


def serie(F, k):
    """Datumlistan byggs EN gång per namn och fönster. Att konvertera arrayen
    vid varje anrop kostade tiotals miljoner strängkonverteringar."""
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


_CACHE = {}


def faktor(F, k, dt, sort):
    n = (id(F), k, dt, sort)
    if n in _CACHE:
        return _CACHE[n]
    s = serie(F, k)
    v = None
    if s is not None:
        ds, adj = s
        lo = (date.fromisoformat(dt) - timedelta(days=364)).isoformat()
        i = bisect.bisect_right(ds, dt)
        j = bisect.bisect_left(ds, lo)
        w = adj[j:i]
        w = w[w > 0]
        if len(w) >= 200:
            if sort == "dd":
                topp = np.maximum.accumulate(w)
                v = -float(abs(np.min(w / topp - 1)))
            else:
                y = np.log(w)
                x = np.arange(len(y), dtype=float)
                X = np.column_stack([np.ones(len(x)), x])
                beta = np.linalg.lstsq(X, y, rcond=None)[0]
                res = y - X @ beta
                s2 = float(res @ res) / (len(x) - 2)
                se = math.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
                v = float(beta[1] / se) if se > 0 else None
    _CACHE[n] = v
    return v


def pctrank(d):
    g = sorted((v, k) for k, v in d.items() if v is not None)
    n = len(g)
    return {k: (i + 0.5) / n for i, (_, k) in enumerate(g)} if n else {}


def sim(F, modell="H0", N=30):
    """Track H: lika vikt, urval var 8:e vecka, behåll på mellanpanel."""
    dts, ret = F["eval_dates"], F["returns_map"]
    schedf = F["sched_fn"]
    previous, prev_w, nets, oms = [], {}, [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if modell == "H0":
            arbets = raw
        else:
            sort = "dd" if modell == "H1" else "trend"
            fv = {r["kod"]: faktor(F, r["kod"], dt, sort) for r in raw}
            pr = pctrank(fv)
            med = 0.5
            arbets = sorted(({"kod": r["kod"],
                              "score": 0.5 * r["score"] + 0.5 * pr.get(r["kod"], med)}
                             for r in raw), key=lambda x: (x["score"], x["kod"]), reverse=True)
        elig = {r["kod"] for r in arbets}
        if schedf(pi, dt) or not previous:
            sel = [r["kod"] for r in arbets][:N]
        else:
            sel = [k for k in previous if k in elig]
            if len(sel) < N:
                sel += [r["kod"] for r in arbets if r["kod"] not in sel][: N - len(sel)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); oms.append(0.0); previous, prev_w = sel, {}; continue
        w = np.full(n, 1.0 / N)
        curr = dict(zip(sel, w))
        turn = float(np.sum(w)) if not previous else \
            sum(abs(curr.get(k, 0.0) - prev_w.get(k, 0.0)) for k in set(prev_w) | set(curr)) / 2.0
        oms.append(turn)
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        previous, prev_w = sel, curr
    return np.array(nets), float(np.mean(oms)) * PPY


def topn_ic(F, modell, N=30):
    """Spearman-IC inom topp-N mot nästa panels avkastning — projektets eget
    urvalskriterium sedan SPARF F5."""
    dts, ret = F["eval_dates"], F["returns_map"]
    ut = []
    for dt in dts[:-1]:
        raw = F["rankings"][dt]
        if modell == "H0":
            arbets = raw
        else:
            sort = "dd" if modell == "H1" else "trend"
            pr = pctrank({r["kod"]: faktor(F, r["kod"], dt, sort) for r in raw})
            arbets = sorted(({"kod": r["kod"], "score": 0.5 * r["score"] + 0.5 * pr.get(r["kod"], 0.5)}
                             for r in raw), key=lambda x: (x["score"], x["kod"]), reverse=True)
        t = arbets[:N]
        par = [(r["score"], ret.get((r["kod"], dt))) for r in t]
        par = [(a, b) for a, b in par if b is not None]
        if len(par) < 15:
            continue
        a = np.argsort(np.argsort([x for x, _ in par]))
        b = np.argsort(np.argsort([y for _, y in par]))
        if a.std() > 0 and b.std() > 0:
            ut.append(float(np.corrcoef(a, b)[0, 1]))
    v = np.array(ut)
    t = float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))) if len(v) > 3 else float("nan")
    return round(float(v.mean()), 4), round(t, 2), len(v)


def main():
    ut = {"version": "H0_H1_H2_TVAFONSTER_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "konstruktion": "Track H: lika vikt 1/30, urval var 8:e vecka, 20 bp",
          "fonster": {}}
    ser = {}
    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        print(f"\n{namn}")
        print(f"  {'modell':<8}{'CAGR':>9}{'vol':>8}{'maxDD':>9}{'Sharpe':>8}"
              f"{'oms/år':>9}{'topp30-IC':>11}{'t':>7}")
        rad = {}
        for m in ("H0", "H1", "H2"):
            nets, o = sim(F, m)
            ic, ict, nic = topn_ic(F, m)
            st = S.stat(nets)
            ser[(w_, m)] = nets
            rad[m] = {**st, "omsattning_ar": round(o, 4), "topp30_ic": ic,
                      "topp30_ic_t": ict, "n_ic_paneler": nic}
            print(f"  {m:<8}{st['cagr']:>9.2%}{st['vol']:>8.2%}{st['maxdd']:>9.2%}"
                  f"{st['sharpe']:>8.3f}{o:>9.1%}{ic:>11.4f}{ict:>7.2f}")
        for m in ("H1", "H2"):
            b = S.boot(ser[(w_, m)], ser[(w_, "H0")])
            rad[m]["mot_H0"] = b
            print(f"     {m} mot H0: Δ {b['delta_cagr']:+.2%}  "
                  f"KI [{b['ki_lo']:+.2%},{b['ki_hi']:+.2%}]  t {b['t']:+.2f}")
        ut["fonster"][w_] = rad

    print("\nDOM — slår challengern H0 i BÅDA fönstren?")
    for m in ("H1", "H2"):
        a = ut["fonster"]["2020_2026"][m]["mot_H0"]["delta_cagr"]
        b = ut["fonster"]["2014_2019"][m]["mot_H0"]["delta_cagr"]
        rep = a > 0 and b > 0
        ut.setdefault("dom", {})[m] = {"delta_26": a, "delta_19": b, "bada_positiva": bool(rep)}
        print(f"  {m}: {a:+.2%} / {b:+.2%}   {'JA' if rep else 'NEJ'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
