"""FUNGERAR MOMENTUM PÅ OLIKA HORISONTER I OLIKA SEGMENT?

Hypotesen: momentum borde vara KORTARE på små, olönsamma bolag och LÄNGRE på
stora kvalitetsbolag, som drivs av andra saker.

Vi har prövat horisonter GLOBALT (3+6, 6+12, 3+12, 6+18, rena 3m och 6m — alla
föll). Men ett globalt test tar ut effekten mot sig själv om kort fungerar på
små och lång på stora. Segmentuppdelat är detta oprövat.

STEG 1 ÄR DIAGNOSTIK, INTE EN REGEL. Först mäts om horisontpreferensen
överhuvudtaget skiljer sig mellan segmenten. Bygger man portföljregeln först
mäter man sin egen parametersökning.

SEGMENTERING (PIT)
  Storlek     tercil av börsvärde (KPI 50, r12) med senaste report_date <= dt
  Lönsamhet   rörelsemarginal (KPI 29, r12) över/under noll
  Kombinerat  liten+olönsam mot stor+lönsam — användarens faktiska fråga

  Endast SEK-rapporterande bolag ingår i storleksindelningen (90 % av raderna).
  Att räkna om EUR/USD/NOK över elva år skulle införa mer fel än det löser.

MÅTT
  Spearman-IC mellan momentum över h veckor och NÄSTA panels avkastning, per
  panel och segment. Rapporterar medel-IC, t-värde och antal namn.

TÄCKNINGSFÖRBEHÅLL
  KPI-historiken börjar på allvar 2017 (2015: 4 rader, 2016: 264). Det sena
  fönstret är fullt täckt; det tidiga blir i praktiken 2017-2019, alltså halva.
  Det är en verklig begränsning och inte något som går att kringgå med
  befintlig data.

Kör: /opt/momentum/venv/bin/python tools/segment_horisont_diagnostik.py
"""
from __future__ import annotations
import bisect, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/segment_horisont_diagnostik_results.json"
KPI = V2 / "validated/kpi_pit"
HORISONTER = [(13, "3m"), (26, "6m"), (52, "12m"), (78, "18m"), (104, "24m")]
LAGG_DAGAR = 5


def ladda_kpi(fil, bara_sek=False):
    rows = json.loads((KPI / f"{fil}.json").read_text())
    per = defaultdict(list)
    for r in rows:
        if not r.get("report_date") or r.get("v") is None:
            continue
        if bara_sek and r.get("currency") != "SEK":
            continue
        per[r["kod"]].append((r["report_date"], float(r["v"])))
    for k in per:
        per[k].sort()
    return dict(per)


BORSVARDE = ladda_kpi("50_Borsvarde_r12", bara_sek=True)
MARGINAL = ladda_kpi("29_Rorelsemarginal_r12")


def pit(d, k, dt):
    h = d.get(k)
    if not h:
        return None
    from datetime import date, timedelta
    g = (date.fromisoformat(dt) - timedelta(days=LAGG_DAGAR)).isoformat()
    i = bisect.bisect_right([x[0] for x in h], g) - 1
    return h[i][1] if i >= 0 else None


def serie(F, k):
    if F is S.F19:
        s = M.SERIE.get(k)
        return None if s is None else (s[0], s[1], True)
    s = S.PS26.get(k)
    return None if s is None else (s[0], s[1], False)


def mom(F, k, dt, weeks):
    s = serie(F, k)
    if s is None:
        return None
    ds, v, npdate = s
    if npdate:
        now = np.datetime64(dt)
        mal = now - np.timedelta64(int(7 * weeks), "D")
        i = int(np.searchsorted(ds, now, side="right")) - 1
        j = int(np.searchsorted(ds, mal, side="right")) - 1
        if j >= 0 and int((mal - ds[j]) / np.timedelta64(1, "D")) > 10:
            return None
    else:
        from datetime import date, timedelta
        mal = (date.fromisoformat(dt) - timedelta(days=int(7 * weeks))).isoformat()
        i = bisect.bisect_right(ds, dt) - 1
        j = bisect.bisect_right(ds, mal) - 1
    if i < 0 or j < 0 or v[j] <= 0:
        return None
    return float(v[i] / v[j] - 1)


def spearman(x, y):
    n = len(x)
    if n < 12:
        return None
    def rk(a):
        o = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        i = 0
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


