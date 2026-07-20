"""
altdata/fiscal.py – Fiscal AI REST-API-klient.

Hämtar data från Fiscal AI.
Nyckel: FISCAL_API_KEY i ~/.momentum.env (chmod 600 – ALDRIG i repot).

Körs på Pi:n (nät):
    python -m altdata.fiscal probe             # nyckel OK? dumpar bolagslistan
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE = "https://api.fiscal.ai"

def _key() -> str:
    k = os.environ.get("FISCAL_API_KEY")
    if not k:
        envf = Path.home() / ".momentum.env"
        if envf.exists():
            m = re.search(r"^\s*(?:export\s+)?FISCAL_API_KEY\s*=\s*(.+)$", envf.read_text(), re.M)
            if m:
                k = m.group(1).strip().strip('"').strip("'")
    if not k:
        raise RuntimeError("FISCAL_API_KEY saknas – lägg nyckeln i ~/.momentum.env (chmod 600).")
    return k

def _get(path: str, params: dict = None) -> dict:
    """GET med X-Api-Key-header."""
    q = dict(params or {})
    headers = {"X-Api-Key": _key()}
    r = requests.get(f"{BASE}{path}", params=q, headers=headers, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Fiscal AI {r.status_code}: {r.text[:300]}")
    return r.json()

def probe():
    """Nyckel OK? Hämtar bolagslistan (1 anrop) och dumpar EN post rått
    så vi ser de riktiga fältnamnen."""
    try:
        data = _get("/v3/companies-list", params={"compact": "true"})
        items = data.get("data") or (data if isinstance(data, list) else [])
        print(f"HTTP OK · {data.get('pagination', {}).get('totalCount', len(items))} instrument totalt")
        if items:
            print("\nExempel-instrument (rått, compact):")
            print(json.dumps(items[0], indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Fel vid probe: {e}")

def _load_local_universe():
    import csv
    tickers = []
    ours_path = Path(__file__).parent.parent / "data" / "sweden_universe.csv"
    with open(ours_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tickers.append(row["ticker"])
    return tickers

def match():
    """Matchar Fiscal AIs instrument mot vårt universum."""
    ours = _load_local_universe()
    ours_bare = {t[:-3]: t for t in ours if t.endswith(".ST")}

    try:
        matched = []
        page = 1
        while True:
            data = _get("/v3/companies-list", params={"compact": "true", "allCompanies": "true", "pageNumber": page})
            items = data.get("data") or (data if isinstance(data, list) else [])
            if not items:
                break

            for item in items:
                ticker = item.get("ticker")
                if ticker and ticker in ours_bare:
                    matched.append((ours_bare[ticker], item.get("companyFiscalIdentifier")))

            pagination = data.get("pagination", {})
            total_pages = pagination.get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.5)

        print(f"[match] {len(matched)} av {len(ours)} i vårt universum matchade mot Fiscal AI")
        if matched:
            print("\nExempel (5 första):")
            for tk, f_id in matched[:5]:
                print(f"  {tk:<14} ← {f_id}")
        return matched
    except Exception as e:
        print(f"Fel vid match: {e}")
        return []

def backfill():
    """Hämtar all relevant data för matchade bolag."""
    matched = match()
    if not matched:
        print("Inget att backfilla, inga bolag matchade.")
        return

    cache_dir = Path(__file__).parent.parent / "cache" / "fiscal"
    cache_dir.mkdir(parents=True, exist_ok=True)

    endpoints = {
        "profile": "/v3/company/profile",
        "income": "/v1/company/financials/income-statement/standardized",
        "balance": "/v1/company/financials/balance-sheet/standardized",
        "cashflow": "/v1/company/financials/cash-flow-statement/standardized",
        "ratios": "/v1/company/ratios",
        "prices": "/v3/company/stock-prices"
    }

    for tk, f_id in matched:
        print(f"\nHämtar data för {tk} ({f_id})")
        for name, path in endpoints.items():
            cache_file = cache_dir / f"{tk}_{name}.json"
            if cache_file.exists():
                print(f"  [SKIPPED] {name} (redan cachad)")
                continue

            try:
                # Add a small delay to respect rate limits
                time.sleep(0.5)
                data = _get(path, params={"company": f_id})
                cache_file.write_text(json.dumps(data, ensure_ascii=False))
                print(f"  [OK] {name}")
            except Exception as e:
                print(f"  [FEL] {name}: {e}")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "match":
        match()
    elif cmd == "backfill":
        backfill()
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
