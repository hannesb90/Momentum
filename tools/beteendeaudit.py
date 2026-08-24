"""BETEENDEAUDIT — systematisk jakt på motsägelser i modellens beteende.

Kör fem generativa mallar mot sju beslutsdimensioner och rapporterar
avvikelser sorterade efter storlek. Syftet är att ersätta "vänta på att en
motsägelse råkar synas" med en lista som finns innan sessionen börjar.

MALLAR
  T1  specifikation mot kod      — gör koden det dokumentationen påstår?
  T2  två regler som strider     — var ger mekanismerna motsatt besked?
  T3  fel mått döljer sanningen  — vad döljer varje rapporterat tal?
  T4  signal snabbare än panel   — aliasering, lookback/panelgap
  T5  villkorad nedbrytning      — håller resultatet i alla tillstånd?

DIMENSIONER: urval, timing, storlek, hålltid, utgång, kassa, icke-ägt.

DIAGNOSTISKT. Rör ingen fryst modell, skriver inget till registret.
Kör:  /opt/momentum/venv/bin/python tools/beteendeaudit.py
"""
from __future__ import annotations

import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/beteendeaudit_results.json"
PPY, COST = 13.0, 0.002
DECL = {"cap": 0.06, "floor": 0.01, "n_top": 30, "rebalance_weeks": 8}

FYND = []
def fynd(mall, dim, namn, deklarerat, faktiskt, avvikelse, kommentar=""):
    FYND.append({"mall": mall, "dimension": dim, "namn": namn,
                 "deklarerat": deklarerat, "faktiskt": faktiskt,
                 "avvikelse": float(avvikelse), "kommentar": kommentar})


def ladda():
    s = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    core, prices, term = m.load_data()
    rmap, alld = m.execution_engine(core, prices, term)
    vmap, pser = m.compute_vols(prices, window=60)
    rk = m.derive_h0_scores(core, prices)
    cf = m.fetch_fundamental_confirmations(rk, prices)
    return m, prices, rmap, alld, vmap, pser, rk, cf


def simulera(rk, alld, vmap, pser, cf, rmap, dates, anchor):
    prev, H, R, T = [], [], [], []
    for dt in dates:
        sched = alld.index(dt) % 2 == anchor
        raw = rk[dt]; elig = {r["kod"] for r in raw}
        sel0 = [r["kod"] for r in raw[:30]] if (sched or not prev) else [k for k in prev if k in elig]
        if not (sched or not prev) and len(sel0) < 30:
            sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
        turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)
        sel, orsak = [], {}
        for k in sel0:
            ok = True
            if k in pser:
                ds, a = pser[k]
                i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
                if i is not None and i >= 200 and a[i] < float(np.mean(a[i - 200:i])):
                    ok = False; orsak[k] = "sma200"
            if ok: sel.append(k)
        n = len(sel)
        if n:
            vols = np.array([vmap.get((k, dt), 0.25) for k in sel], float)
            iv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            w = iv / iv.sum() * (n / 30.0); w = np.clip(w, 0.01, 0.06); w = w / w.sum() * (n / 30.0)
            c = np.array([1.0 if cf.get((k, dt), False) else 0.75 for k in sel])
            w = w * c; w = np.clip(w, 0.01, 0.06); w = w / w.sum() * (n / 30.0)
        else:
            w = np.array([])
        r = np.array([rmap.get((k, dt), 0.0) for k in sel]) if n else np.array([])
        H.append(dict(zip(sel, w))); R.append(float((w * r).sum()) - COST * turn if n else 0.0); T.append(turn)
        prev = sel0
    return H, np.array(R), np.array(T)


