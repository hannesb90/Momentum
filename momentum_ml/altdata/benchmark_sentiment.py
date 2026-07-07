"""
altdata/benchmark_sentiment.py – Steg 3: benchmarka lokal modell mot Claude.

Kör SAMMA urval PM genom båda backends (score_item med backend='claude' resp.
'ollama', samma prompt/schema – se sentiment.py) och jämför:
  · Samstämmighet: andel identiska sentiment/guidance/materiality/kategori
  · Genomsnittlig avvikelse på de numeriska fälten
  · Prediktivt värde: kör backtest_sentiment.py-liknande spread separat per
    backend (kräver att båda scorats för samma PM-mängd)

Skriver INTE över den skarpa sentiment-cachen – körs mot en separat cache-
katalog (BENCHMARK_CACHE_DIR) så produktionsdata aldrig rör vid detta.

    python -m altdata.benchmark_sentiment run 500   # scorar 500 slumpade cachade PM med båda
    python -m altdata.benchmark_sentiment compare    # jämför resultaten
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from altdata import sentiment as sent


def _bench_dir(backend: str) -> Path:
    d = Path(config.anchor(getattr(config, "BENCHMARK_CACHE_DIR", "cache/sentiment_benchmark"))) / backend
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sample_items(n: int) -> list:
    """Slumpa n redan hämtade MFN-poster (samma källa som skarp drift) för
    en rättvis, existerande jämförelsemängd."""
    mdir = Path(config.anchor(config.MFN_CACHE_DIR))
    pool = []
    for f in mdir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            items = json.loads(f.read_text(encoding="utf-8")).get("items", [])
        except Exception:  # noqa: BLE001
            continue
        pool.extend(items)
    random.seed(42)   # reproducerbart urval
    return random.sample(pool, min(n, len(pool)))


def run(n: int = 500):
    items = _sample_items(n)
    if not items:
        print("Ingen MFN-cache – kör mfn_fetch.py fetch_universe först.")
        return
    print(f"[benchmark] {len(items)} PM utvalda (seed=42, reproducerbart)")

    for backend in ("claude", "ollama"):
        print(f"\n[{backend}] scorar...")
        cache = _bench_dir(backend)
        done = 0
        for it in items:
            cp = cache / (sent._cid(it["id"]) + ".json")
            if cp.exists():
                done += 1
                continue
            try:
                if backend == "ollama":
                    parsed = sent._ollama_score(it)
                else:
                    client = sent._client()
                    msg = client.messages.create(
                        model=config.SENTIMENT_MODEL, max_tokens=config.SENTIMENT_MAX_TOKENS,
                        system=sent._SYSTEM, messages=[{"role": "user", "content": sent._prompt(it)}],
                    )
                    parsed = sent._parse_content(msg)
                if parsed:
                    cp.write_text(json.dumps(parsed, ensure_ascii=False))
                    done += 1
            except Exception as e:  # noqa: BLE001
                print(f"  [{backend}] {it['id']}: FEL {e}")
        print(f"[{backend}] klart: {done}/{len(items)}")


def compare():
    ca, oa = _bench_dir("claude"), _bench_dir("ollama")
    common = sorted(set(f.name for f in ca.glob("*.json")) & set(f.name for f in oa.glob("*.json")))
    if not common:
        print("Ingen överlappande scorad mängd – kör 'run' först.")
        return
    print(f"[compare] {len(common)} PM scorade av båda backends\n")

    fields = ["sentiment", "materiality", "guidance", "ceo_tone", "category"]
    agree = {f: 0 for f in fields}
    abs_diff = {f: [] for f in fields if f != "category"}
    for name in common:
        c = json.loads((ca / name).read_text())
        o = json.loads((oa / name).read_text())
        for f in fields:
            if c.get(f) == o.get(f):
                agree[f] += 1
            if f != "category" and isinstance(c.get(f), (int, float)) and isinstance(o.get(f), (int, float)):
                abs_diff[f].append(abs(c[f] - o[f]))

    print(f"{'fält':<14}{'samstämmighet':>15}{'snittavvikelse':>16}")
    for f in fields:
        pct = agree[f] / len(common)
        dev = (sum(abs_diff[f]) / len(abs_diff[f])) if f in abs_diff and abs_diff[f] else float("nan")
        dev_s = f"{dev:.2f}" if dev == dev else "  –"
        print(f"{f:<14}{pct:>14.0%}{dev_s:>16}")

    print("""
  Tolkning: hög samstämmighet (>70%) på sentiment/guidance/materiality och låg
  snittavvikelse (<0.5) → lokal modell duger för produktion, byt backend och
  spara alla framtida API-kostnader. Låg samstämmighet → kör historik-backfillen
  med Claude batch (billigare ändå, -50%) och spara Ollama för daglig drift av
  NYA PM där kvalitetskravet är lägre (färsk signal, snabb OOS-korrigering).
  Nästa steg om lokal håller: kör tune_case_tracker.py separat per backends
  cache för att jämföra PREDIKTIVT värde, inte bara samstämmighet.""")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if cmd == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 500)
    elif cmd == "compare":
        compare()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
