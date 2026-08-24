"""Spar B: SLUTLIG frysning. Bygger VALIDATED for ar, kvartal OCH R12 med
identiska PIT-regler, och skriver det konsoliderade manifestet.

Nytt jamfort med den forsta (rc1) byggen av arsdata:
  - R9 (ny): rader dar report_Date ligger >180 dagar EFTER report_End_Date
    utesluts. Upptackt via Alligo AB:s kvartalsserie (sju rader med
    sekventiellt batch-tilldelade datum 2020-05-01..08 for perioder
    2017-2019 - inte genuina publiceringsdatum). Paverkar 16 arsrader,
    10 kvartalsrader, 2 R12-rader - smaskaligt men konsekvent tillampat
    pa alla tre kallor.
  - earnings_Per_Share och dividend GODKANDA (uppgraderade fran KRAVER
    ATGARD) efter splitverifiering, se docs/FUNDAMENTAL_QA.md steg 1.
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
MAX_EFTERSLAPNING = 180

UTESLUTNA_FALT = {"stock_Price_Average", "stock_Price_High", "stock_Price_Low", "net_Sales"}
GODKANDA = [
    "revenues", "gross_Income", "operating_Income", "profit_Before_Tax",
    "profit_To_Equity_Holders", "total_Assets", "total_Equity",
    "total_Liabilities_And_Equity", "current_Assets", "current_Liabilities",
    "non_Current_Assets", "non_Current_Liabilities", "cash_And_Equivalents",
    "net_Debt", "tangible_Assets", "intangible_Assets", "financial_Assets",
    "cash_Flow_From_Operating_Activities", "cash_Flow_From_Investing_Activities",
    "cash_Flow_From_Financing_Activities", "cash_Flow_For_The_Year", "free_Cash_Flow",
    "number_Of_Shares", "earnings_Per_Share", "dividend",
]


def senaste_per_slug(mönster: str) -> dict:
    ut = {}
    for f in sorted(glob.glob(str(RAW / mönster))):
        ut[Path(f).name.rsplit("__", 1)[0]] = f
    return ut


def bygg(mönster: str, nyckel: str, insid2post: dict) -> tuple:
    kallhashar, alla = {}, []
    for slug, f in senaste_per_slug(mönster).items():
        insid = int(slug.split("/")[-1].split("_")[0])
        kallhashar[insid] = hashlib.sha256(Path(f).read_bytes()).hexdigest()
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for r in (d.get(nyckel) or d.get("reports") or []):
            r["_insid"] = insid
            r["_kod"] = insid2post.get(insid, {}).get("kod")
            alla.append(r)

    stat = {"in": len(alla)}
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
            if (rdd - redd).days > MAX_EFTERSLAPNING:
                stat["orimlig_eftersläpning"] = stat.get("orimlig_eftersläpning", 0) + 1
                continue
        cur, ratio = r.get("currency"), r.get("currency_Ratio")
        if cur and cur != "SEK" and ratio == 1.0 and cur in ("EUR", "USD", "PLN", "ISK"):
            stat["valuta_ratio_orimlig"] = stat.get("valuta_ratio_orimlig", 0) + 1
            continue
        rad = {"insid": r["_insid"], "kod": r["_kod"], "year": r.get("year"),
              "period": r.get("period"),
              "report_start_date": (r.get("report_Start_Date") or "")[:10],
              "report_end_date": red[:10] if red else None,
              "report_date": rd[:10], "currency": cur, "currency_ratio": ratio,
              "quality_class": "A",
              "ratio_flagg": (cur == "NOK" and ratio == 1.0)}
        # BUGFIX (2026-08-08, se docs/SPAR_B_VALUTAFEL_REPARATION.md): Börsdatas
        # /reports-endpoint returnerar monetära råvärden REDAN SEK-konverterade
        # (verifierat mot externt kända siffror, t.ex. AstraZenecas 2023-omsättning
        # och mot Capex/kassaflödesidentiteter över samtliga icke-SEK-bolag).
        # Föregående kod multiplicerade råvärdet med currency_Ratio IGEN, vilket
        # dubbelkonverterade alla icke-SEK-bolag (~9-11x för EUR/USD). Ingen
        # konvertering ska göras här - råvärdet används oförändrat.
        for kol in GODKANDA:
            rad[kol] = r.get(kol)
        kept.append(rad)
    stat["ut"] = len(kept)
    return kept, stat, kallhashar


def main() -> None:  # noqa: C901
    OUT.mkdir(parents=True, exist_ok=True)
    match = json.loads((RAW / "_matchning.json").read_text(encoding="utf-8"))
    insid2post = {m["insid"]: m for m in match["matchade"]}

    tabeller = {}
    for namn, mönster, nyckel, fil in (
        ("ar", "year/*.json", "reportsYear", "fundamentals_year_validated.json"),
        ("kvartal", "quarter/*.json", "reports", "fundamentals_quarter_validated.json"),
        ("r12", "r12/*.json", "reports", "fundamentals_r12_validated.json"),
    ):
        kept, stat, kallhashar = bygg(mönster, nyckel, insid2post)
        (OUT / fil).write_text(json.dumps(kept, ensure_ascii=False, separators=(",", ":")),
                               encoding="utf-8")
        kanon = json.dumps(sorted(kept, key=lambda x: (x["insid"], x["year"], x.get("period") or 0)),
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        h = hashlib.sha256(kanon.encode("utf-8")).hexdigest()
        tabeller[namn] = {"fil": fil, "regelutfall": stat, "dataset_sha256": h,
                          "file_sha256": hashlib.sha256((OUT / fil).read_bytes()).hexdigest(),
                          "n_rader": len(kept),
                          "n_instrument": len(kallhashar), "kallfil_sha256": kallhashar}
        print(f"[{namn}] in={stat['in']} -> validated={stat['ut']} | sha256 {h[:24]}…")
        print(f"        {json.dumps({k: v for k, v in stat.items() if k not in ('in', 'ut')})}")

    kombinerad = json.dumps({k: v["dataset_sha256"] for k, v in tabeller.items()},
                            sort_keys=True).encode()
    man = {
        "dataset": "dataset_v1.0 / spår B (fundamenta, år+kvartal+R12)",
        "version": "1.0.0",
        "fryst_utc": "2026-08-08T00:00:00+00:00",
        "timestamp_policy": "deterministic dataset_v1.0 release timestamp; rebuild wall-clock time is not serialized",
        "kombinerad_sha256": hashlib.sha256(kombinerad).hexdigest(),
        "tabeller": tabeller,
        "track_A": {"beskrivning": "V2 RAW, live Börsdata 2026-08-08, verbatim+sha256",
                    "n_instrument": 358, "n_hämtningar": 1077, "n_fel": 0},
        "track_B": {"status": "TOM I PRAKTIK",
                    "forklaring": "Enda B-raden (Besqab, insId 2197) finns redan i Track A "
                                 "via live-API. Track B tillför noll unika instrument. "
                                 "67/68 avnoterade Nasdaq Stockholm-bolag 2020-2026 saknar "
                                 "all identifierbar fundamentadata, i alla källor.",
                    "n_avnoterade_facit": 68, "n_med_data_nagonstans": 1, "n_helt_utan_data": 67},
        "pit_regler": {
            "R1": "rad utan report_Date utesluts",
            "R2": "report_Date < 1990-01-01 (Excel-epok m.fl.) utesluts",
            "R3": "look-ahead: report_Date < report_End_Date utesluts",
            "R4": f"orimlig eftersläpning: report_Date > {MAX_EFTERSLAPNING} dagar efter "
                 "report_End_Date utesluts (Alligo AB-mönstret: sekventiellt "
                 "batch-tilldelade datum för historiska kvartal, inte genuina "
                 "publiceringsdatum)",
            "R5": "EUR/USD/PLN/ISK med currency_Ratio exakt 1.0 utesluts (bevisligen fel); "
                 "NOK med ratio 1.0 behålls men flaggas (ratio_flagg)",
        },
        "splitverifiering": {
            "metod": "EODHD-splitdata (spår A) korsat mot number_Of_Shares och mot "
                    "earnings_Per_Share=profit_To_Equity_Holders/number_Of_Shares",
            "eps_konsistens_generellt_under_10pct": 0.973,
            "eps_konsistens_kring_split_under_10pct": 0.899,
            "namngivna_hopp_kontrollerade": 10,
            "namngivna_hopp_med_matchande_split": 0,
            "slutsats": "Samtliga tio tidigare flaggade 'oförklarade' hopp (Humana, Holmen, "
                       "Carasent, Paradox Interactive för EPS; Hufvudstaden, Avarda Bank, "
                       "Volati, NAXS, NCC, New Wave Group för dividend) har NOLL matchande "
                       "EODHD-split och oförändrat aktieantal — bekräftat äkta ekonomiska "
                       "händelser (resultatvolatilitet respektive utdelningspolicyändringar), "
                       "inte datafel. EPS-konsistensen försämras bara marginellt kring "
                       "genuina split-år (89,9% mot 97,3% baseline), vilket visar att "
                       "aktieantal och EPS uppdateras samordnat vid splitar."},
        "faltklassificering_slutlig": {
            "godkanda": sorted(GODKANDA),
            "uteslutna": sorted(UTESLUTNA_FALT),
            "andringar_mot_forsta_klassificeringen": {
                "earnings_Per_Share": "KRÄVER ÅTGÄRD → GODKÄND (splitverifierad)",
                "dividend": "KRÄVER ÅTGÄRD → GODKÄND (splitverifierad, se dock kvarvarande "
                           "begränsning nedan)"},
        },
        "kvarvarande_begransningar": [
            "Fundamenta för avnoterade bolag saknas nästan helt (67/68). Priser (spår A) "
            "är survivorship-säkra; fundamenta är INTE det och kan inte göras det med "
            "tillgängliga källor. Varje modell som använder fundamentalfeatures tränar de "
            "facto på en överlevande delmängd för den informationen.",
            "Alligo AB:s report_Date-fält för perioder före ~2020 är dokumenterat "
            "opålitligt (R4 utesluter de värsta fallen, men subtilare fall kan finnas kvar "
            "för samma och liknande instrument med bolagshändelsehistorik).",
            "revenues vs net_Sales: definitionsskillnaden (21,3% av raderna skiljer sig) är "
            "inte utredd. net_Sales exkluderad, revenues använd.",
            "Splitverifieringen är gjord på en riktad kontroll (namngivna extremfall + "
            "aggregerad konsistens), inte en uttömmande rad-för-rad-genomgång av alla "
            "instrument-år med känd split.",
        ],
        "status": "SPÅR B FRYST (år, kvartal, R12 — samtliga tre tabeller)",
    }
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nkombinerad_sha256 {man['kombinerad_sha256']}")
    print(f"artefakt: {MANIFEST}")


if __name__ == "__main__":
    main()
