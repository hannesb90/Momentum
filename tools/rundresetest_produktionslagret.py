"""RUNDRESETEST MOT PRODUKTIONSLAGRET 2020+

Historikbygget 2026-08-15 avslöjade en korruptionstyp som varken divergens-
eller splitkontroll ser: en spik som tas tillbaka nästan exakt dagen efter,
där BÅDE close och adjusted_close är fel. Investor A +1507 %, Hexagon +604 %
och Electrolux +73 % på 2013-05-10 och 2019-06-10, alla med återgång dagen
efter. 33 sådana fel fångades i det historiska lagret.

Samma fel skulle vara osynligt i produktionslagret med nuvarande QA. Detta
skript kör hela bevisbatteriet mot validated/prices/prices_validated.json:

  rundresa        (1+r_t)(1+r_t+1) ≈ 1        endagsspik, datafel
  divergens       ret(adj) − ret(close)        justeringsfel
  splitkvot       kvot nära 1/2, 1/3, 3/1 ...  ojusterad split
  kontinuitet     faktor > 3 utan återgång     nivåskifte/instrumentbyte
  platshållare    close >= 999999              arkivets platshållarvärde

DIAGNOSTISKT. Ingen fryst fil ändras, inget prislager skrivs om. Utfallet är
underlag för beslut om produktionslagret behöver byggas om.

Kör: /opt/momentum/venv/bin/python tools/rundresetest_produktionslagret.py
"""
from __future__ import annotations
import gzip, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
OUT = V2 / "research_k/rundresetest_produktionslagret_results.json"

BROTT_RET = 0.40
RUNDRESA_GRANS = 0.10
DIVERGENS_GRANS = 0.15
SPLIT_TOLERANS = 0.01
KONTINUITET_FAKTOR = 3.0
VANLIGA = [2, 3, 4, 5, 6, 8, 10, 20, 100]


