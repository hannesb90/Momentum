"""Spar B steg 2: fullstandig QA av kvartals- och R12-radata, samma krav som
arsdatan i fund_qa_track_a.py: PIT, tackning per ar/instrument, definitioner,
enheter, skala, extremvarden, missing-semantik OCH kallkonsistens - har
dessutom kvartal mot R12 (rullande 12 manader) samt bada mot arsdatan.

Ren diagnostik. Ingen radata andras, ingen feature engineering.
"""
from __future__ import annotations

import glob
import json
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
RAW = V2 / "raw/borsdata"
UT = V2 / "docs/probes/fund_qa_quarter.json"
MIN_PLAUSIBEL = date(1990, 1, 1)


def senaste_per_slug(mönster: str) -> dict:
    ut = {}
    for f in sorted(glob.glob(str(RAW / mönster))):
        ut[Path(f).name.rsplit("__", 1)[0]] = f
    return ut


def läs(f: str) -> dict:
    return json.loads(Path(f).read_text(encoding="utf-8"))


def las_metadata():
    f = sorted(glob.glob(str(RAW / "metadata/*.json")))[-1]
    d = läs(f)
    return {r["reportPropery"]: r for r in d["reportMetadatas"]}


def pit_klass(r: dict) -> str:
    rd, red = r.get("report_Date"), r.get("report_End_Date")
    if not rd:
        return "saknar_datum"
    rdd = date.fromisoformat(rd[:10])
    if rdd < MIN_PLAUSIBEL:
        return "epok"
    if red:
        redd = date.fromisoformat(red[:10])
        if rdd < redd:
            return "look_ahead"
    return "ok"


