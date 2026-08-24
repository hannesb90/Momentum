"""H1419-MOTOR — DELAD SIMULERINGSKÄRNA FÖR 2014-2019

Alla nattens tester importerar härifrån så att de kör mot exakt samma
prislager, panelgitter, rankning och avkastningsdefinition som den låsta
förregistreringen (H1419_PREREG_FREEZE_V2, sha 23cd3cde…).

Baslinjekrav: motorn måste reproducera det förregistrerade resultatet,
H0 N=30 = 29,99 % och likaviktat universum = 17,84 %. verifiera_baslinje()
kastar om den inte gör det.
"""
from __future__ import annotations
import json, math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
PRIS = V2 / "validated/prices_h1419/prices_h1419_universum_v2.json"
PPY = 13.0
RF = 0.0224
COST = 0.002
BLOCK, DRAWS, SEED = 13, 2000, 20260815

_priser = json.loads(PRIS.read_text())
SERIE = {k: (np.array([np.datetime64(r["d"]) for r in rs]),
             np.array([r["adj"] for r in rs], dtype=float)) for k, rs in _priser.items()}

PANELER = []
_c = date(2014, 1, 1)
while _c <= date(2019, 12, 31):
    PANELER.append(_c.isoformat())
    _c += timedelta(days=28)


def _idx(k, dt):
    ds, _ = SERIE[k]
    i = int(np.searchsorted(ds, np.datetime64(dt), side="right")) - 1
    return i if i >= 0 else None


def handlas(k, dt):
    i = _idx(k, dt)
    if i is None:
        return False
    ds, _ = SERIE[k]
    return int((np.datetime64(dt) - ds[i]) / np.timedelta64(1, "D")) <= 30


def momentum(k, dt, weeks):
    ds, v = SERIE[k]
    now = np.datetime64(dt)
    mal = now - np.timedelta64(7 * weeks, "D")
    i = int(np.searchsorted(ds, now, side="right")) - 1
    j = int(np.searchsorted(ds, mal, side="right")) - 1
    if i < 0 or j < 0 or int((mal - ds[j]) / np.timedelta64(1, "D")) > 10:
        return None
    return float(v[i] / v[j] - 1.0)


