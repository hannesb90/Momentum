"""JUSTERINGSIDENTITETEN — HELTÄCKANDE TEST AV PRODUKTIONSLAGRET

Rundresetestet hittade åtta justeringsfel över 40 %, varav ett satte Betsson på
rank 1. Granskningen av råraderna visar orsaken: justeringsfaktorn close/adj
ändras på utdelningsdagen UTAN att historiken skalas om, så den justerade
serien hoppar uppåt i stället för att vara jämn.

  Betsson 2022-05-12 → 05-13:  close 64,88 → 66,96 (+3,2 %)
                               adj   36,35 → 53,05 (+45,9 %)
                               faktor 1,7848 → 1,2623

Det betyder att felet INTE är begränsat till stora rörelser. En felaktigt
applicerad normalutdelning ger ett litet falskt hopp som aldrig passerar en
40-procentströskel men ändå förorenar momentum.

Rätt test är identiteten som en justerad serie måste uppfylla varje dag:

    adj_t / adj_(t-1)  ==  (close_t * splitfaktor + utdelning_t) / close_(t-1)

Skriptet mäter avvikelsen från den identiteten för varje dag i lagret och
rapporterar var den brister, hur mycket, och hur många topp-30-observationer
som berörs.

DIAGNOSTISKT. Ingen fryst fil ändras. Utfallet är underlag för beslut om
prislagret måste byggas om.

Kör: /opt/momentum/venv/bin/python tools/justeringsidentitet_produktionslagret.py
"""
from __future__ import annotations
import gzip, importlib.util, json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
OUT = V2 / "research_k/justeringsidentitet_produktionslagret_results.json"

TOL = 0.005          # 0,5 % tolerans mot avrundning i arkivet


