"""
portfolio.py – Portfölj-medveten analys + nytt-kapital-plan.

Läser dina innehav (cache/portfolio_holdings.csv – GITIGNORERAD, personlig data),
klassar per hink (broad/sweden/theme/leverage), jämför mot en diversifierad
mål-fördelning (config.PORTFOLIO_TARGET) och riktar NYTT kapital mot det du är
underviktad i. Fyll-mot-mål via inflöden – ingen försäljning, ingen skatt, ingen
timing. Skriver results/portfolio_analysis.json för appen.

    python portfolio.py analyze            # nuläge + koncentrationsvarningar
    python portfolio.py newcapital 10000   # hur denna månads 10 000 kr bör placeras

Holdings-CSV (skapa på Pi:n): kolumner  name,value_sek,bucket
  bucket ∈ {broad, sweden, theme, leverage}
"""
import sys
import csv
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

_BUCKET_LABEL = {"broad": "Bred kärna (World/US/EM)", "sweden": "Sverige",
                 "theme": "Tematiskt", "leverage": "Hävstång"}


def _load():
    p = Path(config.PORTFOLIO_HOLDINGS_FILE)
    if not p.exists():
        print(f"[portfolio] {p} saknas. Skapa den med kolumner name,value_sek,bucket "
              "(bucket: broad/sweden/theme/leverage).")
        return None
    rows = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"name": r["name"], "value": float(r["value_sek"]),
                             "bucket": (r.get("bucket") or "theme").strip()})
            except (ValueError, KeyError):
                continue
    return rows


def _by_bucket(rows):
    out = {}
    for r in rows:
        out[r["bucket"]] = out.get(r["bucket"], 0.0) + r["value"]
    return out


def analyze():
    rows = _load()
    if not rows:
        return
    total = sum(r["value"] for r in rows)
    buckets = _by_bucket(rows)
    print(f"\n  PORTFÖLJ – {total:,.0f} kr, {len(rows)} innehav\n".replace(",", " "))
    print(f"  {'Hink':<26}{'nu':>8}{'mål':>8}{'diff':>8}")
    for b in ("broad", "sweden", "theme", "leverage"):
        cur = buckets.get(b, 0.0) / total
        tgt = config.PORTFOLIO_TARGET.get(b, 0.0)
        print(f"  {_BUCKET_LABEL[b]:<26}{cur:>7.0%}{tgt:>8.0%}{cur - tgt:>+8.0%}")

    print("\n  Varningar:")
    warn = []
    if buckets.get("broad", 0) / total < 0.1:
        warn.append("Ingen bred diversifierad kärna – allt är riktade vad.")
    if buckets.get("leverage", 0) > 0:
        warn.append(f"Hävstång i portföljen ({buckets['leverage']/total:.0%}) – decay/ruinrisk på sikt.")
    big = sorted(rows, key=lambda r: -r["value"])[0]
    if big["value"] / total > 0.12:
        warn.append(f"Störst enskilt innehav: {big['name']} ({big['value']/total:.0%}).")
    if buckets.get("theme", 0) / total > 0.30:
        warn.append(f"Hög tema-koncentration ({buckets['theme']/total:.0%}) – rör sig ofta ihop.")
    for w in warn:
        print(f"   ⚠ {w}")
    _write(rows, total, buckets)


def newcapital(amount):
    rows = _load()
    if not rows:
        return
    total = sum(r["value"] for r in rows)
    buckets = _by_bucket(rows)
    after = total + amount
    # Gap = hur många kr som fattas för att nå mål EFTER insättningen (bara underviktade).
    gaps = {b: max(0.0, config.PORTFOLIO_TARGET.get(b, 0.0) * after - buckets.get(b, 0.0))
            for b in config.PORTFOLIO_TARGET}
    gsum = sum(gaps.values()) or 1.0
    plan = {b: amount * g / gsum for b, g in gaps.items() if g > 0}

    print(f"\n  NYTT KAPITAL: {amount:,.0f} kr → fyll mot målet (ingen försäljning)\n".replace(",", " "))
    for b, kr in sorted(plan.items(), key=lambda x: -x[1]):
        print(f"   {_BUCKET_LABEL[b]:<26}{kr:>10,.0f} kr   ({kr/amount:.0%})".replace(",", " "))
    # Konkreta ETF-förslag för den breda kärnan (dit merparten går när broad=0).
    if plan.get("broad", 0) > 0:
        n = len(config.PORTFOLIO_BROAD_ETFS)
        print("\n   Bred kärna – dela lika över:")
        for lbl, tk in config.PORTFOLIO_BROAD_ETFS.items():
            print(f"     {lbl:<20}{tk:<10}{plan['broad']/n:>9,.0f} kr".replace(",", " "))
    print("\n  Logik: du är kraftigt underviktad bred kärna (~0%), så nästan allt nytt "
          "kapital dit tills basen är byggd. Inget säljs – koncentrationen späds över tid.")
    _write(rows, total, buckets, plan=plan, amount=amount)


def _write(rows, total, buckets, plan=None, amount=None):
    out = Path("results/portfolio_analysis.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {"total": round(total, 0),
            "buckets": {b: round(buckets.get(b, 0.0) / total, 4) for b in config.PORTFOLIO_TARGET},
            "target": config.PORTFOLIO_TARGET,
            "holdings": [{"name": r["name"], "value": r["value"], "bucket": r["bucket"]} for r in rows]}
    if plan is not None:
        data["newcapital"] = {"amount": amount, "plan": {b: round(v) for b, v in plan.items()}}
    out.write_text(json.dumps(data, ensure_ascii=False))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    if cmd == "analyze":
        analyze()
    elif cmd == "newcapital":
        newcapital(float(sys.argv[2]) if len(sys.argv) > 2 else 10000)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
