"""
altdata/borsapi.py – BörsAPI.se-klient (historiska svenska kvartals-/årsrapporter).

Vad den ger som vi INTE har: tidsserier av resultat-/balans-/kassaflödesrapporter
(TradingView-scannern är bara en ögonblicksbild). Låser upp fundamental momentum,
Piotroski F-score och PEAD-surprise. Täcker First North/Spotlight/NGM via
include_mtf=true (våra Micro caps).

KVOT-DISCIPLIN: gratis = 100 rapporter TOTALT (engångspott); varje returnerad
rapport = 1 kredit. Därför cachas ALLT för alltid i cache/borsapi/ – en rapport
hämtas aldrig två gånger. Kör aldrig svep utan att räkna på kostnaden först.

Nyckel: BORSAPI_API_KEY i ~/.momentum.env (chmod 600 – ALDRIG i repot).

Körs på Pi:n (nät):
    python -m altdata.borsapi probe            # verifiera nyckel + kvarvarande kvot
    python -m altdata.borsapi search Acconeer  # sök bolag (1 kredit)
    python -m altdata.borsapi eval             # utvärdering: 5 kända bolag (~27 krediter)
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

BASE = "https://borsapi.se/api/v1"


def _key() -> str:
    k = os.environ.get("BORSAPI_API_KEY")
    if not k:
        # Fallback: läs ~/.momentum.env direkt så interaktiva körningar bara funkar.
        # Tål både 'VAR=...' (systemd EnvironmentFile) och 'export VAR=...' (shell).
        envf = Path.home() / ".momentum.env"
        if envf.exists():
            m = re.search(r"^\s*(?:export\s+)?BORSAPI_API_KEY\s*=\s*(.+)$", envf.read_text(), re.M)
            if m:
                k = m.group(1).strip().strip('"').strip("'")
    if not k:
        raise RuntimeError("BORSAPI_API_KEY saknas – lägg nyckeln i ~/.momentum.env (chmod 600).")
    return k


def _cache_dir() -> Path:
    d = Path(config.anchor(getattr(config, "BORSAPI_CACHE_DIR", "cache/borsapi")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s)[:80]


def _get(path: str, params: dict = None, cache_key: str = None) -> dict:
    """GET med Bearer + evig cache (kvoten är en engångspott – slösa aldrig)."""
    cp = _cache_dir() / f"{_slug(cache_key or path + '_' + json.dumps(params or {}, sort_keys=True))}.json"
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    r = requests.get(f"{BASE}{path}", params=params or {},
                     headers={"Authorization": f"Bearer {_key()}"}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"BörsAPI {r.status_code}: {r.text[:300]}")
    data = r.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def probe():
    """Nyckel + användningsstatistik (GET /test cachas INTE – färsk kvot varje gång)."""
    r = requests.get(f"{BASE}/test", headers={"Authorization": f"Bearer {_key()}"}, timeout=30)
    print(f"HTTP {r.status_code}")
    print(json.dumps(r.json(), indent=2, ensure_ascii=False) if r.ok else r.text[:500])


def search(q: str, mtf: bool = True) -> list:
    data = _get("/companies", {"search": q, "include_mtf": str(mtf).lower(), "limit": 5},
                cache_key=f"search_{q}_{mtf}")
    items = data.get("data") or data.get("companies") or (data if isinstance(data, list) else [])
    return items


def _find_dates(obj, path=""):
    """Rekursiv jakt på publicerings-/datumfält i payloaden (PEAD behöver dem)."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if any(w in kl for w in ("publish", "publicer", "announc", "report_date", "created", "released")):
                hits.append((f"{path}.{k}", v))
            hits += _find_dates(v, f"{path}.{k}")
    elif isinstance(obj, list) and obj:
        hits += _find_dates(obj[0], f"{path}[0]")
    return hits


EVAL_COMPANIES = [
    # (sökterm, förväntat namn-fragment, marknad) – mix huvudlista + First North (micro)
    ("Acconeer",   "acconeer",   "First North/micro"),
    ("Swedencare", "swedencare", "First North/micro"),
    ("Physitrack", "physitrack", "First North/micro"),
    ("Avanza",     "avanza",     "XSTO Mid"),
    ("Swedbank",   "swedbank",   "XSTO Large"),
]


