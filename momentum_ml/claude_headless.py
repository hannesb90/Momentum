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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def _salvage_string_field(blob: str, key: str) -> "str | None":
    """Räddar VÄRDET för ETT namngivet strängfält ur ett {...}-block som
    inte gick att json.loads():a i sin helhet (bara för text_fallback_key-
    anropare, se extract_json()). Kräver ett fullständigt, KORREKT
    AVSLUTAT citattecken för fältet - en trunkerad sträng (svaret klipptes
    av mitt i, t.ex. tokengräns) har inget sådant citattecken att matcha
    mot, så regexen missar helt och vi faller tillbaka på det vanliga
    felet i stället för att gissa på ofullständig text. Det regexen FAKTISKT
    räddar är fallet där resten av JSON-blocket (efter fältet) är trasigt
    av någon annan anledning (t.ex. modellen la till text efter den
    stängande klammern) - då är själva fältvärdet fortfarande komplett och
    tolkningsbart, bara omslaget runt det som är fel."""
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)"', blob, re.S)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')  # återanvänder JSON:s egen escape-avkodning
    except json.JSONDecodeError:
        return None


def extract_json(text: str, text_fallback_key: str = None) -> dict:
    """Plockar ut FÖRSTA {...}-blocket ur ett LLM-svar. {"error": ...} om
    inget hittas eller om det inte går att parsa (och inte kan räddas, se
    text_fallback_key nedan).

    text_fallback_key: BUGG (fixad, verkligt fall: /api/commentary/ask
    fick "Kunde inte svara: inget JSON-svar från claude: <ett fullt
    korrekt, sammanhängande svar i klartext>" - modellen ignorerade
    JSON-instruktionen och svarade i ren prosa efter en WebSearch, ett
    känt LLM-beteende i verktygstunga anrop, INTE ett trasigt svar). Ett
    korrekt svar utan JSON-omslag är fortfarande ett korrekt svar - att
    kasta bort det för ett formateringsmiss är sämre än att använda det.
    Sätt till t.ex. "answer"/"commentary" för anropare med ETT text-fält
    (ask()/build() i portfolio_commentary.py) så en JSON-lös men i övrigt
    vettig textrespons används som svaret i stället för att slängas.

    SAMMA nyckel används ÄVEN om ett {...}-block HITTADES men inte gick
    att json.loads():a (verkligt fall 2026-07-21: portfolio_commentary.py
    fick "trasigt JSON-svar" trots att texten SYNLIGT började helt
    korrekt, {"commentary": "Sedan förra kommentaren..." - troligen ett
    oescapead citattecken längre in i texten, eller ett tillägg efter
    stängande klammern). Försöker då rädda BARA det namngivna fältet med
    en riktad regex (_salvage_string_field) - se den för varför en
    trunkerad sträng INTE räddas (ingen gissning på ofullständig text).
    Anropare som behöver FLERA fält (trade-ticket, kvalitetsbetyg m.fl.)
    ska INTE sätta detta - där är ett strukturerat svar meningslöst utan
    alla fält, bättre att fela synligt."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        if text_fallback_key and text:
            return {text_fallback_key: text}
        return {"error": f"inget JSON-svar från claude: {text[:200]}"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        if text_fallback_key:
            salvaged = _salvage_string_field(m.group(0), text_fallback_key)
            if salvaged:
                print(f"[claude_headless] trasigt JSON men räddade fältet "
                      f"'{text_fallback_key}' via regex-fallback")
                return {text_fallback_key: salvaged}
        return {"error": f"trasigt JSON-svar från claude: {text[:200]}"}


def run(prompt: str, allowed_tools: str, timeout: int = 120, model: str = None,
        text_fallback_key: str = None) -> dict:
    """Kör `claude -p`, låst till allowed_tools (kommaseparerad
    --allowedTools-lista, t.ex. "WebSearch" eller "mcp__montrose__..."),
    permission-mode dontAsk (nekar allt utanför listan). model: None ->
    config.CLAUDE_MODEL_DEFAULT ("sonnet") – ange config.CLAUDE_MODEL_FAST
    ("haiku") explicit för högvolyms enkel klassificering (se
    quality_screener.py), aldrig för trade-ticket-/watchlist-anrop där
    verktygsprecision spelar roll. Returnerar det tolkade JSON-svaret,
    eller {"error": ...} vid problem (process, timeout, trasigt svar).

    text_fallback_key: se extract_json() - bara för anropare med ETT
    text-fält som svar (t.ex. "answer"/"commentary"), aldrig för
    strukturerade flerfälts-svar."""
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
    return extract_json(result_text, text_fallback_key=text_fallback_key)


def _parse_quota_reset(detail: str):
    """Tolkar en "resets HH(:MM)?(am|pm)? (Zone/City)"-tid ur claude-cli:s
    kvot-/rate-limit-felmeddelande (verkligt format 2026-07-20: "You've hit
    your weekly limit · resets 4pm (Europe/Stockholm)"). Returnerar NÄSTA
    förekomst av den klocktiden (tz-medveten datetime – idag om den inte
    redan passerat, annars imorgon) plus en 10-minuters buffert (kvoten
    fylls inte garanterat exakt på sekunden claude-cli angav), eller None
    om inget sådant mönster hittas i texten – ingen ombokning då, bara
    nuvarande "logga och ge upp"-beteende."""
    m = re.search(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?:\s*\(([\w/]+)\))?",
                  detail or "", re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    ampm, tzname = (m.group(3) or "").lower(), m.group(4)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    tz = timezone.utc
    if tzname:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tzname)
        except Exception:  # noqa: BLE001
            pass
    now = datetime.now(tz)
    try:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate + timedelta(minutes=10)


_RETRY_QUEUE_FILE = "cache/claude_retry_queue.json"


def queue_retry(script_path, argv, error_detail: str, fallback_delay_min: int = None) -> bool:
    """Kallas av ett SCHEMALAGT jobbs entry point (portfolio_commentary.py,
    watchlist_sync.py, insight_report.py, sync_montrose_holdings.py – ALDRIG
    interaktiva/på-begäran-anrop som montrose_ticket.create_ticket eller
    portfolio_commentary.ask(), en misslyckad knapptryckning ska felas
    synligt direkt i appen, inte tystas ner i en bakgrundskö) när run() gav
    ett fel. Om felmeddelandet innehåller en tolkningsbar "resets HH:MM"-tid
    (se _parse_quota_reset) skrivs en post i cache/claude_retry_queue.json
    med DEN tidpunkten; retry_dispatcher.py (momentum-retry.timer, var 2:e
    minut) kör då om EXAKT samma skript+argument när kvoten borde vara
    påfylld, i stället för att jobbet bara tappas till nästa ordinarie
    natt-timer (kan vara >20h bort om felet inträffar tidigt på natten).

    fallback_delay_min: om felet INTE går att tolka som en tidsbestämd
    kvotgräns (t.ex. ett trasigt JSON-svar, se claude_headless.extract_json,
    eller ett övergående nätverksfel) - boka ändå om körningen om detta är
    satt, "nu + N minuter" i stället för en exakt påfylld-tid (verkligt
    fall 2026-07-21: portfolio_commentary.py fick ett trasigt JSON-svar en
    natt, ingen kvotgräns inblandad alls, men ändå värt ett nytt försök).
    None (default) = bara boka om vid en faktisk tolkningsbar kvotgräns,
    som tidigare - använd för jobb där ett övergående fel oftast LÖSER sig
    själv till nästa ordinarie natt-timer och inte är värt en extra
    ombokning (t.ex. inget uppenbart skäl att anta att en omkörning om
    20 min skulle lyckas bättre).

    En ny köad post för samma skript ersätter en äldre (t.ex. om nästa
    körning misslyckas igen med en senare reset-tid). Returnerar True om en
    ombokning köades, False om felet varken gick att tolka som en
    tidsbestämd kvotgräns ELLER fallback_delay_min var satt."""
    retry_at = _parse_quota_reset(error_detail)
    if retry_at is None:
        if fallback_delay_min is None:
            return False
        retry_at = datetime.now(timezone.utc) + timedelta(minutes=fallback_delay_min)
    qpath = Path(config.anchor(_RETRY_QUEUE_FILE))
    qpath.parent.mkdir(parents=True, exist_ok=True)
    try:
        queue = json.loads(qpath.read_text(encoding="utf-8")) if qpath.exists() else []
    except Exception:  # noqa: BLE001
        queue = []
    script_path = str(Path(script_path).resolve())
    queue = [e for e in queue if e.get("script") != script_path]
    queue.append({"script": script_path, "args": list(argv or []),
                  "retry_at": retry_at.isoformat(),
                  "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "reason": (error_detail or "")[:200]})
    qpath.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[claude_headless] kvot-/tidsgräns – {Path(script_path).name} ombokad till {retry_at.isoformat()}")
    return True
