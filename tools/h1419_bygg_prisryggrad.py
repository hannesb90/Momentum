"""H1419 STEG 1b — PRISRYGGRAD OCH QA-LAGER FÖR 2012-07 → 2019-12

Bygger prislagret för den historiska robusthetskörningen 2014-2019. Fönstret
startar 2012-07 så att 18-månadersmomentum är komplett redan vid första
beslutet 2014-01.

Följer samma regler som validated-lagret för 2020+ (docs/PRIS_QA_KLASSIFICERING.md §3):
  R1  endast adjusted_close används för avkastning; close bevaras och flaggas
  R2  serier trunkeras vid sista giltiga handelsdag (avnotering)
  R3  ogiltiga värden UTESLUTS, aldrig interpoleras (golv 0.0001, platshållare 1e6)
  R4  justeringsproblem: ±10 handelsdagar kring brottet utesluts
  R5  annan verifierad orsak: handelsveckan utesluts, dokumenterad per fall
  R6  ingen clipping, ingen winsorisering, ingen imputering

VIKTIGT: R4 och R5 tillämpas INTE automatiskt. De kräver verifierad orsak per
fall. Skriptet producerar en KANDIDATLISTA som måste klassificeras innan
lagret får användas till ett test. Ryggraden skrivs som PRELIMINÄR.

Utdata:
  validated/prices_h1419/prices_h1419_preliminar.json    kod -> [{d, adj, c}]
  validated/prices_h1419/manifest_h1419.json             sha256 per källfil
  research_k/h1419_pris_qa_kandidater.json               brott att klassificera

Kör: /opt/momentum/venv/bin/python tools/h1419_bygg_prisryggrad.py
"""
from __future__ import annotations
import gzip, hashlib, json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
OUTDIR = V2 / "validated/prices_h1419"
QAOUT = V2 / "research_k/h1419_pris_qa_kandidater.json"

LOOKBACK_START = "2012-07-01"
FONSTER_START, FONSTER_SLUT = "2014-01-01", "2019-12-31"
FLOOR, PLACEHOLDER = 0.0001, 1_000_000.0

# QA-trösklar
BROTT_RET = 0.40           # enskild dagsrörelse i adjusted_close
SPLIT_FONSTER_DAGAR = 3    # split får förklara ett brott inom denna radie
STALE_MIN = 10             # identiska stängningar i rad
VANLIGA_SPLITKVOTER = [2, 3, 4, 5, 6, 8, 10, 20, 100]


