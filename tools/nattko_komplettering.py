"""NATTKÖ — KOMPLETTERING MED DE FYRA PRISBASERADE FAMILJER SOM MISSADES

Nattkön Q1-Q10 täckte de avfärdade familjer som går att pröva på ett prislager.
Genomgång i efterhand visar att fyra till var testbara och utelämnades:

  Q12  Trendstyrka som kvalitetsmått        (falsifierad på 66 paneler)
  Q13  Korrelationsfyllnad / diversifiering (inget stöd)
  Q14  Target-vol-sizing                    (inget stöd)
  Q15  Time stop och drawdown-stop          (svagt stöd / inget stöd)

Övriga sju avfärdade familjer är datablockerade för 2014-2019: de kräver
fundamenta, sektortillhörighet eller CORE-features som inte finns i H1419-lagret.

Kör: /opt/momentum/venv/bin/python tools/nattko_komplettering.py
"""
from __future__ import annotations
import json, math, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import h1419_motor as M

UT = Path("/home/hannesb/momentum_v2/research_k/nattko_2026_08_15")
LOGG = UT / "_logg.md"


def logga(t):
    with open(LOGG, "a", encoding="utf-8") as f:
        f.write(t + "\n")
    print(t, flush=True)


def _dagsserie(k, dt, dagar):
    i = M._idx(k, dt)
    if i is None or i < dagar + 1:
        return None
    _, v = M.SERIE[k]
    return v[i - dagar:i + 1]


