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
import re
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


# Svaret begärs som ren JSON via INSTRUKTION (inte output_config/structured
# outputs). Skälet: det exakta output_config-formatet är SDK-/modellversions-
# känsligt och ett fel ger 400 mitt i en betald bulk-körning. Prompt-instruerad
# JSON + robust parsning fungerar på vilken Claude-modell/SDK-version som helst –
# och uppgiften (klassificering) är trivial för Haiku att svara strikt på.
_CATEGORIES = ["report", "guidance", "order", "ma", "capital",
               "personnel", "legal", "product", "other"]

_SYSTEM = (
    "Du är en erfaren svensk aktieanalytiker. Du läser ett regulatoriskt "
    "pressmeddelande och bedömer enbart hur en rationell investerare borde tolka "
    "TONEN och MATERIALITETEN för bolagets aktie de närmaste veckorna – inte "
    "vad du redan vet om bolaget i efterhand. Var nykter: rubriker är ofta "
    "positivt vinklade av bolaget självt.\n\n"
    "Svara ENDAST med ett giltigt JSON-objekt – ingen prosa, inga markdown-fences – "
    "med exakt dessa fält:\n"
    '  "sentiment": heltal -2..2 (ton för aktieägare; -2 mkt negativ, 0 neutral, +2 mkt positiv)\n'
    '  "materiality": heltal 0..3 (kurspåverkan; 0 rutin/admin, 1 mindre, 2 väsentlig, 3 mkt väsentlig)\n'
    f'  "category": en av {_CATEGORIES}\n'
    '  "rationale": max en mening på svenska\n'
    'Exempel: {"sentiment": 1, "materiality": 2, "category": "order", "rationale": "Stororder lyfter orderboken."}'
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


def _valid(d) -> bool:
    """Grundkontroll så vi inte cachar skräp-parsningar."""
    return (isinstance(d, dict) and isinstance(d.get("sentiment"), (int, float))
            and isinstance(d.get("materiality"), (int, float)))


def _parse_content(msg) -> Optional[dict]:
    for block in msg.content:
        txt = getattr(block, "text", None)
        if not txt:
            continue
        try:
            d = json.loads(txt)
            if _valid(d):
                return d
        except Exception:
            pass
        # Fallback: plocka ut första {...}-blocket om modellen lagt till prosa.
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                if _valid(d):
                    return d
            except Exception:
                pass
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
    # Defensiv dedup på id: aldrig betala för samma PM två gånger (A/B-aktier),
    # även om anroparen skickar dubbletter.
    todo, seen = [], set()
    cached = {}
    for it in items:
        pid = it["id"]
        if pid in seen:
            continue
        seen.add(pid)
        cp = _cache_path(pid)
        if cp.exists():
            cached[pid] = json.loads(cp.read_text())
        else:
            todo.append(it)
    if not todo:
        return cached
    client = _client()

    # custom_id måste vara unikt + giltigt (≤64 tecken, [a-zA-Z0-9_-]). MFN-id:n
    # kan innehålla otillåtna tecken/kollidera vid trunkering → använd index-id.
    requests = [{
        "custom_id": f"r{i}",
        "params": {
            "model": config.SENTIMENT_MODEL,
            "max_tokens": config.SENTIMENT_MAX_TOKENS,
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": _prompt(it)}],
        },
    } for i, it in enumerate(todo)]
    id_by_custom = {f"r{i}": it["id"] for i, it in enumerate(todo)}

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
    floor = str(getattr(config, "SENTIMENT_SCORE_FROM", "2015-09-01"))
    out, skipped, dups = [], 0, 0
    seen = set()
    for t in tickers:
        p = cache_dir / f"{t}.json"
        if not p.exists():
            continue
        blob = json.loads(p.read_text())
        for it in blob.get("items", []):
            # Datumgolv: poängsätt bara PM vi faktiskt backtestar (OOS-fönstret) –
            # ISO-datum jämförs lexikografiskt, så strängjämförelsen räcker.
            if str(it.get("published", "")) < floor:
                skipped += 1
                continue
            # DEDUP på news_id: samma PM ligger i både A- och B-aktiens cache
            # (samma emittent). Utan detta poängsätts (= betalas för) samma PM två
            # gånger i batchen, och estimate räknar dubbelt.
            pid = it.get("id")
            if pid in seen:
                dups += 1
                continue
            seen.add(pid)
            it = dict(it)
            it["ticker"] = t
            out.append(it)
    if skipped:
        print(f"[score] hoppar över {skipped} PM före {floor} (utanför OOS – spar kostnad)")
    if dups:
        print(f"[score] dedup: {dups} dubblett-PM (A/B-aktier, samma emittent) – betalas en gång")
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


def estimate_cost(segment: str) -> None:
    """OFFLINE kostnadsestimat (ingen nyckel/anrop): räknar PM i OOS-fönstret och
    projicerar batch-kostnaden. Token-heuristik: ~4 tecken/token (svensk text)."""
    items = _load_cached_releases(segment)
    n = len(items)
    if not n:
        print(f"[estimate] inga cachade PM för '{segment}' – kör mfn_fetch.py fetch {segment} först.")
        return
    sys_tok = len(_SYSTEM) / 4.0
    in_tok = sum(sys_tok + len(_prompt(it)) / 4.0 for it in items)
    out_tok = n * 70.0                       # JSON-svaret är litet (~70 tokens)
    # Haiku 4.5: $1/1M in, $5/1M ut. Batch = -50%. (USD)
    full = in_tok / 1e6 * 1.0 + out_tok / 1e6 * 5.0
    batch = full * 0.5
    usd_sek = 10.6
    print("\n" + "=" * 60)
    print(f"  KOSTNADSESTIMAT ({segment}) – {config.SENTIMENT_MODEL}, OFFLINE")
    print("=" * 60)
    print(f"  PM att poängsätta (>= {getattr(config,'SENTIMENT_SCORE_FROM','?')}):  {n:,}")
    print(f"  Snitt input-tokens/PM:   {in_tok/n:,.0f}")
    print(f"  Totalt input-tokens:     {in_tok/1e6:,.2f}M")
    print(f"  Totalt output-tokens:    {out_tok/1e6:,.2f}M")
    print("-" * 60)
    print(f"  Fullpris:   ${full:,.2f}   (~{full*usd_sek:,.0f} kr)")
    print(f"  Batch -50%: ${batch:,.2f}   (~{batch*usd_sek:,.0f} kr)   <- vi använder denna")
    print("-" * 60)
    print("  OBS: konservativt – promptcache (systemprompten är identisk) kan sänka")
    print("  input-kostnaden ytterligare. Token-heuristik ±20%.")


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
    elif cmd == "estimate":
        estimate_cost(sys.argv[2] if len(sys.argv) > 2 else config.DEFAULT_SEGMENT)
    elif cmd == "one":
        score_one(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