def las(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def splitfaktor(s):
    """'3.000000/1.000000' -> 3.0 (antal nya per gammal)."""
    txt = str(s.get("split") or s.get("Split") or "")
    if "/" in txt:
        try:
            a, b = txt.split("/")
            return float(a) / float(b)
        except Exception:
            return None
    return None


def main():
    priser = json.loads((V2 / "validated/prices/prices_validated.json").read_text())

    spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    core_df, prices_raw, terminal = m.load_data()
    rankings = m.derive_h0_scores(core_df, prices_raw)
    eval_dates = sorted(rankings.keys())
    rank_map = {(r["kod"], dt): i + 1 for dt in eval_dates for i, r in enumerate(rankings[dt])}

    avvikelser, statistik = [], Counter()
    per_kod = Counter()
    alla_avv = []

    for kod, serie in sorted(priser.items()):
        raw, kat = None, None
        for k in ("active", "delisted"):
            r = las(EOD / k / "eod" / f"{kod}.json.gz")
            if r:
                raw, kat = {x["date"]: x for x in r}, k
                break
        if not raw:
            statistik["saknar_raserie"] += 1
            continue
        divs = {x["date"]: x for x in las(EOD / kat / "div" / f"{kod}.json.gz")}
        splits = {}
        for s in las(EOD / kat / "splits" / f"{kod}.json.gz"):
            dt = str(s.get("date") or s.get("Date"))[:10]
            f = splitfaktor(s)
            if f:
                splits[dt] = f

        for i in range(1, len(serie)):
            d0, d1 = serie[i - 1]["d"], serie[i]["d"]
            a0, a1 = serie[i - 1]["adj"], serie[i]["adj"]
            r0, r1 = raw.get(d0), raw.get(d1)
            if not r0 or not r1 or a0 <= 0 or not r0.get("close"):
                continue
            c0, c1 = float(r0["close"]), float(r1["close"])
            if c0 <= 0:
                continue
            sf = splits.get(d1, 1.0)
            utd = float(divs[d1].get("unadjustedValue") or divs[d1].get("value") or 0.0) if d1 in divs else 0.0
            ret_adj = a1 / a0 - 1.0
            ret_tr = (c1 * sf + utd) / c0 - 1.0
            avv = ret_adj - ret_tr
            statistik["dagar_provade"] += 1
            alla_avv.append(avv)
            if abs(avv) > TOL:
                statistik["dagar_med_avvikelse"] += 1
                per_kod[kod] += 1
                avvikelser.append({"kod": kod, "datum": d1,
                                   "ret_adjusted": round(ret_adj, 5),
                                   "ret_totalavkastning": round(ret_tr, 5),
                                   "avvikelse": round(avv, 5),
                                   "close_fore": c0, "close_efter": c1,
                                   "utdelning": utd, "splitfaktor": sf,
                                   "faktor_fore": round(c0 / a0, 4),
                                   "faktor_efter": round(c1 / a1, 4),
                                   "rank_denna_panel": rank_map.get((kod, d1))})

    aa = np.array(alla_avv)
    stora = [a for a in avvikelser if abs(a["avvikelse"]) > 0.05]

    # påverkan: berörda namn som når topp-30 inom 20 paneler efter avvikelsen
    beror = defaultdict(set)
    for a in stora:
        efter = [p for p in eval_dates if p >= a["datum"]][:20]
        for p in efter:
            r = rank_map.get((a["kod"], p))
            if r and r <= 30:
                beror[a["kod"]].add(p)
    t30_beror = sum(len(v) for v in beror.values())

    ut = {"version": "JUSTERINGSIDENTITET_PRODUKTIONSLAGRET_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "status": "DIAGNOSTISKT — ingen fryst fil ändrad",
          "identitet": "adj_t/adj_(t-1) == (close_t*split + utdelning_t)/close_(t-1)",
          "tolerans": TOL,
          "statistik": dict(statistik),
          "avvikelsefordelning": {
              "n": len(aa), "medel": round(float(aa.mean()), 6),
              "median": round(float(np.median(aa)), 6),
              "p99": round(float(np.percentile(np.abs(aa), 99)), 5),
              "max_abs": round(float(np.abs(aa).max()), 4)},
          "serier_med_avvikelse": len(per_kod),
          "varsta_serier": per_kod.most_common(15),
          "avvikelser_over_5pct": len(stora),
          "berorda_serier_som_nar_topp30": len(beror),
          "berorda_topp30_panelobservationer": t30_beror,
          "avvikelser": sorted(avvikelser, key=lambda x: -abs(x["avvikelse"]))[:400]}
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))

    print("JUSTERINGSIDENTITETEN I PRODUKTIONSLAGRET")
    print(f"  dagar prövade:            {statistik['dagar_provade']}")
    print(f"  dagar med avvikelse >{TOL:.1%}: {statistik['dagar_med_avvikelse']} "
          f"({statistik['dagar_med_avvikelse']/statistik['dagar_provade']:.3%})")
    print(f"  serier med avvikelse:     {len(per_kod)} av {len(priser)}")
    print(f"  avvikelser > 5 %:         {len(stora)}")
    print(f"  |avvikelse| p99:          {ut['avvikelsefordelning']['p99']:.3%}   "
          f"max {ut['avvikelsefordelning']['max_abs']:.1%}")
    print(f"\n  berörda serier som når topp-30 inom 20 paneler: {len(beror)}")
    print(f"  berörda topp-30-panelobservationer: {t30_beror} av 1980 "
          f"({t30_beror/1980:.2%})")
    print(f"\n  värsta serier (antal avvikelsedagar):")
    for k, c in per_kod.most_common(10):
        print(f"    {k:<12} {c:>4}")
    print(f"\n  största enskilda avvikelser:")
    for a in sorted(avvikelser, key=lambda x: -abs(x["avvikelse"]))[:10]:
        print(f"    {a['datum']} {a['kod']:<11} adj {a['ret_adjusted']:+8.2%} mot "
              f"TR {a['ret_totalavkastning']:+8.2%}  avvikelse {a['avvikelse']:+8.2%}  "
              f"utd {a['utdelning']}")
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
