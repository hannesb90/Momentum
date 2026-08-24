"""H1419 STEG 1c — KLASSIFICERING AV PRISBROTT I KANDIDATUNIVERSUMET

R4 och R5 kräver verifierad orsak per fall. Den här klassificeringen bygger på
bevis som finns i datan själv, inte på extern bolagsinformation, och varje
beslut skrivs ut med sina bevis så att det kan granskas och överprövas.

Bevisen:
  divergens      ret(adjusted_close) − ret(close) samma dag. En ÄKTA
                 kursrörelse syns lika mycket i båda serierna. Divergens är
                 per definition ett justeringsfel.
  splitkvot      hur nära kvoten ligger en enkel splitkvot (1/2, 1/3, 3/1 ...).
                 En verklig rörelse landar inte på 0,500 med en promilles
                 marginal.
  reversal       nästa dags avkastning. Ett datafel studsar tillbaka, en
                 verklig rörelse gör det inte.
  volym          dagens volym mot 20-dagarsmedianen. Verkliga nyheter kommer
                 med volym, splitar gör det inte.
  bredd          andel av kandidatuniversumet som rörde sig >10 % samma dag.
                 Hög bredd = marknadshändelse, inte instrumentfel.

Regler (deterministiska, i prioritetsordning):
  R4_JUSTERINGSFEL      |divergens| > 0,15 — serierna säger olika saker
  R4_OJUSTERAD_SPLIT    kvoten inom 1 % av en enkel splitkvot, låg volym,
                        ingen reversal — split som aldrig justerades
  R5_MARKNADSHANDELSE   bredd > 20 % — hela marknaden rörde sig
  REELL_ROERELSE        allt annat med bevis bifogade, ingen uteslutning
  MANUELL_GRANSKNING    motstridiga bevis

R4 utesluter ±10 handelsdagar, R5 utesluter handelsveckan. REELL_ROERELSE
utesluter ingenting.

Kör: /opt/momentum/venv/bin/python tools/h1419_klassificera_brott.py
"""
from __future__ import annotations
import gzip, json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
INDIR = V2 / "validated/prices_h1419"
OUT = V2 / "research_k/h1419_brottklassificering_results.json"
SLUTLAGER = INDIR / "prices_h1419_klassificerad.json"

DIVERGENS_GRANS = 0.15
SPLIT_TOLERANS = 0.01
VOLYM_HOG = 3.0
REVERSAL_GRANS = 0.25
BREDD_GRANS = 0.20
RUNDRESA_GRANS = 0.10        # |(1+r_t)(1+r_t+1) - 1| under detta = endagsspik
KONTINUITET_FAKTOR = 3.0     # prisnivåbyte med denna faktor utan återgång = brott
R4_FONSTER, R5_FONSTER = 10, 5      # handelsdagar som utesluts
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
    kand = []
    for q in VANLIGA:
        for v in (float(q), 1.0 / q):
            kand.append((v, abs(kvot - v) / v))
    return min(kand, key=lambda x: x[1])


