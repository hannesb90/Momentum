"""
claude_headless.py – delad subprocess-wrapper för headless Claude Code-anrop
(`claude -p`), använd av montrose_ticket.py (trading) och insight_report.py
(narrativ). Inloggad med Claude-prenumerationen på maskinen (`claude login`)
- ingen Anthropic-API-nyckel. Se montrose_ticket.py:s docstring för hur
en MCP-server (t.ex. Montrose) registreras LOKALT så dess verktyg syns här
(kontobundna claude.ai-connectors syns inte i headless-läge, verifierat).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def extract_json(text: str) -> dict:
    """Plockar ut FÖRSTA {...}-blocket ur ett LLM-svar. {"error": ...} om
    inget hittas eller om det inte går att parsa."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"error": f"inget JSON-svar från claude: {text[:200]}"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"error": f"trasigt JSON-svar från claude: {text[:200]}"}


def run(prompt: str, allowed_tools: str, timeout: int = 120, model: str = None) -> dict:
    """Kör `claude -p`, låst till allowed_tools (kommaseparerad
    --allowedTools-lista, t.ex. "WebSearch" eller "mcp__montrose__..."),
    permission-mode dontAsk (nekar allt utanför listan). model: None ->
    config.CLAUDE_MODEL_DEFAULT ("sonnet") – ange config.CLAUDE_MODEL_FAST
    ("haiku") explicit för högvolyms enkel klassificering (se
    quality_screener.py), aldrig för trade-ticket-/watchlist-anrop där
    verktygsprecision spelar roll. Returnerar det tolkade JSON-svaret,
    eller {"error": ...} vid problem (process, timeout, trasigt svar)."""
    claude_bin = getattr(config, "CLAUDE_BIN", "claude")
    model = model or getattr(config, "CLAUDE_MODEL_DEFAULT", "sonnet")
    env = {**os.environ, "MCP_TIMEOUT": str(getattr(config, "MONTROSE_MCP_TIMEOUT_MS", 60000))}
    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt,
             "--output-format", "json",
             "--allowedTools", allowed_tools,
             "--permission-mode", "dontAsk",
             "--model", model],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except FileNotFoundError:
        return {"error": f"claude hittades inte ({claude_bin}) – installerad och rätt sökväg i config.CLAUDE_BIN?"}
    except subprocess.TimeoutExpired:
        return {"error": f"claude svarade inte inom {timeout}s"}
    if proc.returncode != 0:
        # BUGG (fixad, verkligt fall: 528-bolags quality_screener-körning som
        # tog slut på prenumerationens användningskvot mitt i): stderr är ofta
        # TOMT vid en kvot-/rate-limit-avvisning – felmeddelandet blev då
        # obegripligt kort ("claude avslutade med fel: "). Faller tillbaka på
        # stdout (kan ha en JSON-envelope med orsaken) och flaggar uttryckligen
        # om texten ser ut som en användningsgräns, så orsaken syns direkt i
        # loggen istället för att behöva grävas fram i efterhand.
        detail = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        detail = detail[:300]
        low = detail.lower()
        if not detail or any(w in low for w in ("usage limit", "rate limit", "quota", "5-hour", "kvot")):
            hint = " (ser ut som prenumerationens användningsgräns – vänta och kör om)" if not detail else \
                   " (användningsgräns)"
            return {"error": f"claude avslutade med fel (kod {proc.returncode}){hint}: {detail or 'inget felmeddelande'}"}
        return {"error": f"claude avslutade med fel: {detail}"}
    try:
        envelope = json.loads(proc.stdout)
        result_text = envelope.get("result", proc.stdout)
    except json.JSONDecodeError:
        result_text = proc.stdout
    # BUGG (fixad, verkligt fall: sync_montrose_holdings.py efter att den
    # LOKALA montrose-registreringen tappats – bara den kontobundna claude.ai-
    # connectorn fanns kvar, som dontAsk inte kan använda). Då lyckas processen
    # (kod 0) men modellen svarar i klartext att verktyget nekades – utan JSON,
    # så det landar som ett obegripligt "inget JSON-svar". Känn igen mönstret
    # och peka på den faktiska åtgärden istället: registrera om MCP-servern
    # lokalt (`claude mcp add … && claude mcp login <server>`).
    low = (result_text or "").lower()
    if allowed_tools and "mcp__" in allowed_tools and any(
            w in low for w in ("nekades behörighet", "don't ask", "dontask",
                               "denied permission", "not authorized", "icke-interaktiva")):
        server = allowed_tools.split("mcp__", 1)[1].split("__", 1)[0] if "mcp__" in allowed_tools else "<server>"
        return {"error": f"MCP-verktyg nekades i dontAsk-läge – den LOKALA '{server}'-"
                f"registreringen saknas troligen (bara kontobunden claude.ai-connector "
                f"funkar inte headless). Kör: claude mcp add --transport http {server} "
                f"<url> && claude mcp login {server}"}
    return extract_json(result_text)
