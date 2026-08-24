"""REVALIDATION-WRAPPER — tidig_detektion_och_utdelning, endast forskningsdelarna.

Originalskriptet ar OFORANDRAT. Det bestar av tre block:

  del1_detektion(S.F26 / S.F19)          forskning, gatad motordata
  del2_rotera(S.F26 / S.F19, tilt)       forskning, gatad motordata
  del3_utdelning()                       DATA_QA_INTRINSIC_RAW_ACCESS

Separationen ar verifierad: del3_utdelning() tar inga argument, dess returvarde skrivs
enbart till ut["utdelning"] och lases aldrig av del 1-2, och forskningsdelarna berakans
FORE del3 anropas. Noll dataflode fran ra-QA in i alfaresultatet.

Problemet ar rent exekveringsmassigt: del3 kastar hart fel i REVALIDATION-mode innan
originalets OUT.write_text(), sa forskningsresultatet aldrig skrivs.

Denna wrapper anropar EXAKT samma funktioner med EXAKT samma argument som originalets
main() gor, i samma ordning, och skriver forskningsnyttolasten separat. Ingen
signaldefinition, parameter, ranking, feature eller universumlogik ar rord, och ingen
forskningsdel ar borttagen.

Kor via central runner i REVALIDATION-mode.
"""
from __future__ import annotations
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
OUT = V2 / "research_k/tidig_detektion_research_only_results.json"
ORIGINAL = V2 / "tools/tidig_detektion_och_utdelning.py"


def main() -> None:
    import tidig_detektion_och_utdelning as T
    import stack_h_motor as S

    ut = {"version": "TIDIG_DETEKTION_RESEARCH_ONLY_V1",
          "wrapper_note": "endast forskningsdelarna; del3_utdelning() ar utelamnad och kors "
                          "separat i DATA_QA-mode",
          "original_script": str(ORIGINAL.relative_to(V2)),
          "original_sha256": hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),
          "wrapper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

    # --- identiskt med originalets main(), block 1
    ut["detektion"] = {"2020_2026": T.del1_detektion(S.F26, "2020-2026"),
                       "2014_2019": T.del1_detektion(S.F19, "2014-2019")}

    # --- identiskt med originalets main(), block 2
    bas26, bas19 = S.kor(**S.F26)[0], S.kor(**S.F19)[0]
    ut["rotation"] = {}
    for t in (0.5, 1.0, 2.0, -1.0):
        a26, a19 = T.del2_rotera(S.F26, t), T.del2_rotera(S.F19, t)
        d26, d19 = S.boot(a26, bas26), S.boot(a19, bas19)
        rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
        ut["rotation"][f"tilt_{t}"] = {"f2020_2026": {**S.stat(a26), **d26},
                                       "f2014_2019": {**S.stat(a19), **d19},
                                       "bada_positiva": bool(rep)}

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
