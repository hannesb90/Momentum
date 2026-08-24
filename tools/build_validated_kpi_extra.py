"""Spar B: PIT-mappning + QA av Borsdata KPI-historik (EBITDA, Capex) och
transaktionsniva-atarkop, for hela Spar A-universumet.

RAW ror inte - denna byggare LASER ENDAST raw/borsdata/{kpi_history,buyback,
year,quarter}/, skriver till validated/fundamenta_extra/. Ingen
normalisering/PIT-logik i RAW-lagret.

PIT-mappning (verifierad empiriskt, se docs/SPAR_B_KPI_HISTORIK_SAMPLE.md):
  KPI-historikens (y,p) mappar 1:1 mot reports-endpointens (year,period):
    reportType=quarter  (y,p)      -> quarter-rapportens (year=y, period=p)
    reportType=r12      (y,p)      -> quarter-rapportens (year=y, period=p)
                                       (R12 slutar vid kvartal p ar y, blir
                                       kant nar DET kvartalet rapporteras)
    reportType=year, p=5 (KOMPLETT) -> ar-rapportens (year=y, period=5)
    reportType=year, p<5 (PARTIELLT)-> UTESLUTS ur PIT-panelen (representerar
                                       inte ett faktiskt bokslut, bara en
                                       alias for senaste R12 - anvand r12
                                       istallet for partiella ar)

Samma PIT-regler (R1-R4) som redan galler for reports-falten i
build_validated_fundamentals_final.py ateranvands for join-malets
report_Date-giltighet. currency/currency_Ratio bars med per datapunkt men
KONVERTERAS INTE automatiskt - se README_KPI_EXTRA-varning.
"""
from __future__ import annotations

import glob
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
RAW = V2 / "raw/borsdata"
OUT = V2 / "validated/fundamenta_extra"
MANIFEST = V2 / "validated/manifest_sparB_extra.json"

MIN_PLAUSIBEL = date(1990, 1, 1)
MAX_EFTERSLAPNING = 400


def senaste_per_insid(mönster: str) -> dict:
    ut = {}
    for p in sorted(glob.glob(str(RAW / mönster))):
        insid = Path(p).name.split("_")[0]
        ut[insid] = p  # sorterat filnamn -> senaste tidsstämpel vinner
    return ut


def las(p: str) -> dict:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def bygg_rapport_lookup() -> tuple:
    """(insid) -> {(year,period): {report_date, currency, currency_ratio, giltig}}"""
    lookup = {}
    kallhashar = {}
    for mönster, nyckel in (("year/*.json", "reportsYear"), ("quarter/*.json", "reports")):
        for insid, p in senaste_per_insid(mönster).items():
            d = las(p)
            kallhashar[f"{insid}:{mönster.split('/')[0]}"] = hashlib.sha256(
                Path(p).read_bytes()).hexdigest()
            for r in (d.get(nyckel) or []):
                y, per = r.get("year"), r.get("period")
                if y is None or per is None:
                    continue
                rd, red = r.get("report_Date"), r.get("report_End_Date")
                giltig, orsak = True, None
                if not rd:
                    giltig, orsak = False, "saknar_report_date"
                else:
                    rdd = date.fromisoformat(rd[:10])
                    if rdd < MIN_PLAUSIBEL:
                        giltig, orsak = False, "epok"
                    elif red:
                        redd = date.fromisoformat(red[:10])
                        if rdd < redd:
                            giltig, orsak = False, "look_ahead"
                        elif (rdd - redd).days > MAX_EFTERSLAPNING:
                            giltig, orsak = False, "orimlig_eftersläpning"
                cur, ratio = r.get("currency"), r.get("currency_Ratio")
                if giltig and cur and cur != "SEK" and ratio == 1.0 and cur in ("EUR", "USD", "PLN", "ISK"):
                    giltig, orsak = False, "valuta_ratio_orimlig"
                lookup.setdefault(insid, {})[(y, per)] = {
                    "report_date": rd[:10] if rd else None, "currency": cur,
                    "currency_ratio": ratio, "giltig": giltig, "orsak": orsak}
    return lookup, kallhashar


