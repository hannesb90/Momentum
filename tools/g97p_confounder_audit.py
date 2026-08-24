"""G97-P — MECHANISM / CONFOUNDER FALSIFICATION AUDIT

Syftet är att DÖDA G97-P, inte förbättra den. Ingen ny regel, ingen optimering,
ingen alternativ kvantil, inget parametersök.

Hypotes som ska falsifieras:
  "Hög vol_52w innehåller SJÄLVSTÄNDIG negativ information inom H0 Top-30."

Alternativ: vol_52w är bara en proxy för size, likviditet, sektor, beta,
lönsamhet eller idiosynkratisk volatilitet.

DATAANMÄRKNINGAR SOM MÅSTE STÅ FÖRST
  * `illiquidity_amihud_13w` och `turnover_13w_msek` är **UTESLUTNA ur
    featureregistret**: "kräver QA-godkänt faktiskt ojusterat handelsvolym".
    Jag använder därför en PROVISORISK likviditetsproxy — medianen av
    daglig omsatt krona (volym x close) över 13 veckor — och den är
    uttryckligen INTE QA-godkänd. Att en effekt överlever kontroll av en
    brusig proxy är svagare bevis än att den överlever en ren.
  * Ingen PIT-indexserie finns i det frysta lagret för 2014-2019.
    Marknadsproxyn för beta och idiosynkratisk vol är därför den
    LIKAVIKTADE universumavkastningen, beräknad ur samma veckorekonstruktion.
    Det är featureregistrets definition med universum i indexets roll.
  * Börsvärde (KPI 50) och rörelsemarginal (KPI 29) börjar 2017 och täcker
    därmed bara omkring halva det tidiga fönstret.

Kör: /opt/momentum/venv/bin/python tools/g97p_confounder_audit.py
"""
from __future__ import annotations
import bisect, json, math, sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g97p_confounder_audit_results.json"
KPI = V2 / "validated/kpi_pit"
N, K = 30, 6
HOR = [(1, "4v"), (2, "8v"), (3, "12v"), (6, "24v")]
MINV = 45
LAGG = 5

_D, _W, _MKT = {}, {}, {}


def dagsserie(F, k):
    n = (id(F), k)
    if n not in _D:
        if F is S.F19:
            s = M.SERIE.get(k)
            _D[n] = None if s is None else \
                (s[0].astype("datetime64[D]").astype(str).tolist(), np.asarray(s[1]), None)
        else:
            s = S.PS26.get(k)
            _D[n] = None if s is None else (list(s[0]), np.asarray(s[1]), None)
    return _D[n]


def veckor(F, k):
    n = (id(F), k)
    if n in _W:
        return _W[n]
    s = dagsserie(F, k)
    if s is None:
        _W[n] = None
        return None
    ds, adj, _ = s
    sista = {}
    for i, d in enumerate(ds):
        y, wk, _ = date.fromisoformat(d).isocalendar()
        sista[(y, wk)] = i
    nyck = sorted(sista)
    idx = [sista[x] for x in nyck]
    _W[n] = (nyck, [ds[i] for i in idx], adj[idx])
    return _W[n]


def marknadsveckor(F):
    """Likaviktad universumavkastning per ISO-vecka. Marknadsproxy."""
    if id(F) in _MKT:
        return _MKT[id(F)]
    per = defaultdict(list)
    alla = {r["kod"] for dt in F["eval_dates"] for r in F["rankings"][dt]}
    for k in alla:
        w = veckor(F, k)
        if w is None:
            continue
        nyck, wd, wp = w
        r = wp[1:] / wp[:-1] - 1
        for i in range(len(r)):
            if np.isfinite(r[i]) and abs(r[i]) < 3:
                per[nyck[i + 1]].append(float(r[i]))
    _MKT[id(F)] = {k: float(np.mean(v)) for k, v in per.items() if len(v) >= 20}
    return _MKT[id(F)]


