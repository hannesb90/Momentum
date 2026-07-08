"""
altdata/mfn_pdf.py – Hämtar PDF-bilagor från MFN-cachens 'attachments'-fält
och kör den EXISTERANDE extract_hard_facts()-parsern (mfn_fundamentals.py)
mot PDF-texten i stället för press-releasens korta announcement-text.

Byggd för de PM som bara publicerar en kort announcement + PDF-länk utan
siffror i själva pressmeddelandet – bekräftat gång på gång via
mfn_fundamentals.py:s 'misses'-kommando (AAK:s årsredovisning, Tre Kronor,
...). Fältnamnet/strukturen ('content.attachments' =
[{file_title, content_type, url, tags}]) är VERIFIERAT mot skarp MFN-data
via mfn_fetch.py:s 'raw'-kommando, inte gissat. Att PDF-text + samma regex-
parser fungerar är verifierat mot ett syntetiskt testdokument (pdfplumber +
extract_hard_facts gav alla 6 kärnfält korrekt) – men INTE ännu mot en
riktig nedladdad MFN-PDF (kräver nät, körs på Pi:n).

Kräver mfn_fetch.py:s attachments-fält (schema 2) – 'fetch <segment>'
uppgraderar automatiskt gammal cache, ingen manuell radering behövs.

    python -m altdata.mfn_pdf backfill large        # alla miss-PM med PDF-bilaga
    python -m altdata.mfn_pdf backfill large 20      # bara de första 20 (snabbt test)
    python -m altdata.mfn_pdf diagnose_empty large   # varför gav vissa PDF:er noll fält? (inget nätanrop)
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
from altdata.mfn_fundamentals import extract_hard_facts, _report_items, detect_period

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
_MAX_PDF_PAGES = 20                 # nyckeltal ligger i sammanfattningen, inte sist i en 100-sidig rapport
_PDF_REQUEST_PAUSE_S = 1.0          # artigare paus än PM-textens – större filer, annan värd (storage.mfn.se/Cision)


def _pdf_text_cache_dir() -> Path:
    d = Path(config.anchor(getattr(config, "MFN_PDF_TEXT_CACHE_DIR", "cache/mfn_pdf_text")))
    d.mkdir(parents=True, exist_ok=True)
    return d


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


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Text ur de första _MAX_PDF_PAGES sidorna. En enskild trasig sida ska
    inte stoppa hela dokumentet – hoppa över den och fortsätt."""
    if pdfplumber is None:
        raise RuntimeError("paketet 'pdfplumber' saknas – pip install pdfplumber")
    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:_MAX_PDF_PAGES]:
            try:
                t = page.extract_text()
            except Exception:  # noqa: BLE001
                t = None
            if t:
                out.append(t)
    return "\n".join(out)


def get_pdf_text(pm_id: str, url: str) -> Optional[str]:
    """Evig cache (rapporter ändras inte i efterhand) – varje PDF laddas
    ner+extraheras högst en gång, oavsett hur många gånger backfill() körs."""
    cp = _pdf_text_cache_dir() / f"{_cache_key(pm_id, url)}.json"
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8")).get("text")
        except Exception:  # noqa: BLE001
            pass
    pdf_bytes = _download_pdf(url)
    if pdf_bytes is None:
        cp.write_text(json.dumps({"text": None, "error": "download_failed_or_too_large"}),
                       encoding="utf-8")
        return None
    try:
        text = extract_pdf_text(pdf_bytes)
    except Exception as e:  # noqa: BLE001 – trasig/krypterad PDF ska inte stoppa hela körningen
        cp.write_text(json.dumps({"text": None, "error": str(e)[:200]}), encoding="utf-8")
        return None
    cp.write_text(json.dumps({"text": text[:50000]}, ensure_ascii=False), encoding="utf-8")
    return text


def _peek_cached(pm_id: str, url: str) -> Optional[dict]:
    """Läser PDF-textcachen UTAN att trigga en nedladdning om den saknas –
    för diagnos av redan körda PDF:er, inte för att köra nya."""
    cp = _pdf_text_cache_dir() / f"{_cache_key(pm_id, url)}.json"
    if not cp.exists():
        return None
    try:
        return json.loads(cp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def diagnose_empty(segment: Optional[str] = None, n: int = 5) -> None:
    """Svarar EMPIRISKT på 'är de tomma PDF:erna gamla/skannade filer?' i
    stället för att gissa. Jämför år-fördelning och extraherad textlängd
    mellan lyckade och tomma resultat – nära-noll text = troligen en
    skannad bild utan textlager (olösbart utan OCR); mycket text men ändå
    noll fält = ett fras-/tabellmönster vi missar (potentiellt fixbart).
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
        if extract_hard_facts(text):
            by_year_ok[year] += 1
        else:
            by_year_empty[year] += 1
            textlens_empty.append(len(text))
            if len(empty_examples) < n:
                empty_examples.append((it, att, text))

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

    if empty_examples:
        print(f"\nExempel på TOMMA (för manuell koll):")
        for it, att, text in empty_examples:
            print(f"\n  {it.get('ticker')} {str(it.get('published', ''))[:10]} "
                  f"'{it.get('title', '')[:60]}'")
            print(f"  PDF: {att['url']}")
            print(f"  Extraherad text ({len(text)} tecken): {text[:300]!r}")


def backfill(segment: Optional[str] = None, limit: Optional[int] = None) -> None:
    """Går igenom rapport-PM som INTE fick något extraherat ur press-texten
    (extract_hard_facts på item['text'] gav tomt) men SOM har minst en PDF-
    bilaga. Laddar ner+extraherar+kör om parsern mot PDF-texten. Resumable –
    varje PDF cachas för alltid. Skriver <results_dir>/fundamentals_from_pdf.csv."""
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
            facts = extract_hard_facts(text)
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