def main() -> None:  # noqa: C901
    OUT.mkdir(parents=True, exist_ok=True)
    univ = json.loads((V2 / "docs/probes/kpi_history_universum.json").read_text(encoding="utf-8"))
    insid2kod = {str(x["insId"]): x["kod"] for x in univ["instrument"]}

    rapport_lookup, kallhashar_rapport = bygg_rapport_lookup()

    # -------------------- KPI-historik (EBITDA, Capex) ------------------
    stat = Counter()
    rader = []
    kallhashar_kpi = {}
    # dedupe till SENASTE fil per (insid,kpi,reportType) - tva olika Spar
    # A-koder (EMPIR-B/SAFETY-B) delar rakenskapsinsId 147 (odokumenterat
    # kvarstaende Spar A-fel, se SPAR_B_KPI_HISTORIK_SAMPLE.md §9), vilket
    # annars ger tva separat tidsstampade RAW-filer med identiskt innehall
    # och dubbelraknade rader.
    senaste_kpi_fil: dict = {}
    for p in sorted(glob.glob(str(RAW / "kpi_history/*.json"))):
        namn = Path(p).stem.split("__")[0]
        senaste_kpi_fil[namn] = p  # sorterat filnamn => sista tidsstampeln vinner
    for namn, p in senaste_kpi_fil.items():
        insid, kpi_namn, rt = namn.split("_", 2)
        kallhashar_kpi[namn] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
        d = las(p)
        kod = insid2kod.get(insid)
        for v in (d.get("values") or []):
            y, per, val = v.get("y"), v.get("p"), v.get("v")
            stat["kpi_varden_in"] += 1
            if rt == "year" and per != 5:
                stat["uteslutet_partiellt_ar"] += 1
                continue
            join_period = per if rt in ("quarter", "r12") else 5
            meta = (rapport_lookup.get(insid) or {}).get((y, join_period))
            if meta is None:
                stat["ej_mappningsbar_period"] += 1
                continue
            if not meta["giltig"]:
                stat[f"pit_utesluten_{meta['orsak']}"] += 1
                continue
            ratio = meta["currency_ratio"]
            # Verifierat mot CFI-identiteten över samtliga valutagrupper:
            # KPI-historiken är lokal valuta, reports är redan SEK. Exakt en
            # periodspecifik currency_ratio-konvertering krävs här.
            value_sek = (val * ratio) if (val is not None and ratio is not None) else None
            rader.append({
                "insid": insid, "kod": kod, "kpi": kpi_namn, "report_type": rt,
                "year": y, "period": per, "value_local": val, "value_sek": value_sek,
                "report_date": meta["report_date"], "currency": meta["currency"],
                "currency_ratio": meta["currency_ratio"],
                "period_komplett": (rt != "year") or (per == 5),
            })
            stat["kpi_varden_ut"] += 1
    (OUT / "kpi_ebitda_capex.json").write_text(
        json.dumps(rader, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # -------------------- Buyback (transaktionsniva) ---------------------
    bb_rader = []
    bb_stat = Counter()
    insid_med_svar = set()
    kallhashar_bb = {}
    for p in sorted(glob.glob(str(RAW / "buyback/*.json"))):
        kallhashar_bb[Path(p).stem] = hashlib.sha256(Path(p).read_bytes()).hexdigest()
        d = las(p)
        for entry in (d.get("list") or []):
            insid = str(entry.get("insId"))
            insid_med_svar.add(insid)
            kod = insid2kod.get(insid)
            if entry.get("error"):
                bb_stat["api_fel"] += 1
                continue
            vals = entry.get("values") or []
            if not vals:
                bb_stat["verifierat_noll_transaktioner"] += 1
                continue
            for v in vals:
                dt = (v.get("date") or "")[:10]
                if not dt:
                    continue
                bb_rader.append({"insid": insid, "kod": kod, "date": dt,
                                 "change": v.get("change"), "price": v.get("price"),
                                 "currency": v.get("currency"), "shares": v.get("shares"),
                                 "shares_proc": v.get("sharesProc")})
                bb_stat["transaktioner"] += 1
    # instrument som finns i universumet men ALDRIG dyker upp i nagot batch-svar
    for insid in insid2kod:
        if insid not in insid_med_svar:
            bb_stat["saknas_helt_i_svar"] += 1
    (OUT / "buyback_transaktioner.json").write_text(
        json.dumps(bb_rader, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # -------------------- coverage per KPI / instrument / ar --------------
    cov = defaultdict(lambda: defaultdict(set))
    for r in rader:
        cov[r["kpi"]][r["kod"]].add(r["year"])
    coverage_rapport = {
        kpi: {"n_instrument_med_data": len(kod2ar),
              "median_n_ar_per_instrument": sorted(len(v) for v in kod2ar.values())[len(kod2ar)//2] if kod2ar else 0}
        for kpi, kod2ar in cov.items()
    }

    # -------------------- ekonomiska rimlighetskontroller ------------------
    # EBITDA >= EBIT (operating_Income), bara nar report-radens egen valuta
    # ar SEK (undviker det oklarade konverteringsantagandet for KPI-varden).
    ebit_lookup = {}
    for insid, p in senaste_per_insid("year/*.json").items():
        d = las(p)
        for r in (d.get("reportsYear") or []):
            if r.get("currency") == "SEK":
                ebit_lookup[(insid, r.get("year"))] = r.get("operating_Income")
    identitet = Counter()
    identitet_avvikelser = []
    for r in rader:
        # jamfor ENDAST helarsgranularitet (year p=5, eller r12 p=4 = samma
        # observation) mot den arliga EBIT-figuren - kvartalsvarden har
        # annan periodgranularitet och ar INTE jamforbara har.
        if r["kpi"] != "EBITDA" or r["currency"] != "SEK":
            continue
        if not ((r["report_type"] == "year" and r["period"] == 5)
                or (r["report_type"] == "r12" and r["period"] == 4)):
            continue
        ebit = ebit_lookup.get((r["insid"], r["year"]))
        if ebit is None or r["value_sek"] is None:
            continue
        identitet["testade"] += 1
        # float32-brus i kallan (t.ex. -5.454999923706055 lagrat for -5.4545)
        # kraver en rimlig tolerans, inte 1e-6 - annars falsklarm pa
        # praktiskt identiska varden (D&A ~ 0, sma bolag/tidiga bolag).
        tolerans = max(0.05, abs(ebit) * 0.001)
        if r["value_sek"] + tolerans >= ebit:
            identitet["godkanda"] += 1
        else:
            identitet["avvikelser"] += 1
            identitet_avvikelser.append({"kod": r["kod"], "year": r["year"],
                                         "ebitda_sek": r["value_sek"], "ebit": ebit})

    man = {
        "dataset": "dataset_v1.0 / spår B, KPI-utökning (EBITDA, Capex, återköp)",
        "version": "1.0.0",
        "dataset_sha256": hashlib.sha256(json.dumps({
            "kpi": hashlib.sha256((OUT / "kpi_ebitda_capex.json").read_bytes()).hexdigest(),
            "buyback": hashlib.sha256((OUT / "buyback_transaktioner.json").read_bytes()).hexdigest(),
        }, sort_keys=True).encode()).hexdigest(),
        "fryst_utc": "2026-08-08T00:00:00+00:00",
        "timestamp_policy": "deterministic dataset_v1.0 release timestamp; rebuild wall-clock time is not serialized",
        "kallor": {
            "kpi_history_kallfiler": len(kallhashar_kpi),
            "buyback_kallfiler": len(kallhashar_bb),
            "rapport_kallfiler_for_pit_join": len(kallhashar_rapport),
            "kpi_history_sha256": kallhashar_kpi,
            "buyback_sha256": kallhashar_bb,
            "reports_sha256": kallhashar_rapport,
        },
        "artefakter": {
            "kpi_ebitda_capex": {"fil": "validated/fundamenta_extra/kpi_ebitda_capex.json",
                "sha256": hashlib.sha256((OUT / "kpi_ebitda_capex.json").read_bytes()).hexdigest(),
                "n_rader": len(rader)},
            "buyback_transaktioner": {"fil": "validated/fundamenta_extra/buyback_transaktioner.json",
                "sha256": hashlib.sha256((OUT / "buyback_transaktioner.json").read_bytes()).hexdigest(),
                "n_rader": len(bb_rader)},
        },
        "pit_mappning": {
            "quarter/r12": "(y,p) -> reports/quarter (year=y,period=p).report_Date",
            "year_p5": "(y,5) -> reports/year (year=y,period=5).report_Date",
            "year_partiellt_p<5": "UTESLUTET ur panelen - representerar inte ett bokslut",
        },
        "regelutfall_kpi": dict(stat),
        "regelutfall_buyback": dict(bb_stat),
        "coverage_per_kpi": coverage_rapport,
        "ekonomisk_identitetskontroll_EBITDA_vs_EBIT": dict(identitet),
        "identitet_avvikelser_sample": identitet_avvikelser[:20],
        "kanda_begransningar": {
            "restatement_risk": "KPI-historikens {y,p,v} saknar versionsdatum - kan INTE "
                "verifieras mot retroaktiv omräkning. Samma begränsning som redan gäller "
                "reports-endpointen (ingen ny risk introduceras).",
            "valuta_konvertering_kpi": "GODKÄND: KPI-värdet är lokal rapporteringsvaluta; "
                "value_sek=value_local*currency_ratio exakt en gång. Verifierat med "
                "Capex/CFI-identitet per SEK/EUR/USD/PLN/ISK/NOK.",
            "buybacks_shareholder_yield": "UTESLUTEN: transaktionsdatan har egna valutor, "
                "positiva och negativa change/corrections samt extrema sharesProc. Ingen "
                "QA-godkänd cashflow/FX-definition finns; KPI 213-215 hämtades inte i fullskala.",
        },
        "faltstatus": {
            "EBITDA": "GODKÄND OCH MANIFESTERAD (value_sek)",
            "Capex": "GODKÄND OCH MANIFESTERAD (value_sek)",
            "buyback_transaktioner": "GODKÄND SOM RÅ/PIT-DATERAD TRANSAKTIONSTABELL; UTESLUTEN FRÅN FEATURES",
            "KPI_213_214_215": "UTESLUTEN: endast sample, kalenderbaserade aggregat och ej fullskalehämtade",
            "shareholder_yield": "UTESLUTEN: saknar verifierad transaktions-/FX-/korrektionsdefinition",
            "roic_proxy": "BEFINTLIG C-PROXY; inte ersatt av extra-data och inte sann ROIC",
        },
        "status": "DELvis GODKÄND: EBITDA/Capex godkända; buyback/shareholder_yield uteslutna",
    }
    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    # B-extra är en formell dimension i B-kedjan, inte en sidofil.
    main_manifest_path = V2 / "validated/manifest_sparB.json"
    main_manifest = json.loads(main_manifest_path.read_text(encoding="utf-8"))
    main_manifest["extra_dimension"] = {
        "manifest": "validated/manifest_sparB_extra.json",
        "sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "status": man["status"], "faltstatus": man["faltstatus"]}
    main_manifest["status"] = "SPÅR B FRYST; B-extra formellt länkat; fundamental survivorship är explicit datasetbegränsning"
    main_manifest_path.write_text(json.dumps(main_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in man.items() if k not in ("kallor",)}, indent=1, ensure_ascii=False)[:4000])
    print(f"\nartefakter: {OUT}, {MANIFEST}")


if __name__ == "__main__":
    main()
