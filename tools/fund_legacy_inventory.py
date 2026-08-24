"""Spar B, steg 1-3: inventering av legacy Borsdata-fundamenta for de 68
avnoterade Nasdaq Stockholm-bolagen 2020-2026, med full provenance per rad.

Legacy ar STRIKT READ-ONLY. Ingenting flyttas, andras eller hamtas om.
cache/borsdata/reports_<insId>_max20y.json skrevs av altdata/borsdata.py via
json.dumps(r.json()) - EN OMSERIALISERING, inte verbatim ravar (samma defekt
som underkande researchdb_v1/raw). Filerna kan darfor INTE hashverifieras mot
ursprungliga natverksbytes. De klassas som LEGACY_ARCHIVE (klass B):
ej reproducerbara pa rabytesniva, men semantiskt/PIT-verifierbara via sitt
eget innehall (report_Date, report_Start/End_Date, siffervarden).

Matchning mot Borsdata-instrumentets insId gors i TVA led (starkast forst):
  1. ISIN (fran instrument_master.eodhd.isin) mot en ALDRE Borsdata-snapshot
     (cache/borsdata/instruments_all.json, 1718 instrument - innehaller
     AVNOTERADE bolag som dagens /instruments inte langre listar, verifierat
     2026-08-07: HELIO/MNDRK/MVE fanns dar men saknas idag).
  2. Namn (exakt, sedan fuzzy) mot samma snapshot, som fallback.
"""
from __future__ import annotations

import difflib
import glob
import hashlib
import json
import re
from pathlib import Path

LEG = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache")
V2 = Path("/home/hannesb/momentum_v2")
MASTER = V2 / "docs/probes/instrument_master.json"
UT = V2 / "docs/probes/fund_legacy_inventory.json"