def las(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def narmaste_split(kvot):
    kand = [(v, abs(kvot - v) / v) for q in VANLIGA for v in (float(q), 1.0 / q)]
    return min(kand, key=lambda x: x[1])


def main():
    priser = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    print(f"Produktionslagret: {len(priser)} serier, "
          f"{sum(len(v) for v in priser.values())} rader")

    # råa rader (close/volym) ur arkivet för divergens- och volymbevis
    ra = {}
    for kat in ("active", "delisted"):
        for kod in list(priser):
            if kod in ra:
                continue
            rows = las(EOD / kat / "eod" / f"{kod}.json.gz")
            if rows:
                ra[kod] = {r["date"]: r for r in rows}
    print(f"  råserier återfunna i arkivet: {len(ra)} av {len(priser)}")

    # marknadsbredd
    bredd_rak = defaultdict(lambda: [0, 0])
    for kod, serie in priser.items():
        for i in range(1, len(serie)):
            a0, a1 = serie[i - 1]["adj"], serie[i]["adj"]
            if a0 <= 0:
                continue
            b = bredd_rak[serie[i]["d"]]
            b[1] += 1
            if abs(a1 / a0 - 1.0) > 0.10:
                b[0] += 1
    bredd = {d: (v[0] / v[1] if v[1] else 0.0) for d, v in bredd_rak.items()}

    fynd, statistik = [], Counter()
    platshallare = []
    for kod, serie in sorted(priser.items()):
        raw = ra.get(kod, {})
        # platshållarkontroll direkt mot arkivet
        for r in serie:
            c = raw.get(r["d"], {}).get("close")
            if c is not None and float(c) >= 999_999:
                platshallare.append({"kod": kod, "datum": r["d"], "close": c, "adj": r["adj"]})
        for i in range(1, len(serie)):
            a0, a1 = serie[i - 1]["adj"], serie[i]["adj"]
            if a0 <= 0:
                continue
            ret = a1 / a0 - 1.0
            if abs(ret) < BROTT_RET:
                continue
            dt = serie[i]["d"]
            nasta = (serie[i + 1]["adj"] / a1 - 1.0) if i + 1 < len(serie) and a1 > 0 else None
            rundresa = (1.0 + ret) * (1.0 + nasta) if nasta is not None else None
            c0 = raw.get(serie[i - 1]["d"], {}).get("close")
            c1 = raw.get(dt, {}).get("close")
            ret_close = (c1 / c0 - 1.0) if (c0 and c1 and c0 > 0) else None
            divergens = (ret - ret_close) if ret_close is not None else None
            kvot = a1 / a0
            nara, avvik = narmaste_split(kvot)
            vol = raw.get(dt, {}).get("volume")
            hist = [raw.get(serie[j]["d"], {}).get("volume") for j in range(max(0, i - 20), i)]
            hist = [h for h in hist if h]
            volkvot = (vol / float(np.median(hist))) if (vol and hist and np.median(hist) > 0) else None
            b = bredd.get(dt, 0.0)

            if rundresa is not None and abs(rundresa - 1.0) < RUNDRESA_GRANS:
                kl = "ENDAGSSPIK_DATAFEL"
            elif divergens is not None and abs(divergens) > DIVERGENS_GRANS:
                kl = "JUSTERINGSFEL"
            elif avvik < SPLIT_TOLERANS and (volkvot is None or volkvot < 3.0) \
                    and (nasta is None or abs(nasta) < 0.25):
                kl = "OJUSTERAD_SPLIT"
            elif kvot > KONTINUITET_FAKTOR or kvot < 1.0 / KONTINUITET_FAKTOR:
                kl = "KONTINUITETSBROTT"
            elif b > 0.20:
                kl = "MARKNADSHANDELSE"
            else:
                kl = "REELL_ROERELSE"
            statistik[kl] += 1
            if kl != "REELL_ROERELSE":
                fynd.append({"kod": kod, "datum": dt, "klassificering": kl,
                             "ret_adjusted": round(ret, 4),
                             "ret_close": round(ret_close, 4) if ret_close is not None else None,
                             "divergens": round(divergens, 4) if divergens is not None else None,
                             "kvot": round(kvot, 5), "narmaste_splitkvot": nara,
                             "nasta_dags_avkastning": round(nasta, 4) if nasta is not None else None,
                             "rundresa": round(rundresa, 4) if rundresa is not None else None,
                             "volym_mot_20d_median": round(volkvot, 2) if volkvot else None,
                             "marknadsbredd": round(b, 3)})

    ut = {"version": "RUNDRESETEST_PRODUKTIONSLAGRET_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "status": "DIAGNOSTISKT — ingen fryst fil ändrad, inget prislager omskrivet",
          "lager": "validated/prices/prices_validated.json",
          "n_serier": len(priser), "n_rader": sum(len(v) for v in priser.values()),
          "raserier_aterfunna": len(ra),
          "trosklar": {"brott_ret": BROTT_RET, "rundresa": RUNDRESA_GRANS,
                       "divergens": DIVERGENS_GRANS, "kontinuitet": KONTINUITET_FAKTOR},
          "utfall": dict(statistik),
          "platshallarrader": platshallare,
          "fynd": fynd}
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))

    print(f"\nBROTT > {BROTT_RET:.0%} PÅ EN DAG: {sum(statistik.values())}")
    for k, v in statistik.most_common():
        print(f"  {k:<22} {v:>4}")
    print(f"\nPlatshållarrader (close >= 999999) i produktionslagret: {len(platshallare)}")
    misst = [f for f in fynd if f["klassificering"] in
             ("ENDAGSSPIK_DATAFEL", "JUSTERINGSFEL", "KONTINUITETSBROTT", "OJUSTERAD_SPLIT")]
    print(f"\nMISSTÄNKTA DATAFEL I PRODUKTIONSLAGRET: {len(misst)}")
    for f in sorted(misst, key=lambda x: -abs(x["ret_adjusted"]))[:15]:
        print(f"  {f['datum']} {f['kod']:<11} {f['klassificering']:<20} "
              f"{f['ret_adjusted']:+8.1%} nästa {f['nasta_dags_avkastning']} "
              f"rundresa {f['rundresa']} div {f['divergens']}")
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
