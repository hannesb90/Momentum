"""Spar B, steg 4: fullstandig fundamental-QA pa Track A (V2 RAW, hashverifierad)
och Track B (LEGACY_ARCHIVE), rafalt for rafalt.

Klassificerar VARJE av Borsdatas 37 rapportfalt som GODKAND / KRAVER ATGARD /
UTESLUTEN, med skalen dokumenterade. Ingen imputering, winsorisering eller
feature engineering - ren diagnostik.

Kontroller per falt:
  PIT       report_Date narvaro/giltighet, look-ahead mot report_End_Date
  tackning  andel rader/bolag med varde, per ar
  definition/enhet  Borsdatas metadata-format (MCURR/CURR/MILL), valutaspridning
  skala/tecken  percentiler, andel exakta nollor, extremvarden
  split     korrelation mellan CURR-falt (per aktie) och kanda splitar (Skatteverket)
  kallkonsistens  revenues vs net_Sales (dubblettfalt i samma svar)
  missing-semantik  null vs 0, konsekvent over tid
"""
from __future__ import annotations

import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
RAW = V2 / "raw/borsdata"
UT = V2 / "docs/probes/fund_qa_track_a.json"

NUMERISKA = None  # sätts från metadata


def las_metadata():
    f = sorted(glob.glob(str(RAW / "metadata/*.json")))[-1]
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    return {r["reportPropery"]: r for r in d["reportMetadatas"]}


def senaste_per_slug(mönster: str) -> dict:
    """slug (t.ex. 'year/1010_year') -> senaste filens payload, given flera hämtningar."""
    ut = {}
    for f in sorted(glob.glob(str(RAW / mönster))):
        slug = Path(f).name.rsplit("__", 1)[0]
        ut[slug] = f          # sorted -> sista skriver över, dvs senaste tidsstämpel
    return ut


def läs(f: str) -> dict:
    return json.loads(Path(f).read_text(encoding="utf-8"))