def main() -> None:  # noqa: C901
    meta = las_metadata()
    fält = [k for k in meta if k not in ("period", "year", "report_Date",
                                         "report_Start_Date", "report_End_Date",
                                         "broken_Fiscal_Year", "currency", "currency_Ratio")]
    match = json.loads((RAW / "_matchning.json").read_text(encoding="utf-8"))
    insid2namn = {m["insid"]: m["namn"] for m in match["matchade"]}

    def ladda(mönster: str, nyckel: str) -> list:
        rader = []
        for slug, f in senaste_per_slug(mönster).items():
            insid = int(slug.split("/")[-1].split("_")[0])
            d = läs(f)
            for r in (d.get(nyckel) or d.get("reports") or []):
                r["_insid"] = insid
                r["_namn"] = insid2namn.get(insid, f"insId {insid}")
                rader.append(r)
        return rader

    kv = ladda("quarter/*.json", "reports")
    r12 = ladda("r12/*.json", "reports")
    print(f"[kvartal] {len(kv)} rader, {len({r['_insid'] for r in kv})} instrument")
    print(f"[R12]     {len(r12)} rader, {len({r['_insid'] for r in r12})} instrument")

    rep = {"production": False}

    for namn, data in (("KVARTAL", kv), ("R12", r12)):
        print("\n" + "=" * 100)
        print(f"PIT-KORREKTHET — {namn}")
        print("=" * 100)
        c = Counter(pit_klass(r) for r in data)
        for r in data:
            r["_pit"] = pit_klass(r)
        print(f"  {dict(c)}")
        n = len(data)
        print(f"  giltiga: {c['ok']}/{n} ({100*c['ok']/n:.1f} %)")
        rep[f"pit_{namn.lower()}"] = dict(c)

        # eftersläpning
        lag = []
        for r in data:
            if r["_pit"] == "ok":
                rd, red = r["report_Date"][:10], r["report_End_Date"][:10]
                lag.append((date.fromisoformat(rd) - date.fromisoformat(red)).days)
        if lag:
            lag = np.array(lag)
            print(f"  eftersläpning (dagar): p10={np.percentile(lag,10):.0f} "
                  f"median={np.median(lag):.0f} p90={np.percentile(lag,90):.0f} max={lag.max():.0f}")
            rep[f"eftersläpning_{namn.lower()}"] = {"p10": float(np.percentile(lag, 10)),
                                                     "median": float(np.median(lag)),
                                                     "p90": float(np.percentile(lag, 90)),
                                                     "max": float(lag.max())}

        # täckning per bolag: hur många kvartal/rader har varje instrument?
        per_inst = Counter(r["_insid"] for r in data)
        antal = np.array(list(per_inst.values()))
        print(f"  rader per instrument: min={antal.min()} median={int(np.median(antal))} "
              f"max={antal.max()} ({len(per_inst)} instrument)")
        få = sum(1 for v in antal if v < 8)
        print(f"  instrument med <8 rader (≈2 år): {få}/{len(per_inst)}")

        # år-täckning
        år = Counter(r.get("year") for r in data if r.get("year"))
        print(f"  årsspann: {min(år)}–{max(år)}")
        gles = {y: n for y, n in sorted(år.items()) if y < 2022}
        print(f"  rader per år FÖRE 2022 (API-taket på 40 kvartal syns här): {gles}")
        rep[f"ar_fordelning_{namn.lower()}"] = dict(sorted(år.items()))

        print(f"\n  {'fält':32s} {'täckn%':>7s} {'noll%':>6s} {'p1':>12s} {'p50':>12s} "
              f"{'p99':>14s} {'max':>16s}")
        falt_rep = {}
        for kol in fält:
            def sek(r):
                v = r.get(kol)
                if v is None:
                    return None
                cr = r.get("currency_Ratio")
                if meta[kol]["format"] in ("MCURR", "CURR") and cr and cr != 0:
                    return v * cr
                return v
            vals_raw = [r.get(kol) for r in data]
            n_ok = sum(1 for v in vals_raw if v is not None)
            täckn = 100 * n_ok / len(data) if data else 0
            vals = np.array([v for v in (sek(r) for r in data) if v is not None], dtype=float)
            noll = 100 * float((vals == 0).mean()) if len(vals) else 0
            rad = {"tackning_pct": täckn, "noll_pct": noll}
            if len(vals):
                rad.update({"p1": float(np.percentile(vals, 1)), "p50": float(np.percentile(vals, 50)),
                           "p99": float(np.percentile(vals, 99)), "max": float(vals.max())})
                print(f"  {kol:32s} {täckn:>6.1f}% {noll:>5.1f}% {rad['p1']:>12.2f} "
                      f"{rad['p50']:>12.2f} {rad['p99']:>14.2f} {rad['max']:>16.2f}")
            else:
                print(f"  {kol:32s} {täckn:>6.1f}% {'–':>6s}")
            falt_rep[kol] = rad
        rep[f"falt_{namn.lower()}"] = falt_rep

    # ================================================================
    # KÄLLKONSISTENS 1: kvartal-summa mot R12
    # ================================================================
    print("\n" + "=" * 100)
    print("KÄLLKONSISTENS — summan av 4 kvartal mot motsvarande R12-rad (flödesfält)")
    print("=" * 100)
    by_inst_kv = {}
    for r in kv:
        by_inst_kv.setdefault(r["_insid"], {}).setdefault((r.get("year"), r.get("period")), r)
    by_inst_r12 = {}
    for r in r12:
        by_inst_r12.setdefault(r["_insid"], {}).setdefault((r.get("year"), r.get("period")), r)

    flödesfält = ["revenues", "operating_Income", "profit_To_Equity_Holders"]
    for kol in flödesfält:
        diffar = []
        for insid, per in by_inst_r12.items():
            kvdict = by_inst_kv.get(insid, {})
            for (y, p), r12rad in per.items():
                summa = 0.0
                n_kv = 0
                for dp in range(4):
                    yy, pp = y, p - dp
                    if pp <= 0:
                        yy, pp = y - 1, p - dp + 4
                    kvrad = kvdict.get((yy, pp))
                    if kvrad and kvrad.get(kol) is not None:
                        summa += kvrad[kol]
                        n_kv += 1
                if n_kv == 4 and r12rad.get(kol) is not None and abs(summa) > 1e-6:
                    diffar.append(abs(r12rad[kol] - summa) / abs(summa))
        if diffar:
            d = np.array(diffar)
            print(f"  {kol:26s} n={len(d):5d}  <1%: {100*np.mean(d<0.01):5.1f}%  "
                  f"<10%: {100*np.mean(d<0.10):5.1f}%  median: {100*np.median(d):5.2f}%")
            rep.setdefault("r12_vs_kvartalssumma", {})[kol] = {
                "n": len(d), "andel_under_1pct": float(np.mean(d < 0.01)),
                "andel_under_10pct": float(np.mean(d < 0.10)), "median_pct": float(np.median(d) * 100)}

    # ================================================================
    # KÄLLKONSISTENS 2: kvartal (helårskvartalet Q4) mot årsdata
    # ================================================================
    print("\n" + "=" * 100)
    print("KÄLLKONSISTENS — R12 vid Q4 mot motsvarande ÅRSDATA (samma period, oberoende endpoint)")
    print("=" * 100)
    year_files = senaste_per_slug("year/*.json")
    årsrader = {}
    for slug, f in year_files.items():
        insid = int(slug.split("/")[-1].split("_")[0])
        d = läs(f)
        for r in (d.get("reportsYear") or []):
            årsrader.setdefault(insid, {})[r.get("year")] = r
    for kol in flödesfält + ["total_Assets", "total_Equity"]:
        diffar = []
        for insid, per in by_inst_r12.items():
            for (y, p), r12rad in per.items():
                if p != 4:
                    continue
                årsrad = årsrader.get(insid, {}).get(y)
                if not årsrad or r12rad.get(kol) is None or årsrad.get(kol) is None:
                    continue
                if abs(årsrad[kol]) > 1e-6:
                    diffar.append(abs(r12rad[kol] - årsrad[kol]) / abs(årsrad[kol]))
        if diffar:
            d = np.array(diffar)
            print(f"  {kol:26s} n={len(d):5d}  identiska(<0,1%): {100*np.mean(d<0.001):5.1f}%  "
                  f"<10%: {100*np.mean(d<0.10):5.1f}%  median: {100*np.median(d):5.2f}%")
            rep.setdefault("r12q4_vs_arsdata", {})[kol] = {
                "n": len(d), "andel_identiska": float(np.mean(d < 0.001)),
                "andel_under_10pct": float(np.mean(d < 0.10)), "median_pct": float(np.median(d) * 100)}

    # ================================================================
    # MISSING-SEMANTIK: dividend i kvartal (utdelning betalas sällan varje kvartal)
    # ================================================================
    print("\n" + "=" * 100)
    print("MISSING-SEMANTIK — dividend i kvartalsdata (utbetalning är säsongsbunden, inte kontinuerlig)")
    print("=" * 100)
    div_per_period = Counter()
    for r in kv:
        if r.get("dividend") not in (None, 0):
            div_per_period[r.get("period")] += 1
    print(f"  kvartal med dividend≠0, fördelat på period (1–4): {dict(sorted(div_per_period.items()))}")
    print("  → om koncentrerat till ETT kvartalsnummer är 0 i övriga kvartal en ÄKTA nolla "
          "('ingen utdelning denna period'), inte ett saknat värde.")
    rep["dividend_period_fordelning"] = dict(div_per_period)

    (UT).write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {UT}")


if __name__ == "__main__":
    main()