def riskmatt(F, k, dt):
    """-> vol_52w, beta_52w, idio_vol_52w. Endast information t.o.m. dt."""
    w = veckor(F, k)
    if w is None:
        return None, None, None
    nyck, wd, wp = w
    j = bisect.bisect_right(wd, dt)
    if j < MINV + 1:
        return None, None, None
    lo = max(0, j - 53)
    p = wp[lo:j]
    nk = nyck[lo + 1:j]
    if len(p) < MINV + 1:
        return None, None, None
    r = p[1:] / p[:-1] - 1
    vol = float(np.std(r, ddof=1))
    mkt = marknadsveckor(F)
    par = [(r[i], mkt[nk[i]]) for i in range(len(r)) if nk[i] in mkt]
    if len(par) < MINV:
        return vol, None, None
    y = np.array([a for a, _ in par]); x = np.array([b for _, b in par])
    if np.var(x) <= 0:
        return vol, None, None
    beta = float(np.cov(y, x)[0, 1] / np.var(x))
    res = y - (y.mean() - beta * x.mean()) - beta * x
    return vol, beta, float(np.std(res, ddof=1))


def ladda_kpi(fil, bara_sek=False):
    per = defaultdict(list)
    for r in json.loads((KPI / f"{fil}.json").read_text()):
        if r.get("report_date") and r.get("v") is not None:
            if bara_sek and r.get("currency") != "SEK":
                continue
            per[r["kod"]].append((r["report_date"], float(r["v"])))
    return {k: (np.array([x[0] for x in v]), np.array([x[1] for x in sorted(v)]))
            for k, v in {k: sorted(v) for k, v in per.items()}.items()}


BV = ladda_kpi("50_Borsvarde_r12", bara_sek=True)
MG = ladda_kpi("29_Rorelsemarginal_r12")


def pit(d, k, dt):
    h = d.get(k)
    if h is None:
        return None
    g = (date.fromisoformat(dt) - timedelta(days=LAGG)).isoformat()
    i = int(np.searchsorted(h[0], g, side="right")) - 1
    return float(h[1][i]) if i >= 0 else None


def likviditet(F, k, dt):
    """PROVISORISK, EJ QA-GODKÄND: median daglig omsatt krona, 13 veckor."""
    if F is S.F19:
        return None                     # volym finns ej i h1419-lagret
    p = V2 / "validated/prices/prices_validated.json"
    global _PRIS
    try:
        _PRIS
    except NameError:
        _PRIS = json.loads(p.read_text())
    rows = _PRIS.get(k)
    if not rows:
        return None
    lo = (date.fromisoformat(dt) - timedelta(days=91)).isoformat()
    v = [x["v"] * x["close"] for x in rows
         if lo <= x["d"] <= dt and x.get("v") and x.get("close")]
    return float(np.log1p(np.median(v))) if len(v) >= 30 else None


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


def resid(mal, kontroller):
    y = np.argsort(np.argsort(mal)).astype(float)
    kols = [np.ones(len(y))]
    for c in kontroller:
        c = np.asarray(c, float)
        if np.all(np.isfinite(c)) and np.std(c) > 0:
            kols.append(np.argsort(np.argsort(c)).astype(float))
    X = np.column_stack(kols)
    try:
        return y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    except Exception:
        return y


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


def nw_t(x, lag):
    x = np.asarray(x, float); n = len(x)
    if n < 5:
        return float("nan")
    e = x - x.mean(); s = float(e @ e) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2 * (1 - L / (lag + 1)) * float(e[L:] @ e[:-L]) / n
    return float(x.mean() / math.sqrt(s / n)) if s > 0 else float("nan")


def bygg(F):
    """Panelvis tabell över topp-30 med samtliga confounders."""
    ut = []
    for pi, dt in enumerate(F["eval_dates"]):
        raw = F["rankings"][dt]
        top = [r["kod"] for r in raw][:N]
        sc = {r["kod"]: r["score"] for r in raw}
        rows = []
        for r_, k in enumerate(top):
            vol, beta, idio = riskmatt(F, k, dt)
            if vol is None:
                continue
            bv = pit(BV, k, dt); mg = pit(MG, k, dt)
            rows.append({"kod": k, "pi": pi, "dt": dt, "rank": r_ + 1, "score": sc[k],
                         "vol": vol, "beta": beta, "idio": idio,
                         "size": math.log(bv) if (bv and bv > 0) else None,
                         "prof": mg, "liq": likviditet(F, k, dt)})
        if len(rows) >= 20:
            ut.append(rows)
    return ut