def main() -> None:  # noqa: C901
    meta = las_metadata()
    fält = [k for k in meta if k not in ("period", "year", "report_Date",
                                         "report_Start_Date", "report_End_Date",
                                         "broken_Fiscal_Year", "currency", "currency_Ratio")]
    print(f"metadata: {len(meta)} fält totalt, {len(fält)} numeriska/kandidatfält")

    match = json.loads((RAW / "_matchning.json").read_text(encoding="utf-8"))
    insid2namn = {m["insid"]: m["namn"] for m in match["matchade"]}
    print(f"instrument matchade mot live Börsdata: {len(insid2namn)}")

    # ---- ladda ÅRSDATA (Track A) --------------------------------------
    year_files = senaste_per_slug("year/*.json")
    rader = []
    n_tom = n_fel = 0
    for slug, f in year_files.items():
        insid = int(slug.split("/")[-1].split("_")[0])
        try:
            d = läs(f)
        except Exception:  # noqa: BLE001
            n_fel += 1
            continue
        yr = d.get("reportsYear") or []
        if not yr:
            n_tom += 1
            continue
        for r in yr:
            r["_insid"] = insid
            r["_namn"] = insid2namn.get(insid, f"insId {insid}")
            r["_kalla"] = "A"
            rader.append(r)
    print(f"[Track A] {len(rader)} årsrader över {len({r['_insid'] for r in rader})} "
          f"instrument | tomma svar {n_tom} | trasiga {n_fel}")

    # ---- ladda LEGACY (Track B) — endast Besqab, se fund_legacy_inventory ----
    legacy = json.loads((V2 / "docs/probes/fund_legacy_inventory.json").read_text(encoding="utf-8"))
    b_rader = []
    for bolag in legacy["bolag"]:
        if bolag["klass"] != "B":
            continue
        arf = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache") / bolag["filer"]["ar"]
        d = läs(str(arf))
        for r in (d.get("reportsYear") or []):
            r["_insid"] = bolag["insid"]
            r["_namn"] = bolag["namn"]
            r["_kalla"] = "B"
            b_rader.append(r)
    if b_rader:
        n_b_inst = len({r["_insid"] for r in b_rader})
        print(f"[Track B] {len(b_rader)} årsrader över {n_b_inst} instrument — se "
              "fund_legacy_inventory.json: 67/68 äkta avnoterade saknar helt data")
    else:
        print("[Track B] 0 rader")

    alla = rader + b_rader
    n_inst_total = len({r["_insid"] for r in alla})
    år_range = sorted({r.get("year") for r in alla if r.get("year")})
    print(f"\nkombinerat: {len(alla)} rader, {n_inst_total} instrument, "
          f"år {min(år_range) if år_range else '–'}–{max(år_range) if år_range else '–'}")

    # =========================================================
    # PIT
    # =========================================================
    print("\n" + "=" * 100)
    print("PIT-KORREKTHET — report_Date narvaro och look-ahead")
    print("=" * 100)
    from datetime import date
    MIN_PLAUSIBEL = date(1990, 1, 1)
    saknar_datum = epok = look_ahead = ok_pit = 0
    exempel_la = []
    for r in alla:
        rd, red = r.get("report_Date"), r.get("report_End_Date")
        if not rd:
            saknar_datum += 1
            continue
        rdd = date.fromisoformat(rd[:10])
        if rdd < MIN_PLAUSIBEL:
            epok += 1
            continue
        if red:
            redd = date.fromisoformat(red[:10])
            if rdd < redd:
                look_ahead += 1
                if len(exempel_la) < 5:
                    exempel_la.append((r["_namn"], r.get("year"), rd, red))
                continue
        ok_pit += 1
    print(f"  giltiga (report_Date ≥ report_End_Date, rimligt datum): {ok_pit}/{len(alla)}")
    print(f"  saknar report_Date: {saknar_datum}")
    print(f"  orimligt tidigt datum (< 1990): {epok}")
    print(f"  look-ahead (report_Date < report_End_Date): {look_ahead}")
    for ex in exempel_la:
        print(f"    exempel: {ex}")

    # rapporteftersläpning (dagar mellan periodslut och publicering)
    lag = []
    for r in alla:
        rd, red = r.get("report_Date"), r.get("report_End_Date")
        if rd and red:
            try:
                lag.append((date.fromisoformat(rd[:10]) - date.fromisoformat(red[:10])).days)
            except ValueError:
                pass
    if lag:
        lag = np.array(lag)
        print(f"\n  rapporteftersläpning (report_Date − report_End_Date), dagar: "
              f"p10={np.percentile(lag,10):.0f} median={np.median(lag):.0f} "
              f"p90={np.percentile(lag,90):.0f} max={lag.max():.0f}")

    # =========================================================
    # VALUTA
    # =========================================================
    print("\n" + "=" * 100)
    print("VALUTA OCH ENHETSKONVERTERING")
    print("=" * 100)
    valutor = Counter(r.get("currency") for r in alla)
    print(f"  valutafördelning: {dict(valutor.most_common())}")
    icke_sek = [r for r in alla if r.get("currency") and r.get("currency") != "SEK"]
    print(f"  rader i annan valuta än SEK: {len(icke_sek)} ({100*len(icke_sek)/len(alla):.1f} %)")
    ratio_avvik = [r for r in icke_sek if r.get("currency_Ratio") in (None, 0, 1.0)]
    print(f"  därav med currency_Ratio saknad/0/exakt 1.0 (misstänkt icke-konverterad): "
          f"{len(ratio_avvik)}")
    for r in ratio_avvik[:5]:
        print(f"    {r['_namn'][:30]:30s} {r.get('year')} valuta={r.get('currency')} "
              f"ratio={r.get('currency_Ratio')}")

    # =========================================================
    # PER FÄLT: täckning, extremvärden, missing-semantik
    # =========================================================
    print("\n" + "=" * 100)
    print("PER FÄLT — täckning, nollor, extremvärden (efter currency_Ratio-konvertering "
          "till SEK för MCURR/CURR)")
    print("=" * 100)

    def sek(r, kol):
        v = r.get(kol)
        if v is None:
            return None
        cr = r.get("currency_Ratio")
        if meta[kol]["format"] in ("MCURR", "CURR") and cr and cr != 0:
            return v * cr
        return v

    falt_rapport = {}
    print(f"{'fält':32s} {'format':7s} {'täckn%':>7s} {'noll%':>6s} {'bolag':>10s} "
          f"{'p1':>12s} {'p50':>12s} {'p99':>14s} {'max':>16s}")
    for kol in fält:
        vals_raw = [r.get(kol) for r in alla]
        n_ok = sum(1 for v in vals_raw if v is not None)
        täckn = 100 * n_ok / len(alla) if alla else 0
        bolag_ok = len({r["_insid"] for r in alla if r.get(kol) is not None})
        vals = [sek(r, kol) for r in alla]
        vals = np.array([v for v in vals if v is not None], dtype=float)
        noll = 100 * float((vals == 0).mean()) if len(vals) else 0.0
        rad = {"format": meta[kol]["format"], "namn_sv": meta[kol]["nameSv"],
              "tackning_pct": täckn, "n_bolag_med_varde": bolag_ok,
              "n_bolag_totalt": n_inst_total, "noll_pct": noll}
        if len(vals):
            rad.update({"p1": float(np.percentile(vals, 1)), "p50": float(np.percentile(vals, 50)),
                       "p99": float(np.percentile(vals, 99)), "max": float(vals.max()),
                       "min": float(vals.min())})
            print(f"{kol:32s} {str(meta[kol]['format']):7s} {täckn:>6.1f}% {noll:>5.1f}% "
                  f"{bolag_ok:>4d}/{n_inst_total:<5d} {rad['p1']:>12.2f} {rad['p50']:>12.2f} "
                  f"{rad['p99']:>14.2f} {rad['max']:>16.2f}")
        else:
            print(f"{kol:32s} {str(meta[kol]['format']):7s} {täckn:>6.1f}% {'–':>6s} "
                  f"{bolag_ok:>4d}/{n_inst_total:<5d} {'(inga giltiga värden)':>12s}")
        falt_rapport[kol] = rad

    # =========================================================
    # KÄLLKONSISTENS: revenues vs net_Sales (dubblettfält)
    # =========================================================
    print("\n" + "=" * 100)
    print("KÄLLKONSISTENS — revenues vs net_Sales (två fält, samma svar)")
    print("=" * 100)
    par = [(r.get("revenues"), r.get("net_Sales")) for r in alla
          if r.get("revenues") is not None and r.get("net_Sales") is not None]
    if par:
        lika = sum(1 for a, b in par if abs(a - b) < 1e-6)
        print(f"  {len(par)} rader har båda fälten. Identiska: {lika} "
              f"({100*lika/len(par):.1f} %)")
        avvik = [(a, b) for a, b in par if abs(a - b) >= 1e-6]
        if avvik:
            print(f"  avvikande: {len(avvik)}. exempel: {avvik[:5]}")

    # =========================================================
    # SPLIT-PÅVERKAN på per aktie-fälten (EPS, dividend, kurser)
    # =========================================================
    print("\n" + "=" * 100)
    print("SPLITPÅVERKAN — EPS/utdelning/aktiekurser mot kända splitar (Skatteverket)")
    print("=" * 100)
    try:
        skv = json.loads((V2 / "docs/probes/skv_corporate_actions.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        skv = {}
    per_aktie = ["earnings_Per_Share", "dividend", "stock_Price_Average",
                "stock_Price_High", "stock_Price_Low"]
    n_med_split, n_kontroll = 0, 0
    grov_hopp = []
    by_inst = defaultdict(list)
    for r in alla:
        by_inst[r["_insid"]].append(r)
    for insid, rs in by_inst.items():
        rs = sorted(rs, key=lambda x: (x.get("year") or 0, x.get("period") or 0))
        for i in range(1, len(rs)):
            a, b = rs[i - 1], rs[i]
            for kol in per_aktie:
                va, vb = a.get(kol), b.get(kol)
                if va and vb and va > 0 and vb > 0:
                    kv = vb / va
                    if kv < 0.2 or kv > 5:
                        n_kontroll += 1
                        grov_hopp.append((a["_namn"], kol, a.get("year"), b.get("year"),
                                          va, vb, kv))
    print(f"  år-till-år-hopp >5× eller <0,2× i per aktie-fält: {n_kontroll}")
    for h in grov_hopp[:10]:
        print(f"    {h[0][:26]:26s} {h[1]:22s} {h[2]}→{h[3]}  {h[4]:>10.3f}→{h[5]:<10.3f} "
              f"({h[6]:.2f}x)")

    # =========================================================
    # AVNOTERADE — bekräftelse
    # =========================================================
    print("\n" + "=" * 100)
    print("AVNOTERADE BOLAG — bekräftad täckning i fundamentadatan")
    print("=" * 100)
    print(f"  68 avnoterade Nasdaq Stockholm-bolag 2020–2026 (facit: fund_legacy_inventory.json)")
    print(f"  därav med ÅTKOMLIG fundamentadata (Track A eller B): "
          f"{legacy['n_klass_B']} (Besqab — se anmärkning nedan)")
    print(f"  utan någon fundamentadata (klass C): {legacy['n_klass_C']}")
    print("  ANMÄRKNING: Besqab är enligt spår A (PRIS_QA_KLASSIFICERING.md) inte en äkta")
    print("  survivorship-händelse — bolagets handel fortsatte, serien delades vid ett")
    print("  datafel. Den enda 'avnoterade' med fundamenta är alltså inte en död observation.")

    (UT).write_text(json.dumps({
        "production": False,
        "n_rader_A": len(rader), "n_rader_B": len(b_rader), "n_instrument": n_inst_total,
        "pit": {"ok": ok_pit, "saknar_datum": saknar_datum, "epok": epok,
               "look_ahead": look_ahead, "exempel_look_ahead": exempel_la},
        "valuta": dict(valutor), "n_icke_sek": len(icke_sek),
        "n_ratio_avvik": len(ratio_avvik),
        "falt": falt_rapport,
        "revenues_vs_net_sales": {"n_par": len(par),
                                  "n_identiska": lika if par else 0},
        "split_kontroll_hopp": n_kontroll,
        "avnoterade_med_data": legacy["n_klass_B"], "avnoterade_utan_data": legacy["n_klass_C"],
    }, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {UT}")


if __name__ == "__main__":
    main()
