"""Spar B steg 1: splitverifiering av earnings_Per_Share och dividend mot
Spar A:s EODHD-splitdata (samma kalla som klassificerade de 871 prisniva-
brotten). Slutlig klassificering av de tva KRAVER ATGARD-falten.

Metod:
  1. Instrument -> EODHD-kod via raw/borsdata/_matchning.json (ISIN-verifierad).
  2. EODHD splits (legacy, read-only) per instrument: {date, split="ny/gammal"}.
  3. For varje arsrapportpar (Y-1 -> Y): finns en split mellan de tva
     report_End_Date? Om ja: stammer number_Of_Shares-forandringen med
     splitfaktorn (inom tolerans, tillater nyemission utover splitten)?
  4. Ar splitten reflekterad i aktieantalet, testa om earnings_Per_Share
     FORTSATT ar konsistent med profit_To_Equity_Holders/number_Of_Shares
     (samma test som i fund_qa_track_a.py, men ISOLERAT till split-ar) -
     om konsistensen haller lika bra runt splitar som generellt, ar faltet
     korrekt splitjusterat.
  5. For de namngivna "oforklarade" hoppen fran FUNDAMENTAL_QA.md (Humana,
     Holmen, Carasent, Paradox / Hufvudstaden, NCC, Volati, NAXS, New Wave):
     slutgiltig kontroll direkt mot EODHD:s splitfiler (mer tillforlitlig an
     det tidigare Skatteverket-textbaserade +/-1ar-fonstret).

Ren diagnostik. Ingen rådata ändras.
"""
from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
RAW = V2 / "raw/borsdata"
EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
UT = V2 / "docs/probes/fund_split_verify.json"


