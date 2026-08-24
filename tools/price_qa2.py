"""Spar A, steg 2: klassificering med Skatteverkets corporate actions som extra bevis.

Bevisordning: dokumenterad handelse fore heuristik.
Ingen clipping, ingen automatisk korrigering — bara klassificering + behandlingsregel.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
IN = V2 / "docs/probes/price_qa_klassificering.json"
SKV = V2 / "docs/probes/skv_corporate_actions.json"
MASTER = V2 / "docs/probes/instrument_master.json"
UT = V2 / "docs/probes/price_qa_slutlig.json"

FLOOR = 0.0001


def d2(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def skv_datum(ar: int, dag: str):
    m = re.match(r"\s*(\d{1,2})\s*/\s*(\d{1,2})", dag or "")
    if not m:
        return None
    try:
        return date(ar, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def tiopotens(k: float) -> bool:
    for p in (0.001, 0.01, 0.1, 10, 100, 1000):
        if abs(k / p - 1) < 0.02:
            return True
    return False


def main() -> None:  # noqa: C901
    data = json.loads(IN.read_text(encoding="utf-8"))
    brott = data["brott"]
    skv = json.loads(SKV.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    avn = {}
    for r in master:
        e = r.get("eodhd") or {}
        if e.get("code") and r.get("avnoterad_datum"):
            avn[e["code"]] = r["avnoterad_datum"][:10]

    # Skatteverkets CA per kod -> lista (datum, villkor)
    skv_ca = {}
    for kod, rader in skv.items():
        for x in rader:
            dd = skv_datum(x["ar"], x.get("dag", ""))
            if dd:
                skv_ca.setdefault(kod, []).append((dd, x["villkor"]))

    sentinel = {1000000.0, 4013.58}
    per_datum = Counter(b["datum_efter"] for b in brott)

    def klassa(b):  # noqa: C901
        kv, kadj = b["kvot"], b.get("kvot_adj")
        adj_kont = kadj is not None and 0.5 <= kadj <= 2.0
        de = d2(b["datum_efter"])

        # 1. dokumenterad split hos EODHD
        if b["splits"]:
            r = b["splits"][0].get("split") or b["splits"][0].get("ratio")
            return (("legitim corporate action", f"EODHD-split {r}, adjusted_close kontinuerlig")
                    if adj_kont else
                    ("split-/justeringsproblem", f"EODHD-split {r} men adjusted_close bryter"))

        # 2. dokumenterad handelse hos Skatteverket
        nara = [(dd, v) for dd, v in skv_ca.get(b["code"], []) if abs((dd - de).days) <= 12]
        if nara:
            v = nara[0][1]
            if re.search(r"\bS\s*\d|split|sammanläggning|omvänd", v, re.I):
                return (("legitim corporate action", f"Skatteverket: {v[:48]} (split), adj kontinuerlig")
                        if adj_kont else
                        ("split-/justeringsproblem", f"Skatteverket: {v[:48]} — ojusterad i close"))
            return ("legitim corporate action", f"Skatteverket: {v[:56]}")

        # 3. stor utdelning/inlosen
        if b["divs"]:
            dv = b["divs"][0].get("value")
            if dv and b["close_fore"] and dv / b["close_fore"] > 0.3:
                return ("legitim corporate action",
                        f"utdelning/inlösen {dv} = {100*dv/b['close_fore']:.0f} % av kursen")

        # 4. leverantorens golvvarde
        if abs(b["close_efter"] - FLOOR) < 1e-9 or abs(b["close_fore"] - FLOOR) < 1e-9:
            return ("leverantörs-/datafel", f"golvvärde {FLOOR} som kurs")

        # 5. platshallarvarde
        if round(b["close_fore"], 2) in sentinel:
            return ("leverantörs-/datafel", f"platshållarvärde {b['close_fore']:.0f} som kurs")

        # 6. datumkluster
        if per_datum[b["datum_efter"]] >= 4:
            return ("leverantörs-/datafel",
                    f"{per_datum[b['datum_efter']]} instrument bryter samma dag")

        # 7. spik som atervander
        if b["revert10"]:
            return ("leverantörs-/datafel", "kursen återvänder inom 10 dagar")

        # 8. instrumentateranvandning: brott inom +/-45 dagar kring avnotering
        if b["code"] in avn:
            da = d2(avn[b["code"]])
            if -45 <= (de - da).days <= 3650:
                return ("instrumentåteranvändning",
                        f"brott {(de-da).days:+d} dagar från avnotering {avn[b['code']]}, "
                        "serien fortsätter på annan nivå")

        # 9. exakt tiopotens utan dokumentation
        if tiopotens(kv):
            return ("split-/justeringsproblem",
                    f"exakt tiopotens {kv:.4g}× utan registrerad split — oregistrerad sammanläggning")

        # 10. ojusterad historisk niva
        if b["close_fore"] > 1000 and de.year < 2015:
            return ("split-/justeringsproblem",
                    f"historisk nivå {b['close_fore']:.0f} kr före {de.year} — ojusterad serie")

        return ("OKLASSIFICERAD", "inget bevis räckte")

    for b in brott:
        b["klass"], b["motivering"] = klassa(b)

    c = Counter(b["klass"] for b in brott)
    print("=" * 92)
    print(f"SLUTLIG KLASSIFICERING — {len(brott)} nivåbrott över "
          f"{len({b['code'] for b in brott})} serier")
    print("=" * 92)
    for k, n in c.most_common():
        print(f"  {k:28s} {n:>5d}  ({100*n/len(brott):>4.1f} %)")
    print(f"\n  serier som berörs per klass:")
    for k in c:
        print(f"    {k:28s} {len({b['code'] for b in brott if b['klass']==k}):>4d} serier")

    ok = [b for b in brott if b["klass"] == "OKLASSIFICERAD"]
    print(f"\nÅTERSTÅENDE OKLASSIFICERADE: {len(ok)} "
          f"({len({b['code'] for b in ok})} serier)")
    for b in sorted(ok, key=lambda x: x["kvot"])[:15]:
        print(f"  {b['code']:12s} {str(b['namn'])[:24]:24s} {b['datum_efter']} "
              f"{b['close_fore']:>10.2f}→{b['close_efter']:<10.4f} ({b['kvot']:.4g}x)")

    print("\n" + "=" * 92)
    print("INSTRUMENTÅTERANVÄNDNING — de allvarligaste (falska katastrofförluster)")
    print("=" * 92)
    for b in sorted([x for x in brott if x["klass"] == "instrumentåteranvändning"],
                    key=lambda x: x["kvot"])[:10]:
        print(f"  {b['code']:12s} {str(b['namn'])[:26]:26s} {b['datum_efter']} "
              f"{b['close_fore']:>9.2f}→{b['close_efter']:<9.4f}  {b['motivering'][:52]}")

    UT.write_text(json.dumps({"n_brott": len(brott), "klasser": dict(c), "brott": brott},
                             indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nartefakt: {UT}")


if __name__ == "__main__":
    main()