def _bygg_rankningar():
    ut = {}
    for dt in PANELER:
        rows = [{"kod": k, "m12": momentum(k, dt, 52), "m18": momentum(k, dt, 78)}
                for k in SERIE if handlas(k, dt)]
        for col in ("m12", "m18"):
            giltiga = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            grupp = defaultdict(list)
            for val, kod in giltiga:
                grupp[val].append(kod)
            ranks, pos = {}, 1
            for val in sorted(grupp):
                ks = grupp[val]
                ranks.update({kod: (pos + pos + len(ks) - 1) / 2 / max(1, len(giltiga)) for kod in ks})
                pos += len(ks)
            for r in rows:
                r[col + "_rank"] = ranks.get(r["kod"])
        raa = [0.5 * (r["m12_rank"] + r["m18_rank"])
               if r["m12_rank"] is not None and r["m18_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raa if x is not None])) if any(x is not None for x in raa) else 0.5
        sc = [{**r, "score": med if v is None else v} for r, v in zip(rows, raa)]
        sc.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        ut[dt] = sc
    return ut


RANKNINGAR = _bygg_rankningar()
RANK = {(r["kod"], dt): i + 1 for dt in PANELER for i, r in enumerate(RANKNINGAR[dt])}


def _bygg_retmap():
    ut = {}
    for k in SERIE:
        ds, v = SERIE[k]
        for a in range(len(PANELER) - 1):
            i = int(np.searchsorted(ds, np.datetime64(PANELER[a]), side="right"))
            j = int(np.searchsorted(ds, np.datetime64(PANELER[a + 1]), side="right"))
            ut[(k, PANELER[a])] = float(v[j - 1] / v[i] - 1.0) if (i < j and i < len(ds) and v[i] > 0) else 0.0
        ut[(k, PANELER[-1])] = 0.0
    return ut


RET = _bygg_retmap()

_sma, _bek, _vol = {}, {}, {}


def sma_ok(k, dt):
    if (k, dt) not in _sma:
        i = _idx(k, dt)
        if i is None or i < 200:
            _sma[(k, dt)] = True
        else:
            _, v = SERIE[k]
            _sma[(k, dt)] = bool(v[i] >= float(np.mean(v[i - 200:i])))
    return _sma[(k, dt)]


def bekraftad(k, dt):
    if (k, dt) not in _bek:
        i = _idx(k, dt)
        if i is None or i < 120:
            _bek[(k, dt)] = False
        else:
            _, v = SERIE[k]
            r = np.diff(v[i - 60:i + 1]) / v[i - 60:i]
            _bek[(k, dt)] = bool(v[i] >= float(np.mean(v[i - 120:i]))
                                 and float(np.std(r) * math.sqrt(252)) < 0.35)
    return _bek[(k, dt)]


def vol(k, dt):
    if (k, dt) not in _vol:
        i = _idx(k, dt)
        _, v = SERIE[k]
        j = (i - 1) if i is not None else None      # samma index som förregistreringen
        if j is None or j < 60 or len(v) < 62:
            _vol[(k, dt)] = 0.25
        else:
            r = np.diff(v) / v[:-1]
            s = float(np.std(r[j - 60:j]) * math.sqrt(252))
            _vol[(k, dt)] = s if s > 1e-4 else 0.25
    return _vol[(k, dt)]


def w_legacy(w, ts, cap):
    w = np.clip(w, 0.01, cap)
    s = float(np.sum(w))
    return w / s * ts if s > 0 else w


def w_waterfill(w, ts, cap, iters=200):
    w = np.array(w, dtype=float)
    s0 = float(np.sum(w))
    if w.size == 0 or s0 <= 0:
        return w
    w = w / s0 * ts
    for _ in range(iters):
        w = np.clip(w, 0.01, cap)
        diff = ts - float(np.sum(w))
        if abs(diff) < 1e-13:
            break
        fri = (w > 0.01 + 1e-15) & (w < cap - 1e-15)
        if not fri.any():
            break
        fs = float(np.sum(w[fri]))
        w[fri] += diff * (w[fri] / fs if fs > 0 else 1.0 / fri.sum())
    return np.clip(w, 0.01, cap)


def sim(N=30, sma=True, viktning="invvol1.5", fr=True, tak="legacy",
        ombalansering=2, lat_rida=False, exit_rank=None, utgangsband=None,
        kopband=None, rng=None):
    """Generell H0-simulering. tak: 'legacy' | 'waterfill' | None.
    viktning: 'lika' | 'invvol1.0' | 'invvol1.5' | 'invvol2.0'.
    kopband: (lo, hi) rankintervall nya innehav får köpas ur.
    exit_rank: behåll innehav tills rank > exit_rank (annars topp-N)."""
    cap = max(0.06, 1.5 / N)
    prev, nets, w_prev = [], [], None
    for a, dt in enumerate(PANELER):
        sched = a % ombalansering == 0
        raw = RANKNINGAR[dt]
        elig = {r["kod"] for r in raw}
        lo, hi = kopband if kopband else (1, N)
        if not prev:
            sel0 = [r["kod"] for r in raw[lo - 1:hi]][:N]
        elif sched:
            gr = exit_rank if exit_rank else N
            behall = [k for k in prev if k in elig and RANK[(k, dt)] <= gr]
            sel0 = sorted(behall, key=lambda k: RANK[(k, dt)])
            if len(sel0) < N:
                kand = [r["kod"] for r in raw[lo - 1:hi] if r["kod"] not in sel0]
                if rng is not None:
                    pool = [r["kod"] for r in raw[:60] if r["kod"] not in sel0]
                    rng.shuffle(pool)
                    kand = pool[:len(kand)]
                sel0 += kand[: N - len(sel0)]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
        sel = [k for k in sel0 if sma_ok(k, dt)] if sma else list(sel0)
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev = sel0; w_prev = None; continue
        ts = n / N
        if lat_rida and w_prev is not None and not sched:
            w = np.array([w_prev.get(k, ts / n) for k in sel], dtype=float)
            w = w / np.sum(w) * ts
        else:
            if viktning == "lika":
                w = np.full(n, ts / n)
            else:
                p = float(viktning.replace("invvol", ""))
                inv = 1.0 / (np.maximum(np.array([vol(k, dt) for k in sel]), 0.05) ** p)
                w = inv / np.sum(inv) * ts
            if fr:
                w = w * np.array([1.0 if bekraftad(k, dt) else 0.75 for k in sel])
            if tak == "legacy":
                w = w_legacy(w, ts, cap)
            elif tak == "waterfill":
                w = w_waterfill(w, ts, cap)
            else:
                w = w / np.sum(w) * ts
        rets = np.array([RET.get((k, dt), 0.0) for k in sel])
        nets.append(float(np.sum(w * rets)) - COST * turn)
        w_prev = {k: float(x * (1 + r)) for k, x, r in zip(sel, w, rets)}
        prev = sel0
    return np.array(nets)


def universum_likavikt():
    return np.array([float(np.mean([RET.get((r["kod"], dt), 0.0) for r in RANKNINGAR[dt]]))
                     for dt in PANELER])


def stat(x):
    w = np.cumprod(1 + x)
    dd = w / np.maximum.accumulate(w) - 1
    c = float(w[-1] ** (PPY / len(x)) - 1)
    v = float(x.std(ddof=1) * math.sqrt(PPY))
    return {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(float(dd.min()), 4),
            "sharpe": round((c - RF) / v, 3) if v > 0 else None,
            "median_panel": round(float(np.median(x)), 4),
            "medel_panel": round(float(x.mean()), 4)}


def boot(a, b, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(a); nb = int(math.ceil(n / BLOCK)); outs = []
    for _ in range(DRAWS):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, n - BLOCK + 1)
            idx.extend(range(s, s + BLOCK))
        idx = np.array(idx[:n])
        outs.append(np.cumprod(1 + a[idx])[-1] ** (PPY / n) - np.cumprod(1 + b[idx])[-1] ** (PPY / n))
    outs = np.array(outs)
    d = a - b
    sd = d.std(ddof=1)
    return {"delta_cagr": round(stat(a)["cagr"] - stat(b)["cagr"], 4),
            "ki_lo": round(float(np.percentile(outs, 2.5)), 4),
            "ki_hi": round(float(np.percentile(outs, 97.5)), 4),
            "t_parvis": round(float(d.mean() / (sd / math.sqrt(len(d)))), 3) if sd > 0 else None,
            "andel_positiva": round(float(np.mean(outs > 0)), 3)}


def verifiera_baslinje():
    h0 = stat(sim(N=30))["cagr"]
    u = stat(universum_likavikt())["cagr"]
    assert abs(h0 - 0.2999) < 0.0002, f"H0 reproducerar inte förregistreringen: {h0:.4f}"
    assert abs(u - 0.1784) < 0.0002, f"universum reproducerar inte: {u:.4f}"
    return h0, u
