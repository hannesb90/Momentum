"""PEAD SOM EGET SPÅR — INTE SOM FILTER PÅ H0

Spår J/K prövade rapportinformation som CONFIRMATION ovanpå H0 och fick
INGET STÖD (delta mean IC52 −0,0476). Men den FRISTÅENDE PEAD-hypotesen fick
STÖD: mean IC13w 0,0750, median 0,0857, 54,7 % positiva datum, båda
kronologiska halvorna positiva, 0,0689 även utan terminalinstrument.

Det testet mätte informationsinnehåll (IC). Detta bygger en faktisk portfölj:
köp de namn vars senaste primära resultatrapport gav starkast initial reaktion,
håll dem ett fast antal paneler, och jämför mot universumet och mot STACK_H.

Exekvering följer projektets disciplin: reaktionen mäts från sista stängning
FÖRE market_known_time till första stängning EFTER, och en position kan tas
tidigast på nästa paneldatum därefter.

FÖNSTER: endast 2020-2026. MFN-datan börjar 2020, så tvåfönsterkriteriet kan
inte uppfyllas. Ett positivt utfall här är hypotesgenererande och kräver
förregistrering mot forward-epoken, inte befordran.

Kör: /opt/momentum/venv/bin/python tools/pead_eget_spar.py
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

OUT = V2 / "research_k/pead_eget_spar_results.json"
EVENTS = V2 / "trackj/validated_mfn_report_events_v1/validated_mfn_report_events.jsonl"
COST = 0.002
DTS = S.DT26
SER = {k: ([x for x in ds], np.array(adj)) for k, (ds, adj) in S.PS26.items()}


def px_index(k, datum):
    """Index för sista handelsdag <= datum."""
    if k not in SER:
        return None
    ds, _ = SER[k]
    i = bisect.bisect_right(ds, datum) - 1
    return i if i >= 0 else None


def reaktion(k, mkt):
    """Avkastning från sista stängning FÖRE market_known_time till första EFTER."""
    if k not in SER:
        return None
    ds, adj = SER[k]
    dag = mkt[:10]
    i = bisect.bisect_left(ds, dag) - 1          # sista stängning före dagen
    j = bisect.bisect_right(ds, dag)             # första stängning efter dagen
    if i < 0 or j >= len(ds) or adj[i] <= 0:
        return None
    return float(adj[j] / adj[i] - 1), ds[j]


def ladda_events():
    ut = []
    with open(EVENTS) as f:
        for rad in f:
            try:
                e = json.loads(rad)
            except Exception:
                continue
            def flagga(v):
                return v is True or (isinstance(v, str) and v.lower() == "true")
            if not flagga(e.get("primary_earnings_release_eligible")):
                continue
            if not flagga(e.get("primary_event_for_instrument_day")):
                continue
            if flagga(e.get("is_correction_or_update")):
                continue
            k, mkt = e.get("instrument_id"), e.get("market_known_time")
            if not k or not mkt or k not in SER:
                continue
            r = reaktion(k, mkt)
            if r is None:
                continue
            ut.append({"kod": k, "mkt": mkt[:10], "reaktion": r[0], "handelsdag": r[1],
                       "typ": e.get("event_type")})
    return ut


def sim_pead(ev, N=20, fonster_paneler=2, hall_paneler=3, viktning="invvol"):
    """Köp namn med starkast reaktion bland rapporter inom de senaste
    fonster_paneler panelerna; håll hall_paneler paneler."""
    per_kod = defaultdict(list)
    for e in ev:
        per_kod[e["kod"]].append(e)
    for k in per_kod:
        per_kod[k].sort(key=lambda x: x["handelsdag"])
    prev, nets, alder = [], [], {}
    for pi, dt in enumerate(DTS):
        lo = DTS[max(0, pi - fonster_paneler)]
        kandidater = []
        for k, lista in per_kod.items():
            for e in lista:
                if lo < e["handelsdag"] <= dt:
                    kandidater.append((e["reaktion"], k))
                    break
        kandidater.sort(reverse=True)
        nya = [k for _, k in kandidater][:N]
        behall = [k for k in prev if alder.get(k, 0) < hall_paneler]
        sel = behall + [k for k in nya if k not in behall]
        sel = sel[:N]
        for k in list(alder):
            if k not in sel:
                alder.pop(k)
        for k in sel:
            alder[k] = alder.get(k, 0) + 1
        turn = 0.0 if not prev else 1.0 - len(set(sel) & set(prev)) / max(1, len(sel))
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev = sel; continue
        if viktning == "lika":
            w = np.full(n, 1.0 / N)
        else:
            inv = 1.0 / (np.maximum(np.array([S.VOL26.get((k, dt), 0.25) for k in sel]), 0.05) ** 1.5)
            w = inv / np.sum(inv) * (n / N)
        w = np.clip(w, 0.01, 0.10); w = w / np.sum(w) * (n / N)
        rets = np.array([S.RET26.get((k, dt), 0.0) for k in sel])
        nets.append(float(np.sum(w * rets)) - COST * turn)
        prev = sel
    return np.array(nets)


def main():
    ev = ladda_events()
    print(f"Primära resultatpubliceringar med mätbar reaktion: {len(ev)}")
    r = np.array([e["reaktion"] for e in ev])
    print(f"  initial reaktion: medel {r.mean():+.2%}, median {np.median(r):+.2%}, "
          f"sd {r.std(ddof=1):.2%}, andel positiva {np.mean(r > 0):.0%}")
    ar = defaultdict(int)
    for e in ev:
        ar[e["handelsdag"][:4]] += 1
    print(f"  per år: {dict(sorted(ar.items()))}")

    univ = np.array([float(np.mean([S.RET26.get((x["kod"], dt), 0.0) for x in S.ROWS26[dt]]))
                     for dt in DTS])
    bas = S.kor(**S.F26)[0]
    ut = {"version": "PEAD_EGET_SPAR_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "forbehall": "ENDAST 2020-2026. Tvåfönsterkriteriet kan inte uppfyllas — MFN börjar 2020.",
          "n_events": len(ev), "varianter": {}}
    print(f"\n{'variant':<34}{'CAGR':>8}{'vol':>8}{'maxDD':>9}{'Sharpe':>8}{'korr STACK_H':>14}")
    print(f"{'likaviktat universum':<34}{S.stat(univ)['cagr']:>8.2%}{S.stat(univ)['vol']:>8.2%}"
          f"{S.stat(univ)['maxdd']:>9.2%}{S.stat(univ)['sharpe']:>8.3f}")
    print(f"{'STACK_H':<34}{S.stat(bas)['cagr']:>8.2%}{S.stat(bas)['vol']:>8.2%}"
          f"{S.stat(bas)['maxdd']:>9.2%}{S.stat(bas)['sharpe']:>8.3f}")
    for N in (15, 20, 30):
        for hall in (1, 3, 6):
            a = sim_pead(ev, N=N, hall_paneler=hall)
            st = S.stat(a)
            kk = float(np.corrcoef(a, bas)[0, 1]) if np.std(a) > 0 else 0.0
            namn = f"PEAD N={N}, håll {hall} paneler"
            ut["varianter"][namn] = {**st, "korr_stack_h": round(kk, 3),
                                     **S.boot(a, univ)} if np.std(a) > 0 else {**st}
            print(f"{namn:<34}{st['cagr']:>8.2%}{st['vol']:>8.2%}{st['maxdd']:>9.2%}"
                  f"{st['sharpe']:>8.3f}{kk:>14.3f}")
    # bästa varianten kombinerad med STACK_H
    b = max(ut["varianter"], key=lambda k: ut["varianter"][k]["sharpe"])
    N = int(b.split("N=")[1].split(",")[0]); hall = int(b.split("håll ")[1].split()[0])
    p = sim_pead(ev, N=N, hall_paneler=hall)
    print(f"\nBLANDNING med bästa PEAD-varianten ({b}):")
    print(f"  {'andel PEAD':<14}{'CAGR':>8}{'vol':>8}{'maxDD':>9}{'Sharpe':>8}")
    ut["blandning"] = {}
    for andel in (0.0, 0.1, 0.2, 0.3, 0.5):
        m = (1 - andel) * bas + andel * p
        st = S.stat(m)
        ut["blandning"][f"{andel:.0%}"] = st
        print(f"  {andel:<14.0%}{st['cagr']:>8.2%}{st['vol']:>8.2%}{st['maxdd']:>9.2%}{st['sharpe']:>8.3f}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
