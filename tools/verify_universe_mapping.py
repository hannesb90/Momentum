"""Verifiering av instrumentmappning EODHD <-> Borsdata.

Fristaende: importerar INGEN legacy-kod och ingen legacy-config. Laser legacy
enbart som READ-ONLY datafiler via explicita sokvagar nedan. Skriver enbart under
/home/hannesb/momentum_v2/.

Svarar pa:
  1. Hur stor del av EODHD:s aktiva universum gar att mappa till Borsdata?
  2. Hur ser det ut for de avnoterade? (forvantat: nastan ingen - Borsdata rensar bort dem)
  3. Tickerbyten: samma ISIN men olika kod i de tva kallorna
  4. Avnoteringsdatum: harleds ur sista EOD-datum per avnoterat instrument
  5. Corporate actions: EODHD splits mot Borsdata StockSplits
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# --- explicita sokvagar; legacy ar READ-ONLY -------------------------------
LEGACY = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache")
EOD = LEGACY / "eodhd_archive/ST"
V2 = Path("/home/hannesb/momentum_v2")
PROBES = V2 / "docs/probes"
OUT = V2 / "docs/probes/universe_mapping.json"


def las_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def las_gz(p: Path):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def norm_isin(x) -> str | None:
    if not isinstance(x, str):
        return None
    s = x.strip().upper()
    return s if len(s) == 12 and s[:2].isalpha() else None


def norm_kod(x) -> str | None:
    if not isinstance(x, str):
        return None
    return x.strip().upper().replace(" ", "").replace("_", "-")


def main() -> None:
    rep: dict = {"skapad": pd.Timestamp.utcnow().isoformat(), "legacy_lases_readonly": True}

    akt = las_json(EOD / "active_catalogue.json")
    avn = las_json(EOD / "delisted_catalogue.json")
    bd = las_json(PROBES / "instruments_live.json")
    print(f"EODHD aktiva {len(akt)} | EODHD avnoterade {len(avn)} | Börsdata {len(bd)}")

    # Borsdata: ticker + yahoo ("AAK.ST") + isin
    bd_isin = {}
    bd_tick = {}
    for i in bd:
        z = norm_isin(i.get("isin"))
        if z:
            bd_isin.setdefault(z, []).append(i)
        t = norm_kod(i.get("ticker"))
        if t:
            bd_tick.setdefault(t, []).append(i)
    print(f"Börsdata med giltig ISIN: {sum(len(v) for v in bd_isin.values())} "
          f"({len(bd_isin)} unika)")

    # ---------- 1-2. mappning ---------------------------------------
    print("\n" + "=" * 92)
    print("1-2. MAPPNING EODHD -> BÖRSDATA")
    print("=" * 92)
    print(f"{'grupp':22s} {'n':>6s} {'m. ISIN':>8s} {'ISIN-träff':>11s} "
          f"{'+ tickerträff':>14s} {'ingen träff':>12s}")
    detalj = {}
    for namn, lst in (("aktiva (alla typer)", akt), ("aktiva Common Stock",
                                                     [x for x in akt if x.get("Type") == "Common Stock"]),
                      ("avnoterade (alla)", avn), ("avnoterade Common Stock",
                                                   [x for x in avn if x.get("Type") == "Common Stock"])):
        n_isin = tr_isin = tr_tick = 0
        oparade = []
        for x in lst:
            z = norm_isin(x.get("Isin"))
            k = norm_kod(x.get("Code"))
            if z:
                n_isin += 1
            if z and z in bd_isin:
                tr_isin += 1
            elif k and k in bd_tick:
                tr_tick += 1
            else:
                oparade.append(x)
        print(f"{namn:22s} {len(lst):>6d} {n_isin:>8d} {tr_isin:>11d} {tr_tick:>14d} "
              f"{len(oparade):>12d}")
        detalj[namn] = {"n": len(lst), "med_isin": n_isin, "isin_traff": tr_isin,
                        "ticker_traff": tr_tick, "ingen_traff": len(oparade)}
    rep["mappning"] = detalj

    # ---------- 3. tickerbyten --------------------------------------
    print("\n" + "=" * 92)
    print("3. TICKERBYTEN — samma ISIN, olika kod i källorna")
    print("=" * 92)
    byten = []
    for x in akt:
        z = norm_isin(x.get("Isin"))
        if not z or z not in bd_isin:
            continue
        k = norm_kod(x.get("Code"))
        for b in bd_isin[z]:
            bt = norm_kod(b.get("ticker"))
            if k and bt and k != bt:
                byten.append({"isin": z, "eodhd": k, "borsdata": bt,
                              "namn": x.get("Name"), "bd_namn": b.get("name")})
    print(f"  {len(byten)} instrument har olika kod trots samma ISIN")
    for b in byten[:12]:
        print(f"    {b['isin']}  EODHD {b['eodhd']:12s} Börsdata {b['borsdata']:12s}  "
              f"{str(b['namn'])[:34]}")
    rep["tickerbyten"] = {"n": len(byten), "exempel": byten[:40]}

    # duplicerade ISIN inom respektive källa (A/B-aktier m.m.)
    dubb_bd = {z: [i.get("ticker") for i in v] for z, v in bd_isin.items() if len(v) > 1}
    ce = Counter(norm_isin(x.get("Isin")) for x in akt if norm_isin(x.get("Isin")))
    dubb_eod = {z: c for z, c in ce.items() if c > 1}
    print(f"  ISIN som pekar på flera instrument: Börsdata {len(dubb_bd)}, EODHD {len(dubb_eod)}")
    rep["dubbla_isin"] = {"borsdata": len(dubb_bd), "eodhd": len(dubb_eod),
                          "exempel_borsdata": dict(list(dubb_bd.items())[:8])}

    # ---------- 4. avnoteringsdatum ---------------------------------
    print("\n" + "=" * 92)
    print("4. AVNOTERINGSDATUM — härlett ur sista EOD-datum per avnoterat instrument")
    print("=" * 92)
    slut = []
    saknad_serie = 0
    for x in avn:
        k = x.get("Code")
        p = EOD / "delisted/eod" / f"{k}.json.gz"
        if not p.exists():
            saknad_serie += 1
            continue
        try:
            d = las_gz(p)
        except Exception:  # noqa: BLE001
            saknad_serie += 1
            continue
        if not d:
            saknad_serie += 1
            continue
        slut.append({"code": k, "namn": x.get("Name"), "isin": norm_isin(x.get("Isin")),
                     "forsta": d[0].get("date"), "sista": d[-1].get("date"), "n": len(d)})
    s = pd.DataFrame(slut)
    if len(s):
        s["sista_dt"] = pd.to_datetime(s["sista"], errors="coerce")
        s["forsta_dt"] = pd.to_datetime(s["forsta"], errors="coerce")
        print(f"  {len(s)} avnoterade med EOD-serie ({saknad_serie} utan)")
        print(f"  sista handelsdag: {s.sista_dt.min().date()} – {s.sista_dt.max().date()}")
        per_ar = s.sista_dt.dt.year.value_counts().sort_index()
        print("  avnoteringar per år: " + "  ".join(f"{y}:{n}" for y, n in per_ar.items()
                                                    if y >= 2010))
        fore2010 = int((s.sista_dt.dt.year < 2010).sum())
        print(f"  avnoterade före 2010 (utanför panelperioden): {fore2010}")
        print(f"  medianlängd på serien: {int(s.n.median())} handelsdagar")
        rep["avnoteringar"] = {
            "n_med_serie": int(len(s)), "n_utan_serie": saknad_serie,
            "sista_min": str(s.sista_dt.min().date()), "sista_max": str(s.sista_dt.max().date()),
            "per_ar": {int(y): int(n) for y, n in per_ar.items()},
            "n_fore_2010": fore2010, "median_dagar": int(s.n.median())}
        s.drop(columns=["sista_dt", "forsta_dt"]).to_json(
            PROBES / "eodhd_delisted_serier.json", orient="records", force_ascii=False)

    # ---------- 5. corporate actions --------------------------------
    print("\n" + "=" * 92)
    print("5. CORPORATE ACTIONS — EODHD splits mot Börsdata StockSplits")
    print("=" * 92)
    bd_spl_p = LEGACY / "borsdata/stocksplits_from2000.json"
    bd_spl = las_json(bd_spl_p).get("stockSplitList", []) if bd_spl_p.exists() else []
    print(f"  Börsdata: {len(bd_spl)} splitar sedan 2000 (från legacy-cachen)")
    n_split_akt = n_split_avn = 0
    tot_akt = tot_avn = 0
    for grupp, lst, sub in (("aktiva", akt, "active"), ("avnoterade", avn, "delisted")):
        for x in lst:
            p = EOD / sub / "splits" / f"{x.get('Code')}.json.gz"
            if not p.exists():
                continue
            try:
                d = las_gz(p)
            except Exception:  # noqa: BLE001
                continue
            if grupp == "aktiva":
                tot_akt += 1
                n_split_akt += len(d or [])
            else:
                tot_avn += 1
                n_split_avn += len(d or [])
    print(f"  EODHD: {n_split_akt} splitar över {tot_akt} aktiva, "
          f"{n_split_avn} över {tot_avn} avnoterade")
    print(f"  → EODHD har splithistorik även för avnoterade; Börsdata har det inte alls "
          f"(instrumenten är borttagna)")
    rep["corporate_actions"] = {"borsdata_splitar": len(bd_spl),
                                "eodhd_splitar_aktiva": n_split_akt,
                                "eodhd_splitar_avnoterade": n_split_avn,
                                "eodhd_filer_aktiva": tot_akt, "eodhd_filer_avnoterade": tot_avn}

    OUT.write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {OUT}")


if __name__ == "__main__":
    sys.exit(main())
