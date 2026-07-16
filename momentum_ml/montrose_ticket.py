"""
montrose_ticket.py – skapar en Montrose-trade-ticket-URL via headless Claude
Code (`claude -p`), inloggad med Claude-prenumerationen (claude login) på
maskinen som kör backend:en. Ingen separat Anthropic-API-nyckel, kostnaden
räknas mot samma prenumeration du redan betalar för.

BARA köp (side=Buy), ALDRIG sälj härifrån – i linje med appens köp-och-behåll-
disciplin (säljvakten/takeprofit i appen är rådgivande, ingen knapp lägger en
säljorder).

--allowedTools + --permission-mode dontAsk låser headless-anropet till EXAKT
två Montrose-verktyg (search_instruments, create_trade_ticket) – det kan inte
röra filer, köra Bash eller göra något annat.

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
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

_ALLOWED_TOOLS = "mcp__montrose__search_instruments,mcp__montrose__create_trade_ticket"

_PROMPT = """Skapa EN Montrose-trade-ticket:
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


def _base_ticker(ticker: str) -> str:
    return (ticker or "").split(".")[0].strip().upper()


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"error": f"inget JSON-svar från claude: {text[:200]}"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"error": f"trasigt JSON-svar från claude: {text[:200]}"}


def create_ticket(ticker: str, kr: float, account_id: str = None, timeout: int = 120) -> dict:
    """{"url": ...} eller {"error": ...}. Kör headless Claude Code, låst till
    Montrose-verktygen via --allowedTools + --permission-mode dontAsk.

    MCP_TIMEOUT höjs från Claude Codes default (30s) – en fjärransluten
    connector (Montrose är kontobunden, inte lokalt konfigurerad) hann inte
    alltid ansluta klart inom defaulten i en färsk headless-process, vilket
    gjorde att verktygen inte var listade när prompten redan besvarats."""
    claude_bin = getattr(config, "CLAUDE_BIN", "claude")
    account_id = account_id or getattr(config, "MONTROSE_ACCOUNT_ID", None)
    if not account_id:
        return {"error": "MONTROSE_ACCOUNT_ID saknas i config.py"}
    prompt = _PROMPT.format(ticker=ticker, base_ticker=_base_ticker(ticker),
                             kr=round(float(kr)), account_id=account_id)
    env = {**os.environ, "MCP_TIMEOUT": str(getattr(config, "MONTROSE_MCP_TIMEOUT_MS", 60000))}
    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt,
             "--output-format", "json",
             "--allowedTools", _ALLOWED_TOOLS,
             "--permission-mode", "dontAsk"],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except FileNotFoundError:
        return {"error": f"claude hittades inte ({claude_bin}) – installerad och rätt sökväg i config.CLAUDE_BIN?"}
    except subprocess.TimeoutExpired:
        return {"error": f"claude svarade inte inom {timeout}s"}
    if proc.returncode != 0:
        return {"error": f"claude avslutade med fel: {(proc.stderr or '').strip()[:300]}"}
    try:
        envelope = json.loads(proc.stdout)
        result_text = envelope.get("result", proc.stdout)
    except json.JSONDecodeError:
        result_text = proc.stdout
    return _extract_json(result_text)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python montrose_ticket.py <ticker> <kr>")
        raise SystemExit(1)
    print(json.dumps(create_ticket(sys.argv[1], float(sys.argv[2])), ensure_ascii=False, indent=2))
