"""H0_V3_WINDOW_2_EXTENSION — strikt temporal utvidgning av fryst H0 V3.

Ingen H0-logik duplicerad. Modulen tools/h0_v3_kor.py importeras och dess main()
anropas oforandrad. Det enda som tillfors ar mekaniken for att peka ut ett annat
fonster:

  PREREG / FREEZE   -> fonster-2-preregistreringen och dess frysning
  OUT               -> fonster-2-resultatfilen
  _ISIN             -> identitetshint for 2020-2026-universumet
  prisfilen         -> omdirigeras via revalidation_sandbox (sokvagen ar hardkodad
                       INUTI main() och kan inte nas som modulkonstant)

Signal, momentumdefinition, lookbacks, ranking, Top-N, rebalanscadens, viktning,
SMA200-grind, bekraftelsemultiplikator, vikttak, eligibility-semantik, PIT-medlemskap,
identitetshantering, avnoteringshantering, missing-data, kostnader, benchmark och
portfoljkonstruktion ar OFORANDRADE — de ligger i den importerade modulen.

Kor:
  python tools/h0_v3_window2_kor.py --mode negative-control   (fonster 1, reproduktion)
  python tools/h0_v3_window2_kor.py --mode window2            (fonster 2)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))

W2 = V2 / "research_k/h0_v3_window2"
PRICES_W1 = V2 / "validated/prices_h1419/prices_h1419_universum_v2.json"
PRICES_W2 = V2 / "validated/prices/prices_validated.json"


def sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def bygg_isin_hint() -> dict:
    """Ticker -> ISIN for fonster 2, samma semantiska roll som fonster 1:s hint.

    Fonster 1 tog ISIN ur membership_h1419_v2.json:s 'kalla'-falt. Fonster 2:s
    analog ar den kanoniska identitetskartan, vars isin_aliases for Main
    Market-instrument kommer ur Nasdaq-mastern — exakt den kalla som
    h0_v3_eligibility matchar mot.
    """
    idm = json.loads((V2 / "research_k/canonical_identity/CANONICAL_IDENTITY_MAP.json").read_text())
    ut = {}
    for e in idm["entries"]:
        al = [a["isin"] for a in (e.get("isin_aliases") or [])
              if a.get("isin") and len(a["isin"]) == 12 and a["isin"][:2].isalpha()]
        if al:
            ut[e["instrument_id"]] = al[0]
    return ut


def kor(mode: str) -> dict:
    import revalidation_sandbox as S
    import h0_v3_kor as H

    if mode == "negative-control":
        # Ingen omdirigering, ingen patch. Exakt den frysta korningen, men med
        # utdata till en kontrollfil sa att originalet inte ror sig.
        H.OUT = W2 / "negative_control_window1_result.json"
        W2.mkdir(parents=True, exist_ok=True)
        H.main()
        return {"mode": mode, "out": str(H.OUT)}

    # ---- fonster 2
    pre = W2 / "preregistration.json"
    frz = W2 / "PREREG_FREEZE.json"
    if not (pre.exists() and frz.exists()):
        sys.exit("AVBRYTER: fonster-2-preregistreringen ar inte last.")
    if sha(pre) != json.loads(frz.read_text())["sha256"]:
        sys.exit("AVBRYTER: fonster-2-preregistreringen har andrats efter frysningen.")

    S.install({str(PRICES_W1): str(PRICES_W2)}, [], "H0V3-W2", "H0_V3_WINDOW_2_EXTENSION")
    H.PREREG = pre
    H.FREEZE = frz
    H.OUT = W2 / "result.json"
    H._ISIN = bygg_isin_hint()
    H.main()
    S.uninstall()
    (W2 / "sandbox_access_log.json").write_text(json.dumps(S.LOG, ensure_ascii=False, indent=1))
    return {"mode": mode, "out": str(H.OUT), "redirects": len(S.LOG)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["negative-control", "window2"])
    a = ap.parse_args()
    print(json.dumps(kor(a.mode), ensure_ascii=False))
