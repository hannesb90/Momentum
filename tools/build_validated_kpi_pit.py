"""Bygger VALIDATED PIT-lager ur de array-hämtade KPI-lagren.

RAW in : raw/borsdata/kpi_valuation/, raw/borsdata/kpi_kvalitet/   (batchade, {y,p,v})
UT     : validated/kpi_pit/{kpi}.json  +  validated/kpi_pit/_qa.json

PIT-regeln är den preregistrerade (K2_PREREG_FREEZE.json, sha256
aa046c08...): varje (y,p) joinas mot sitt report_Date ur det redan frysta
rapportlagret. Saknas report_Date UTESLUTS raden — ingen estimering, ingen
periodslutssubstitution.

R1-R5 återanvänds VERBATIM från tools/build_validated_kpi_extra.py via import,
så reglerna inte kan glida isär mellan de två lagren.

INGEN target läses. Ingen IC beräknas. Ingen portfölj simuleras.
"""
from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
RAW = V2 / "raw/borsdata"
OUT = V2 / "validated/kpi_pit"
LAGER = {"kpi_valuation": "vardering", "kpi_kvalitet": "kvalitet"}
RESOLUTION = "r12"          # preregistrerad primärupplösning


def _extra():
    src = V2 / "tools/build_validated_kpi_extra.py"
    spec = importlib.util.spec_from_file_location("kpiextra", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    extra = _extra()
    OUT.mkdir(parents=True, exist_ok=True)

    lookup, kallhashar = extra.bygg_rapport_lookup()
    print(f"rapportlookup: {len(lookup)} instrument")

    match = json.loads((RAW / "_matchning.json").read_text(encoding="utf-8"))
    insid2kod = {str(m["insid"]): m["kod"] for m in match["matchade"]}
    print(f"matchning    : {len(insid2kod)} insid -> kod\n")

    qa = {"byggd_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "prereg_sha256": json.loads((V2 / "research_k/K2_PREREG_FREEZE.json")
                                      .read_text(encoding="utf-8"))["sha256"],
          "resolution": RESOLUTION, "lager": {}}

    for katalog, etikett in LAGER.items():
        filer = sorted(glob.glob(str(RAW / katalog / f"*_{RESOLUTION}_b*.json")))
        per_kpi = defaultdict(list)
        for f in filer:
            m = re.match(r"(\d+)_(.+)_" + RESOLUTION + r"_b\d+__", Path(f).name)
            if not m:
                continue
            kpi_id, kpi_namn = m.group(1), m.group(2)
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            for a in (d.get("kpisList") or []):
                insid = str(a.get("instrument"))
                for v in (a.get("values") or []):
                    per_kpi[(kpi_id, kpi_namn)].append((insid, v.get("y"), v.get("p"), v.get("v")))

        stat = {"kpier": {}, "in": 0, "ut": 0}
        orsaker = defaultdict(int)
        for (kpi_id, kpi_namn), rader in sorted(per_kpi.items(), key=lambda x: int(x[0][0])):
            ut, n_in = [], 0
            for insid, y, p, val in rader:
                n_in += 1
                if val is None or y is None or p is None:
                    orsaker["saknar_varde_eller_period"] += 1
                    continue
                kod = insid2kod.get(insid)
                if kod is None:
                    orsaker["insid_ej_i_matchning"] += 1
                    continue
                rp = (lookup.get(insid) or {}).get((y, p))
                if rp is None:
                    orsaker["ingen_rapportrad_for_perioden"] += 1
                    continue
                if not rp["giltig"]:
                    orsaker[rp["orsak"] or "ogiltig"] += 1
                    continue
                ut.append({"kod": kod, "insid": insid, "y": y, "p": p,
                           "report_date": rp["report_date"], "v": float(val),
                           "currency": rp["currency"]})
            ut.sort(key=lambda r: (r["kod"], r["report_date"]))
            (OUT / f"{kpi_id}_{kpi_namn}_{RESOLUTION}.json").write_text(
                json.dumps(ut, ensure_ascii=False), encoding="utf-8")
            stat["kpier"][kpi_namn] = {"in": n_in, "ut": len(ut),
                                       "andel": round(len(ut) / n_in, 4) if n_in else 0.0,
                                       "instrument": len({r["kod"] for r in ut}),
                                       "forsta": min((r["report_date"] for r in ut), default=None),
                                       "sista": max((r["report_date"] for r in ut), default=None)}
            stat["in"] += n_in
            stat["ut"] += len(ut)
        stat["bortfall_orsaker"] = dict(sorted(orsaker.items(), key=lambda x: -x[1]))
        stat["andel_godkand"] = round(stat["ut"] / stat["in"], 4) if stat["in"] else 0.0
        qa["lager"][etikett] = stat

        print(f"── {etikett}: {stat['in']:,} in → {stat['ut']:,} godkända "
              f"({stat['andel_godkand']:.1%})")
        for o, n in list(stat["bortfall_orsaker"].items())[:6]:
            print(f"     bortfall  {o:32s} {n:,}")
        print()

    qa["kallhashar_n"] = len(kallhashar)
    (OUT / "_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    samlad = hashlib.sha256()
    for f in sorted(glob.glob(str(OUT / "*.json"))):
        if Path(f).name != "_qa.json":
            samlad.update(Path(f).read_bytes())
    print(f"validated/kpi_pit/ byggt — samlad sha256 {samlad.hexdigest()}")


if __name__ == "__main__":
    main()