def las(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def d(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def naramsta_splitkvot(kvot: float):
    """Returnerar (kvot, avvikelse) för den vanliga splitkvot som ligger närmast."""
    kandidater = []
    for q in VANLIGA_SPLITKVOTER:
        for v in (float(q), 1.0 / q):
            kandidater.append((v, abs(kvot - v) / v))
    return min(kandidater, key=lambda x: x[1])


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)

    kataloger = {}
    for kat in ("active", "delisted"):
        rows = json.loads((EOD / f"{kat}_catalogue.json").read_text())
        rows = rows if isinstance(rows, list) else rows.get("instruments", rows.get("rows", []))
        for r in rows:
            kataloger[(kat, r["Code"])] = r

    priser, manifest, qa, statistik = {}, [], [], Counter()
    for (kat, kod), meta in sorted(kataloger.items()):
        if (meta.get("Type") or "") != "Common Stock":
            statistik["ej_common_stock"] += 1
            continue
        p_eod = EOD / kat / "eod" / f"{kod}.json.gz"
        rows = las(p_eod)
        if not rows:
            statistik["tom_eller_saknad_fil"] += 1
            continue
        # överlappar fönstret?
        if rows[-1]["date"] < FONSTER_START or rows[0]["date"] > FONSTER_SLUT:
            statistik["utanfor_fonstret"] += 1
            continue

        splits = las(EOD / kat / "splits" / f"{kod}.json.gz")
        splitdatum = set()
        for s in splits:
            dt = s.get("date") or s.get("Date")
            if dt:
                splitdatum.add(d(str(dt)[:10]))

        # ---- R3: uteslut ogiltiga värden, aldrig interpolera ----
        rena = []
        for r in rows:
            dt = r["date"]
            if dt < LOOKBACK_START or dt > FONSTER_SLUT:
                continue
            a, c = r.get("adjusted_close"), r.get("close")
            if a is None or not (FLOOR < float(a) < PLACEHOLDER):
                statistik["r3_uteslutna_rader"] += 1
                continue
            # Platshållaren i det historiska arkivet är 999999.9999, inte exakt
            # 1e6. Både close och den justerade motsvarigheten måste bort — en
            # kvarlämnad platshållarrad skapar två falska 40-procentsbrott.
            if c is not None and float(c) >= PLACEHOLDER - 1.0:
                statistik["r3_platshallare_uteslutna"] += 1
                continue
            rena.append({"d": dt, "adj": float(a), "c": float(c) if c is not None else None})
        if len(rena) < 60:
            statistik["for_kort_efter_r3"] += 1
            continue

        # ---- QA: brottdetektion (klassificeras INTE här) ----
        brott = []
        for i in range(1, len(rena)):
            a0, a1 = rena[i - 1]["adj"], rena[i]["adj"]
            if a0 <= 0:
                continue
            ret = a1 / a0 - 1.0
            if abs(ret) < BROTT_RET:
                continue
            dt = d(rena[i]["d"])
            forklarad = any(abs((dt - sd).days) <= SPLIT_FONSTER_DAGAR for sd in splitdatum)
            kvot = a1 / a0
            nara, avvik = naramsta_splitkvot(kvot)
            brott.append({
                "datum": rena[i]["d"], "avkastning": round(ret, 4),
                "kvot": round(kvot, 5),
                "split_i_arkivet_inom_3_dagar": forklarad,
                "narmaste_splitkvot": nara, "relativ_avvikelse": round(avvik, 4),
                "misstankt_ojusterad_split": (not forklarad) and avvik < 0.03,
                "klassificering": "OKLASSIFICERAD",
            })

        # ---- QA: justeringsfaktorns monotoni (close/adj ska aldrig växa bakåt) ----
        faktorbrott = []
        fakt = [(r["d"], r["c"] / r["adj"]) for r in rena if r["c"] and r["adj"] > 0]
        for i in range(1, len(fakt)):
            if fakt[i][1] > fakt[i - 1][1] * 1.02:      # faktorn ska falla mot 1 framåt i tiden
                faktorbrott.append({"datum": fakt[i][0],
                                    "faktor_fore": round(fakt[i - 1][1], 4),
                                    "faktor_efter": round(fakt[i][1], 4)})

        # ---- QA: stillastående serier ----
        stale, langd, start = [], 1, 0
        for i in range(1, len(rena)):
            if rena[i]["adj"] == rena[i - 1]["adj"]:
                langd += 1
            else:
                if langd >= STALE_MIN:
                    stale.append({"fran": rena[start]["d"], "till": rena[i - 1]["d"], "dagar": langd})
                langd, start = 1, i
        if langd >= STALE_MIN:
            stale.append({"fran": rena[start]["d"], "till": rena[-1]["d"], "dagar": langd})

        priser[kod] = rena
        manifest.append({"katalog": kat, "kod": kod, "namn": meta.get("Name"),
                         "isin": meta.get("Isin") or None,
                         "fil": str(p_eod.relative_to(EOD)), "sha256": sha(p_eod),
                         "rader_efter_r3": len(rena),
                         "serie_start": rena[0]["d"], "serie_slut": rena[-1]["d"],
                         "tacker_hela_fonstret": rena[0]["d"] <= "2012-07-15" and rena[-1]["d"] >= "2019-12-15"})
        if brott or faktorbrott or stale:
            qa.append({"kod": kod, "katalog": kat, "namn": meta.get("Name"),
                       "prisbrott": brott, "justeringsfaktor_brott": faktorbrott[:20],
                       "stillastaende": stale})
        statistik["serier_i_lagret"] += 1

    # ---- panelgitter ----
    paneler, cur = [], d(FONSTER_START)
    while cur <= d(FONSTER_SLUT):
        paneler.append(cur.isoformat())
        cur += timedelta(days=28)

    n_brott = sum(len(q["prisbrott"]) for q in qa)
    n_misstankt = sum(1 for q in qa for b in q["prisbrott"] if b["misstankt_ojusterad_split"])
    n_oforklarat = sum(1 for q in qa for b in q["prisbrott"] if not b["split_i_arkivet_inom_3_dagar"])

    (OUTDIR / "prices_h1419_preliminar.json").write_text(json.dumps(priser, ensure_ascii=False))
    (OUTDIR / "manifest_h1419.json").write_text(json.dumps({
        "version": "H1419_PRISRYGGRAD_V1_PRELIMINAR",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "PRELIMINÄR — R4/R5 ej tillämpade, QA-kandidater oklassificerade",
        "fonster": {"lookback_fran": LOOKBACK_START, "start": FONSTER_START, "slut": FONSTER_SLUT},
        "regler": "docs/PRIS_QA_KLASSIFICERING.md §3 R1-R6",
        "kalla": str(EOD), "n_serier": len(priser),
        "n_paneler_i_gittret": len(paneler),
        "statistik": dict(statistik), "filer": manifest,
    }, ensure_ascii=False, indent=1))
    QAOUT.write_text(json.dumps({
        "version": "H1419_PRIS_QA_KANDIDATER_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "OKLASSIFICERAD — varje brott kräver verifierad orsak innan R4/R5 tillämpas",
        "trosklar": {"brott_dagsavkastning": BROTT_RET, "split_fonster_dagar": SPLIT_FONSTER_DAGAR,
                     "stale_min_dagar": STALE_MIN},
        "sammanfattning": {"serier_med_anmarkning": len(qa), "prisbrott_totalt": n_brott,
                           "darav_utan_split_i_arkivet": n_oforklarat,
                           "darav_misstankt_ojusterad_split": n_misstankt},
        "serier": qa,
    }, ensure_ascii=False, indent=1))

    print("H1419 PRISRYGGRAD — PRELIMINÄR")
    print(f"  serier i lagret:            {len(priser)}")
    print(f"  varav täcker hela fönstret: {sum(1 for f in manifest if f['tacker_hela_fonstret'])}")
    print(f"  panelgitter 2014-2019:      {len(paneler)} paneler à 28 dagar "
          f"({len(paneler)//2} ombalanseringar)")
    print(f"\n  bortsorterat: {dict(statistik)}")
    print(f"\nQA-KANDIDATER (oklassificerade):")
    print(f"  serier med anmärkning:          {len(qa)}")
    print(f"  prisbrott > {BROTT_RET:.0%} på en dag:      {n_brott}")
    print(f"    utan split i arkivet:         {n_oforklarat}")
    print(f"    misstänkt ojusterad split:    {n_misstankt}")
    print(f"  serier med justeringsfaktorbrott: {sum(1 for q in qa if q['justeringsfaktor_brott'])}")
    print(f"  serier med stillastående block:   {sum(1 for q in qa if q['stillastaende'])}")
    print(f"\nSkrivet:\n  {OUTDIR/'prices_h1419_preliminar.json'}\n  {OUTDIR/'manifest_h1419.json'}\n  {QAOUT}")


if __name__ == "__main__":
    main()
