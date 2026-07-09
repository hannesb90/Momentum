"""
altdata/mfn_pdf.py – Hämtar PDF-bilagor från MFN-cachens 'attachments'-fält
och kör BÅDE extract_hard_facts() (narrativa "X uppgick till Y (Z) Mkr"-
meningar) och extract_table_facts() (tabellformaterade resultat-/balans-
räkningar, mfn_fundamentals.py) mot PDF-texten i stället för press-
releasens korta announcement-text.

Byggd för de PM som bara publicerar en kort announcement + PDF-länk utan
siffror i själva pressmeddelandet – bekräftat gång på gång via
mfn_fundamentals.py:s 'misses'-kommando (AAK:s årsredovisning, Tre Kronor,
...). Fältnamnet/strukturen ('content.attachments' =
[{file_title, content_type, url, tags}]) är VERIFIERAT mot skarp MFN-data
via mfn_fetch.py:s 'raw'-kommando, inte gissat.

Verifierat mot en RIKTIG nedladdad AAK-årsredovisning (190 sidor, via
scan_pages/dump_page på Pi:n): resultaträkningen låg på sida 124-135 (inte
sista sidan – därför höjt _MAX_PDF_PAGES) och är TABELLFORMATERAD
("Nettoomsättning 26 46.021 45.052", punkt-tusentalsavgränsare) – ett helt
annat mönster än narrativa meningar, därav extract_table_facts() som ett
separat, radankrat regex-läge (se mfn_fundamentals.py för detaljer och
skydd mot falska träffar i femårs-sammanfattningstabeller).

Kräver mfn_fetch.py:s attachments-fält (schema 2) – 'fetch <segment>'
uppgraderar automatiskt gammal cache, ingen manuell radering behövs.

    python -m altdata.mfn_pdf backfill large        # alla miss-PM med PDF-bilaga
    python -m altdata.mfn_pdf backfill large 20      # bara de första 20 (snabbt test)
    python -m altdata.mfn_pdf diagnose_empty large   # varför gav vissa PDF:er noll fält? (inget nätanrop)
    python -m altdata.mfn_pdf compare_layout <pdf-url>  # standard vs layout=True mot EN känd trasig PDF
    python -m altdata.mfn_pdf scan_pages <pdf-url>       # var i dokumentet börjar siffrorna? (ingen sidkapning)
    python -m altdata.mfn_pdf dump_page <pdf-url> <sida> # hela texten för EN sida, okapad
"""
import csv
import hashlib
import io
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from altdata.mfn_fundamentals import extract_hard_facts, extract_table_facts, _report_items, detect_period

try:
    import requests
except ImportError:
    requests = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# pdfminer (pdfplumber:s motor) loggar varningar för lätt trasiga/icke-
# standard PDF:er rakt till stdout ("Cannot set stroke color: 2 components
# specified..." osv) – ofarligt (extraktionen fortsätter ändå) men
# översvämmar output när tusentals PDF:er körs i en batch. Tysta ner till
# ERROR – vi bryr oss bara om PDF:en gick att öppna över huvud taget, inte
# om enstaka grafik-operatorer var lite fel formaterade.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# Pi:n har begränsat minne/lagring (2GB RAM, se deploy/momentum-train.service) –
# sätt konservativa tak i stället för att lita på att alla PDF:er är små.
_MAX_PDF_BYTES = 20 * 1024 * 1024   # 20 MB nedladdningstak
# Historik: 20 -> 200 (sida 124-135 i en riktig 190-sidig AAK-årsredovisning
# låg utanför det gamla taket på 20) -> 5000 ("praktiskt obegränsat") -> 300.
# 5000 drogs tillbaka: Pi:n (2GB RAM, redan 362 MB i swap i vila) startade om
# oväntat under en backfill-körning över natten. Ingen beständig logg fanns
# kvar för att bevisa OOM, men vi har samtidigt INGEN evidens för att 5000
# behövdes – 200 räckte redan för att hitta alla 16 fält i AAK-exemplet
# (compare_layout), och en full backfill vid 200 gav bara marginell extra
# träffgrad över hela batchen ("enstaka till, inte så många fler"). Att då
# riskera ett jättetak för en obekräftad, sannolikt liten vinst är fel
# avvägning på en minnessvag maskin. 300 ger god marginal över det vi
# FAKTISKT sett behövas (190 sidor) utan att öppna för pathologiska fall.
_MAX_PDF_PAGES = 300
_PDF_REQUEST_PAUSE_S = 1.0          # artigare paus än PM-textens – större filer, annan värd (storage.mfn.se/Cision)
# Cachens textrutning – måste följa med när _MAX_PDF_PAGES höjs, annars
# tappas nyupptäckt data tyst vid nästa cache-läsning även om DEN AKTUELLA
# körningen såg hela texten i minnet. 2 MB räcker även för ovanligt stora
# rapporter (en riktig 190-sidig AAK-rapport gav ~650k tecken totalt).
_MAX_CACHED_TEXT_CHARS = 2_000_000
# PDF-textcachen är "evig" (rapporter ändras inte i efterhand) – MEN vad som
# extraheras beror på _MAX_PDF_PAGES, som just ändrats (20 -> 200 -> 5000).
# Utan versionering skulle en omkörning tyst återanvända gammal, ofullständig
# text i stället för att faktiskt extrahera fler sidor – exakt samma
# cache-uppgraderingsproblem som mfn_fetch.py:s _SCHEMA_VERSION löser för
# PM-cachen. Bump:a denna siffra varje gång _MAX_PDF_PAGES eller
# extraktionslogiken ändras väsentligt.
_PDF_TEXT_SCHEMA_VERSION = 2


