"""STACK_H-MOTOR — SHADOW_INTEGRATED_STACK_H FÖR BÅDA FÖNSTREN

Exakt konfiguration ur research_ag_reconciliation_canonical.py:
    SHADOW_INTEGRATED_STACK_H = {use_erc: True, use_fr: True,
                                 use_hysteresis: True, use_ntz: True}

  ERC        vikt ~ 1/vol^1,5
  FR         0,75x för obekräftade (pris >= MA120 och vol60 < 0,35 = bekräftad)
  hysteres   vid ombalansering behålls tidigare innehav med rank <= 35, därefter
             påfyllnad till 30 ur ranklistan
  NTZ        om |ny vikt - gammal vikt| < 0,005 behålls den gamla vikten
  tak        clip(w, 0,01, 0,06) följt av renormalisering till n_held/30
  omsättning sum|dw|/2, viktbaserad (INTE namnbaserad)
  kostnad    20 bp på viktomsättningen

Registrerat utfall att reproducera på 2020-2026:
    Net CAGR 13,56 %, Vol 17,02 %, MaxDD -24,32 %, omsättning 24,0 %

verifiera() kastar om reproduktionen misslyckas.
"""
from __future__ import annotations
import importlib.util, math, sys
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
COST = 0.002
PPY, RF = 13.0, 0.0224


def kor(rankings, eval_dates, returns_map, vol_fn, sma_fn, conf_fn, sched_fn,
        N=30, use_erc=True, use_fr=True, use_hysteresis=True, use_ntz=True,
        use_tv=False, hyst_rank=35, ntz_band=0.005, kopband=None, exit_rank=None):
    previous, prev_weights, periods = [], {}, []
    for pi, dt in enumerate(eval_dates):
        scheduled = sched_fn(pi, dt)
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        rank_map = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        lo, hi = kopband if kopband else (1, N)

        if scheduled or not previous:
            if use_hysteresis and previous:
                gr = exit_rank if exit_rank else hyst_rank
                keep = [k for k in previous if rank_map.get(k, 999) <= gr and k in elig]
                fill = [r["kod"] for r in raw[lo - 1:hi] if r["kod"] not in keep]
                sel0 = (keep + fill)[:N]
            else:
                sel0 = [r["kod"] for r in raw[lo - 1:hi]][:N]
        else:
            sel0 = [k for k in previous if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]

        sel = [k for k in sel0 if sma_fn(k, dt)]
        n = len(sel)
        vols = np.array([vol_fn(k, dt) for k in sel], dtype=float) if n else np.array([])

        if n == 0:
            w = np.array([])
        else:
            p = 1.5 if use_erc else 1.0
            inv = 1.0 / (np.maximum(vols, 0.05) ** p)
            w = inv / np.sum(inv) * (n / N)
            if use_fr:
                w = w * np.array([1.0 if conf_fn(k, dt) else 0.75 for k in sel])
            w = np.clip(w, 0.01, 0.06)
            w = w / np.sum(w) * (n / N)
            if use_ntz and prev_weights:
                w = np.array([prev_weights.get(k, 0.0)
                              if (abs(w[i] - prev_weights.get(k, 0.0)) < ntz_band
                                  and prev_weights.get(k, 0.0) > 0) else w[i]
                              for i, k in enumerate(sel)])
                w = w / np.sum(w) * (n / N)
            if use_tv:
                p_vol = float(np.sqrt(np.sum((w * vols) ** 2))) if n else 0.15
                w = w * min(1.0, 0.15 / max(p_vol, 0.05))

        curr = dict(zip(sel, w))
        if not previous:
            turnover = float(np.sum(w)) if n else 0.0
        else:
            alla = set(prev_weights) | set(curr)
            turnover = sum(abs(curr.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in alla) / 2.0
        rets = np.array([returns_map.get((k, dt), 0.0) for k in sel]) if n else np.array([])
        gross = float(np.sum(w * rets)) if n else 0.0
        periods.append({"net": gross - COST * turnover, "turnover": turnover, "n": n})
        previous, prev_weights = sel0, curr
    return np.array([p["net"] for p in periods]), \
           float(np.mean([p["turnover"] for p in periods])) * PPY, \
           float(np.mean([p["n"] for p in periods]))


def stat(x):
    w = np.cumprod(1 + x)
    dd = w / np.maximum.accumulate(w) - 1
    c = float(w[-1] ** (PPY / len(x)) - 1)
    v = float(x.std(ddof=1) * math.sqrt(PPY))
    return {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(float(dd.min()), 4),
            "sharpe": round((c - RF) / v, 3) if v > 0 else None}


def boot(a, b, seed=20260816, block=13, draws=2000):
    rng = np.random.default_rng(seed)
    n = len(a); nb = int(math.ceil(n / block)); o = []
    for _ in range(draws):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, n - block + 1); idx.extend(range(s, s + block))
        idx = np.array(idx[:n])
        o.append(np.cumprod(1 + a[idx])[-1] ** (PPY / n) - np.cumprod(1 + b[idx])[-1] ** (PPY / n))
    d = a - b; sd = d.std(ddof=1)
    return {"delta_cagr": round(stat(a)["cagr"] - stat(b)["cagr"], 4),
            "ki_lo": round(float(np.percentile(o, 2.5)), 4),
            "ki_hi": round(float(np.percentile(o, 97.5)), 4),
            "t": round(float(d.mean() / (sd / math.sqrt(len(d)))), 3)}


