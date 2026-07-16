"""
watchlist_sync.py – speglar modellens topplista + säljvaktens flaggade
innehav som två Montrose-watchlists, så de syns direkt i mäklarappen utan
att öppna Momentum (idé 7).

Två listor, helt omskrivna varje körning (tas bort/läggs till så listan
alltid matchar dagens data, ackumulerar aldrig gamla poster):
  - config.MONTROSE_WATCHLIST_TOP  – modellens topp-10 sammanvägda rankning
  - config.MONTROSE_WATCHLIST_SELL – säljvaktens flaggade innehav (level >= 1)

Rör bara watchlists, ALDRIG en order – create_trade_ticket ingår inte i
--allowedTools här. Headless Claude, samma princip som resten av
Montrose-integrationen (se montrose_ticket.py:s docstring för den lokala
server-registreringen som krävs).

    python watchlist_sync.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402
import claude_headless as ch  # noqa: E402

WATCHLIST_TOP = getattr(config, "MONTROSE_WATCHLIST_TOP", "Momentum - Topplista")
WATCHLIST_SELL = getattr(config, "MONTROSE_WATCHLIST_SELL", "Momentum - Säljvakt")

_TOOLS = ("mcp__montrose__create_watchlist,mcp__montrose__get_watchlists,"
          "mcp__montrose__get_watchlist,mcp__montrose__search_instruments,"
          "mcp__montrose__add_to_watchlist,mcp__montrose__remove_from_watchlist")

_PROMPT = """Synka TVÅ Montrose-watchlists så de EXAKT speglar listorna nedan
- inget mer, inget mindre. Gör i tur och ordning, för VARJE lista:

1. create_watchlist(name) – idempotent, ger tillbaka listan om den redan finns.
2. get_watchlist(listId) för att se nuvarande innehåll.
3. För varje ticker i mållistan som INTE redan finns: search_instruments för
   att hitta orderbookId (matcha ticker utan börs-suffix som .ST/.DE/.L exakt
   - hoppa över om ingen exakt match), sedan add_to_watchlist.
4. För varje befintlig post som INTE finns i mållistan: remove_from_watchlist.

LISTA 1 - "{name_top}":
{tickers_top}

LISTA 2 - "{name_sell}":
{tickers_sell}

Svara ENDAST med kompakt JSON, ingen markdown:
  {{"top": {{"added": [...], "removed": [...], "skipped": [...]}},
    "sell": {{"added": [...], "removed": [...], "skipped": [...]}}}}
(ticker-strängar i listorna; "skipped" = tickers som inte kunde matchas)
"""


def build():
    rows = pf.load_holdings()
    top = pf._safe(lambda: pf._unified_rank(rows, top_n=10), [], "sammanvägd rank")
    sell = [s for s in pf._safe(lambda: pf._takeprofit(rows), [], "säljvakt")
            if (s.get("level") or 0) >= 1]

    top_tickers = [c["ticker"] for c in top]
    sell_tickers = [s["ticker"] for s in sell]
    if not top_tickers and not sell_tickers:
        print("[watchlist] inget att synka (ingen rankning/säljvakt-data).")
        return

    prompt = _PROMPT.format(
        name_top=WATCHLIST_TOP, name_sell=WATCHLIST_SELL,
        tickers_top=", ".join(top_tickers) or "(tom)",
        tickers_sell=", ".join(sell_tickers) or "(tom)",
    )
    result = ch.run(prompt, _TOOLS, timeout=180)
    if "error" in result:
        print(f"[watchlist] misslyckades: {result['error']}")
        return
    for key, label in (("top", WATCHLIST_TOP), ("sell", WATCHLIST_SELL)):
        r = result.get(key) or {}
        print(f"[watchlist] {label}: +{len(r.get('added', []))} -{len(r.get('removed', []))} "
              f"({len(r.get('skipped', []))} ej matchade)")


if __name__ == "__main__":
    build()
