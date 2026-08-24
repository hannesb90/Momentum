"""INSPEKTERA NON-PRIS OCH FUNDAMENTALA INSTRUMENT OCH DATA

Inspekterar vad som finns i:
  - core_fundamenta_panel.json
  - raw/borsdata/r12, quarter, kpi_valuation, buyback, etc.

DIAGNOSTISKT.
Kör: /opt/momentum/venv/bin/python tools/inspektera_fundamenta_data.py
"""
from __future__ import annotations
import json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")

def main():
    print("Inspekterar core_fundamenta_panel.json...")
    fp = V2 / "panels/core_fundamenta_panel.json"
    if fp.exists():
        data = json.loads(fp.read_text())
        print(f"  Typ: {type(data)}, Antal rader: {len(data)}")
        if isinstance(data, list) and data:
            sample = data[0]
            print(f"  Exempel på fält/kolumner ({len(sample)} st):")
            for k, v in list(sample.items())[:30]:
                print(f"    - {k}: {type(v).__name__} = {repr(v)[:50]}")

    print("\nInspekterar raw/borsdata undermappar...")
    bd = V2 / "raw/borsdata"
    for d in sorted(bd.iterdir()):
        if d.is_dir():
            files = list(d.glob("*.json")) + list(d.glob("*.csv")) + list(d.glob("*.jsonl"))
            print(f"  Folder '{d.name}': {len(files)} filer. Exempel: {[f.name for f in files[:3]]}")

if __name__ == "__main__":
    main()
