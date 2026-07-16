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


def run(prompt: str, allowed_tools: str, timeout: int = 120) -> dict:
    """Kör `claude -p`, låst till allowed_tools (kommaseparerad
    --allowedTools-lista, t.ex. "WebSearch" eller "mcp__montrose__..."),
    permission-mode dontAsk (nekar allt utanför listan). Returnerar det
    tolkade JSON-svaret, eller {"error": ...} vid problem (process, timeout,
    trasigt svar)."""
    claude_bin = getattr(config, "CLAUDE_BIN", "claude")
    env = {**os.environ, "MCP_TIMEOUT": str(getattr(config, "MONTROSE_MCP_TIMEOUT_MS", 60000))}
    try:
        proc = subprocess.run(
            [claude_bin, "-p", prompt,
             "--output-format", "json",
             "--allowedTools", allowed_tools,
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
    return extract_json(result_text)
