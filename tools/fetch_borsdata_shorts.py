"""HÄMTAR BLANKNINGSDATA FRÅN BÖRSDATA — /v1/holdings/shorts

Den enda källan i hela dataregistret som aldrig laddats ned. Endpointen kräver
Pro+ och returnerar samtliga nordiska instrument i ett anrop.

Sparas som immutable RAW med sha256 och manifest, enligt samma mönster som
raw/borsdata/kpi_*. Ingen bearbetning, ingen target läses.

Kör: /opt/momentum/venv/bin/python tools/fetch_borsdata_shorts.py
"""
from __future__ import annotations
import hashlib, json, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
UT = V2 / "raw/borsdata/shorts"
BAS = "https://apiservice.borsdata.se"


def nyckel():
    p = Path.home() / ".momentum.env"
    if not p.exists():
        sys.exit("saknar ~/.momentum.env")
    m = re.search(r"^\s*(?:export\s+)?BORSDATA_API_KEY\s*=\s*(.+)$", p.read_text(), re.M)
    if not m:
        sys.exit("BORSDATA_API_KEY saknas i ~/.momentum.env")
    return m.group(1).strip().strip('"').strip("'")


def hamta(vag, params):
    url = f"{BAS}{vag}?" + urllib.parse.urlencode(params)
    # Cloudflare framför Börsdata blockerar Python-urllibs standard-UA med
    # felkod 1010. Det är inte ett behörighetsfel.
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json"})
    for forsok in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode()), r.status
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and forsok < 3:
                time.sleep(2 + 3 * forsok)
                continue
            return {"fel": e.code, "text": e.read().decode()[:300]}, e.code
        except Exception as e:
            if forsok < 3:
                time.sleep(2)
                continue
            return {"fel": type(e).__name__, "text": str(e)[:300]}, None
    return None, None


def main():
    UT.mkdir(parents=True, exist_ok=True)
    k = nyckel()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print("Hämtar /v1/holdings/shorts ...")
    data, status = hamta("/v1/holdings/shorts", {"authKey": k})
    if status != 200:
        print(f"  MISSLYCKADES, status {status}")
        print(f"  {json.dumps(data, ensure_ascii=False)[:400]}")
        if status in (401, 403):
            print("\n  403 med error code 1010 = Cloudflare blockerar user-agenten, inte behörighet.")
        sys.exit(1)
    fil = UT / f"shorts_{stamp}.json"
    txt = json.dumps(data, ensure_ascii=False)
    fil.write_text(txt)
    sha = hashlib.sha256(txt.encode()).hexdigest()
    rader = None
    for nyck in ("shorts", "list", "holdings", "values"):
        if isinstance(data, dict) and isinstance(data.get(nyck), list):
            rader = data[nyck]
            break
    if rader is None and isinstance(data, list):
        rader = data
    man = {"hamtat_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "endpoint": "/v1/holdings/shorts", "fil": fil.name, "sha256": sha,
           "bytes": len(txt), "toppnycklar": list(data.keys()) if isinstance(data, dict) else "lista",
           "n_rader": len(rader) if rader is not None else None}
    (UT / f"_manifest_{stamp}.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    print(f"  OK — {len(txt)/1e6:.2f} MB, sha {sha[:16]}…")
    print(f"  toppnycklar: {man['toppnycklar']}")
    if rader:
        print(f"  rader: {len(rader)}")
        print(f"  exempel: {json.dumps(rader[0], ensure_ascii=False)[:400]}")
    print(f"  sparat: {fil}")


if __name__ == "__main__":
    main()