def evaluate():
    """
    Utvärdering inom gratispotten (~27 krediter): täckning, datakvalitet att
    verifiera manuellt, och om publiceringsdatum finns (avgör PEAD-nyttan).
    """
    spent_est = 0
    print("=" * 72)
    print("  BÖRSAPI-UTVÄRDERING (allt cachas – omkörning kostar 0)")
    print("=" * 72)
    for term, frag, mkt in EVAL_COMPANIES:
        print(f"\n── {term} ({mkt}) " + "─" * max(1, 40 - len(term)))
        try:
            items = search(term)
            spent_est += 1
            hit = next((c for c in items if frag in json.dumps(c, ensure_ascii=False).lower()), None)
            if not hit:
                print(f"  INTE FUNNEN (sökningen gav {len(items)} träffar) – täckningslucka!")
                continue
            cid = hit.get("id") or hit.get("isin") or hit.get("uuid")
            print(f"  Träff: {hit.get('name')} · id={cid} · marknad={hit.get('market') or hit.get('mic') or '?'}")

            cov = _get(f"/companies/{cid}/coverage", cache_key=f"coverage_{cid}")
            spent_est += 1
            cov_str = json.dumps(cov, ensure_ascii=False)
            years = sorted(set(re.findall(r"20\d\d", cov_str)))
            print(f"  Täckning: {years[0]}–{years[-1]}" if years else "  Täckning: oklar",
                  f"· kvartal: {'JA' if 'quarter' in cov_str.lower() or '-q' in cov_str.lower() else 'okänt'}")

            rep = _get(f"/companies/{cid}/reports",
                       {"period_type": "year", "limit": 3},
                       cache_key=f"reports_{cid}_year_3")
            rows = rep.get("data") or rep.get("reports") or []
            spent_est += max(len(rows), 1)
            if rows:
                r0 = rows[0]
                print(f"  Senaste årsrapport: {r0.get('period') or r0.get('year') or '?'}")
                flat = {k: v for k, v in r0.items() if not isinstance(v, (dict, list))}
                keys = list(flat)[:10]
                print(f"  Fält (topp-nivå): {', '.join(keys)}")
                # Nyckeltal att verifiera manuellt mot bolagets faktiska rapport:
                for k, v in flat.items():
                    if isinstance(v, (int, float)) and abs(v) > 1e5:
                        print(f"    {k} = {v:,.0f}".replace(",", " "))
                dates = _find_dates(r0)
                print(f"  Publiceringsdatum-fält: {dates[:3] if dates else 'HITTADES INTE (PEAD kräver MFN-datum)'}")
            else:
                print("  Inga rapporter returnerade!")
        except Exception as e:  # noqa: BLE001
            print(f"  FEL: {e}")
    print("\n" + "=" * 72)
    print(f"  Uppskattad kvotåtgång denna körning: ~{spent_est} krediter (cachad = 0 nästa gång)")
    print("  Verifiera siffrorna ovan mot bolagens faktiska rapporter innan vi bygger vidare.")
    print("  Kör 'python -m altdata.borsapi probe' för exakt kvarvarande kvot.")


def _company_list() -> list:
    """Hela bolagslistan via sidindelad /companies (billig: 1 kredit/sida).
    Cachas för evigt – körs i praktiken en gång."""
    out, offset = [], 0
    while True:
        page = _get("/companies", {"limit": 100, "offset": offset, "market": "all"},
                    cache_key=f"companies_all_{offset}")
        items = page.get("data") or []
        out += items
        total = page.get("total") or 0
        offset += 100
        if offset >= total or not items:
            break
    return out


def _norm_name(s: str) -> str:
    s = (s or "").lower()
    for junk in (" ab (publ)", " (publ)", " ab", " publ", " plc", " asa", "."):
        s = s.replace(junk, "")
    return re.sub(r"\s+", " ", s).strip()


def _backfill_state_path() -> Path:
    return _cache_dir() / "_backfill_state.json"


def backfill(budget: int = None):
    """
    Kvot-medveten backfill av ÅRSRAPPORTER för huvudlist-bolagen i vårt stora
    segment (First North-rapporter är tomma i deras beta – hoppas över tills de
    fylls på). Hushållar med daglig budget (default config.BORSAPI_DAILY_BUDGET),
    återupptar där den slutade, cachar allt för evigt. Körs manuellt eller via
    cron tills klar:  python -m altdata.borsapi backfill
    """
    import datetime as dt
    budget = int(budget or getattr(config, "BORSAPI_DAILY_BUDGET", 90))
    sp = _backfill_state_path()
    state = json.loads(sp.read_text()) if sp.exists() else {"done": [], "empty": []}

    # Vårt stora segment (Large+Mid, huvudlistan) → matcha mot BörsAPI:s lista på namn.
    from data.data_loader import load_sweden_universe
    seg = config.SEGMENTS["large"]
    tickers, _s, _c, name_map = load_sweden_universe(min_market_cap=seg["market_cap"])
    ours = {_norm_name(name_map.get(t, t)): t for t in tickers}

    companies = _company_list()
    matched = [(c, ours[_norm_name(c.get("name"))]) for c in companies
               if _norm_name(c.get("name")) in ours and (c.get("market") or "") == "XSTO"]
    pending = [(c, tk) for c, tk in matched
               if (c.get("id") not in state["done"]) and (c.get("id") not in state["empty"])]
    print(f"[backfill] {len(matched)} matchade huvudlist-bolag · {len(pending)} kvar · budget {budget} krediter")

    spent = 0
    for c, tk in pending:
        if spent >= budget:
            break
        cid = c["id"]
        try:
            # Bara åren features:en behöver (F-score: 2 år, fund. momentum: ~3;
            # +1 buffert). Full historik är forskningslyx som kan hämtas senare –
            # detta kapar backfill-kostnaden ~60%.
            import datetime as _dt
            since = _dt.date.today().year - int(getattr(config, "BORSAPI_BACKFILL_YEARS", 4))
            rep = _get(f"/companies/{cid}/reports",
                       {"period_type": "year", "limit": 100, "from_year": since},
                       cache_key=f"reports_{cid}_year_since{since}")
            rows = rep.get("data") or []
            spent += max(len(rows), 1)
            if rows:
                state["done"].append(cid)
                print(f"  {tk:<14} {c.get('name','')[:34]:<34} {len(rows)} årsrapporter")
            else:
                state["empty"].append(cid)
                print(f"  {tk:<14} {c.get('name','')[:34]:<34} TOM")
        except Exception as e:  # noqa: BLE001
            print(f"  {tk}: FEL {e}")
            break   # trolig kvot-/nätgräns – fortsätt imorgon
        sp.write_text(json.dumps(state))
    remaining = len(pending) - len([1 for c, _ in pending if c["id"] in state["done"] + state["empty"]])
    print(f"[backfill] klart för idag: ~{spent} krediter · ~{remaining} bolag kvar "
          f"(kör igen imorgon, cachen gör omstart gratis)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "search":
        for c in search(" ".join(sys.argv[2:])):
            print(json.dumps(c, ensure_ascii=False))
    elif cmd == "eval":
        evaluate()
    elif cmd == "backfill":
        backfill(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