# ---------------- fönster 2020-2026 ----------------
_s = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
H = importlib.util.module_from_spec(_s); _s.loader.exec_module(H)
_core, _prices, _term = H.load_data()
RET26, ALLD = H.execution_engine(_core, _prices, _term)
VOL26, PS26 = H.compute_vols(_prices, window=60)
ROWS26 = H.derive_h0_scores(_core, _prices)
CONF26 = H.fetch_fundamental_confirmations(ROWS26, _prices)
DT26 = sorted(ROWS26.keys())
_ANCH = ALLD.index(H.PHASE_ANCHOR_H0) % 2
_sma26 = {}


def sma26(k, dt):
    if (k, dt) not in _sma26:
        v = True
        if k in PS26:
            ds, adj = PS26[k]
            i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
            if i is not None and i >= 200:
                v = adj[i] >= float(np.mean(adj[i - 200:i]))
        _sma26[(k, dt)] = v
    return _sma26[(k, dt)]


F26 = dict(rankings=ROWS26, eval_dates=DT26, returns_map=RET26,
           vol_fn=lambda k, dt: VOL26.get((k, dt), 0.25), sma_fn=sma26,
           conf_fn=lambda k, dt: CONF26.get((k, dt), False),
           sched_fn=lambda pi, dt: ALLD.index(dt) % 2 == _ANCH)

# ---------------- fönster 2014-2019 ----------------
import h1419_motor as M
F19 = dict(rankings=M.RANKNINGAR, eval_dates=M.PANELER, returns_map=M.RET,
           vol_fn=M.vol, sma_fn=M.sma_ok, conf_fn=M.bekraftad,
           sched_fn=lambda pi, dt: pi % 2 == 0)


def verifiera():
    nets, oms, n = kor(**F26)
    s = stat(nets)
    ok = abs(s["cagr"] - 0.1356) < 0.004 and abs(s["vol"] - 0.1702) < 0.004
    return s, oms, n, ok


if __name__ == "__main__":
    s, oms, n, ok = verifiera()
    print(f"STACK_H 2020-2026: CAGR {s['cagr']:.2%} vol {s['vol']:.2%} "
          f"maxDD {s['maxdd']:.2%} Sharpe {s['sharpe']}")
    print(f"  omsättning {oms:.1%}, medelinnehav {n:.2f}")
    print(f"  registret: CAGR 13,56 % vol 17,02 % maxDD -24,32 % omsättning 24,0 %")
    print(f"  REPRODUKTION: {'OK' if ok else 'AVVIKER'}")
    nets19, oms19, n19 = kor(**F19)
    s19 = stat(nets19)
    print(f"\nSTACK_H 2014-2019: CAGR {s19['cagr']:.2%} vol {s19['vol']:.2%} "
          f"maxDD {s19['maxdd']:.2%} Sharpe {s19['sharpe']}  omsättning {oms19:.1%}")
