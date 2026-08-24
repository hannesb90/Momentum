"""PRICE_ADJUSTMENT_REPAIR_V2 — ersatter RATTELSE_JUSTERINGSBROTT_V1.

R4 (+/-N dagar) ar falsifierad for permanenta faktorregimskiften: den kan per
konstruktion inte ta bort en permanent andring av justeringsfaktorn, bara flytta
den till spannets kant.

Denna version tillater tre atgarder, var och en med explicit evidenskrav:

  NO_ACTION     faktorbytet ar en verifierad corporate action vars teoretiska
                multiplikator stammer. SAS ar positiv kontroll (fel 0,00 %).
  RESCALE       faktorregimen ar bevisat spurios: den korrekta multiplikatorn ar
                1,0. Historiken FORE brottet skalas om sa att faktorn blir
                kontinuerlig. Inget varde efter brottet ror sig.
  SERIES_SPLIT  en verklig handelse intraffade men korrekt multiplikator kan inte
                faststallas. Serien delas; langsta sammanhangande segment behalls.
                Ingen gissad TERP.

BLOCK anvands for allt dar evidensen inte racker. Ingen automatisk korrigering.

Las: validated/prices/prices_validated.json (RORS EJ)
Skriv: validated/prices_adjustment_repair_v2/
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
SRC = V2 / "validated/prices/prices_validated.json"
OUT = V2 / "validated/prices_adjustment_repair_v2"

# ---- evidensbaserad reparationsplan -------------------------------------
# RESCALE: multiplicera adj for datum < brott med ratio. Evidens kravs per post.
RESCALE = {
    "PNDX-B": [{"break": "2020-04-06", "ratio": 1.82709,
                "evidence": "Borsdata ex-datum 2020-04-06 belopp 0,0 SEK; faktorkedjan efter "
                            "brottet stammer exakt (1,099764 mot 1,099764)"}],
    "SSAB-A": [{"break": "2020-04-02", "ratio": 1.491082,
                "evidence": "Borsdata ex-datum 2020-04-02 belopp 0,0 SEK; kedja efter brottet "
                            "1,418416 mot 1,418419 (2 ppm)"}],
    "VBG-B":  [{"break": "2020-04-29", "ratio": 1.534062,
                "evidence": "Borsdata ex-datum 2020-04-29 belopp 0,0 SEK; kedja efter brottet "
                            "1,172234 mot 1,172233 (1 ppm)"}],
    "OEM-B":  [{"break": "2020-04-23", "ratio": 1.281117,
                "evidence": "Borsdata ex-datum 2020-04-23 belopp 0,0 SEK; persistens 251 dagar"}],
    "SAAB-B": [{"break": "2020-04-02", "ratio": 1.112439,
                "evidence": "Borsdata ex-datum 2020-04-02 belopp 0,0 SEK; persistens 257 dagar"}],
    "PROF-B": [{"break": "2020-04-22", "ratio": 1.081968,
                "evidence": "Borsdata ex-datum 2020-04-22 belopp 0,0 SEK; persistens 508 dagar"}],
    # tva steg: senast forst, sa att tidigare steg ackumuleras korrekt
    "BEIJ-B": [{"break": "2020-10-02", "ratio": 1.234378,
                "evidence": "struken andra delutdelning; ingen Borsdata-post; den FAKTISKT betalda "
                            "utdelningen 1,75 SEK har sin EGEN korrekta justering 2020-06-26 "
                            "(ratio 1,006263, EXACTLY_RECONCILED)"},
               {"break": "2020-04-17", "ratio": 1.365907,
                "evidence": "forsta delutdelningen; samma bevis — 1,75 SEK ar redan korrekt "
                            "justerad 2020-06-26, sa denna justering ar en dubbelrakning"}],
}
SERIES_SPLIT = {
    "BETS-B": {"break": "2022-05-13",
               "evidence": "Skatteverket: split+inlosen S 2:1, inlosen 1,97 kr, ex 2022-05-18. "
                           "Teoretisk multiplikator 1,031315 mot observerad 1,413981 (-27,1 %). "
                           "Brottdatumet ligger 5 dagar fore SKV:s ex-datum."},
    "ATORX":  {"break": "2025-01-24",
               "evidence": "Skatteverket: N 37 unit:10, kurs 0,1 kr. TERP tvetydig — unitstrukturen "
                           "innehaller TO12 och TO13 vars varde inte ingar i formeln. "
                           "Teoretisk 2,899047 mot observerad 11,825481."},
    "QLINEA": {"break": "2025-01-13",
               "evidence": "Skatteverket: N 77 unit:4, kurs 0,10 kr. Samma unitproblematik. "
                           "Teoretisk 3,623321 mot observerad 7,067685."},
}
NO_ACTION = {
    "SAS": {"break": "2020-09-29",
            "evidence": "Nyemission 9:1 a 1,16 SEK. TERP = (6,12 + 9x1,16)/10 = 1,656000, exakt "
                        "lika med adjusted_close dagen fore. Teoretisk multiplikator 3,695652 mot "
                        "observerad 3,695652 — avstamningsfel 0,00 %. Justeringen ar KORREKT."},
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src_sha = hashlib.sha256(SRC.read_bytes()).hexdigest()
    P = json.loads(SRC.read_text())
    fore_rader = sum(len(v) for v in P.values())
    logg = []

    # ---- RESCALE
    for kod, steps in RESCALE.items():
        if kod not in P:
            logg.append({"kod": kod, "atgard": "RESCALE", "status": "INSTRUMENT_SAKNAS"})
            continue
        for st in steps:
            n = 0
            for r in P[kod]:
                if r["d"] < st["break"] and r.get("adj"):
                    gammal = r["adj"]
                    r["adj"] = round(gammal * st["ratio"], 6)
                    n += 1
                    if n <= 3 or n % 200 == 0:
                        logg.append({"kod": kod, "datum": r["d"], "atgard": "RESCALE",
                                     "original_value": gammal, "new_value": r["adj"],
                                     "ratio": st["ratio"], "break": st["break"],
                                     "root_cause_class": "SPURIOUS_ADJUSTMENT_FACTOR",
                                     "evidence": st["evidence"]})
            logg.append({"kod": kod, "atgard": "RESCALE_SUMMARY", "break": st["break"],
                         "ratio": st["ratio"], "rader_omskalade": n,
                         "root_cause_class": "SPURIOUS_ADJUSTMENT_FACTOR",
                         "evidence": st["evidence"]})

    # ---- SERIES_SPLIT: behall langsta sammanhangande segment (byggarens R8-konvention)
    for kod, sp in SERIES_SPLIT.items():
        if kod not in P:
            continue
        fore = [r for r in P[kod] if r["d"] < sp["break"]]
        efter = [r for r in P[kod] if r["d"] >= sp["break"]]
        behall, kastad = (fore, efter) if len(fore) >= len(efter) else (efter, fore)
        P[kod] = behall
        logg.append({"kod": kod, "atgard": "SERIES_SPLIT", "break": sp["break"],
                     "segment_fore": len(fore), "segment_efter": len(efter),
                     "behallet_segment": "FORE" if behall is fore else "EFTER",
                     "rader_borttagna": len(kastad),
                     "root_cause_class": "AMBIGUOUS_CORPORATE_ACTION",
                     "evidence": sp["evidence"]})

    for kod, na in NO_ACTION.items():
        logg.append({"kod": kod, "atgard": "NO_ACTION", "break": na["break"],
                     "root_cause_class": "VALID_CORPORATE_ACTION", "evidence": na["evidence"]})

    kanon = json.dumps(P, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dst = OUT / "prices_validated_adjustment_repair_v2.json"
    dst.write_text(kanon, encoding="utf-8")
    efter_rader = sum(len(v) for v in P.values())
    man = {"version": "PRICE_ADJUSTMENT_REPAIR_V2",
           "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "source": str(SRC.relative_to(V2)), "source_sha256": src_sha,
           "output": str(dst.relative_to(V2)),
           "output_sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
           "rader_fore": fore_rader, "rader_efter": efter_rader,
           "serier_fore": len(json.loads(SRC.read_text())), "serier_efter": len(P),
           "atgarder": {"RESCALE": len(RESCALE), "SERIES_SPLIT": len(SERIES_SPLIT),
                        "NO_ACTION": len(NO_ACTION)},
           "ersatter": "RATTELSE_JUSTERINGSBROTT_V1 (R4 +/-5 dagar, falsifierad)",
           "gamla_filer_ororda": True,
           "logg": logg}
    (OUT / "REPAIR_V2_MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    print(f"rader {fore_rader:,} -> {efter_rader:,}   serier {len(P)}")
    print(f"sha256 {man['output_sha256']}")
    print(f"skrivet: {dst}")


if __name__ == "__main__":
    main()
