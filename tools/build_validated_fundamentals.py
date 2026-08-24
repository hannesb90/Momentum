"""Spar B: VALIDATED-lager for fundamentaldata + frysning.

Bygger pa TRACK A ENBART (V2 RAW, hashverifierad, 358 instrument). Track B
bidrar noll unik data till detta universum: dess enda rad (Besqab, insId 2197)
finns redan i Track A via live-API - se docs/FUNDAMENTAL_QA.md. Varje rad
taggas ANDA med quality_class="A" av det skalet, men faltet finns kvar sa
en framtida panel med annan instrumentmangd (dar B FAKTISKT tillfor nagot)
kan filtrera pa det.

PIT-regler (tillampade, ingen gissning):
  - rader utan report_Date UTESLUTS (kan inte PIT-dateras)
  - rader med report_Date < 1990-01-01 (Excel-epok 1899-12-30 m.fl.) UTESLUTS
  - rader dar report_Date < report_End_Date (look-ahead/felregistrering) UTESLUTS
  - currency_Ratio anvands for att konvertera MCURR/CURR-falt till SEK
  - EUR-rader med currency_Ratio exakt 1.0 UTESLUTS (bevisligen fel, EUR/SEK≈11)
  - NOK-rader med currency_Ratio exakt 1.0 BEHALLS men FLAGGAS
    (NOK/SEK har historiskt legat nara paritet - kan vara ratt, men ett
    konstant exakt 1.0 over flera ar racker inte som bevis pa akta konvertering)

Faltklassificering, se docs/FUNDAMENTAL_QA.md for full motivering:
  UTESLUTNA: stock_Price_Average/High/Low, net_sales (metadata-alias, se nedan)
"""
from __future__ import annotations

import glob
import hashlib
import json
from datetime import date
from pathlib import Path

RAW = Path("/home/hannesb/momentum_v2/raw/borsdata")
V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "validated/fundamentals"
MANIFEST = V2 / "validated/manifest_sparB.json"

MIN_PLAUSIBEL = date(1990, 1, 1)

UTESLUTNA_FALT = {
    "stock_Price_Average", "stock_Price_High", "stock_Price_Low",   # se §klassificering: redundant med spår A:s VALIDATED-priser, sämre verifierade
    "net_Sales",                                                    # 78,7% identisk med revenues; hålls kvar för spårbarhet men markeras alias
}
GODKANDA = [
    "revenues", "gross_Income", "operating_Income", "profit_Before_Tax",
    "profit_To_Equity_Holders", "total_Assets", "total_Equity",
    "total_Liabilities_And_Equity", "current_Assets", "current_Liabilities",
    "non_Current_Assets", "non_Current_Liabilities", "cash_And_Equivalents",
    "net_Debt", "tangible_Assets", "intangible_Assets", "financial_Assets",
    "cash_Flow_From_Operating_Activities", "cash_Flow_From_Investing_Activities",
    "cash_Flow_From_Financing_Activities", "cash_Flow_For_The_Year", "free_Cash_Flow",
    "number_Of_Shares",
]
KRAVER_ATGARD = ["earnings_Per_Share", "dividend"]


def senaste_per_slug(mönster: str) -> dict:
    ut = {}
    for f in sorted(glob.glob(str(RAW / mönster))):
        ut[Path(f).name.rsplit("__", 1)[0]] = f
    return ut