# ---------------------------------------------------------------- Q12
def q12_trendstyrka():
    """R² för linjär anpassning av log(pris) över 252 dagar, som filter på topp-N."""
    def r2(k, dt):
        v = _dagsserie(k, dt, 252)
        if v is None or np.any(v <= 0):
            return None
        y = np.log(v)
        x = np.arange(len(y), dtype=float)
        b = np.polyfit(x, y, 1)
        yh = np.polyval(b, x)
        ss = float(np.sum((y - yh) ** 2))
        st = float(np.sum((y - y.mean()) ** 2))
        return 1 - ss / st if st > 0 else None

    cache = {}
    def f(k, dt):
        if (k, dt) not in cache:
            cache[(k, dt)] = r2(k, dt)
        return cache[(k, dt)]

    bas = M.sim(N=30)
    res = {"baslinje": M.stat(bas)}
    for tr in (0.5, 0.7, 0.8):
        prev, nets = [], []
        for a, dt in enumerate(M.PANELER):
            raw = [r for r in M.RANKNINGAR[dt] if (f(r["kod"], dt) or 0.0) >= tr]
            elig = {r["kod"] for r in raw}
            if a % 2 == 0 or not prev:
                sel0 = [r["kod"] for r in raw[:30]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < 30:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
            sel = [k for k in sel0 if M.sma_ok(k, dt)]
            n = len(sel)
            if n == 0:
                nets.append(0.0); prev = sel0; continue
            inv = 1.0 / (np.maximum(np.array([M.vol(k, dt) for k in sel]), 0.05) ** 1.5)
            ts = n / 30
            w = inv / np.sum(inv) * ts
            w = w * np.array([1.0 if M.bekraftad(k, dt) else 0.75 for k in sel])
            w = M.w_legacy(w, ts, max(0.06, 1.5 / 30))
            rets = np.array([M.RET.get((k, dt), 0.0) for k in sel])
            nets.append(float(np.sum(w * rets)) - M.COST * turn)
            prev = sel0
        nets = np.array(nets)
        res[f"r2_krav_{tr}"] = {**M.stat(nets), **M.boot(nets, bas)}
    b = max((k for k in res if k.startswith("r2")), key=lambda k: res[k]["delta_cagr"])
    return res, (f"Trendstyrka: bästa {b} {res[b]['delta_cagr']:+.2%} "
                 f"KI [{res[b]['ki_lo']:+.2%},{res[b]['ki_hi']:+.2%}] t {res[b]['t_parvis']}")


# ---------------------------------------------------------------- Q13
def q13_korrelationsfyllnad():
    """Hoppa över kandidat vars 252-dagarskorrelation mot redan vald överstiger gränsen."""
    ret_cache = {}
    def dagsret(k, dt):
        if (k, dt) not in ret_cache:
            v = _dagsserie(k, dt, 252)
            ret_cache[(k, dt)] = (np.diff(v) / v[:-1]) if v is not None and np.all(v > 0) else None
        return ret_cache[(k, dt)]

    bas = M.sim(N=30)
    res = {"baslinje": M.stat(bas)}
    for gr in (0.75, 0.85):
        prev, nets = [], []
        for a, dt in enumerate(M.PANELER):
            raw = M.RANKNINGAR[dt]
            elig = {r["kod"] for r in raw}
            if a % 2 == 0 or not prev:
                sel0, valda_r = [], []
                for r in raw:
                    if len(sel0) >= 30:
                        break
                    rr = dagsret(r["kod"], dt)
                    if rr is not None and any(
                            abs(float(np.corrcoef(rr, v)[0, 1])) > gr for v in valda_r):
                        continue
                    sel0.append(r["kod"])
                    if rr is not None:
                        valda_r.append(rr)
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < 30:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
            sel = [k for k in sel0 if M.sma_ok(k, dt)]
            n = len(sel)
            if n == 0:
                nets.append(0.0); prev = sel0; continue
            inv = 1.0 / (np.maximum(np.array([M.vol(k, dt) for k in sel]), 0.05) ** 1.5)
            ts = n / 30
            w = inv / np.sum(inv) * ts
            w = w * np.array([1.0 if M.bekraftad(k, dt) else 0.75 for k in sel])
            w = M.w_legacy(w, ts, max(0.06, 1.5 / 30))
            rets = np.array([M.RET.get((k, dt), 0.0) for k in sel])
            nets.append(float(np.sum(w * rets)) - M.COST * turn)
            prev = sel0
        nets = np.array(nets)
        res[f"grans_{gr}"] = {**M.stat(nets), **M.boot(nets, bas)}
    b = max((k for k in res if k.startswith("grans")), key=lambda k: res[k]["delta_cagr"])
    return res, (f"Korrelationsfyllnad: bästa {b} {res[b]['delta_cagr']:+.2%} "
                 f"KI [{res[b]['ki_lo']:+.2%},{res[b]['ki_hi']:+.2%}] t {res[b]['t_parvis']}")


# ---------------------------------------------------------------- Q14
def q14_target_vol():
    """Skala hela exponeringen mot ett volmål baserat på trailing panelvol."""
    bas = M.sim(N=30)
    res = {"baslinje": M.stat(bas)}
    for mal in (0.12, 0.15, 0.18):
        nets = []
        hist = []
        for i, x in enumerate(bas):
            if len(hist) >= 13:
                rv = float(np.std(hist[-13:], ddof=1) * math.sqrt(M.PPY))
                skala = min(1.5, mal / rv) if rv > 1e-6 else 1.0
            else:
                skala = 1.0
            nets.append(x * skala)
            hist.append(x)
        nets = np.array(nets)
        res[f"volmal_{mal}"] = {**M.stat(nets), **M.boot(nets, bas)}
    b = max((k for k in res if k.startswith("volmal")), key=lambda k: res[k]["delta_cagr"])
    return res, (f"Target-vol: bästa {b} {res[b]['delta_cagr']:+.2%} "
                 f"KI [{res[b]['ki_lo']:+.2%},{res[b]['ki_hi']:+.2%}] t {res[b]['t_parvis']}")


# ---------------------------------------------------------------- Q15
def q15_stoppar():
    """Time stop (sälj efter X paneler) och drawdown-stop (sälj vid -X % från inträde)."""
    bas = M.sim(N=30)
    res = {"baslinje": M.stat(bas)}

    def kor(time_stop=None, dd_stop=None):
        prev, nets = [], []
        alder, ingang = {}, {}
        for a, dt in enumerate(M.PANELER):
            raw = M.RANKNINGAR[dt]
            elig = {r["kod"] for r in raw}
            if a % 2 == 0 or not prev:
                behall = [k for k in prev if k in elig and M.RANK[(k, dt)] <= 30]
                if time_stop:
                    behall = [k for k in behall if alder.get(k, 0) < time_stop]
                if dd_stop:
                    behall = [k for k in behall if not (
                        k in ingang and M._idx(k, dt) is not None
                        and M.SERIE[k][1][M._idx(k, dt)] / ingang[k] - 1 <= -dd_stop)]
                sel0 = sorted(behall, key=lambda k: M.RANK[(k, dt)])
                sparr = set(prev) - set(behall)
                for r in raw:
                    if len(sel0) >= 30:
                        break
                    if r["kod"] not in sel0 and r["kod"] not in sparr:
                        sel0.append(r["kod"])
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < 30:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
            for k in sel0:
                alder[k] = alder.get(k, 0) + 1
                if k not in ingang:
                    i = M._idx(k, dt)
                    ingang[k] = float(M.SERIE[k][1][i]) if i is not None else None
            for k in list(alder):
                if k not in sel0:
                    alder.pop(k, None); ingang.pop(k, None)
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
            sel = [k for k in sel0 if M.sma_ok(k, dt)]
            n = len(sel)
            if n == 0:
                nets.append(0.0); prev = sel0; continue
            inv = 1.0 / (np.maximum(np.array([M.vol(k, dt) for k in sel]), 0.05) ** 1.5)
            ts = n / 30
            w = inv / np.sum(inv) * ts
            w = w * np.array([1.0 if M.bekraftad(k, dt) else 0.75 for k in sel])
            w = M.w_legacy(w, ts, max(0.06, 1.5 / 30))
            rets = np.array([M.RET.get((k, dt), 0.0) for k in sel])
            nets.append(float(np.sum(w * rets)) - M.COST * turn)
            prev = sel0
        return np.array(nets)

    for ts_ in (6, 13, 26):
        nets = kor(time_stop=ts_)
        res[f"time_stop_{ts_}p"] = {**M.stat(nets), **M.boot(nets, bas)}
    for dd in (0.20, 0.30):
        nets = kor(dd_stop=dd)
        res[f"dd_stop_{int(dd*100)}pct"] = {**M.stat(nets), **M.boot(nets, bas)}
    b = max((k for k in res if k != "baslinje"), key=lambda k: res[k]["delta_cagr"])
    return res, (f"Stoppar: bästa {b} {res[b]['delta_cagr']:+.2%} "
                 f"KI [{res[b]['ki_lo']:+.2%},{res[b]['ki_hi']:+.2%}] t {res[b]['t_parvis']}")


KO = [("Q12_trendstyrka", q12_trendstyrka), ("Q13_korrelationsfyllnad", q13_korrelationsfyllnad),
      ("Q14_target_vol", q14_target_vol), ("Q15_stoppar", q15_stoppar)]


def main():
    logga("\n## Komplettering — fyra prisbaserade familjer som saknades i Q1-Q10\n")
    M.verifiera_baslinje()
    samm = {}
    for namn, fn in KO:
        t0 = time.time()
        try:
            res, rad = fn()
            (UT / f"{namn}.json").write_text(json.dumps(
                {"test": namn, "kord_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                 "sekunder": round(time.time() - t0, 1), "resultat": res}, ensure_ascii=False, indent=1))
            samm[namn] = rad
            logga(f"- **{namn}** ({time.time()-t0:.0f}s) — {rad}")
        except Exception as e:
            import traceback
            logga(f"- **{namn}** MISSLYCKADES: {type(e).__name__}: {e}")
            (UT / f"{namn}_FEL.json").write_text(json.dumps(
                {"fel": str(e), "trace": traceback.format_exc()}, ensure_ascii=False, indent=1))
    (UT / "_sammanfattning_komplettering.json").write_text(json.dumps(samm, ensure_ascii=False, indent=1))
    logga(f"\nKomplettering klar {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}")


if __name__ == "__main__":
    main()
