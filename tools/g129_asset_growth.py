"""G129 — ASSET GROWTH / INVESTMENT EFFECT som inkrementell information

INFORMATIONSTEST. Ingen portföljregel körs. Ingen G97-variant. H0 oförändrad.

DEFINITION — LÅST FÖRE ALL RESULTATBERÄKNING
  Källa: `validated/kpi_pit/100_Tillvaxt_Totala_Tillgangar_r12.json`
    numerator/denominator : Börsdatas egen R12-serie för tillväxt i totala
                            tillgångar; levereras färdigberäknad, ingen
                            konstruktion görs här
    period               : R12 (rullande tolv månader), fält `y` och `p`
    enhet                : PROCENT (median 7,50 = 7,5 % tillväxt)
    PIT                  : senaste `report_date` <= paneldatum − 5 dagar,
                           samma lagg som allt annat KPI-arbete i projektet
    valuta               : fältet finns men tillväxt är en kvot och därmed
                           enhetslös; ingen valutaomräkning behövs och den
                           tidigare Börsdata-valutabuggen kan inte återuppstå
    negativa värden      : tillåtna och behållna, 29 % av raderna
    saknade värden       : noll rader saknar `v`; missingness uppstår enbart
                           genom att bolaget saknar rapport före paneldatum
    winsorisering        : INGEN finns och INGEN läggs till. Fördelningen har
                           extrem högersvans (max +31 408 %). Rangbaserad
                           inferens (Spearman på percentilrank) är immun mot
                           det, och att införa vinsorisering vore ett nytt
                           definitionsval.

  VARFÖR DENNA OCH INTE EN EGEN KONSTRUKTION: en alternativ definition kunde
  byggas ur `57_Totala_Tillgangar_r12` som nivå[t]/nivå[t−4 kvartal] − 1. Den
  konstrueras INTE, eftersom två definitioner skulle innebära ett val efter att
  utfallet setts. KPI 100 är den enda som levereras direkt med report_date.

  ANMÄRKNING: asset growth finns **inte** i `feature_registry.json` (som har
  `revenue_growth_yoy`, `eps_growth_yoy`, `shares_growth_yoy`,
  `asset_turnover_ttm`). Detta är alltså PIT-korrekt rådata, inte en
  QA-registrerad feature. Det sänker bevisvärdet och redovisas.

FÖRVÄNTAD RIKTNING: hög tillgångstillväxt → LÄGRE framtida avkastning, alltså
NEGATIV inkrementell IC.

Kör: /opt/momentum/venv/bin/python tools/g129_asset_growth.py
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

OUT = V2 / "research_k/g129_asset_growth_results.json"
PANEL = V2 / "research_k/g129_paneldata.jsonl"
KPI = V2 / "validated/kpi_pit"
COST = 0.002
PPY = 13
N, K = 30, 6
LAGG = 5
MINV = 45
MIN_GILTIGA = 20
HOR = [(1, "4v"), (2, "8v"), (3, "12v"), (6, "24v")]


def ladda(fil, bara_sek=False):
    per = defaultdict(list)
    for r in json.loads((KPI / f"{fil}.json").read_text()):
        if r.get("report_date") and r.get("v") is not None:
            if bara_sek and r.get("currency") != "SEK":
                continue
            per[r["kod"]].append((r["report_date"], float(r["v"])))
    return {k: (np.array([x[0] for x in sorted(v)]), np.array([x[1] for x in sorted(v)]))
            for k, v in per.items()}


AG = ladda("100_Tillvaxt_Totala_Tillgangar_r12")
BV = ladda("50_Borsvarde_r12", bara_sek=True)


def pit(d, k, dt):
    h = d.get(k)
    if h is None:
        return None
    g = (date.fromisoformat(dt) - timedelta(days=LAGG)).isoformat()
    i = int(np.searchsorted(h[0], g, side="right")) - 1
    return float(h[1][i]) if i >= 0 else None


_D, _W = {}, {}


def veckor(F, k):
    n = (id(F), k)
    if n in _W:
        return _W[n]
    if F is S.F19:
        s = M.SERIE.get(k)
        d = None if s is None else (s[0].astype("datetime64[D]").astype(str).tolist(), np.asarray(s[1]))
    else:
        s = S.PS26.get(k)
        d = None if s is None else (list(s[0]), np.asarray(s[1]))
    if d is None:
        _W[n] = None
        return None
    ds, adj = d
    sista = {}
    for i, x in enumerate(ds):
        y, wk, _ = date.fromisoformat(x).isocalendar()
        sista[(y, wk)] = i
    idx = [sista[x] for x in sorted(sista)]
    _W[n] = ([ds[i] for i in idx], adj[idx])
    return _W[n]


def vol52(F, k, dt):
    w = veckor(F, k)
    if w is None:
        return None
    wd, wp = w
    j = bisect.bisect_right(wd, dt)
    fon = wp[max(0, j - 53):j]
    if len(fon) < MINV + 1:
        return None
    return float(np.std(fon[1:] / fon[:-1] - 1, ddof=1))


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


def resid(mal, kontroll):
    y = np.argsort(np.argsort(mal)).astype(float)
    X = np.column_stack([np.ones(len(y))] + [np.argsort(np.argsort(c)).astype(float) for c in kontroll])
    return y - X @ np.linalg.lstsq(X, y, rcond=None)[0]


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


def h0_kontroll(F):
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    w, nets = {}, []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w:
            sel = [r["kod"] for r in raw][:N]
            mal = {k: 1.0 / N for k in sel}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0)) for k in set(mal) | set(w)) / 2.0
        else:
            mal = dict(w); turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        nets.append(float(sum(mal[k] * r[k] for k in mal)) - COST * turn)
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return np.array(nets)


def main():
    ut = {"version": "G129_ASSET_GROWTH_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "definition": {
              "kalla": "validated/kpi_pit/100_Tillvaxt_Totala_Tillgangar_r12.json",
              "period": "R12", "enhet": "procent", "pit_lagg_dagar": LAGG,
              "valuta": "enhetslos kvot; ingen omrakning behovs",
              "negativa_varden": "tillatna, 29 % av raderna",
              "winsorisering": "INGEN; rangbaserad inferens anvands i stallet",
              "i_feature_registry": False,
              "anmarkning": "PIT-korrekt radata, INTE en QA-registrerad feature. Registret har "
                            "revenue_growth_yoy, eps_growth_yoy, shares_growth_yoy men ingen asset growth.",
              "alternativ_ej_konstruerad": "57_Totala_Tillgangar_r12 som niva/niva-4q; INTE byggd, "
                                           "for att undvika val efter sett utfall"},
          "forvantad_riktning": "hog tillgangstillvaxt -> LAGRE framtida avkastning (negativ IC)",
          "fonster": {}}
    rader = []

    for w_, F, namn, ref in (("2020_2026", S.F26, "2020-2026", 0.0720),
                             ("2014_2019", S.F19, "2014-2019", 0.3156)):
        nets = h0_kontroll(F)
        cagr = float(np.prod(1 + nets) ** (PPY / len(nets)) - 1)
        print(f"\n{'='*78}\n{namn}")
        print(f"  A. locked H0 reproducerar: {cagr:.2%} mot referens {ref:.2%}  "
              f"{'OK' if abs(cagr - ref) < 0.001 else 'AVVIKER'}")

        # bygg paneltabell
        tab = []
        for pi, dt in enumerate(F["eval_dates"]):
            raw = F["rankings"][dt]
            top = [r["kod"] for r in raw][:N]
            sc = {r["kod"]: r["score"] for r in raw}
            rows = []
            for r_, k in enumerate(top):
                ag = pit(AG, k, dt)
                rows.append({"kod": k, "pi": pi, "dt": dt, "rank": r_ + 1, "score": sc[k],
                             "ag": ag, "vol": vol52(F, k, dt),
                             "size": pit(BV, k, dt), "fw1": framat(F, k, pi, 1)})
            tab.append(rows)

        # ---- B. coverage
        giltiga = [sum(1 for r in p if r["ag"] is not None) for p in tab]
        g = np.array(giltiga)
        andel_obs = float(np.mean([r["ag"] is not None for p in tab for r in p]))
        ok_paneler = [i for i, x in enumerate(giltiga) if x >= MIN_GILTIGA]
        print(f"\n  B. COVERAGE")
        print(f"    paneler {len(tab)}   giltiga av 30: medel {g.mean():.1f}  median "
              f"{np.median(g):.0f}  min {g.min()}  max {g.max()}")
        print(f"    andel paneler med >= {MIN_GILTIGA}/30: {len(ok_paneler)/len(tab):.1%} "
              f"({len(ok_paneler)} av {len(tab)})")
        print(f"    andel observationer med giltigt varde: {andel_obs:.1%}")
        halv = len(tab) // 2
        print(f"    coverage over tid: forsta halvan {np.mean(giltiga[:halv]):.1f}, "
              f"andra halvan {np.mean(giltiga[halv:]):.1f}")

        # ---- C. coverage-selection audit
        print(f"\n  C. COVERAGE-SELECTION AUDIT — namn MED mot UTAN asset-growth-data")
        print(f"    {'variabel':<12}{'MED':>11}{'UTAN':>11}{'diff':>10}{'t':>8}{'n paneler':>11}")
        sel = {}
        for f_ in ("rank", "score", "vol", "size", "fw1"):
            a_, b_ = [], []
            for p in tab:
                x = [r[f_] for r in p if r["ag"] is not None and r[f_] is not None]
                y = [r[f_] for r in p if r["ag"] is None and r[f_] is not None]
                if len(x) >= 5 and len(y) >= 2:
                    a_.append(float(np.mean(x))); b_.append(float(np.mean(y)))
            if len(a_) < 8:
                print(f"    {f_:<12}   for fa paneler med bada grupper"); continue
            d_ = np.array(a_) - np.array(b_)
            t = float(d_.mean() / (d_.std(ddof=1) / math.sqrt(len(d_))))
            sel[f_] = {"med": round(float(np.mean(a_)), 5), "utan": round(float(np.mean(b_)), 5),
                       "diff": round(float(d_.mean()), 5), "t": round(t, 2), "n": len(d_)}
            print(f"    {f_:<12}{np.mean(a_):>11.4f}{np.mean(b_):>11.4f}{d_.mean():>+10.4f}"
                  f"{t:>8.2f}{len(d_):>11}")

        # ---- D/E. signaltest
        print(f"\n  D/E. SIGNALTEST — residual-IC mot asset growth (forvantat NEGATIV)")
        print(f"    {'horisont':<9}{'rank-IC':>10}{'residual':>11}{'t naiv':>8}{'t R6':>7}"
              f"{'boot-KI':>20}{'Q1-Q5':>9}{'paneler':>9}")
        res = {}
        for h, e in HOR:
            serie, kv = [], defaultdict(list)
            for p in tab:
                rows = [r for r in p if r["ag"] is not None]
                if len(rows) < MIN_GILTIGA:
                    continue
                fw = [framat(F, r["kod"], rows[0]["pi"], h) for r in rows]
                m = [i for i, x in enumerate(fw) if x is not None]
                if len(m) < MIN_GILTIGA:
                    continue
                yy = [fw[i] for i in m]
                ag = [rows[i]["ag"] for i in m]
                sc = [rows[i]["score"] for i in m]
                raw_ic = spearman(ag, yy)
                rr = resid(ag, [sc])
                v = spearman(list(rr), yy)
                if v is not None:
                    serie.append((raw_ic if raw_ic is not None else np.nan, v))
                ordn = sorted(range(len(m)), key=lambda i: ag[i])
                q = max(3, len(ordn) // 5)
                kv["Q1"].append(float(np.mean([yy[i] for i in ordn[:q]])))
                kv["Q5"].append(float(np.mean([yy[i] for i in ordn[-q:]])))
            if len(serie) < 8:
                continue
            a1 = np.array([x[0] for x in serie]); a2 = np.array([x[1] for x in serie])
            tn = float(a2.mean() / (a2.std(ddof=1) / math.sqrt(len(a2))))
            rng = np.random.default_rng(20260817)
            bs = np.array([np.mean(rng.choice(a2, len(a2), replace=True)) for _ in range(2000)])
            q15 = float(np.mean(kv["Q1"]) - np.mean(kv["Q5"]))
            res[e] = {"rank_ic": round(float(np.nanmean(a1)), 4),
                      "residual_ic": round(float(a2.mean()), 4), "t_naiv": round(tn, 2),
                      "t_regel6": round(tn / math.sqrt(h), 2),
                      "boot_ki": [round(float(np.percentile(bs, 2.5)), 4),
                                  round(float(np.percentile(bs, 97.5)), 4)],
                      "Q1_minus_Q5": round(q15, 5),
                      "Q1_lag_tillvaxt": round(float(np.mean(kv["Q1"])), 5),
                      "Q5_hog_tillvaxt": round(float(np.mean(kv["Q5"])), 5),
                      "n_paneler": len(a2)}
            print(f"    {e:<9}{np.nanmean(a1):>+10.4f}{a2.mean():>+11.4f}{tn:>8.2f}"
                  f"{tn/math.sqrt(h):>+7.2f}"
                  f"   [{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}]"
                  f"{q15:>+9.2%}{len(a2):>9}")

        # ---- H. G97-diagnostik
        print(f"\n  H. G97-DIAGNOSTIK — har de sex high-vol-exkluderade hogre asset growth?")
        dg, dg_res = [], []
        for p in tab:
            med = [r for r in p if r["vol"] is not None and r["ag"] is not None]
            if len(med) < MIN_GILTIGA:
                continue
            bort = set(x["kod"] for x in sorted(med, key=lambda r: -r["vol"])[:K])
            a_ = [r["ag"] for r in med if r["kod"] in bort]
            b_ = [r["ag"] for r in med if r["kod"] not in bort]
            if len(a_) >= 3 and len(b_) >= 8:
                dg.append(float(np.mean(a_) - np.mean(b_)))
                # kontrollerat for H0-rank: rangresidual av ag mot rank, jamfor gruppmedel
                rr = resid([r["ag"] for r in med], [[r["rank"] for r in med]])
                idx = [i for i, r in enumerate(med) if r["kod"] in bort]
                oth = [i for i, r in enumerate(med) if r["kod"] not in bort]
                dg_res.append(float(np.mean(rr[idx]) - np.mean(rr[oth])))
        if len(dg) >= 8:
            a1, a2 = np.array(dg), np.array(dg_res)
            t1 = float(a1.mean() / (a1.std(ddof=1) / math.sqrt(len(a1))))
            t2 = float(a2.mean() / (a2.std(ddof=1) / math.sqrt(len(a2))))
            print(f"    ra skillnad i asset growth (high-vol minus ovriga): "
                  f"{a1.mean():+.2f} procentenheter, t {t1:+.2f}")
            print(f"    efter kontroll for H0-rank (rangenheter): {a2.mean():+.2f}, t {t2:+.2f}")
            g97 = {"ra_diff": round(float(a1.mean()), 4), "t_ra": round(t1, 2),
                   "rankkontrollerad_diff_rangenheter": round(float(a2.mean()), 4),
                   "t_rankkontrollerad": round(t2, 2), "n_paneler": len(a1)}
        else:
            print(f"    for fa paneler")
            g97 = None

        ut["fonster"][w_] = {"h0_cagr": round(cagr, 5), "h0_reproducerar": bool(abs(cagr - ref) < 0.001),
                             "coverage": {"n_paneler": len(tab), "medel_giltiga": round(float(g.mean()), 2),
                                          "median_giltiga": float(np.median(g)),
                                          "min": int(g.min()), "max": int(g.max()),
                                          "andel_paneler_over_20": round(len(ok_paneler)/len(tab), 4),
                                          "andel_obs_giltiga": round(andel_obs, 4),
                                          "forsta_halvan": round(float(np.mean(giltiga[:halv])), 2),
                                          "andra_halvan": round(float(np.mean(giltiga[halv:])), 2)},
                             "coverage_selection": sel, "signal": res, "g97_diagnostik": g97}
        for p in tab:
            for r in p:
                rader.append({"fonster": namn, "dt": r["dt"], "kod": r["kod"], "rank": r["rank"],
                              "ag": r["ag"], "vol": r["vol"]})

    with open(PANEL, "w") as f:
        for r in rader:
            f.write(json.dumps(r, ensure_ascii=False, default=float) + "\n")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nPaneldata: {PANEL} ({len(rader)} observationer)")


if __name__ == "__main__":
    main()
