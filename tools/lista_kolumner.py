"""SKRIV UT ALLA 59 KOLUMNER I CORE_FUNDAMENTA_PANEL.JSON

DIAGNOSTISKT.
Kör: /opt/momentum/venv/bin/python tools/lista_kolumner.py
"""
import json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")

def main():
    fp = V2 / "panels/core_fundamenta_panel.json"
    data = json.loads(fp.read_text())
    sample = data[0]
    print(f"Totalt {len(sample)} kolumner i core_fundamenta_panel.json:")
    for i, k in enumerate(sample.keys(), 1):
        print(f"  {i:2d}. {k}")

if __name__ == "__main__":
    main()
