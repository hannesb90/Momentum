import time
import os
from pathlib import Path
import csv

def test_original():
    p = Path("test_log.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value_sek"])
        for i in range(100):
            w.writerow([f"2023-01-{i:02d}", str(1000 + i)])

    start = time.perf_counter()
    for _ in range(10000):
        rows = {}
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                if r.get("date"):
                    rows[r["date"]] = r.get("value_sek", "")
    end = time.perf_counter()
    print(f"Original unclosed: {end - start:.4f} seconds")

def test_fixed():
    p = Path("test_log.csv")
    start = time.perf_counter()
    for _ in range(10000):
        rows = {}
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r.get("date"):
                        rows[r["date"]] = r.get("value_sek", "")
    end = time.perf_counter()
    print(f"Fixed with-block: {end - start:.4f} seconds")

test_original()
test_fixed()
