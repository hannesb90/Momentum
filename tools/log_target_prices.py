"""Veckovis loggning av offentliga riktkurser för v2:s universum.

Syfte: riktkursREVISIONER kräver en tidsserie. Idag finns exakt en snapshot
(2026-07-23, legacy). Den här loggen bygger serien framåt.

Källa: Yahoo Finance aggregerade targetMeanPrice/High/Low, som i sin tur
samlar Redeye/Carnegie/Pareto/SEB m.fl. Verifierad i legacy mot Otto-
diagrammens externa riktkurser (Physitrack 20,08 = Redeye 20 kr exakt).

Fristående: läser v2:s eget universum, ingen import från legacy.
Append-only. En rad per bolag och körning. Manifest med sha256 per körning.

Kör:  /opt/momentum/venv/bin/python tools/log_target_prices.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "raw/target_prices"
CSV = OUT / "target_prices_history.csv"
MANIFEST = OUT / "_manifest.jsonl"
COLS = ["date", "fetch_utc", "kod", "ticker", "name", "price_now",
        "target_mean", "target_high", "target_low", "n_analysts", "recommendation"]


def universum() -> list[str]:
    """v2:s validerade universum. Avnoterade utesluts — de har ingen riktkurs."""
    prices = json.loads((V2 / "validated/prices/prices_validated_v1_1.json").read_text())
    term = set(json.loads((V2 / "validated/terminal_events.json").read_text()))
    return sorted(k for k in prices if k not in term)


def hamta(kod: str) -> dict | None:
    import yfinance as yf
    try:
        info = yf.Ticker(f"{kod}.ST").get_info()
    except Exception:  # noqa: BLE001
        return None
    tgt = info.get("targetMeanPrice")
    if tgt is None:
        return None
    now = datetime.now(timezone.utc)
    return {"date": now.date().isoformat(), "fetch_utc": now.isoformat(timespec="seconds"),
            "kod": kod, "ticker": f"{kod}.ST",
            "name": info.get("longName") or info.get("shortName") or kod,
            "price_now": info.get("currentPrice") or info.get("regularMarketPrice"),
            "target_mean": tgt, "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "n_analysts": info.get("numberOfAnalystOpinions"),
            "recommendation": info.get("recommendationKey")}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    koder = universum()
    ny_fil = not CSV.exists()
    rader, saknas = 0, 0
    with CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if ny_fil:
            w.writeheader()
        for i, kod in enumerate(koder, 1):
            r = hamta(kod)
            if r:
                w.writerow(r); rader += 1
            else:
                saknas += 1
            time.sleep(0.25)
            if i % 100 == 0:
                print(f"  [{i}/{len(koder)}] med riktkurs {rader}", flush=True)

    sha = hashlib.sha256(CSV.read_bytes()).hexdigest()
    rec = {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_universum": len(koder), "n_med_riktkurs": rader, "n_utan": saknas,
           "kalla": "Yahoo Finance get_info targetMeanPrice/High/Low",
           "fil": CSV.name, "csv_sha256_efter": sha,
           "syfte": "bygger tidsserie for riktkursrevisioner; en snapshot rader inte"}
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_dagar = 0
    if CSV.exists():
        with CSV.open(encoding="utf-8") as fh:
            n_dagar = len({row["date"] for row in csv.DictReader(fh)})
    print(f"\n  universum {len(koder)}   med riktkurs {rader}   utan {saknas}")
    print(f"  observationsdagar i serien: {n_dagar}")
    print(f"  {CSV.relative_to(V2)}  sha256 {sha[:16]}…")
    if n_dagar < 8:
        print(f"  → revisioner blir mätbara vid ca 26 observationer (~6 månader veckovis)")


if __name__ == "__main__":
    main()