def main():
    man = json.loads((INDIR / "manifest_h1419.json").read_text())
    priser = json.loads((INDIR / "prices_h1419_preliminar.json").read_text())
    live = json.loads((V2 / "docs/probes/instruments_live.json").read_text())
    sthlm = {(i.get("isin") or "").upper() for i in live if i.get("marketId") in (1, 2, 3)}

    kandidat = {f["kod"]: f for f in man["filer"]
                if f["tacker_hela_fonstret"] and f["isin"] and f["isin"].upper() in sthlm}
    print(f"Kandidatuniversum: {len(kandidat)} serier")

    # rådata med volym och close
    rad = {}
    for kod, f in kandidat.items():
        rows = las(EOD / f["katalog"] / "eod" / f"{kod}.json.gz")
        rad[kod] = {r["date"]: r for r in rows}

    # marknadsbredd per datum inom kandidatuniversumet
    rorelse_per_datum = defaultdict(lambda: [0, 0])
    for kod, serie in priser.items():
        if kod not in kandidat:
            continue
        for i in range(1, len(serie)):
            a0, a1 = serie[i - 1]["adj"], serie[i]["adj"]
            if a0 <= 0:
                continue
            r = a1 / a0 - 1.0
            d0 = rorelse_per_datum[serie[i]["d"]]
            d0[1] += 1
            if abs(r) > 0.10:
                d0[0] += 1
    bredd = {d: (v[0] / v[1] if v[1] else 0.0) for d, v in rorelse_per_datum.items()}

    beslut, statistik = [], Counter()
    uteslut = defaultdict(set)          # kod -> set av datum som ska bort

    for kod in sorted(kandidat):
        serie = priser.get(kod, [])
        splits = las(EOD / kandidat[kod]["katalog"] / "splits" / f"{kod}.json.gz")
        splitdatum = {str(s.get("date") or s.get("Date"))[:10] for s in splits if s.get("date") or s.get("Date")}
        for i in range(1, len(serie)):
            a0, a1 = serie[i - 1]["adj"], serie[i]["adj"]
            if a0 <= 0:
                continue
            ret_adj = a1 / a0 - 1.0
            if abs(ret_adj) < 0.40:
                continue
            dt = serie[i]["d"]
            c0, c1 = serie[i - 1]["c"], serie[i]["c"]
            ret_close = (c1 / c0 - 1.0) if (c0 and c1 and c0 > 0) else None
            divergens = (ret_adj - ret_close) if ret_close is not None else None
            kvot = a1 / a0
            nara, avvik = narmaste_split(kvot)
            nasta = None
            if i + 1 < len(serie) and serie[i]["adj"] > 0:
                nasta = serie[i + 1]["adj"] / serie[i]["adj"] - 1.0
            r = rad[kod].get(dt, {})
            vol = r.get("volume")
            hist = [rad[kod].get(serie[j]["d"], {}).get("volume") for j in range(max(0, i - 20), i)]
            hist = [h for h in hist if h]
            volkvot = (vol / float(np.median(hist))) if (vol and hist and np.median(hist) > 0) else None
            b = bredd.get(dt, 0.0)

            # Rundresa: en spik som tas tillbaka nästa dag är en felaktig rad,
            # inte en kursrörelse. Testet är oberoende av divergens och fångar
            # därför den korruption som drabbar close och adjusted_close lika
            # (Investor A +1507 %, Hexagon +604 % och Electrolux +73 % samma
            # två datum, alla med nästan exakt återgång dagen efter).
            rundresa = (1.0 + ret_adj) * (1.0 + nasta) if nasta is not None else None

            # ---- regler i prioritetsordning ----
            if rundresa is not None and abs(rundresa - 1.0) < RUNDRESA_GRANS:
                kl, regel = "R4_ENDAGSSPIK", "R4"
            elif divergens is not None and abs(divergens) > DIVERGENS_GRANS:
                kl, regel = "R4_JUSTERINGSFEL", "R4"
            elif avvik < SPLIT_TOLERANS and (volkvot is None or volkvot < VOLYM_HOG) \
                    and (nasta is None or abs(nasta) < REVERSAL_GRANS):
                kl, regel = "R4_OJUSTERAD_SPLIT", "R4"
            elif (kvot > KONTINUITET_FAKTOR or kvot < 1.0 / KONTINUITET_FAKTOR):
                # Nivåskifte utan återgång och utan splitkvot. Ett Main
                # Market-bolag byter inte prisnivå med faktor 3 på en dag och
                # stannar där; serien har bytt instrument eller enhet.
                kl, regel = "R4_KONTINUITETSBROTT", "R4"
            elif b > BREDD_GRANS:
                kl, regel = "R5_MARKNADSHANDELSE", None
            elif avvik < SPLIT_TOLERANS:
                kl, regel = "MANUELL_GRANSKNING", None
            else:
                kl, regel = "REELL_ROERELSE", None

            statistik[kl] += 1
            if regel == "R4":
                lo, hi = max(0, i - R4_FONSTER), min(len(serie), i + R4_FONSTER + 1)
                uteslut[kod].update(serie[j]["d"] for j in range(lo, hi))
            beslut.append({
                "kod": kod, "namn": kandidat[kod]["namn"], "datum": dt,
                "klassificering": kl, "regel_tillampad": regel,
                "bevis": {
                    "ret_adjusted": round(ret_adj, 4),
                    "ret_close": round(ret_close, 4) if ret_close is not None else None,
                    "divergens": round(divergens, 4) if divergens is not None else None,
                    "kvot": round(kvot, 5), "narmaste_splitkvot": nara,
                    "relativ_avvikelse": round(avvik, 5),
                    "split_i_arkivet": dt in splitdatum,
                    "nasta_dags_avkastning": round(nasta, 4) if nasta is not None else None,
                    "rundresa": round(rundresa, 4) if rundresa is not None else None,
                    "volym_mot_20d_median": round(volkvot, 2) if volkvot else None,
                    "marknadsbredd_over_10pct": round(b, 3),
                },
            })

    # ---- andra passet: brott som redan ligger i ett uteslutet fönster ----
    for b in beslut:
        if b["regel_tillampad"] is None and b["datum"] in uteslut.get(b["kod"], set()):
            statistik[b["klassificering"]] -= 1
            b["klassificering"] = "TACKT_AV_ANNAT_BROTT"
            statistik["TACKT_AV_ANNAT_BROTT"] += 1

    # ---- tillämpa uteslutningarna ----
    slut, borttagna = {}, 0
    for kod, serie in priser.items():
        if kod not in kandidat:
            continue
        u = uteslut.get(kod, set())
        kvar = [r for r in serie if r["d"] not in u]
        borttagna += len(serie) - len(kvar)
        if len(kvar) >= 60:
            slut[kod] = [{"d": r["d"], "adj": r["adj"]} for r in kvar]
    SLUTLAGER.write_text(json.dumps(slut, ensure_ascii=False))

    ut = {
        "version": "H1419_BROTTKLASSIFICERING_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "KLASSIFICERAD PÅ DATABEVIS — ingen extern bolagsverifiering, "
                  "MANUELL_GRANSKNING kvarstår att avgöra",
        "kandidatuniversum": len(kandidat),
        "trosklar": {"divergens": DIVERGENS_GRANS, "splittolerans": SPLIT_TOLERANS,
                     "volym_hog": VOLYM_HOG, "reversal": REVERSAL_GRANS, "bredd": BREDD_GRANS,
                     "r4_fonster_handelsdagar": R4_FONSTER},
        "utfall": dict(statistik),
        "serier_i_slutlagret": len(slut),
        "uteslutna_rader": borttagna,
        "serier_med_uteslutning": len(uteslut),
        "beslut": beslut,
    }
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))

    print(f"\nKLASSIFICERADE BROTT: {len(beslut)}")
    for k, v in statistik.most_common():
        print(f"  {k:<24} {v:>4}")
    print(f"\nR4 tillämpad på {len(uteslut)} serier, {borttagna} rader uteslutna "
          f"({borttagna/sum(len(s) for s in priser.values() if s):.3%} av lagret)")
    print(f"Slutlager: {len(slut)} serier → {SLUTLAGER}")
    print(f"Beslut med bevis: {OUT}")

    man_gr = [b for b in beslut if b["klassificering"] == "MANUELL_GRANSKNING"]
    if man_gr:
        print(f"\nKVAR ATT AVGÖRA MANUELLT ({len(man_gr)}):")
        for b in man_gr[:15]:
            e = b["bevis"]
            print(f"  {b['datum']} {b['kod']:<10} {str(b['namn'])[:26]:<26} "
                  f"kvot {e['kvot']:.4f} (~{e['narmaste_splitkvot']}) "
                  f"vol×{e['volym_mot_20d_median']} nästa {e['nasta_dags_avkastning']}")


if __name__ == "__main__":
    main()
