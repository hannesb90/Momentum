"""
altdata/fi_insynsregistret.py – Finansinspektionens FULLA öppna insynsregister
(marknadssok.fi.se), inte MFN-cachens tunna delmängd.

Bakgrund: tune_insider_gap.py testade "nettoinsynsköp utan prisreaktion"
mot altdata/mfn_events.py:s PDMR-cache och landade OAVGJORT (2026-07-19) -
bara 30 PDMR-poster totalt i hela cachen, otillräckligt för en slutsats åt
något håll. FI:s EGET register (lagstadgad rapportering, all insynshandel på
Nasdaq Stockholm/NGM) är den fullständiga källan MFN bara speglar en bråkdel
av. Ett tidigare pip-paket (`insynsregistret`) finns men pekar mot en
nedlagd domän (insynsok.fi.se, 404) - den här modulen pratar med den
NUVARANDE sökportalen direkt.

Skrapar per EMITTENT (FI:s sök tar bolagsnamn, inte ticker) med paginering.
All regulatorisk historik är permanent (ändras aldrig i efterhand) - cachas
därför för alltid, ingen daglig cache-nyckel som prisdata.

    python -m altdata.fi_insynsregistret probe "Fingerprint Cards AB"
"""
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

BASE_URL = "https://marknadssok.fi.se/publiceringsklient/sv-SE/Search/Search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; momentum-research/1.0)"}

# "Karaktär"-värden vi räknar som genuina, diskretionära marknadstransaktioner
# (öppna köp/sälj) - INTE tilldelningar/teckningar/optionslösen/pantsättningar,
# som är administrativa/villkorade och inte samma signal som "en insider valde
# att lägga egna pengar i bolaget".
BUY_CHARACTERS = {"Förvärv"}
SELL_CHARACTERS = {"Avyttring"}


def _cache_dir() -> Path:
    d = Path(config.anchor("cache/fi_insyn"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name)[:100]


def _parse_swe_number(s: str) -> Optional[float]:
    s = (s or "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_issuer_transactions(issuer_name: str, max_pages: int = 60, delay: float = 0.4,
                               use_cache: bool = True) -> List[Dict]:
    """Alla insynstransaktioner för EN emittent (FI:s exakta bolagsnamn, inte
    ticker), all historik, paginerad. Cachas evigt lokalt (regulatorisk
    historik ändras aldrig)."""
    cache_file = _cache_dir() / f"{_slug(issuer_name)}.json"
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    rows_out: List[Dict] = []
    session = requests.Session()
    for page in range(1, max_pages + 1):
        resp = None
        for attempt in range(3):
            try:
                resp = session.get(BASE_URL, params={
                    "SearchFunctionType": "Insyn", "Utgivare": issuer_name,
                    "button": "search", "Page": page,
                }, headers=HEADERS, timeout=20)
                break
            except requests.RequestException as e:
                if attempt == 2:
                    print(f"  [WARN] {issuer_name} sida {page}: nätverksfel efter 3 försök ({e}), avbryter paginering.")
                else:
                    time.sleep(1.5 * (attempt + 1))
        if resp is None:
            break
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_=re.compile("table"))
        if table is None:
            break
        trs = table.find_all("tr")[1:]  # hoppa rubrikraden
        if not trs:
            break
        got_any = False
        for tr in trs:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) < 14:
                continue
            got_any = True
            rows_out.append({
                "publish_date": tds[0], "issuer": tds[1], "person": tds[2],
                "role": tds[3], "related": tds[4], "character": tds[5],
                "instrument": tds[6], "instrument_type": tds[7], "isin": tds[8],
                "transaction_date": tds[9], "volume": _parse_swe_number(tds[10]),
                "volume_unit": tds[11], "price": _parse_swe_number(tds[12]),
                "currency": tds[13],
            })
        if not got_any:
            break
        time.sleep(delay)

    cache_file.write_text(json.dumps(rows_out, ensure_ascii=False), encoding="utf-8")
    return rows_out


def probe(issuer_name: str) -> None:
    rows = fetch_issuer_transactions(issuer_name, use_cache=False)
    print(f"[probe] {issuer_name}: {len(rows)} transaktioner hittade.")
    for r in rows[:10]:
        print(f"  {r['publish_date']}  {r['person']:<28}{r['character']:<14}"
              f"{r['instrument_type']:<8}{r['volume']}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "probe" and len(args) > 1:
        probe(" ".join(args[1:]))
    else:
        print("Användning: python -m altdata.fi_insynsregistret probe <bolagsnamn>")
