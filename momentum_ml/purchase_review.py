"""Dagsfärsk, source-backed pre-purchase review for a Momentum candidate."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import claude_headless as ch  # noqa: E402
import config  # noqa: E402
import security_analysis as sa  # noqa: E402
from altdata import manual_scan as ms  # noqa: E402


_TOOLS = "WebSearch"
_VERDICTS = {"clear", "review", "block_new_entry"}
_CACHE_DIR = Path(config.anchor("results/purchase_reviews"))
_PROMPT = """Du är Momentums oberoende KÖPGRANSKARE. Momentum har redan valt
bolaget; din uppgift är att dagsfärskt försöka falsifiera köpcaset och hitta
sådant som modellens strukturerade universum kan sakna.

Gör flera WebSearch-sökningar på bolagsnamn/ticker och kontrollera i första hand:
- senaste bolagsmeddelanden/rapport och officiella myndighets-/börskällor,
- kritik, rättsprocesser, sanktioner, blankning, lednings-/revisorsavhopp,
- föreslagna eller beslutade regulatoriska krav,
- finansiering, emission, covenant-, likviditets- och going-concern-risk,
- nya kontrakt, godkännanden, insiderköp eller andra positiva katalysatorer,
- om de NUMERISKA fälten i underlaget blivit inaktuella.

Skilj fakta från tolkning. Varje faktor och varje sifferuppdatering MÅSTE ha
en direkt käll-URL och källdatum. Ingen URL = utelämna påståendet. Föreslå
bara uppdatering av ett universumfält när källan uttryckligen stödjer värdet.
Använd block_new_entry bara för en ny, materiell och trovärd risk som rimligen
kan ogiltigförklara köpet; osäker/motstridig information ska ge review.

Svara ENDAST med giltig kompakt JSON:
{{
  "verdict": "clear|review|block_new_entry",
  "confidence": 0.0,
  "summary": "kort svensk slutsats",
  "positive_signals": [
    {{"claim":"...", "source_url":"https://...", "source_date":"YYYY-MM-DD",
      "materiality":"low|medium|high"}}
  ],
  "negative_signals": [samma schema],
  "proposed_universe_updates": [
    {{"field":"befintligt_fältnamn", "old_value":null, "new_value":null,
      "unit":"...", "as_of":"YYYY-MM-DD", "source_url":"https://...",
      "reason":"..."}}
  ],
  "unresolved_questions": ["..."]
}}

DAGENS DATUM: {today}
MOMENTUMS BEFINTLIGA UNDERLAG:
{underlag}
"""


def _valid_url(value) -> bool:
    try:
        parsed = urlparse(str(value))
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def validate_review(raw: dict) -> dict:
    """Fail closed on malformed decisions; discard unsourced individual claims."""
    if not isinstance(raw, dict):
        return {"error": "Claude returnerade inte ett JSON-objekt."}
    verdict = raw.get("verdict")
    if verdict not in _VERDICTS:
        return {"error": f"Ogiltigt verdict: {verdict!r}"}
    try:
        confidence = min(1.0, max(0.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    def sourced(items):
        return [
            item for item in (items or [])
            if isinstance(item, dict)
            and item.get("claim")
            and item.get("source_date")
            and _valid_url(item.get("source_url"))
        ]

    updates = [
        item for item in (raw.get("proposed_universe_updates") or [])
        if isinstance(item, dict)
        and item.get("field")
        and item.get("as_of")
        and item.get("new_value") is not None
        and _valid_url(item.get("source_url"))
    ]
    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": str(raw.get("summary") or "").strip(),
        "positive_signals": sourced(raw.get("positive_signals")),
        "negative_signals": sourced(raw.get("negative_signals")),
        "proposed_universe_updates": updates,
        "unresolved_questions": [
            str(x) for x in (raw.get("unresolved_questions") or []) if str(x).strip()
        ],
    }


def review(ticker: str, amount: float = 10000, segment: str | None = None) -> dict:
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return {"error": "Ticker saknas."}
    scan = ms.scan(ticker, {}, segment=segment)
    impact = sa._portfolio_impact(ticker, scan.get("name"), float(amount))
    underlag = sa._underlag(ticker, scan, impact)
    today = datetime.now(timezone.utc).date().isoformat()
    raw = ch.run(
        _PROMPT.format(today=today, underlag=underlag),
        _TOOLS,
        timeout=240,
    )
    if "error" in raw:
        return {"ticker": ticker, "as_of": today, "error": raw["error"]}
    result = validate_review(raw)
    result.update({"ticker": ticker, "name": scan.get("name"),
                   "as_of": today, "amount": float(amount)})
    if "error" not in result:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = _CACHE_DIR / f"{ticker.replace('/', '_')}_{today}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, target)
    return result


if __name__ == "__main__":
    print(json.dumps(review(sys.argv[1]), ensure_ascii=False, indent=2))
