"""Build the V2 Nasdaq Stockholm main-market PIT membership ledger.

The study starts in 2020.  A price history, a Börsdata marketId, or a later
name/domicile change is never treated as proof of main-market membership.
Only dated admissions/switches in Nasdaq's own notices are verified membership.
For all other instruments the admission date is unknown: the study start is an
observation-window boundary, never an invented membership date.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "validated/membership_main_list_pit.json"

# Dated official admissions affecting codes present in the V2 price universe.
# Dates are first days of trading on Nasdaq Stockholm Main Market.
ADMISSIONS = {
    "AJA-B": ("2024-06-19", "https://www.skatteverket.se/privat/skatter/vardepapper/aktiehistorik/b/byggmastareandersjahlstromholding.4.12815e4f14a62bc048f1bb9.html"),
    "MAHA-A": ("2020-12-16", "https://www.nasdaq.com/docs/2021/04/28/0850-Q21_Surveillance-Annual-Report-2020-Update_OGC-V2.pdf"),
    "TRIAN-B": ("2020-12-17", "https://view.news.eu.nasdaq.com/view?id=b5e092f1f87f0bee257fc1d49655a4395&lang=en"),
    "CIBUS": ("2021-06-01", "https://view.news.eu.nasdaq.com/view?id=b962695069092abd205e07a3b25ad262c&lang=en"),
    "CCC": ("2025-07-09", "https://www.skatteverket.se/privat/skatter/vardepapper/aktiehistorik/c/cavotecgroup.4.40cab8f8197edf03e64b7e.html"),
    "MANG": ("2022-02-24", "https://view.news.eu.nasdaq.com/view?id=bcbec1af5f35799d334682d260724f285&lang=en"),
    "OX2": ("2022-04-06", "https://www.nasdaq.com/docs/2025/02/27/Changes-to-the-list-Nasdaq-Stockholm-2022.pdf"),
    "FNOX": ("2022-04-13", "https://www.nasdaq.com/press-release/nasdaq-stockholm-welcomes-fortnox-to-the-nasdaq-main-market-2022-04-13"),
    "CS": ("2022-12-19", "https://view.news.eu.nasdaq.com/view?id=b73bb1e1553859aa75da92f912793c707&lang=en"),
}


def main() -> None:
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    rows = []
    for code in sorted(prices):
        admission = ADMISSIONS.get(code)
        member_from, source = admission if admission else (None, None)
        rows.append({
            "kod": code,
            "member_from": member_from,
            "member_to": None,
            "source": source,
            "membership_verified": bool(source),
            "basis": "NASDAQ_DATED_ADMISSION" if source else "HISTORICAL_MEMBERSHIP_UNKNOWN",
            "observation_window_from": "2020-01-01",
        })
    payload = {
        "definition": "Nasdaq Stockholm Main Market (Large/Mid/Small), not First North/NGM/Spotlight",
        "study_start": "2020-01-01",
        "rules": [
            "price existence is not membership",
            "current Börsdata marketId is not backfilled membership evidence",
            "name/redomiciliation events do not reset membership",
            "post-start admission requires a dated Nasdaq source",
        ],
        "coverage": {
            "n_codes": len(rows), "n_dated_post_start_admissions": len(ADMISSIONS),
            "n_membership_verified": len(ADMISSIONS),
            "n_membership_unknown": len(rows) - len(ADMISSIONS),
            "unknown_handling": "member_from=null; observable trading is retained from the study window, but is never described as verified membership.",
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{OUT}: {len(rows)} codes, sha256={hashlib.sha256(OUT.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