def norm(s) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(publ\.?\)|\bpubl\b", " ", s)
    s = re.sub(r"\b(ab|abp|asa|a/s|plc|inc|oyj|holding|group|the|of|och)\b", " ", s)
    s = re.sub(r"\bser(ie)?\.?\s*[a-d]\b", " ", s)
    s = re.sub(r"[^a-z0-9åäöéü ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def marknad(t) -> str:
    t = (t or "").lower()
    return "NS" if any(k in t for k in ("nasdaq stockholm", "nordiska listan",
                                        "o-listan", "a-listan")) else "-"


def main() -> None:  # noqa: C901
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    ns = [r for r in master if r.get("status") == "avnoterad" and r.get("avnoterad_ar")
          and 2020 <= r["avnoterad_ar"] <= 2026 and marknad(r.get("avnoterad_orsak")) == "NS"]
    print(f"68-listan (facit): {len(ns)} avnoterade Nasdaq Stockholm-bolag 2020–2026")

    # äldre snapshot: innehåller instrument Börsdata sedan tagit bort ur /instruments
    gammal = json.loads((LEG / "borsdata/instruments_all.json").read_text(encoding="utf-8"))
    gammal = gammal.get("instruments", gammal) if isinstance(gammal, dict) else gammal
    by_isin, by_namn = {}, {}
    for x in gammal:
        z = (x.get("isin") or "").upper()
        if len(z) == 12:
            by_isin.setdefault(z, []).append(x)
        n = norm(x.get("name"))
        if n:
            by_namn.setdefault(n, []).append(x)
    namn_nycklar = list(by_namn)
    print(f"äldre Börsdata-snapshot: {len(gammal)} instrument "
          f"({len(by_isin)} med ISIN)")

    # VIKTIGT: fuzzy namnmatchning är AVSTÄNGD. Kontrollprov: "Nobina AB"
    # (buss, avnoterad 2022-02-16) fuzzy-matchade vid cutoff 0.90 mot "Nobia"
    # (kök, insId 157, alltjämt aktiv med rapporter t.o.m. 2026-07-17) — en
    # falsk identitet hade smugit in fel bolags fundamenta under fel namn.
    # Bara ISIN och EXAKT normaliserat namn accepteras; allt annat lämnas
    # omärkt hellre än riskera tyst felidentifiering.
    def hitta_insid(r):
        z = ((r.get("eodhd") or {}).get("isin") or "").upper()
        if z and z in by_isin:
            return by_isin[z][0]["insId"], "ISIN", by_isin[z][0]
        n = norm(r["namn"])
        if n in by_namn:
            return by_namn[n][0]["insId"], "exakt namn", by_namn[n][0]
        for altn in [b.get("fran") for b in r.get("namnbyten", [])] + \
                    [b.get("till") for b in r.get("namnbyten", [])]:
            nn = norm(altn)
            if nn and nn in by_namn:
                return by_namn[nn][0]["insId"], "namnbyte", by_namn[nn][0]
        return None, None, None

    resultat, saknas_helt = [], []
    for r in ns:
        insid, metod, post = hitta_insid(r)
        rad = {"namn": r["namn"], "orgnr": r.get("orgnr"),
               "isin": (r.get("eodhd") or {}).get("isin"),
               "avnoterad_datum": r.get("avnoterad_datum"),
               "insid": insid, "matchmetod": metod,
               "borsdata_namn_vid_matchning": post.get("name") if post else None}
        if insid is None:
            saknas_helt.append(rad)
            resultat.append(dict(rad, ar_filer=False, kvartal_filer=False, n_ar_rader=0,
                                 n_kvartal_rader=0, sista_kanda_rapport=None,
                                 klass="C", klass_skal="ingen Börsdata insId hittad"))
            continue

        arf = LEG / f"borsdata/reports_{insid}_max20y.json"
        kvf20 = LEG / f"borsdata/reports_{insid}_max20.json"          # buggig, 10 år
        kvq = LEG / f"borsdata/quarterly/reports_{insid}_quarter_max40.json"
        kvr12 = LEG / f"borsdata/quarterly/reports_{insid}_r12_max40.json"

        n_ar = n_kv = 0
        sista = None
        filhashar = {}
        rader_provenance = []
        if arf.exists():
            raw = arf.read_bytes()
            filhashar["ar_fil_sha256_nu"] = hashlib.sha256(raw).hexdigest()
            d = json.loads(raw)
            årsrader = d.get("reportsYear") or []
            n_ar = len(årsrader)
            for x in årsrader:
                rd = (x.get("report_Date") or "")[:10] or None
                sista = max(filter(None, [sista, rd])) if rd else sista
                rader_provenance.append({
                    "typ": "år", "period": x.get("year"),
                    "report_start_date": (x.get("report_Start_Date") or "")[:10] or None,
                    "report_end_date": (x.get("report_End_Date") or "")[:10] or None,
                    "report_date": rd,
                    "currency": x.get("currency"), "currency_ratio": x.get("currency_Ratio"),
                    "broken_fiscal_year": x.get("broken_Fiscal_Year")})
        if kvq.exists():
            raw = kvq.read_bytes()
            filhashar["kvartal_fil_sha256_nu"] = hashlib.sha256(raw).hexdigest()
            d = json.loads(raw)
            kvrader = d.get("reports") or d.get("reportsQuarter") or []
            n_kv = len(kvrader)
            for x in kvrader:
                rd = (x.get("report_Date") or "")[:10] or None
                sista = max(filter(None, [sista, rd])) if rd else sista

        resultat.append({
            **rad,
            "ar_filer": arf.exists(), "kvartal_filer": kvq.exists() or kvr12.exists(),
            "n_ar_rader": n_ar, "n_kvartal_rader": n_kv,
            "sista_kanda_rapport": sista,
            "filer": {"ar": str(arf.relative_to(LEG)) if arf.exists() else None,
                      "kvartal": str(kvq.relative_to(LEG)) if kvq.exists() else None,
                      "mtime_ar": arf.stat().st_mtime if arf.exists() else None,
                      "mtime_kvartal": kvq.stat().st_mtime if kvq.exists() else None},
            "filhashar_nu": filhashar,
            "klass": "B" if (n_ar or n_kv) else "C",
            "klass_skal": ("LEGACY_ARCHIVE: reports_{}_max20y.json omserialiserad vid "
                          "skrivning (json.dumps(r.json())), ej verifierbar mot "
                          "ursprungliga nätverksbytes; PIT-fält (report_Date/"
                          "report_Start_Date/report_End_Date) läses ur innehållet"
                          .format(insid) if (n_ar or n_kv) else
                          "insId hittat men inga rapportfiler i cachen"),
            "provenance_rader": rader_provenance[:3],   # exempel, full lista i separat fil
        })

    # ---------------- sammanfattning --------------------------------
    print("\n" + "=" * 100)
    print("TÄCKNING: 68 AVNOTERADE NASDAQ STOCKHOLM-BOLAG I LEGACY BÖRSDATA-CACHE")
    print("=" * 100)
    B = [r for r in resultat if r["klass"] == "B"]
    C = [r for r in resultat if r["klass"] == "C"]
    print(f"  klass B (legacy-arkiv med data): {len(B)}/{len(resultat)}")
    print(f"  klass C (ingen data alls):       {len(C)}/{len(resultat)}")
    print(f"\n  varav med årsrapporter:    {sum(1 for r in B if r['ar_filer'])}")
    print(f"  varav med kvartalsrapporter: {sum(1 for r in B if r['kvartal_filer'])}")

    from collections import Counter
    metoder = Counter(r["matchmetod"] for r in resultat)
    print(f"\n  matchningsmetod: {dict(metoder)}")

    print(f"\n{'namn':38s} {'insId':>6s} {'metod':10s} {'år':>4s} {'kv':>4s} "
          f"{'sista rapport':>14s} {'avnoterad':>11s} {'klass':>5s}")
    for r in sorted(resultat, key=lambda x: x["namn"]):
        print(f"{r['namn'][:38]:38s} {str(r['insid']):>6s} {str(r['matchmetod'])[:10]:10s} "
              f"{r['n_ar_rader']:>4d} {r['n_kvartal_rader']:>4d} "
              f"{str(r['sista_kanda_rapport']):>14s} {str(r['avnoterad_datum'])[:10]:>11s} "
              f"{r['klass']:>5s}")

    if C:
        print(f"\nKLASS C — INGEN FUNDAMENTA HITTAD ({len(C)}):")
        for r in C:
            print(f"  {r['namn'][:44]:44s} orgnr={r.get('orgnr')} isin={r.get('isin')}")

    # --------- kompletterande: hur många rapportfiler är "spårlösa"? -----
    print("\n" + "=" * 100)
    print("KOMPLETTERANDE KONTROLL — hela cache/borsdata/reports_*_max20y.json-beståndet")
    print("=" * 100)
    alla_arfiler = sorted(glob.glob(str(LEG / "borsdata/reports_*_max20y.json")))
    kanda_ids = {x["insId"] for x in gammal}
    levande = json.loads((V2 / "docs/probes/instruments_live.json").read_text(encoding="utf-8"))
    kanda_ids |= {x["insId"] for x in levande}
    sparlosa = []
    for f in alla_arfiler:
        m = re.search(r"reports_(\d+)_max20y\.json", f)
        if not m:
            continue
        iid = int(m.group(1))
        if iid not in kanda_ids:
            sparlosa.append(iid)
    print(f"  totalt {len(alla_arfiler)} årsrapportfiler i cachen")
    print(f"  insId som INTE finns i någon känd instrumentlista (varken ny eller äldre): "
          f"{len(sparlosa)}")
    print(f"  → dessa KAN teoretiskt innehålla data för ett okänt delistat bolag, men utan "
          f"namn/ISIN att verifiera mot går de inte att identifiera — och identifiering genom "
          f"innehållets finansiella storleksordning skulle vara en gissning, inte en "
          f"verifiering. De lämnas explicit ospårade, inte tyst antagna.")
    if sparlosa:
        print(f"  exempel-insId: {sparlosa[:15]}")

    UT.write_text(json.dumps({"n_facit": len(ns), "n_klass_B": len(B), "n_klass_C": len(C),
                              "n_sparlosa_arfiler": len(sparlosa),
                              "sparlosa_insid": sparlosa,
                              "bolag": resultat},
                             indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {UT}")


if __name__ == "__main__":
    main()