def main() -> None:  # noqa: C901
    OUT.mkdir(parents=True, exist_ok=True)
    match = json.loads((RAW / "_matchning.json").read_text(encoding="utf-8"))
    insid2post = {m["insid"]: m for m in match["matchade"]}

    year_files = senaste_per_slug("year/*.json")
    kallhashar = {}
    alla = []
    for slug, f in year_files.items():
        insid = int(slug.split("/")[-1].split("_")[0])
        kallhashar[insid] = hashlib.sha256(Path(f).read_bytes()).hexdigest()
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for r in (d.get("reportsYear") or []):
            r["_insid"] = insid
            r["_kod"] = insid2post.get(insid, {}).get("kod")
            alla.append(r)

    n_in = len(alla)
    stat = {"in": n_in}
    kept = []
    for r in alla:
        rd, red = r.get("report_Date"), r.get("report_End_Date")
        if not rd:
            stat["saknar_datum"] = stat.get("saknar_datum", 0) + 1
            continue
        rdd = date.fromisoformat(rd[:10])
        if rdd < MIN_PLAUSIBEL:
            stat["epok"] = stat.get("epok", 0) + 1
            continue
        if red:
            redd = date.fromisoformat(red[:10])
            if rdd < redd:
                stat["look_ahead"] = stat.get("look_ahead", 0) + 1
                continue
        cur, ratio = r.get("currency"), r.get("currency_Ratio")
        if cur and cur != "SEK" and ratio == 1.0 and cur in ("EUR", "USD", "PLN", "ISK"):
            stat["valuta_ratio_orimlig"] = stat.get("valuta_ratio_orimlig", 0) + 1
            continue
        rad = {"insid": r["_insid"], "kod": r["_kod"], "year": r.get("year"),
              "report_start_date": (r.get("report_Start_Date") or "")[:10],
              "report_end_date": red[:10] if red else None,
              "report_date": rd[:10], "currency": cur, "currency_ratio": ratio,
              "quality_class": "A",
              "ratio_flagg": (cur == "NOK" and ratio == 1.0)}
        for kol in GODKANDA + KRAVER_ATGARD:
            v = r.get(kol)
            if v is not None and ratio:
                v = v * ratio if kol not in ("number_Of_Shares",) else v
            rad[kol] = v
        kept.append(rad)
    stat["ut"] = len(kept)

    (OUT / "fundamentals_year_validated.json").write_text(
        json.dumps(kept, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kanon = json.dumps(sorted(kept, key=lambda x: (x["insid"], x["year"])),
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    dataset_hash = hashlib.sha256(kanon.encode("utf-8")).hexdigest()

    man = {
        "dataset": "dataset_v1.0 / spår B (fundamenta, årsdata)",
        "version": "1.0.0-rc1",
        "fryst_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "dataset_sha256": dataset_hash,
        "track_A": {"n_instrument": len(kallhashar), "n_rader_raw": n_in,
                    "n_rader_validated": len(kept), "kallfil_sha256": kallhashar},
        "track_B": {"status": "TOM I PRAKTIK",
                    "forklaring": "Enda B-raden (Besqab, insId 2197) finns redan i Track A "
                                 "via live-API. Track B tillför noll unika instrument till "
                                 "detta universum. Se docs/FUNDAMENTAL_QA.md.",
                    "n_avnoterade_facit": 68, "n_avnoterade_med_data_nagonstans": 1,
                    "n_avnoterade_helt_utan_data": 67},
        "pit_regler": stat,
        "faltklassificering": {"godkanda": GODKANDA, "kraver_atgard": KRAVER_ATGARD,
                               "uteslutna": sorted(UTESLUTNA_FALT)},
        "beroende_dokument": ["docs/FUNDAMENTAL_QA.md", "docs/PRIS_QA_KLASSIFICERING.md"],
        "kanda_begransningar": [
            "Endast ÅRSDATA (period=5) validerad här. Kvartals-/R12-rådata är hämtad "
            "(raw/borsdata/quarter,r12) men INTE granskad i denna omgång.",
            "Fundamenta för avnoterade bolag saknas nästan helt (67/68) — modellen kan "
            "inte tränas med fundamentafeatures för döda bolag i detta universum. "
            "Priser (spår A) är survivorship-säkra; fundamenta är det INTE.",
        ],
        "status": "spår B (årsfundamenta) fryst; dataset_v1.0 kräver combinerad frysning "
                 "med spår A samt beslut om kvartalsdata innan hela datasetet är klart",
    }
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"in={n_in} -> validated={len(kept)}")
    print(json.dumps(stat, indent=2, ensure_ascii=False))
    print(f"dataset_sha256 {dataset_hash}")
    print(f"artefakter: {OUT}/fundamentals_year_validated.json\n            {MANIFEST}")


if __name__ == "__main__":
    main()