def läs_gz(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def splitfaktor(s: str) -> float | None:
    try:
        ny, gammal = s.split("/")
        g = float(gammal)
        return float(ny) / g if g else None
    except Exception:  # noqa: BLE001
        return None


def main() -> None:  # noqa: C901
    match = json.loads((RAW / "_matchning.json").read_text(encoding="utf-8"))
    master = json.loads((V2 / "docs/probes/instrument_master.json").read_text(encoding="utf-8"))
    kod2grupp = {}
    for r in master:
        e = r.get("eodhd") or {}
        if e.get("code"):
            kod2grupp[e["code"]] = e.get("grupp", "active")
    insid2kod = {m["insid"]: m["kod"] for m in match["matchade"]}

    validated = json.loads(
        (V2 / "validated/fundamentals/fundamentals_year_validated.json").read_text(encoding="utf-8"))
    by_inst = {}
    for r in validated:
        by_inst.setdefault(r["insid"], []).append(r)

    # ladda EODHD-splitar per instrument
    splits_by_insid = {}
    for insid, kod in insid2kod.items():
        if not kod:
            continue
        grupp = kod2grupp.get(kod, "active")
        p = EOD / grupp / "splits" / f"{kod}.json.gz"
        rader = läs_gz(p)
        if not rader and grupp == "active":
            rader = läs_gz(EOD / "delisted" / "splits" / f"{kod}.json.gz")
        splits_by_insid[insid] = [
            {"datum": s["date"], "faktor": splitfaktor(s.get("split", ""))}
            for s in rader if splitfaktor(s.get("split", "")) is not None]

    n_med_split = sum(1 for v in splits_by_insid.values() if v)
    print(f"instrument med ≥1 EODHD-split: {n_med_split}/{len(splits_by_insid)}")

    # ================================================================
    # 1. Är splitar reflekterade i number_Of_Shares?
    # ================================================================
    print("\n" + "=" * 100)
    print("1. SPLIT → NUMBER_OF_SHARES — reflekteras kända splitar i aktieantalet?")
    print("=" * 100)
    reflekterad = ej_reflekterad = 0
    detaljer = []
    for insid, rs in by_inst.items():
        rs = sorted(rs, key=lambda x: x.get("report_end_date") or "")
        sp = splits_by_insid.get(insid, [])
        if not sp:
            continue
        for i in range(1, len(rs)):
            a, b = rs[i - 1], rs[i]
            ea, eb = a.get("report_end_date"), b.get("report_end_date")
            if not ea or not eb:
                continue
            träffar = [s for s in sp if ea <= s["datum"] <= eb]
            if not träffar:
                continue
            fakt = 1.0
            for s in träffar:
                fakt *= s["faktor"]
            na, nb = a.get("number_Of_Shares"), b.get("number_Of_Shares")
            if not na or not nb or na <= 0:
                continue
            faktisk = nb / na
            avvik = abs(faktisk / fakt - 1) if fakt else None
            ok = avvik is not None and avvik <= 0.30      # tillåter viss nyemission utöver splitten
            if ok:
                reflekterad += 1
            else:
                ej_reflekterad += 1
            detaljer.append({"insid": insid, "kod": insid2kod.get(insid),
                             "år": b.get("year"), "splitdatum": [s["datum"] for s in träffar],
                             "splitfaktor": fakt, "shares_fore": na, "shares_efter": nb,
                             "faktisk_kvot": faktisk, "reflekterad": ok})
    print(f"  split-år med matchande number_Of_Shares-förändring (±30%): {reflekterad}")
    print(f"  split-år där number_Of_Shares INTE stämmer med splitfaktorn: {ej_reflekterad}")
    for d in [x for x in detaljer if not x["reflekterad"]][:10]:
        print(f"    {d['kod']:10s} {d['år']} split {d['splitdatum']} faktor {d['splitfaktor']:.3f} "
              f"aktier {d['shares_fore']:.2f}→{d['shares_efter']:.2f} (kvot {d['faktisk_kvot']:.3f})")

    # ================================================================
    # 2. Är EPS lika konsistent (profit/shares) KRING splitar som generellt?
    # ================================================================
    print("\n" + "=" * 100)
    print("2. EPS-KONSISTENS SPECIFIKT KRING SPLITÅR, JÄMFÖRT MED GENERELLT")
    print("=" * 100)
    split_år_insid_year = {(d["insid"], d["år"]) for d in detaljer}
    kring, ej_kring = [], []
    for insid, rs in by_inst.items():
        for r in rs:
            eps, p, n = r.get("earnings_Per_Share"), r.get("profit_To_Equity_Holders"), \
                r.get("number_Of_Shares")
            if eps is None or not p or not n or n <= 0:
                continue
            calc = p / n
            if abs(calc) < 1e-9:
                continue
            avv = abs(eps - calc) / abs(calc)
            (kring if (insid, r.get("year")) in split_år_insid_year else ej_kring).append(avv)
    import numpy as np
    for namn, arr in (("kring split (±ett rapportpar)", kring), ("övriga rader", ej_kring)):
        a = np.array(arr)
        if len(a):
            print(f"  {namn:32s} n={len(a):5d}  <1%: {100*np.mean(a<0.01):5.1f}%  "
                  f"<10%: {100*np.mean(a<0.10):5.1f}%  median: {100*np.median(a):5.2f}%")

    # ================================================================
    # 3. De namngivna "oförklarade" hoppen — definitiv kontroll
    # ================================================================
    print("\n" + "=" * 100)
    print("3. NAMNGIVNA HOPP FRÅN FUNDAMENTAL_QA.md — definitiv kontroll mot EODHD-splitar")
    print("=" * 100)
    fall = [
        ("Humana AB", "earnings_Per_Share", 2011, 2012),
        ("Holmen AB", "earnings_Per_Share", 2010, 2011),
        ("Carasent AB", "earnings_Per_Share", 2016, 2017),
        ("Paradox Interactive AB", "earnings_Per_Share", 2014, 2015),
        ("Hufvudstaden AB", "dividend", 2006, 2007),
        ("Avarda Bank AB", "dividend", 2013, 2014),
        ("Volati AB", "dividend", 2020, 2021),
        ("NAXS AB", "dividend", 2024, 2025),
        ("NCC AB", "dividend", 2007, 2008),
        ("New Wave Group AB", "dividend", 2007, 2008),
    ]
    namn2insid = {m["namn"]: m["insid"] for m in match["matchade"]}
    for namn, kol, y0, y1 in fall:
        insid = namn2insid.get(namn)
        if insid is None:
            print(f"  {namn:24s} — instrument saknas i matchningen")
            continue
        kod = insid2kod.get(insid)
        rs = by_inst.get(insid, [])
        a = next((r for r in rs if r.get("year") == y0), None)
        b = next((r for r in rs if r.get("year") == y1), None)
        if not a or not b:
            print(f"  {namn:24s} {kol:22s} {y0}→{y1}: rad saknas i VALIDATED (utesluten av PIT-regel)")
            continue
        sp = splits_by_insid.get(insid, [])
        träffar = [s for s in sp if a.get("report_end_date", "") <= s["datum"]
                  <= b.get("report_end_date", "9999")]
        na, nb = a.get("number_Of_Shares"), b.get("number_Of_Shares")
        andrade_aktier = na and nb and abs(nb / na - 1) > 0.02
        print(f"  {namn:24s} {kol:22s} {y0}→{y1}  {a.get(kol):>9.3f}→{b.get(kol):<9.3f}  "
              f"kod={kod}  EODHD-splitar i fönstret: {[s['datum'] for s in träffar] or 'INGEN'}  "
              f"aktieantal {na:.2f}→{nb:.2f} ({'ändrat' if andrade_aktier else 'oförändrat'})")

    (UT).write_text(json.dumps({
        "n_instrument_med_split": n_med_split,
        "split_reflekterad_i_shares": reflekterad, "split_ej_reflekterad": ej_reflekterad,
        "detaljer_ej_reflekterade": [d for d in detaljer if not d["reflekterad"]],
        "eps_konsistens_kring_split_n": len(kring),
        "eps_konsistens_kring_split_under_10pct": float(np.mean(np.array(kring) < 0.10)) if kring else None,
        "eps_konsistens_ovrigt_under_10pct": float(np.mean(np.array(ej_kring) < 0.10)) if ej_kring else None,
    }, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {UT}")


if __name__ == "__main__":
    main()