def main():
    ut = {"version": "G97P_CONFOUNDER_AUDIT_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "syfte": "falsifiera att hog vol_52w bar sjalvstandig negativ information",
          "dataanmarkningar": [
              "illiquidity_amihud_13w och turnover_13w_msek ar UTESLUTNA ur featureregistret "
              "(kraver QA-godkand ojusterad volym). Likviditet har ar en PROVISORISK, EJ "
              "QA-GODKAND proxy och finns bara for 2020-2026.",
              "Ingen PIT-indexserie finns for 2014-2019. Marknadsproxy for beta och idio-vol ar "
              "den LIKAVIKTADE universumavkastningen ur samma veckorekonstruktion.",
              "Borsvarde (KPI 50) och rorelsemarginal (KPI 29) borjar 2017 och tacker bara "
              "omkring halva det tidiga fonstret.",
              "Sektor: K1 fann ingen PIT-forsvarbar historisk sektorstatus. EJ KONTROLLERAD."],
          "fonster": {}}

    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        tab = bygg(F)
        alla = [r for p in tab for r in p]
        print(f"\n{'='*78}\n{namn}   {len(tab)} paneler, {len(alla)} observationer")

        # ---- A. coverage
        print(f"  A. PIT-TÄCKNING (andel av topp-30-observationer med värde)")
        cov = {}
        for f in ("vol", "beta", "idio", "size", "prof", "liq"):
            c = float(np.mean([r[f] is not None for r in alla]))
            cov[f] = round(c, 4)
            print(f"    {f:<8}{c:>7.1%}")
        ut["fonster"][w_] = {"n_paneler": len(tab), "n_obs": len(alla), "tackning": cov}

        # ---- B. high-vol-gruppens karaktär
        print(f"\n  B. DE SEX EXKLUDERADE MOT ÖVRIGA 24 (ex ante, deskriptivt)")
        print(f"    {'variabel':<10}{'high-vol':>11}{'ovriga':>11}{'diff':>10}{'t':>8}{'n par':>7}")
        karakt = {}
        for f in ("rank", "score", "vol", "beta", "idio", "size", "prof", "liq"):
            hv, ov = [], []
            for p in tab:
                med = [r for r in p if r["vol"] is not None]
                if len(med) < 20:
                    continue
                bort = set(x["kod"] for x in sorted(med, key=lambda r: -r["vol"])[:K])
                a = [r[f] for r in med if r["kod"] in bort and r[f] is not None]
                b = [r[f] for r in med if r["kod"] not in bort and r[f] is not None]
                if a and b:
                    hv.append(float(np.mean(a))); ov.append(float(np.mean(b)))
            if len(hv) < 8:
                continue
            d = np.array(hv) - np.array(ov)
            t = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))
            karakt[f] = {"high_vol": round(float(np.mean(hv)), 4),
                         "ovriga": round(float(np.mean(ov)), 4),
                         "diff": round(float(d.mean()), 4), "t": round(t, 2), "n": len(d)}
            print(f"    {f:<10}{np.mean(hv):>11.4f}{np.mean(ov):>11.4f}{d.mean():>+10.4f}"
                  f"{t:>8.2f}{len(d):>7}")
        ut["fonster"][w_]["high_vol_karakter"] = karakt

        # ---- C. residualiserad vol-signal
        SETS = [("A H0-rank", ["score"]), ("B +size", ["score", "size"]),
                ("C +likviditet", ["score", "size", "liq"]),
                ("E +beta", ["score", "beta"]),
                ("F +lonsamhet", ["score", "prof"]),
                ("G parsimoniskt (rank+beta+size)", ["score", "beta", "size"])]
        print(f"\n  C. RESIDUAL-IC FÖR vol_52w EFTER SUCCESSIV KONTROLL")
        print(f"    {'kontroll':<32}{'4v (h=1)':>12}{'t':>7}{'12v':>9}{'t R6':>8}{'t NW':>7}")
        rc = {}
        for namn_s, kols in SETS:
            per_h = {}
            for h, e in HOR:
                serie = []
                for p in tab:
                    rows = [r for r in p if r["vol"] is not None and
                            all(r[c] is not None for c in kols)]
                    if len(rows) < 15:
                        continue
                    fw = [framat(F, r["kod"], rows[0]["pi"], h) for r in rows]
                    m = [i for i, x in enumerate(fw) if x is not None]
                    if len(m) < 15:
                        continue
                    rr = resid([rows[i]["vol"] for i in m],
                               [[rows[i][c] for i in m] for c in kols])
                    v = spearman(list(rr), [fw[i] for i in m])
                    if v is not None:
                        serie.append(v)
                if len(serie) < 8:
                    continue
                a = np.array(serie)
                tn = float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))
                per_h[e] = {"residual_ic": round(float(a.mean()), 4), "t_naiv": round(tn, 2),
                            "t_regel6": round(tn / math.sqrt(h), 2),
                            "t_nw": round(nw_t(a, h - 1), 2), "n_paneler": len(a)}
            rc[namn_s] = per_h
            f4 = per_h.get("4v", {}); f12 = per_h.get("12v", {})
            print(f"    {namn_s:<32}{f4.get('residual_ic', float('nan')):>+12.4f}"
                  f"{f4.get('t_naiv', float('nan')):>7.2f}"
                  f"{f12.get('residual_ic', float('nan')):>+9.4f}"
                  f"{f12.get('t_regel6', float('nan')):>8.2f}{f12.get('t_nw', float('nan')):>7.2f}")
        ut["fonster"][w_]["residual_ic"] = rc

        # ---- E. beta/idio-diagnostik
        print(f"\n  E. BETA OCH IDIOSYNKRATISK VOL — VAD MÄTER G97?")
        diag = {}
        for etikett, mal, kols in (("vol | rank", "vol", ["score"]),
                                   ("vol | rank+beta", "vol", ["score", "beta"]),
                                   ("vol | rank+idio", "vol", ["score", "idio"]),
                                   ("idio | rank", "idio", ["score"]),
                                   ("idio | rank+vol", "idio", ["score", "vol"]),
                                   ("beta | rank", "beta", ["score"]),
                                   ("beta | rank+vol", "beta", ["score", "vol"])):
            serie = []
            for p in tab:
                rows = [r for r in p if r[mal] is not None and
                        all(r[c] is not None for c in kols)]
                if len(rows) < 15:
                    continue
                fw = [framat(F, r["kod"], rows[0]["pi"], 1) for r in rows]
                m = [i for i, x in enumerate(fw) if x is not None]
                if len(m) < 15:
                    continue
                rr = resid([rows[i][mal] for i in m], [[rows[i][c] for i in m] for c in kols])
                v = spearman(list(rr), [fw[i] for i in m])
                if v is not None:
                    serie.append(v)
            if len(serie) < 8:
                continue
            a = np.array(serie)
            t = float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a))))
            diag[etikett] = {"residual_ic_4v": round(float(a.mean()), 4), "t": round(t, 2),
                             "n": len(a)}
            print(f"    {etikett:<20}{a.mean():>+10.4f}   t {t:>+6.2f}   (h=1, {len(a)} paneler)")
        ut["fonster"][w_]["beta_idio_diagnostik"] = diag

        # korrelationer
        kk = {}
        for a_, b_ in (("vol", "beta"), ("vol", "idio"), ("beta", "idio"),
                       ("vol", "size"), ("vol", "liq"), ("vol", "prof")):
            par = [(r[a_], r[b_]) for r in alla if r[a_] is not None and r[b_] is not None]
            if len(par) > 100:
                kk[f"{a_}~{b_}"] = round(float(np.corrcoef([x[0] for x in par],
                                                           [x[1] for x in par])[0, 1]), 3)
        ut["fonster"][w_]["korrelationer"] = kk
        print(f"    korrelationer: " + "  ".join(f"{k} {v:+.2f}" for k, v in kk.items()))

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
