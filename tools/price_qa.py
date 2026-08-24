"""Spar A: klassificering av nivabrott i prisryggraden.

Ingen clipping, ingen automatisk korrigering. Varje brott klassificeras utifran
INSAMLADE BEVIS, och varje klass far en explicit behandlingsregel.

Bevis per brott:
  * close-kvot kontra adjusted_close-kvot  (skiljer justerad split fran datafel)
  * EODHD splits-fil for instrumentet inom +/-7 dagar (ratio)
  * EODHD div-fil inom +/-7 dagar (extrautdelning/inlosen)
  * sentinelvarde (close exakt 1e6 eller annat upprepat platshallarvarde)
  * datumkluster: hur manga ANDRA instrument bryter samma dag
  * avnoteringsdatum ur instrument_master (instrumentateranvandning)
  * atervander kursen inom 10 dagar (spik)

Fristaende v2-kod. Legacy lases READ-ONLY.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

EOD = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST")
V2 = Path("/home/hannesb/momentum_v2")
MASTER = V2 / "docs/probes/instrument_master.json"
UT = V2 / "docs/probes/price_qa_klassificering.json"

NED, UPP = 0.05, 20.0        # samma trosklar som upptacktsskanningen


def las_gz(p: Path):
    if not p.exists():
        return []
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def dagar(a: str, b: str) -> int:
    from datetime import date
    ya, ma, da = int(a[:4]), int(a[5:7]), int(a[8:10])
    yb, mb, db = int(b[:4]), int(b[5:7]), int(b[8:10])
    return abs((date(ya, ma, da) - date(yb, mb, db)).days)


def main() -> None:  # noqa: C901
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    avn_datum = {}
    for r in master:
        e = r.get("eodhd") or {}
        if e.get("code") and r.get("avnoterad_datum"):
            avn_datum.setdefault(e["code"], r["avnoterad_datum"][:10])

    # ---- 1. samla ALLA brott (inte bara det forsta per serie) ------
    brott = []
    for grupp in ("delisted", "active"):
        kat = json.loads((EOD / f"{grupp}_catalogue.json").read_text(encoding="utf-8"))
        for x in kat:
            d = las_gz(EOD / grupp / "eod" / f"{x['Code']}.json.gz")
            if len(d) < 20:
                continue
            spl = las_gz(EOD / grupp / "splits" / f"{x['Code']}.json.gz")
            div = las_gz(EOD / grupp / "div" / f"{x['Code']}.json.gz")
            for i in range(1, len(d)):
                a, b = d[i - 1].get("close"), d[i].get("close")
                if not a or not b or a <= 0 or b <= 0:
                    continue
                kv = b / a
                if NED <= kv <= UPP:
                    continue
                aa = d[i - 1].get("adjusted_close") or 0
                ab = d[i].get("adjusted_close") or 0
                kv_adj = (ab / aa) if aa > 0 and ab > 0 else None
                # revert inom 10 dagar?
                fram = d[i + 1: i + 11]
                revert = any(0.5 <= (y.get("close") or 0) / a <= 2.0 for y in fram if a > 0)
                brott.append({
                    "code": x["Code"], "namn": x.get("Name"), "grupp": grupp,
                    "datum_fore": d[i - 1]["date"], "datum_efter": d[i]["date"],
                    "close_fore": a, "close_efter": b, "kvot": kv,
                    "adj_fore": aa, "adj_efter": ab, "kvot_adj": kv_adj,
                    "vol_efter": d[i].get("volume"),
                    "splits": [s for s in spl
                               if dagar(s.get("date", "1900-01-01"), d[i]["date"]) <= 7],
                    "divs": [v for v in div
                             if dagar(v.get("date", "1900-01-01"), d[i]["date"]) <= 7],
                    "revert10": revert,
                    "avnoterad": avn_datum.get(x["Code"]),
                })
    print(f"nivåbrott totalt: {len(brott)} st över {len({b['code'] for b in brott})} serier")

    # ---- 2. datumkluster --------------------------------------------
    per_datum = Counter(b["datum_efter"] for b in brott)
    for b in brott:
        b["kluster"] = per_datum[b["datum_efter"]]

    # ---- 3. sentinelvarden -------------------------------------------
    vanliga = Counter(round(b["close_fore"], 2) for b in brott)
    sentinel = {v for v, n in vanliga.items() if n >= 3 and v >= 1000}
    print(f"misstänkta sentinelvärden (≥3 förekomster, ≥1000): {sorted(sentinel)[:8]}")

    # ---- 4. beslutstrad ----------------------------------------------
    def klassa(b: dict) -> tuple:
        if round(b["close_fore"], 2) in sentinel:
            return ("leverantörs-/datafel",
                    f"platshållarvärde {b['close_fore']:.0f} som kurs")
        if b["splits"]:
            r = b["splits"][0].get("split") or b["splits"][0].get("ratio")
            if b["kvot_adj"] is not None and 0.5 <= b["kvot_adj"] <= 2.0:
                return ("legitim corporate action",
                        f"split {r} nära datumet, adjusted_close kontinuerlig")
            return ("split-/justeringsproblem",
                    f"split {r} nära datumet men adjusted_close bryter också")
        if b["divs"]:
            dv = b["divs"][0].get("value")
            if dv and b["close_fore"] and dv / b["close_fore"] > 0.3:
                return ("legitim corporate action",
                        f"utdelning/inlösen {dv} = {100*dv/b['close_fore']:.0f} % av kursen")
        if b["avnoterad"] and b["datum_efter"] >= b["avnoterad"]:
            return ("instrumentåteranvändning",
                    f"brott efter avnotering {b['avnoterad']}, serien fortsätter")
        if b["kluster"] >= 3:
            return ("leverantörs-/datafel",
                    f"{b['kluster']} instrument bryter samma dag ({b['datum_efter']})")
        if b["revert10"]:
            return ("leverantörs-/datafel", "kursen återvänder inom 10 dagar (spik)")
        if b["kvot_adj"] is not None and 0.5 <= b["kvot_adj"] <= 2.0:
            return ("split-/justeringsproblem",
                    "adjusted_close kontinuerlig men close bryter — ojusterad rå close")
        return ("OKLASSIFICERAD", "inget bevis räckte — kräver manuell granskning")

    for b in brott:
        b["klass"], b["motivering"] = klassa(b)

    c = Counter(b["klass"] for b in brott)
    print("\n" + "=" * 92)
    print("KLASSIFICERING")
    print("=" * 92)
    for k, n in c.most_common():
        print(f"  {k:28s} {n:>5d}  ({100*n/len(brott):>4.1f} %)")

    print("\nEXEMPEL PER KLASS")
    for k in c:
        print(f"\n--- {k} ---")
        for b in [x for x in brott if x["klass"] == k][:5]:
            print(f"  {b['code']:12s} {str(b['namn'])[:26]:26s} {b['datum_fore']}→{b['datum_efter']} "
                  f"{b['close_fore']:>10.2f}→{b['close_efter']:<10.4f} kvot {b['kvot']:.4f} | {b['motivering'][:60]}")

    # oklassificerade i detalj
    ok = [b for b in brott if b["klass"] == "OKLASSIFICERAD"]
    if ok:
        print(f"\nOKLASSIFICERADE ({len(ok)}) — kräver manuell granskning:")
        for b in sorted(ok, key=lambda x: x["kvot"])[:20]:
            print(f"  {b['code']:12s} {str(b['namn'])[:24]:24s} {b['datum_efter']} "
                  f"{b['close_fore']:>9.2f}→{b['close_efter']:<9.4f} ({b['kvot']:.4f}x) "
                  f"adj-kvot {b['kvot_adj'] if b['kvot_adj'] else float('nan'):.3f} "
                  f"kluster {b['kluster']}")

    UT.write_text(json.dumps({"n_brott": len(brott), "klasser": dict(c), "brott": brott},
                             indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {UT}")


if __name__ == "__main__":
    main()
