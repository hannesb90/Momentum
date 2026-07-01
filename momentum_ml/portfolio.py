"""
portfolio.py – Portfölj-medveten analys + nytt-kapital-plan.

Läser dina innehav (cache/portfolio_holdings.csv – GITIGNORERAD, personlig data),
klassar per hink (broad/sweden/theme/leverage), jämför mot en diversifierad
mål-fördelning (config.PORTFOLIO_TARGET) och riktar NYTT kapital mot det du är
underviktad i. Fyll-mot-mål via inflöden – ingen försäljning, ingen skatt, ingen
timing. Innehav läggs in manuellt (CLI eller i appen, som skriver samma fil).

    python portfolio.py analyze
    python portfolio.py newcapital 10000
"""
import sys
import csv
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config

BUCKETS = ("broad", "sweden", "theme", "leverage")
BUCKET_LABEL = {"broad": "Bred kärna (World/US/EM)", "sweden": "Sverige",
                "theme": "Tematiskt", "leverage": "Hävstång"}


def holdings_path() -> Path:
    return Path(config.PORTFOLIO_HOLDINGS_FILE)


def load_holdings() -> list:
    p = holdings_path()
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"name": r["name"].strip(), "value": float(r["value_sek"]),
                             "bucket": (r.get("bucket") or "theme").strip()})
            except (ValueError, KeyError):
                continue
    return rows


def save_holdings(rows) -> None:
    p = holdings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "value_sek", "bucket"])
        w.writeheader()
        for r in rows:
            b = r.get("bucket", "theme")
            w.writerow({"name": r.get("name", ""),
                        "value_sek": float(r.get("value", r.get("value_sek", 0)) or 0),
                        "bucket": b if b in BUCKETS else "theme"})


def compute(rows, amount=None) -> dict:
    total = sum(r["value"] for r in rows) or 0.0
    buckets = {b: 0.0 for b in BUCKETS}
    for r in rows:
        buckets[r["bucket"] if r["bucket"] in buckets else "theme"] += r["value"]
    warnings = []
    if total > 0:
        if buckets["broad"] / total < 0.10:
            warnings.append("Ingen bred diversifierad kärna – allt är riktade vad.")
        if buckets["leverage"] > 0:
            warnings.append(f"Hävstång i portföljen ({buckets['leverage']/total:.0%}) – decay/ruinrisk på sikt.")
        if buckets["theme"] / total > 0.30:
            warnings.append(f"Hög tema-koncentration ({buckets['theme']/total:.0%}) – rör sig ofta ihop.")
        big = max(rows, key=lambda r: r["value"], default=None)
        if big and big["value"] / total > 0.12:
            warnings.append(f"Störst enskilt innehav: {big['name']} ({big['value']/total:.0%}).")

    out = {"total": round(total, 0),
           "buckets": {b: (round(buckets[b] / total, 4) if total else 0.0) for b in BUCKETS},
           "buckets_sek": {b: round(buckets[b], 0) for b in BUCKETS},
           "target": config.PORTFOLIO_TARGET,
           "warnings": warnings,
           "holdings": [{"name": r["name"], "value": round(r["value"], 0), "bucket": r["bucket"]} for r in rows]}

    if amount:
        after = total + amount
        gaps = {b: max(0.0, config.PORTFOLIO_TARGET.get(b, 0.0) * after - buckets[b]) for b in BUCKETS}
        gsum = sum(gaps.values()) or 1.0
        plan = {b: round(amount * g / gsum) for b, g in gaps.items() if g > 0}
        broad_etfs = {}
        if plan.get("broad", 0) > 0:
            n = len(config.PORTFOLIO_BROAD_ETFS) or 1
            broad_etfs = {lbl: {"ticker": tk, "kr": round(plan["broad"] / n)}
                          for lbl, tk in config.PORTFOLIO_BROAD_ETFS.items()}
        out["newcapital"] = {"amount": amount, "plan": plan, "broad_etfs": broad_etfs}
    return out


def _write_json(data):
    out = Path("results/portfolio_analysis.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False))


def analyze():
    rows = load_holdings()
    if not rows:
        print("[portfolio] inga innehav – lägg in i appen eller cache/portfolio_holdings.csv")
        return
    d = compute(rows)
    print(f"\n  PORTFÖLJ – {d['total']:,.0f} kr, {len(rows)} innehav\n".replace(",", " "))
    print(f"  {'Hink':<26}{'nu':>8}{'mål':>8}{'diff':>8}")
    for b in BUCKETS:
        cur, tgt = d["buckets"][b], d["target"].get(b, 0.0)
        print(f"  {BUCKET_LABEL[b]:<26}{cur:>7.0%}{tgt:>8.0%}{cur - tgt:>+8.0%}")
    print("\n  Varningar:")
    for w in d["warnings"]:
        print(f"   ⚠ {w}")
    _write_json(d)


def newcapital(amount):
    rows = load_holdings()
    if not rows:
        print("[portfolio] inga innehav – lägg in dem först.")
        return
    d = compute(rows, amount=amount)
    print(f"\n  NYTT KAPITAL: {amount:,.0f} kr → fyll mot målet (ingen försäljning)\n".replace(",", " "))
    for b, kr in sorted(d["newcapital"]["plan"].items(), key=lambda x: -x[1]):
        print(f"   {BUCKET_LABEL[b]:<26}{kr:>10,.0f} kr   ({kr/amount:.0%})".replace(",", " "))
    for lbl, e in d["newcapital"]["broad_etfs"].items():
        print(f"     {lbl:<20}{e['ticker']:<10}{e['kr']:>9,.0f} kr".replace(",", " "))
    _write_json(d)


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