def main() -> None:
    m, prices, rmap, alld, vmap, pser, rk, cf = ladda()
    dates = sorted(rk.keys()); anchor = alld.index(m.PHASE_ANCHOR_H0) % 2
    H, R, T = simulera(rk, alld, vmap, pser, cf, rmap, dates, anchor)
    W = np.array([w for h in H for w in h.values()])
    N = np.array([len(h) for h in H])

    # ---- T1 specifikation mot kod ----
    mx = W.max()
    fynd("T1", "storlek", "viktak", DECL["cap"], mx, mx / DECL["cap"] - 1,
         f"överskrids i {np.mean([max(h.values(), default=0) > DECL['cap']*1.001 for h in H]):.0%} av panelerna")
    mn = W.min()
    fynd("T1", "storlek", "viktgolv", DECL["floor"], mn, DECL["floor"] / max(mn, 1e-9) - 1)
    fynd("T1", "urval", "antal innehav", DECL["n_top"], float(N.mean()), N.mean() / DECL["n_top"] - 1,
         f"grinden tar bort {DECL['n_top']-N.mean():.1f} platser i snitt")
    nz = T[T > 0.001]
    arlig = nz.mean() * len(nz) / (len(dates) / PPY)
    fynd("T1", "hålltid", "årlig omsättning (ensidig)", 0.24, arlig, arlig / 0.24 - 1,
         "registrets 'turnover' är per panel, inte per år — lätt att missläsa")

    # ---- T2 två regler som strider ----
    strid = kostnad = 0
    for i in range(1, len(dates)):
        for k, w in H[i].items():
            wp = H[i - 1].get(k)
            if wp and w > wp * 1.02 and k not in H[min(i + 1, len(H) - 1)]:
                strid += 1; kostnad += w * rmap.get((k, dates[i]), 0.0)
    fynd("T2", "storlek", "ökad vikt följt av utgång nästa panel", 0, strid, strid,
         f"summerat bidrag {kostnad:+.2%} — viktformeln och urvalsregeln ger motsatt besked")
    sma = sum(1 for i, dt in enumerate(dates[:-1]) for k in H[i] if k not in H[i + 1]
              and k in pser and (lambda ds, a: (lambda j: j is not None and j >= 200 and a[j] < float(np.mean(a[j-200:j])))(
                  next((x for x in range(len(ds)-1, -1, -1) if ds[x] <= dates[i+1]), None)))(*pser[k]))
    ut = sum(1 for i in range(len(dates)-1) for k in H[i] if k not in H[i+1])
    fynd("T2", "utgång", "andel utgångar via SMA200 vs rangfall", 0.5, sma / max(ut, 1), sma/max(ut,1) - 0.5,
         f"{sma} av {ut} utgångar drivs av grinden, inte av rankningen")

    # ---- T3 fel mått ----
    agg = defaultdict(lambda: [0.0, 0.0, 0, 0])
    for i, dt in enumerate(dates):
        for r in rk[dt]:
            k = r["kod"]; x = rmap.get((k, dt))
            if x is None or not np.isfinite(x) or x <= -0.99: continue
            lg = math.log1p(x); agg[k][1] += lg; agg[k][3] += 1
            if k in H[i]: agg[k][0] += lg; agg[k][2] += 1
    # ENDAST aktier modellen faktiskt agt, och med tillrackligt lang narvaro
    agd = [v for v in agg.values() if v[2] > 0 and v[3] >= 20]
    vinn = [a / b for a, b, _, _ in agd if b > 0.2]
    forl = [a / b for a, b, _, _ in agd if b < -0.2]
    mv, mf = float(np.median(vinn)), float(np.median(forl))
    fynd("T3", "timing", "fångstgrad vinnare (median)", 1.0, mv, mv - 1.0,
         f"n={len(vinn)} vinnare, {len(forl)} förlorare; förlorarnas fångst {mf:.1%} "
         f"— asymmetri {mv-mf:+.1%}, fel håll")
    w_ = np.cumprod(1 + R); dd_panel = float((w_ / np.maximum.accumulate(w_) - 1).min())
    fynd("T3", "utgång", "MaxDD mätt på panel vs daglig", dd_panel, dd_panel, 0.0,
         "panelupplösning kan inte se intraperiod-drawdown; verklig siffra är djupare")

    # ---- T4 aliasering ----
    GAP = 28
    for namn, lb in [("SMA200-grind", 200), ("momentum 52v", 364), ("vol60 (viktning)", 60),
                     ("MA120 (FR-overlay)", 120), ("mom_4w (dippsignal)", 20)]:
        obs = lb / GAP
        if obs < 2:
            fynd("T4", "timing", f"aliasering: {namn}", 2.0, obs, obs - 2.0,
                 f"kräver panelgap ≤ {lb//2} dagar för korrekt sampling")

    # ---- T5 villkorad nedbrytning ----
    h = len(R) // 2
    def cagr(x): return float(np.prod(1 + x) ** (PPY / len(x)) - 1)
    d = cagr(R[:h]) - cagr(R[h:])
    fynd("T5", "urval", "CAGR block1 mot block2", 0.0, d, abs(d),
         f"block1 {cagr(R[:h]):.2%} mot block2 {cagr(R[h:]):.2%}")
    kassa = 1 - np.array([sum(h_.values()) for h_ in H])
    fynd("T5", "kassa", "medelkassa (avkastar 0)", 0.0, float(kassa.mean()), float(kassa.mean()),
         f"vid styrränta 1,75 % är detta värt {kassa.mean()*0.0175:.2%}/år")

    FYND.sort(key=lambda f: -abs(f["avvikelse"]))
    print("=" * 96); print("BETEENDEAUDIT — avvikelser sorterade efter storlek"); print("=" * 96)
    print(f"  {'mall':5s} {'dimension':11s} {'fynd':38s} {'deklarerat':>11s} {'faktiskt':>11s} {'avvik':>9s}")
    for f in FYND:
        dv = f"{f['deklarerat']:.4g}" if isinstance(f["deklarerat"], (int, float)) else str(f["deklarerat"])
        fv = f"{f['faktiskt']:.4g}" if isinstance(f["faktiskt"], (int, float)) else str(f["faktiskt"])
        print(f"  {f['mall']:5s} {f['dimension']:11s} {f['namn'][:38]:38s} {dv:>11s} {fv:>11s} {f['avvikelse']:+9.3f}")
        if f["kommentar"]: print(f"        └─ {f['kommentar']}")
    OUT.write_text(json.dumps({"version": "BETEENDEAUDIT_V1",
                               "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "n_fynd": len(FYND), "fynd": FYND}, ensure_ascii=False, indent=2))
    print(f"\n  {len(FYND)} fynd → {OUT.name}")


if __name__ == "__main__":
    main()