def segmentera(F, dt, koder):
    """-> {segmentnamn: [koder]}"""
    bv = {k: pit(BORSVARDE, k, dt) for k in koder}
    mg = {k: pit(MARGINAL, k, dt) for k in koder}
    med_bv = [k for k in koder if bv[k] is not None and bv[k] > 0]
    ut = {}
    if len(med_bv) >= 30:
        v = np.array([bv[k] for k in med_bv])
        q1, q2 = np.quantile(v, [1 / 3, 2 / 3])
        ut["liten"] = [k for k in med_bv if bv[k] <= q1]
        ut["mellan"] = [k for k in med_bv if q1 < bv[k] <= q2]
        ut["stor"] = [k for k in med_bv if bv[k] > q2]
    lon = [k for k in koder if mg[k] is not None and mg[k] > 0]
    olon = [k for k in koder if mg[k] is not None and mg[k] <= 0]
    if len(lon) >= 20:
        ut["lönsam"] = lon
    if len(olon) >= 20:
        ut["olönsam"] = olon
    if "liten" in ut:
        a = [k for k in ut["liten"] if mg.get(k) is not None and mg[k] <= 0]
        b = [k for k in ut["stor"] if mg.get(k) is not None and mg[k] > 0]
        if len(a) >= 15:
            ut["liten+olönsam"] = a
        if len(b) >= 15:
            ut["stor+lönsam"] = b
    ut["ALLA"] = koder
    return ut


def main():
    ut = {"version": "SEGMENT_HORISONT_DIAGNOSTIK_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "status": "DIAGNOSTISK — ingen portföljregel, ingen befordran",
          "forbehall": "KPI-historiken börjar 2017; det tidiga fönstret är i praktiken "
                       "2017-2019. Endast SEK-rapporterande bolag i storleksindelningen.",
          "fonster": {}}

    for w_, F, namn in (("2020_2026", S.F26, "2020-2026"), ("2014_2019", S.F19, "2014-2019")):
        dts, ret = F["eval_dates"], F["returns_map"]
        ics = defaultdict(lambda: defaultdict(list))
        antal = defaultdict(list)
        paneler_med_data = 0
        for pi, dt in enumerate(dts[:-1]):
            koder = [r["kod"] for r in F["rankings"][dt]]
            segs = segmentera(F, dt, koder)
            if "liten" not in segs:
                continue
            paneler_med_data += 1
            for seg, ks in segs.items():
                antal[seg].append(len(ks))
                fwd = {k: ret.get((k, dt)) for k in ks}
                for h, hnamn in HORISONTER:
                    par = [(mom(F, k, dt, h), fwd[k]) for k in ks]
                    par = [(a, b) for a, b in par if a is not None and b is not None]
                    if len(par) < 12:
                        continue
                    ic = spearman([a for a, _ in par], [b for _, b in par])
                    if ic is not None:
                        ics[seg][hnamn].append(ic)

        print(f"\n{namn}   ({paneler_med_data} av {len(dts)} paneler har KPI-täckning)")
        print(f"  {'segment':<16}{'n/panel':>9}" + "".join(f"{h:>16}" for _, h in HORISONTER))
        rad = {}
        ordning = ["ALLA", "liten", "mellan", "stor", "olönsam", "lönsam",
                   "liten+olönsam", "stor+lönsam"]
        for seg in ordning:
            if seg not in ics:
                continue
            celler, r = [], {}
            for h, hnamn in HORISONTER:
                v = np.array(ics[seg][hnamn])
                if len(v) < 8:
                    celler.append(f"{'—':>16}"); continue
                t = float(v.mean() / (v.std(ddof=1) / math.sqrt(len(v))))
                r[hnamn] = {"mean_ic": round(float(v.mean()), 4), "t": round(t, 2),
                            "n_paneler": len(v)}
                celler.append(f"{v.mean():>+10.4f}(t{t:>4.1f})")
            if not r:
                continue
            b = max(r, key=lambda x: r[x]["mean_ic"])
            r["basta_horisont"] = b
            r["n_per_panel"] = round(float(np.mean(antal[seg])), 1)
            rad[seg] = r
            print(f"  {seg:<16}{np.mean(antal[seg]):>9.0f}" + "".join(celler)
                  + f"   bäst: {b}")
        ut["fonster"][w_] = rad

    print("\nBÄSTA HORISONT PER SEGMENT — replikerar preferensen över fönstren?")
    a = ut["fonster"].get("2020_2026", {}); b = ut["fonster"].get("2014_2019", {})
    ut["replikering"] = {}
    for seg in [s for s in a if s in b]:
        lika = a[seg]["basta_horisont"] == b[seg]["basta_horisont"]
        ut["replikering"][seg] = {"sen": a[seg]["basta_horisont"],
                                  "tidig": b[seg]["basta_horisont"], "samma": bool(lika)}
        print(f"  {seg:<16} sent: {a[seg]['basta_horisont']:<5} "
              f"tidigt: {b[seg]['basta_horisont']:<5} {'SAMMA' if lika else 'olika'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
