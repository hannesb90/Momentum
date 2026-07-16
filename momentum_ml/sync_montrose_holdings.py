"""
sync_montrose_holdings.py – synkar innehav från Montrose (Claude-sessionens
Montrose-MCP: get_user_accounts + get_holdings) till cache/portfolio_holdings.csv
– samma fil "Min portfölj" (portfolio.py) redan läser/skriver. Ersätter det
manuella inmatningssteget nu när kontodata går att läsa direkt.

Läs-läge: skriver bara till den lokala cache-filen, rör aldrig Montrose-kontot.
Ingen order läggs härifrån (det görs separat, se create_trade_ticket).

MCP-verktygen är bara nåbara inifrån en Claude-session, inte från ett fristående
script. Flödet är därför:
  1. Claude anropar get_holdings (+ get_user_accounts vid behov) och sparar
     JSON-svaret till en fil, t.ex. /tmp/montrose_holdings.json.
  2. Detta script läser den filen (eller stdin), matchar varje position mot en
     ticker/hink och anropar portfolio.save_holdings() – samma kodväg som
     appens "spara innehav"-knapp.

    python sync_montrose_holdings.py montrose_holdings.json
    cat montrose_holdings.json | python sync_montrose_holdings.py
    python sync_montrose_holdings.py --from-montrose   # hämta själv (headless
                                     # claude låst till get_holdings; nattlig
                                     # timer momentum-montrose-holdings.timer)

Körs från momentum_ml/ (samma katalog som portfolio.py, för att data/
rotation_universe.csv ska hittas via relativ sökväg).

Hink-gissning (broad/sweden/theme/leverage) per instrument:
  - kind='region' i data/rotation_universe.csv, eller namnet pekar på en bred
    globalindex-ETF (MSCI World/ACWI, S&P 500, FTSE All-World)  → broad
  - .ST-ticker (svensk aktie, matchad via samma _resolve_ticker som resten
    av appen använder)                                          → sweden
  - hävstångsord i namn/ticker (bull/bear/2x/3x/lever/hävstång)  → leverage
  - annars                                                       → theme
Ett innehav som redan fanns i cache-filen BEHÅLLER sin tidigare hink – en
gissning skriver alltså aldrig över en hink du själv satt i appen. Bara helt
nya tickers gissas.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import portfolio as pf  # noqa: E402

_LEVERAGE_WORDS = ("bull", "bear", "2x", "3x", "leverage", "hävstång", "lever")
_BROAD_NAME_HINTS = ("msci world", "msci acwi", "s&p 500", "ftse all-world",
                      "all world", "core world")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _guess_bucket(ticker, name):
    nl = (name or "").lower()
    tl = (ticker or "").upper()
    if any(w in nl or w in tl.lower() for w in _LEVERAGE_WORDS):
        return "leverage"
    if pf._kinds().get(tl) == "region" or any(h in nl for h in _BROAD_NAME_HINTS):
        return "broad"
    if tl.endswith(".ST"):
        return "sweden"
    return "theme"


def _accounts(data):
    return data.get("result", data) if isinstance(data, dict) else data


def _flatten_positions(data):
    out = []
    for acct in _accounts(data):
        out.extend(acct.get("positions", []))
    return out


def _isk_cash(data):
    """Tillgänglig köpkraft på ISK-kontot (config.MONTROSE_ACCOUNT_ID) – None
    om kontot inte syns i svaret (t.ex. accountId-filtrerad hämtning)."""
    for acct in _accounts(data):
        if acct.get("accountId") == getattr(pf.config, "MONTROSE_ACCOUNT_ID", None):
            summary = acct.get("summary") or {}
            return _num(summary.get("availableForPurchase")), _num(summary.get("totalValue"))
    return None, None


def montrose_to_rows(data, existing_by_ticker):
    """(rows redo för pf.save_holdings, namn där ingen ticker kunde matchas)."""
    rows, unresolved = [], []
    for pos in _flatten_positions(data):
        name = (pos.get("instrumentName") or "").strip()
        if not name:
            continue
        qty = _num(pos.get("quantity"))
        value = _num((pos.get("marketValue") or {}).get("accountCurrency")) or 0.0
        unreal = _num((pos.get("unrealizedResult") or {}).get("accountCurrency"))
        cost = (value - unreal) if unreal is not None else None
        buy_price = (cost / qty) if (cost and qty) else None
        ticker = pf._resolve_ticker(name)
        if not ticker:
            unresolved.append(name)
        prev = existing_by_ticker.get(ticker) if ticker else None
        bucket = prev["bucket"] if prev else _guess_bucket(ticker, name)
        rows.append({"name": name, "value": value, "bucket": bucket, "ticker": ticker,
                     "cost": cost, "shares": qty, "buy_price": buy_price})
    return rows, unresolved


def sync(path=None):
    if path == "--from-montrose":
        import montrose_ticket as mt
        data = mt.fetch_holdings()
        if "error" in data:
            print(f"[sync_montrose] hämtning misslyckades: {data['error']} – "
                  f"rör inte befintlig fil.")
            raise SystemExit(1)
    else:
        raw = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
        data = json.loads(raw)
    prev_rows = pf.load_holdings(refresh=False)
    existing_by_ticker = {r["ticker"]: r for r in prev_rows if r.get("ticker")}
    rows, unresolved = montrose_to_rows(data, existing_by_ticker)
    if not rows:
        print("[sync_montrose] inga positioner i indata – avbryter, rör inte befintlig fil.")
        return
    new_tickers = {r["ticker"] for r in rows if r.get("ticker")}
    old_tickers = set(existing_by_ticker)
    added, removed = new_tickers - old_tickers, old_tickers - new_tickers
    pf.save_holdings(rows)
    available, acct_total = _isk_cash(data)
    if available is not None:
        pf.save_cash(available, acct_total)
        print(f"[sync_montrose] ISK köpkraft: {available:,.0f} kr".replace(",", " "))
    pf.check_trade_ticket_ledger(rows)
    total = sum(r["value"] for r in rows)
    print(f"[sync_montrose] {len(rows)} innehav synkade, {total:,.0f} kr totalt".replace(",", " "))
    if added:
        print(f"  + nya: {', '.join(sorted(added))} (hink gissad – kontrollera i appen)")
    if removed:
        print(f"  - borttagna (fanns i cache-filen, inte längre hos Montrose): {', '.join(sorted(removed))}")
    if unresolved:
        print(f"  ⚠ kunde inte matcha ticker automatiskt för: {', '.join(unresolved)} "
              f"– sparade utan ticker, komplettera i appen (Min portfölj).")


if __name__ == "__main__":
    sync(sys.argv[1] if len(sys.argv) > 1 else None)
