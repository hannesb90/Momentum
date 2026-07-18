"""
montrose_ticket.py – skapar en Montrose-trade-ticket-URL, och hämtar innehav,
via headless Claude Code (`claude -p`, se claude_headless.py), inloggad med
Claude-prenumerationen (claude login) på maskinen som kör backend:en. Ingen
separat Anthropic-API-nyckel, kostnaden räknas mot samma prenumeration du
redan betalar för.

BARA köp (side=Buy), ALDRIG sälj härifrån – i linje med appens köp-och-behåll-
disciplin (säljvakten/takeprofit i appen är rådgivande, ingen knapp lägger en
säljorder).

--allowedTools + --permission-mode dontAsk (i claude_headless.run) låser varje
anrop till EXAKT de Montrose-verktyg som behövs för just det anropet – kan
inte röra filer, köra Bash eller göra något annat.

VIKTIGT om server-registreringen: den kontobundna claude.ai-connectorn syns
INTE i headless-läge (`claude -p`) – bara i interaktiva sessioner (verifierat;
headless kan inte köra connectorns OAuth-flöde). Servern måste därför vara
LOKALT registrerad på maskinen, och verktygsnamnen följer det lokala namnet
(gemener):
    claude mcp add --transport http montrose https://mcp.montrose.io
    claude mcp login montrose     # OAuth: öppna länken, klistra in callback-
                                  # URL:en SNABBT (engångskoden dör på ~1 min)

Skapar bara en FÖRIFYLLD länk – ingen order läggs här. Användaren öppnar
länken i Montrose-appen och bekräftar själv innan något köps.

    python montrose_ticket.py IUSQ.DE 10000
    python montrose_ticket.py fetch_holdings
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import claude_headless as ch  # noqa: E402

_TICKET_TOOLS = "mcp__montrose__search_instruments,mcp__montrose__create_trade_ticket"

_TICKET_PROMPT = """Skapa EN Montrose-trade-ticket:
  - side: Buy
  - ticker att slå upp: {ticker}
  - belopp: {kr} SEK
  - accountId: {account_id}

Använd search_instruments för att hitta rätt instrument om orderbookId inte
redan är känt. Välj BARA en träff vars ticker (utan börs-suffix som .ST/.DE/.L)
exakt matchar "{base_ticker}". Om ingen träff matchar exakt, eller flera
matchar lika bra, anropa inget mer verktyg – svara direkt med felet.

Anropa sedan create_trade_ticket med side=Buy, det matchade orderbookId,
amount={kr}, accountId={account_id}.

Svara ENDAST med kompakt JSON, inget annat, ingen markdown:
  lyckades:     {{"url": "<url från create_trade_ticket>"}}
  misslyckades: {{"error": "<kort orsak>"}}
"""

_FETCH_PROMPT = """Anropa verktyget get_holdings (utan accountId, så alla konton kommer med).
Svara ENDAST med verktygets råa JSON-resultat, exakt och oavkortat som det
returnerades – ingen markdown, inga kodstaket, ingen kommentar, inga
utelämnade fält."""


def _base_ticker(ticker: str) -> str:
    return (ticker or "").split(".")[0].strip().upper()


def create_ticket(ticker: str, kr: float, account_id: str = None, timeout: int = 120) -> dict:
    """{"url": ...} eller {"error": ...}."""
    account_id = account_id or getattr(config, "MONTROSE_ACCOUNT_ID", None)
    if not account_id:
        return {"error": "MONTROSE_ACCOUNT_ID saknas i config.py"}
    prompt = _TICKET_PROMPT.format(ticker=ticker, base_ticker=_base_ticker(ticker),
                                    kr=round(float(kr)), account_id=account_id)
    return ch.run(prompt, _TICKET_TOOLS, timeout=timeout)


def fetch_holdings(timeout: int = 120) -> dict:
    """Hämtar innehaven via headless Claude låst till ENBART get_holdings.
    Returnerar Montrose-svaret ({"result": [konton...]}) eller {"error": ...}.
    Nattlig konsument: sync_montrose_holdings.py --from-montrose."""
    data = ch.run(_FETCH_PROMPT, "mcp__montrose__get_holdings", timeout=timeout)
    if "error" in data:
        return data
    # Sanity: svaret ska vara kontolistan – texten mellan LLM och oss får
    # aldrig tyst bli en tom/halv portfölj som sen SKRIVER ÖVER innehavsfilen.
    accounts = data.get("result") if isinstance(data.get("result"), list) else None
    if accounts is None:
        return {"error": f"oväntat svar (saknar 'result'-lista): {str(data)[:200]}"}
    n_pos = sum(len(a.get("positions") or []) for a in accounts)
    if n_pos == 0:
        return {"error": "0 positioner i svaret – vägrar synka (skulle tömma innehavsfilen)"}
    return data


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "fetch_holdings":
        print(json.dumps(fetch_holdings(), ensure_ascii=False, indent=2))
    elif len(sys.argv) >= 3:
        print(json.dumps(create_ticket(sys.argv[1], float(sys.argv[2])), ensure_ascii=False, indent=2))
    else:
        print("usage: python montrose_ticket.py <ticker> <kr>\n"
              "       python montrose_ticket.py fetch_holdings")
        raise SystemExit(1)