def _pdf_text_cache_dir() -> Path:
    d = Path(config.anchor(getattr(config, "MFN_PDF_TEXT_CACHE_DIR", "cache/mfn_pdf_text")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# Enkel-instans-lås: två samtidiga backfill-processer har gång på gång
# uttömt Pi:ns 2GB RAM (varje process håller hela universumet + kör PDF-
# extraktion) → MemoryError-svärm och frusen 'ok'-räknare. Ett PID-baserat
# lås förhindrar dubbelstart HELT (importos.kill(pid, 0) verifierar att en
# lås-fil pekar på en LEVANDE process – en stale låsfil efter en krasch
# städas bort automatiskt, inget manuellt ingrepp behövs).
def _lock_path() -> Path:
    return _pdf_text_cache_dir().parent / "mfn_pdf_backfill.lock"


def _acquire_lock() -> bool:
    import os
    lp = _lock_path()
    if lp.exists():
        try:
            old_pid = int(lp.read_text().strip())
            os.kill(old_pid, 0)          # kastar OSError om processen inte finns
            return False                 # levande process håller låset
        except (ValueError, ProcessLookupError):
            pass                         # trasig/stale låsfil – ta över
        except PermissionError:
            return False                 # processen finns (men ägs av annan) – respektera
    lp.write_text(str(os.getpid()))
    return True


def _release_lock() -> None:
    import os
    lp = _lock_path()
    try:
        if lp.exists() and int(lp.read_text().strip()) == os.getpid():
            lp.unlink()
    except Exception:  # noqa: BLE001
        pass


def _cache_key(pm_id: str, url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    safe_id = "".join(ch if ch.isalnum() else "_" for ch in pm_id)[:60]
    return f"{safe_id}_{h}"


def pick_attachment(attachments: List[dict]) -> Optional[dict]:
    """Om ett PM har flera PDF-bilagor (rapport + appendix etc.) – föredra den
    som MFN själv taggat ':primary'. Annars första i listan."""
    if not attachments:
        return None
    for a in attachments:
        if ":primary" in (a.get("tags") or []):
            return a
    return attachments[0]


def _download_pdf(url: str) -> Optional[bytes]:
    """Laddar ner till minnet – INTE disk. Vi cachar bara den extraherade
    TEXTEN (permanent), inte de råa PDF-byten, för att inte svälla Pi:ns
    lagring med potentiellt tusentals megabyte-stora rapporter."""
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    try:
        r = requests.get(url, timeout=60, stream=True,
                          headers={"User-Agent": "Mozilla/5.0 (Momentum research)"})
        if not r.ok:
            return None
        buf = io.BytesIO()
        for chunk in r.iter_content(chunk_size=65536):
            buf.write(chunk)
            if buf.tell() > _MAX_PDF_BYTES:
                return None
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def extract_pdf_text(pdf_bytes: bytes):
    """Text ur de första _MAX_PDF_PAGES sidorna + TOTALT sidantal i
    dokumentet (oavsett sidkapet). En enskild trasig sida ska inte stoppa
    hela dokumentet – hoppa över den och fortsätt. Sidantalet används av
    diagnose_empty() för att skilja "för kort för att någonsin ha varit en
    riktig rapport" (t.ex. bara en duplicerad presstext utan bilaga, en
    riktig rapport är i praktiken aldrig 1 sida) från "tillräckligt lång
    men ändå inget extraherat" (ett fras-/tabellmönster värt att undersöka
    vidare) – kolla ett riktigt AAK-exempel som ledde fram till detta."""
    if pdfplumber is None:
        raise RuntimeError("paketet 'pdfplumber' saknas – pip install pdfplumber")
    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages[:_MAX_PDF_PAGES]:
            try:
                t = page.extract_text()
            except Exception:  # noqa: BLE001
                t = None
            if t:
                out.append(t)
    return "\n".join(out), n_pages


# Två oväntade Pi-omstarter i rad under backfill-körningar (2026-07-09),
# utan bevis för OOM/underspänning i den logg vi lyckats fånga (vare sig
# minne eller vcgencmd-throttling var förhöjt i de senaste avläsningarna
# innan kraschen) – men mönstret (död efter samma typ av arbete, alltid
# under just PDF-extraktion) pekar mot en ENSKILD pathologisk PDF (extremt
# layout-/grafiktung, hundratals sidor) som får pdfplumber att svälla
# minnesanvändningen på under 5 sekunder – snabbare än övervakningsloopens
# pollintervall hinner fånga, och möjligen snabbt nog för att ta ner hela
# Pi:n (2GB RAM) innan Linux-OOM-killern ens hinner välja ett offer själv.
# I stället för att fortsätta gissa på ännu en sidkaps-konstant: isolera
# den riskabla operationen i en EGEN subprocess med ett HÅRT minnestak
# (resource.RLIMIT_AS). Ett enskilt dokument som slår i taket kraschar då
# bara sin egen subprocess (räknas som "kunde inte extraheras", precis som
# en trasig PDF) – aldrig förälderprocessen eller resten av systemet.
#
# VIKTIGT (rättat): RLIMIT_AS är TOTALT virtuellt adressrum, och en fork:ad
# barnprocess ÄRVER förälderns hela adressrum. Ett ABSOLUT tak (t.ex. 400 MB)
# blev därför fel så fort föräldern själv växte förbi taket: barnet var då
# redan över gränsen innan det ens börjat, och MemoryError:ade direkt →
# 'ok'-räknaren frös vid exakt den punkt där föräldern korsade taket
# (bekräftat mönster: frös på samma tal varje körning). Vi sätter i stället
# taket RELATIVT: barnets ärvda adressrum + ett fast extraktionsutrymme, så
# extraktionen alltid får sin fulla budget oavsett hur stor föräldern hunnit bli.
_EXTRACT_MEM_HEADROOM_BYTES = 500 * 1024 * 1024   # extraktionsbudget UTÖVER ärvt adressrum
_EXTRACT_TIMEOUT_S = 120


def _current_address_space_bytes() -> int:
    """Processens nuvarande virtuella adressrum (bytes) via /proc/self/statm.
    0 om det inte går att läsa (t.ex. icke-Linux) → anropar hoppar taket då."""
    try:
        import resource
        with open("/proc/self/statm") as f:
            vsize_pages = int(f.read().split()[0])
        return vsize_pages * resource.getpagesize()
    except Exception:  # noqa: BLE001
        return 0


def _fetch_extract_worker(url: str, q) -> None:
    """Kör i subprocessen: BÅDE nedladdning och extraktion. Avgörande att BÅDA
    ligger här – den 20 MB stora PDF-bufferten + pdfplumbers strukturer lever
    och dör då i den KORTLIVADE barnprocessen (allt frigörs vid exit), i
    stället för att fragmentera den långlivade förälderns heap iteration efter
    iteration tills 2GB-Pi:n är slut (det var därför även NEDLADDNINGAR – som
    förr skedde i föräldern – började misslyckas och 'ok' frös)."""
    # Tysta subprocessens stderr: en krypterad/trasig PDF som slår i
    # minnestaket ger pdfminer-tracebacks + en Rust-panik ("PyObject pointer
    # is null" från cryptography:s AES-avkodare) rakt till stderr NÄR barnet
    # dör – ofarligt (felet fångas ändå via kön nedan) men översvämmar
    # föräldern-loggen så framstegsraderna drunknar. Omdirigera till /dev/null;
    # den strukturerade felorsaken går fortfarande via q.put nedan.
    try:
        import os as _os
        _devnull = _os.open(_os.devnull, _os.O_WRONLY)
        _os.dup2(_devnull, 2)   # fd 2 = stderr
    except Exception:  # noqa: BLE001
        pass
    try:
        try:
            import resource
            current = _current_address_space_bytes()
            if current > 0:   # bara sätt taket om vi vet vad barnet redan ärvt
                limit = current + _EXTRACT_MEM_HEADROOM_BYTES
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except Exception:  # noqa: BLE001 – t.ex. plattform utan RLIMIT_AS-stöd
            pass
        pdf_bytes = _download_pdf(url)
        if pdf_bytes is None:
            q.put(("download_failed", None))
            return
        text, n_pages = extract_pdf_text(pdf_bytes)
        del pdf_bytes                     # släpp bufferten före put (barnet dör ändå strax)
        q.put(("ok", (text, n_pages)))
    except BaseException as e:  # noqa: BLE001 – inkl. MemoryError vid taket
        try:
            q.put(("error", str(e)[:200]))
        except Exception:  # noqa: BLE001
            pass


def fetch_extract_isolated(url: str):
    """Laddar ner + extraherar i en isolerad subprocess (minnestak+timeout).
    Returnerar (status, text, n_pages) där status ∈ {'ok','download_failed',
    'error'} – anropande get_pdf_text skiljer nedladdningsfel från
    extraktionsfel för cache-taggningen. Allt tungt minne (PDF-bytes,
    pdfplumber) hålls i barnet som frigör det helt vid exit → föräldern
    förblir lean över tiotusentals iterationer.

    RESURS-DISCIPLIN: varje Queue startar en matartråd + pipe-FD:er som INTE
    frigörs automatiskt – utan explicit close()/join_thread() läckte de per
    iteration. Vi läser dessutom kön via en poll-loop (dränerar matartråden så
    en stor payload inte deadlockar) OCH upptäcker tidig processdöd (en hård
    OOM-kill hinner inte ens lägga ett felmeddelande)."""
    import multiprocessing as mp
    import queue as _queue
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    p = ctx.Process(target=_fetch_extract_worker, args=(url, q))
    p.start()
    result = ("error", None, None)
    try:
        deadline = time.time() + _EXTRACT_TIMEOUT_S
        while time.time() < deadline:
            try:
                status, payload = q.get(timeout=0.5)
                if status == "ok":
                    result = ("ok", payload[0], payload[1])
                elif status == "download_failed":
                    result = ("download_failed", None, None)
                else:
                    result = ("error", None, None)
                break
            except _queue.Empty:
                if not p.is_alive():
                    break   # dog utan att lägga ett svar (OOM-kill etc.)
    except Exception:  # noqa: BLE001
        result = ("error", None, None)
    finally:
        if p.is_alive():
            p.terminate()
        p.join(5)
        try:
            q.close()
            q.join_thread()
        except Exception:  # noqa: BLE001
            pass
        try:
            p.close()
        except Exception:  # noqa: BLE001
            pass
    return result


def get_pdf_text(pm_id: str, url: str) -> Optional[str]:
    """Cache med ASYMMETRISK tillit: en LYCKAD extraktion (text != None) är
    permanent (rapporttext ändras aldrig i efterhand) och serveras alltid ur
    cachen. Ett cachat MISSLYCKANDE (text == None) görs däremot ALLTID om –
    ett fel kan vara transient (minne, nät, rate-limit), och konkret: de
    tidigare körningarna med minnesbuggen cachade hundratals bugg-inducerade
    'download_failed'/'oom'-poster som annars skulle serveras för evigt trots
    att koden nu är fixad. En post från en äldre schemaversion behandlas också
    som cache-miss (annars återanvänds ofullständig text från ett lägre sidkap)."""
    cp = _pdf_text_cache_dir() / f"{_cache_key(pm_id, url)}.json"
    if cp.exists():
        try:
            cached = json.loads(cp.read_text(encoding="utf-8"))
            if cached.get("schema") == _PDF_TEXT_SCHEMA_VERSION and cached.get("text") is not None:
                return cached.get("text")   # bara LYCKADE poster serveras ur cachen
        except Exception:  # noqa: BLE001
            pass
    # Nedladdning OCH extraktion sker i EN isolerad subprocess (se
    # fetch_extract_isolated) – föräldern rör aldrig den 20 MB stora
    # PDF-bufferten, så dess heap växer inte iteration för iteration.
    status, text, n_pages = fetch_extract_isolated(url)
    if status != "ok" or text is None:
        err = "download_failed_or_too_large" if status == "download_failed" else "extraction_crashed_or_oom_or_timeout"
        cp.write_text(json.dumps({"text": None, "error": err,
                                   "schema": _PDF_TEXT_SCHEMA_VERSION}), encoding="utf-8")
        return None
    # page_count cachas UTÖVER schema-fältet, inte som en del av det – en
    # ändring här ska inte tvinga fram en ny omkörning av redan lyckade
    # extraktioner (bara nya poster får sidantalet med sig, se
    # diagnose_empty() som hanterar att äldre poster kan sakna det).
    cp.write_text(json.dumps({"text": text[:_MAX_CACHED_TEXT_CHARS], "schema": _PDF_TEXT_SCHEMA_VERSION,
                               "page_count": n_pages}, ensure_ascii=False), encoding="utf-8")
    return text


def _peek_cached(pm_id: str, url: str) -> Optional[dict]:
    """Läser PDF-textcachen UTAN att trigga en nedladdning om den saknas –
    för diagnos av redan körda PDF:er, inte för att köra nya. En post från en
    äldre schemaversion räknas som "inte körd ännu" (samma logik som
    get_pdf_text) så diagnose_empty inte visar stale resultat."""
    cp = _pdf_text_cache_dir() / f"{_cache_key(pm_id, url)}.json"
    if not cp.exists():
        return None
    try:
        cached = json.loads(cp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if cached.get("schema") != _PDF_TEXT_SCHEMA_VERSION:
        return None
    return cached


def diagnose_empty(segment: Optional[str] = None, n: int = 5) -> None:
    """Svarar EMPIRISKT på 'är de tomma PDF:erna gamla/skannade filer?' i
    stället för att gissa. Jämför år-fördelning och extraherad textlängd
    mellan lyckade och tomma resultat – nära-noll text = troligen en
    skannad bild utan textlager (olösbart utan OCR); mycket text men ändå
    noll fält = ett fras-/tabellmönster vi missar (potentiellt fixbart).

    Delar även upp TOMMA efter PDF:ens sidantal: en riktig rapport är i
    praktiken aldrig 1 sida (bekräftade exempel: en PDF som bara duplicerar
    presstexten, ingen faktisk rapport bifogad) – <2 sidor räknas därför
    som sannolikt olösbart via just det PM:et, i stället för ett regex-/
    tabellmönster värt att jaga. Manuella exempel visas bara för de som ÄR
    tillräckligt långa, så du inte slösar tid på att kolla en PDF som
    aldrig innehöll siffror. Sidantal saknas för poster extraherade före
    denna ändring (ingen omkörning tvingas fram bara för detta) – syns som
    "okänt sidantal".

    Läser BARA redan körd cache – triggar inga nya nedladdningar."""
    items = _report_items(segment)
    miss_items = [it for it in items if not extract_hard_facts(it.get("text") or "")]
    candidates = [it for it in miss_items if it.get("attachments")]

    from collections import Counter
    by_year_empty: Counter = Counter()
    by_year_ok: Counter = Counter()
    textlens_empty: List[int] = []
    empty_examples = []
    not_yet_processed = dl_failed = 0
    short_pdf = long_pdf = unknown_pages = 0

    for it in candidates:
        att = pick_attachment(it["attachments"])
        cached = _peek_cached(it["id"], att["url"])
        if cached is None:
            not_yet_processed += 1
            continue
        text = cached.get("text")
        year = str(it.get("published", ""))[:4] or "okänt"
        if text is None:
            dl_failed += 1
            continue
        if extract_hard_facts(text) or extract_table_facts(text):
            by_year_ok[year] += 1
            continue
        by_year_empty[year] += 1
        textlens_empty.append(len(text))
        n_pages = cached.get("page_count")
        if n_pages is None:
            unknown_pages += 1
            if len(empty_examples) < n:
                empty_examples.append((it, att, text, None))
        elif n_pages < 2:
            short_pdf += 1   # sannolikt aldrig en riktig rapport - visas inte som exempel
        else:
            long_pdf += 1
            if len(empty_examples) < n:
                empty_examples.append((it, att, text, n_pages))

    print(f"[mfn_pdf diagnose_empty] {len(candidates)} kandidater totalt, "
          f"{not_yet_processed} inte körda ännu, {dl_failed} nedladdningsfel")

    print("\nÅr-fördelning, LYCKADE (fick minst 1 fält ur PDF:en):")
    for y, c in sorted(by_year_ok.items()):
        print(f"  {y}: {c}")
    print("\nÅr-fördelning, TOMMA (PDF öppnades, noll fält extraherade):")
    for y, c in sorted(by_year_empty.items()):
        print(f"  {y}: {c}")

    if textlens_empty:
        avg_len = sum(textlens_empty) / len(textlens_empty)
        near_zero = sum(1 for l in textlens_empty if l < 200)
        print(f"\nTextlängd för TOMMA: snitt {avg_len:.0f} tecken, {near_zero}/{len(textlens_empty)} "
              f"under 200 tecken (nära-noll text = troligen skannad bild, olösbart utan OCR)")
        print(f"\nAv {len(textlens_empty)} TOMMA efter sidantal: {short_pdf} har <2 sidor (sannolikt "
              f"ALDRIG en riktig rapport, olösbart via just det PM:et), {long_pdf} har >=2 sidor "
              f"(potentiellt ett regex-/tabellmönster värt att jaga), {unknown_pages} okänt sidantal "
              f"(äldre cache-post från före sidantals-spårningen)")

    if empty_examples:
        print(f"\nExempel på TOMMA (bara >=2 sidor eller okänt sidantal – "
              f"<2-siders-fall visas inte, sannolikt olösbara):")
        for it, att, text, n_pages in empty_examples:
            pages_str = f"{n_pages} sidor" if n_pages is not None else "okänt sidantal"
            print(f"\n  {it.get('ticker')} {str(it.get('published', ''))[:10]} "
                  f"'{it.get('title', '')[:60]}' ({pages_str})")
            print(f"  PDF: {att['url']}")
            print(f"  Extraherad text ({len(text)} tecken): {text[:300]!r}")


def dump_page(url: str, page_num: int) -> None:
    """Skriver ut HELA den extraherade texten för EN specifik sida (1-indexerad),
    okapad. scan_pages() visar bara 80 tecken per sida – detta verktyg ger hela
    texten så att regex-mönster kan designas mot verklig text (t.ex. en
    tabellformaterad resultaträkning), inte gissas fram."""
    if pdfplumber is None:
        raise RuntimeError("paketet 'pdfplumber' saknas – pip install pdfplumber")
    print(f"Laddar ner {url} ...")
    pdf_bytes = _download_pdf(url)
    if pdf_bytes is None:
        print("Kunde inte ladda ner PDF:en.")
        return
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            print(f"Sida {page_num} finns inte (dokumentet har {len(pdf.pages)} sidor).")
            return
        page = pdf.pages[page_num - 1]
        t = page.extract_text() or ""
        print(f"--- sida {page_num}/{len(pdf.pages)}, {len(t)} tecken ---")
        print(t)


def scan_pages(url: str) -> None:
    """Sida-för-sida-diagnos: var i dokumentet börjar siffrorna? _MAX_PDF_PAGES
    kapar till de FÖRSTA 20 sidorna – men moderna årsredovisningar har ofta
    20-30 sidor hållbarhet/marknadsföring FÖRE nyckeltalen. Detta verktyg
    öppnar HELA PDF:en (ingen sidkapning), extraherar varje sida för sig och
    visar teckenlängd + om sidan innehåller en enhetstoken (Mkr/MSEK/tkr) +
    om sidans EGEN text ger minst ett extraherat fält. Facit på om det är
    sidkapet (_MAX_PDF_PAGES) eller ordordningen som är boven."""
    import re as _re
    if pdfplumber is None:
        raise RuntimeError("paketet 'pdfplumber' saknas – pip install pdfplumber")
    print(f"Laddar ner {url} ...")
    pdf_bytes = _download_pdf(url)
    if pdf_bytes is None:
        print("Kunde inte ladda ner PDF:en.")
        return
    unit_re = _re.compile(r"\b(Mkr|MSEK|tkr|TSEK|kkr)\b", _re.IGNORECASE)
    print("OK, skannar ALLA sidor (ingen _MAX_PDF_PAGES-kapning i detta verktyg)...")
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total = len(pdf.pages)
        print(f"Totalt {total} sidor i dokumentet (jämfört med _MAX_PDF_PAGES={_MAX_PDF_PAGES} som backfill() faktiskt läser)\n")
        for i, page in enumerate(pdf.pages, 1):
            try:
                t = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                t = ""
            has_unit = bool(unit_re.search(t))
            facts = {}
            if t:
                facts = extract_hard_facts(t)
                for field, d in extract_table_facts(t).items():
                    facts.setdefault(field, d)
            flag = ""
            if i > _MAX_PDF_PAGES:
                flag += " [UTANFÖR sidkapet]"
            if has_unit:
                flag += " [enhetstoken]"
            if facts:
                flag += f" [{len(facts)} FÄLT: {sorted(facts.keys())}]"
            if has_unit or facts or i <= 3:
                snippet = t[:80].replace("\n", " ⏎ ")
                print(f"  sida {i}/{total}: {len(t)} tecken{flag}  {snippet!r}")


def compare_layout(url: str) -> None:
    """Engångsjämförelse för EN given PDF-URL: standard page.extract_text()
    vs page.extract_text(layout=True). Bakgrund: diagnose_empty() visade att
    'tomma' PDF:er INTE är gamla/skannade filer (0/93 hade nära-noll text,
    snitt 17 398 tecken) – i stället är texten på layout-tunga försätts-/
    intro-sidor (t.ex. AAK:s årsredovisningar) ordkastad av pdfplumber:s
    default-läge, som följer PDF:ens interna objektordning i stället för
    visuell läsordning. layout=True är en kandidat-fix – detta verktyg
    testar den mot en KÄND trasig PDF (kör mot en av URL:erna som
    diagnose_empty skrev ut) i stället för att gissa att den hjälper.
    Laddar alltid ner färskt (ingen cache) – avsett för enstaka manuell
    körning, inte batch."""
    if pdfplumber is None:
        raise RuntimeError("paketet 'pdfplumber' saknas – pip install pdfplumber")
    print(f"Laddar ner {url} ...")
    pdf_bytes = _download_pdf(url)
    if pdf_bytes is None:
        print("Kunde inte ladda ner PDF:en (fel status eller för stor).")
        return
    print(f"OK, {len(pdf_bytes)} bytes. Extraherar med båda metoderna...")

    out_default: List[str] = []
    out_layout: List[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:_MAX_PDF_PAGES]:
            try:
                t1 = page.extract_text()
            except Exception:  # noqa: BLE001
                t1 = None
            if t1:
                out_default.append(t1)
            try:
                t2 = page.extract_text(layout=True)
            except Exception:  # noqa: BLE001
                t2 = None
            if t2:
                out_layout.append(t2)
    text_default = "\n".join(out_default)
    text_layout = "\n".join(out_layout)

    facts_default = extract_hard_facts(text_default)
    for field, d in extract_table_facts(text_default).items():
        facts_default.setdefault(field, d)
    facts_layout = extract_hard_facts(text_layout)
    for field, d in extract_table_facts(text_layout).items():
        facts_layout.setdefault(field, d)

    print(f"\nStandard-extraktion:   {len(text_default)} tecken, "
          f"{len(facts_default)} fält funna -> {sorted(facts_default.keys())}")
    print(f"layout=True-extraktion: {len(text_layout)} tecken, "
          f"{len(facts_layout)} fält funna -> {sorted(facts_layout.keys())}")

    print("\n--- Standard, första 500 tecken ---")
    print(text_default[:500])
    print("\n--- layout=True, första 500 tecken ---")
    print(text_layout[:500])

    if len(facts_layout) > len(facts_default):
        print(f"\n=> layout=True hittade {len(facts_layout) - len(facts_default)} fler fält – ser lovande ut.")
    elif len(facts_layout) == len(facts_default):
        print("\n=> Ingen skillnad i antal fält denna gång – kanske inte den rätta fixen (eller fel PDF att testa på).")
    else:
        print("\n=> layout=True hittade FÄRRE fält – inte en förbättring för denna PDF.")


def backfill(segment: Optional[str] = None, limit: Optional[int] = None) -> None:
    """Går igenom rapport-PM som INTE fick något extraherat ur press-texten
    (extract_hard_facts på item['text'] gav tomt) men SOM har minst en PDF-
    bilaga. Laddar ner+extraherar+kör om parsern mot PDF-texten. Resumable –
    varje PDF cachas för alltid. Skriver <results_dir>/fundamentals_from_pdf.csv.

    Enkel-instans: vägrar starta om en annan backfill redan kör (skyddar
    Pi:ns minne mot att två processer krokar ihop – har hänt upprepat)."""
    if not _acquire_lock():
        print("[mfn_pdf backfill] En annan backfill-process kör redan (se "
              f"{_lock_path()}). Avbryter för att inte uttömma minnet – "
              "vänta tills den är klar eller döda den först.")
        return
    try:
        _backfill_inner(segment, limit)
    finally:
        _release_lock()


def _backfill_inner(segment: Optional[str] = None, limit: Optional[int] = None) -> None:
    items = _report_items(segment)
    # extract_hard_facts() på press-texten körs EN gång per item (inte två,
    # som tidigare – onödigt dubbelarbete över tiotusentals PM).
    miss_items = [it for it in items if not extract_hard_facts(it.get("text") or "")]
    candidates_all = [it for it in miss_items if it.get("attachments")]
    candidates = candidates_all[:limit] if limit else candidates_all
    print(f"[mfn_pdf backfill] {len(candidates_all)}/{len(miss_items)} miss-PM har minst en "
          f"PDF-bilaga ({len(miss_items) - len(candidates_all)} saknar helt bilaga – olösbart utan)")
    if limit and len(candidates) < len(candidates_all):
        print(f"[mfn_pdf backfill] bearbetar {len(candidates)} av dem denna körning (limit={limit})")

    rows, ok, dl_fail, empty = [], 0, 0, 0
    for i, it in enumerate(candidates, 1):
        att = pick_attachment(it["attachments"])
        text = get_pdf_text(it["id"], att["url"])
        if text is None:
            dl_fail += 1
        else:
            # Narrativ-mönstret (samma parser som körs mot PM-textens
            # "X uppgick till Y (Z) Mkr"-meningar) OCH tabell-mönstret
            # (resultat-/balansräkning i tabellformat, sett djupt in i
            # årsredovisningar) – tabellträffar fyller bara i FÄLT SOM
            # SAKNAS, narrativa träffar vinner om båda hittar samma fält
            # (redan validerade mot fler verkliga exempel).
            facts = extract_hard_facts(text)
            for field, d in extract_table_facts(text).items():
                facts.setdefault(field, d)
            if facts:
                ok += 1
                row = {"ticker": it.get("ticker"), "published": it.get("published"),
                       "period": detect_period(it.get("title") or ""), "pm_id": it.get("id"),
                       "title": it.get("title"), "pdf_url": att["url"]}
                for field, d in facts.items():
                    row[field] = d.get("value")
                    row[f"{field}_unit"] = d.get("unit", "")
                    if "prior_period" in d:
                        row[f"{field}_prior"] = d["prior_period"]
                rows.append(row)
            else:
                empty += 1
        if i % 20 == 0:
            print(f"  ...{i}/{len(candidates)} ({ok} ok, {dl_fail} nedladdningsfel, "
                  f"{empty} tomma efter extraktion)")
            # Extra försäkran mot minnesfragmentering på 2GB-Pi:n – tvinga en
            # gc-cykel var 20:e PDF (billigt jämfört med _PDF_REQUEST_PAUSE_S).
            import gc
            gc.collect()
        time.sleep(_PDF_REQUEST_PAUSE_S)

    print(f"\n[mfn_pdf backfill] klart: {ok} PM fick nya fält ur PDF, {dl_fail} kunde inte laddas "
          f"ner/öppnas, {empty} gav ändå tomt (t.ex. en skannad bild utan textlager)")
    if not rows:
        print("Inga rader att skriva.")
        return

    cols = ["ticker", "published", "period", "pm_id", "title", "pdf_url"]
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    seg = config.SEGMENTS.get(segment) if segment else None
    seg = seg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    out = Path(config.anchor(seg["results_dir"])) / "fundamentals_from_pdf.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"[mfn_pdf backfill] {len(rows)} rader -> {out}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "backfill"
    if cmd == "compare_layout":
        if len(sys.argv) < 3:
            print("Användning: python -m altdata.mfn_pdf compare_layout <pdf-url>")
            return
        compare_layout(sys.argv[2])
        return
    if cmd == "scan_pages":
        if len(sys.argv) < 3:
            print("Användning: python -m altdata.mfn_pdf scan_pages <pdf-url>")
            return
        scan_pages(sys.argv[2])
        return
    if cmd == "dump_page":
        if len(sys.argv) < 4:
            print("Användning: python -m altdata.mfn_pdf dump_page <pdf-url> <sida>")
            return
        dump_page(sys.argv[2], int(sys.argv[3]))
        return
    seg = sys.argv[2] if len(sys.argv) > 2 else None
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    if cmd == "backfill":
        backfill(seg, limit)
    elif cmd == "diagnose_empty":
        diagnose_empty(seg, limit or 5)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
