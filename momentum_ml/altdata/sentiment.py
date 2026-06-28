"""
altdata/sentiment.py – Poängsätter MFN-pressmeddelanden med Claude (sentiment +
materialitet). Bygger ovanpå cachen från mfn_fetch.py och cachar varje poäng per
PM-id, så samma PM aldrig betalas för två gånger.

Modell: Haiku 4.5 (config.SENTIMENT_MODEL) – billig och fullt tillräcklig för
klassificering. Batch-API:t (-50%) används för den historiska massan; enstaka
live-PM kan poängsättas direkt.

API-nyckeln läses ur miljövariabeln ANTHROPIC_API_KEY – ALDRIG i koden/repot.

Körs på Pi:n (samma plats som MFN-cachen):

    export ANTHROPIC_API_KEY=sk-ant-...           # i ~/.momentum.env, ej i repot
    /opt/momentum/venv/bin/python altdata/sentiment.py score large   # poängsätt segment
    /opt/momentum/venv/bin/python altdata/sentiment.py one  AAA.ST   # ett bolag

Resultat cachas i cache/sentiment/<id>.json och läses av backtest_sentiment.py.
"""
import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import anthropic
except ImportError:
    anthropic = None


# Strikt JSON-schema för svaret. Vi tolkar content som JSON själva (funkar
# identiskt för enstaka anrop och batch, oberoende av SDK-version på Pi:n).
_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "integer", "minimum": -2, "maximum": 2,
                "description": "Tonen i meddelandet för aktieägare: -2 mycket "
                               "negativ, 0 neutral, +2 mycket positiv.",
            },
            "materiality": {
                "type": "integer", "minimum": 0, "maximum": 3,
                "description": "Hur kurspåverkande nyheten är: 0 rutin/admin, "
                               "1 mindre, 2 väsentlig, 3 mycket väsentlig.",
            },
            "category": {
                "type": "string",
                "enum": ["report", "guidance", "order", "ma", "capital",
                         "personnel", "legal", "product", "other"],
            },
            "rationale": {"type": "string", "description": "Max en mening, svenska."},
        },
        "required": ["sentiment", "materiality", "category", "rationale"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "Du är en erfaren svensk aktieanalytiker. Du läser ett regulatoriskt "
    "pressmeddelande och bedömer enbart hur en rationell investerare borde tolka "
    "TONEN och MATERIALITETEN för bolagets aktie de närmaste veckorna – inte "
    "vad du redan vet om bolaget i efterhand. Var nykter: rubriker är ofta "
    "positivt vinklade av bolaget självt. Svara endast enligt schemat."
)


def _client():
    if anthropic is None:
        raise RuntimeError("paketet 'anthropic' saknas – pip install anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY saknas i miljön (lägg i ~/.momentum.env, ej i repot)")
    return anthropic.Anthropic()


def _prompt(item: dict) -> str:
    return (f"PUBLICERAT: {item.get('published','')}\n"
            f"RUBRIK: {item.get('title','')}\n\n"
            f"TEXT:\n{item.get('text','')}")


def _cache_path(pid: str) -> Path:
    d = Path(config.SENTIMENT_CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in pid)[:80]
    return d / f"{safe}.json"


def _parse_content(msg) -> Optional[dict]:
    for block in msg.content:
        txt = getattr(block, "text", None)
        if txt:
            try:
                return json.loads(txt)
            except Exception:
                continue
    return None


# ── Enstaka anrop (live) ──────────────────────────────────────────────────────
def score_item(item: dict, client=None) -> Optional[dict]:
    cp = _cache_path(item["id"])
    if cp.exists():
        return json.loads(cp.read_text())
    client = client or _client()
    msg = client.messages.create(
        model=config.SENTIMENT_MODEL,
        max_tokens=config.SENTIMENT_MAX_TOKENS,
        system=_SYSTEM,
        output_config={"format": _SCHEMA},
        messages=[{"role": "user", "content": _prompt(item)}],
    )
    parsed = _parse_content(msg)
    if parsed:
        parsed["id"] = item["id"]
        cp.write_text(json.dumps(parsed, ensure_ascii=False))
    return parsed


# ── Batch (historisk massa, -50%) ─────────────────────────────────────────────
def score_batch(items: List[dict]) -> Dict[str, dict]:
    """Poängsätter en lista PM via Batch-API:t. Hoppar över redan cachade."""
    todo = [it for it in items if not _cache_path(it["id"]).exists()]
    cached = {it["id"]: json.loads(_cache_path(it["id"]).read_text())
              for it in items if _cache_path(it["id"]).exists()}
    if not todo:
        return cached
    client = _client()

    requests = [{
        "custom_id": it["id"][:64],
        "params": {
            "model": config.SENTIMENT_MODEL,
            "max_tokens": config.SENTIMENT_MAX_TOKENS,
            "system": _SYSTEM,
            "output_config": {"format": _SCHEMA},
            "messages": [{"role": "user", "content": _prompt(it)}],
        },
    } for it in todo]
    id_by_custom = {it["id"][:64]: it["id"] for it in todo}

    print(f"[batch] skickar {len(requests)} PM till {config.SENTIMENT_MODEL} (Batch-API, -50%)")
    batch = client.messages.batches.create(requests=requests)
    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        print(f"  ...status={b.processing_status} ({b.request_counts})")
        time.sleep(15)

    for res in client.messages.batches.results(batch.id):
        if res.result.type != "succeeded":
            continue
        parsed = _parse_content(res.result.message)
        if not parsed:
            continue
        pid = id_by_custom.get(res.custom_id, res.custom_id)
        parsed["id"] = pid
        _cache_path(pid).write_text(json.dumps(parsed, ensure_ascii=False))
        cached[pid] = parsed
    print(f"[batch] klart – {len(cached)} poäng totalt")
    return cached


# ── Orchestrering ─────────────────────────────────────────────────────────────
def _load_cached_releases(segment: str) -> List[dict]:
    from data.data_loader import load_sweden_universe
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    cache_dir = Path(config.MFN_CACHE_DIR)
    out = []
    for t in tickers:
        p = cache_dir / f"{t}.json"
        if not p.exists():
            continue
        blob = json.loads(p.read_text())
        for it in blob.get("items", []):
            it = dict(it)
            it["ticker"] = t
            out.append(it)
    return out


def score_segment(segment: str) -> None:
    items = _load_cached_releases(segment)
    if not items:
        print(f"[score] inga cachade PM för '{segment}' – kör mfn_fetch.py fetch {segment} först.")
        return
    print(f"[score] {len(items)} PM att poängsätta (cachade hoppas över)")
    if config.SENTIMENT_USE_BATCH:
        score_batch(items)
    else:
        client = _client()
        for i, it in enumerate(items, 1):
            score_item(it, client)
            if i % 25 == 0:
                print(f"  ...{i}/{len(items)}")
    print("[score] klart – kör backtest_sentiment.py för OOS-utvärdering.")


def score_one(ticker: str) -> None:
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        print(f"[score] {p} saknas – kör mfn_fetch.py först.")
        return
    items = json.loads(p.read_text()).get("items", [])
    client = _client()
    for it in items[:5]:
        s = score_item(it, client)
        print(f"\n[{it.get('published','')}] {it.get('title','')[:70]}")
        print(f"  → {s}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "score":
        score_segment(sys.argv[2] if len(sys.argv) > 2 else config.DEFAULT_SEGMENT)
    elif cmd == "one":
        score_one(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
