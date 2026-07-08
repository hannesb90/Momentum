"""
altdata/mfn_clean.py – Trimmar MFN-pressmeddelanden INNAN de skickas till
LLM:en, för att sänka token-kostnaden i den historiska massinhämtningen
(altdata/sentiment.py). sentiment.py:s prompt ber INTE modellen extrahera
siffror – schemat är rent kvalitativt (sentiment/materialitet/guidance/
VD-ton) – så "hård data"-extraktion i sig sänker inga LLM-tokens. Det som
FAKTISKT kostar tokens är att hela råtexten (upp till MFN_MAX_BODY_CHARS)
skickas in, och en stor del av den är standardiserad text utan signal.

Två oberoende åtgärder:

  1. strip_boilerplate() – klipper texten vid den TIDIGASTE av några kända,
     lagstadgade/konventionsstyrda avslutningsfraser: MAR-informations-
     plikten ("...är skyldigt att offentliggöra enligt EU:s marknadsmiss-
     bruksförordning"), IR-kontaktblocket ("För mer information kontakta"),
     och Certified Adviser-notisen (First North). Dessa bär ALDRIG signal –
     de är juridiskt obligatorisk/administrativ text som förekommer i
     praktiskt taget varje svenskt regulatoriskt PM, oftast sist i texten.

  2. is_routine() – en SMAL, säker delmängd av administrativa PM (kallelse
     till ÅRSstämma, finansiell kalender) som kan poängsättas med ett
     neutralt default-värde UTAN att anropa modellen alls. Medvetet snävt:
     en EXTRA bolagsstämma eller ett flaggningsmeddelande KAN bära riktig
     signal (kallas ofta för att godkänna en affär/nyemission, eller en
     stor ägare bygger/minskar en position) och skickas därför som vanligt.

INGET av detta är verifierat mot ett stort urval RIKTIGA MFN-texter – byggt
utifrån kända svenska IR-/lagkonventioner, inte gissning om MFN:s API-schema
(det är redan verifierat separat i mfn_fetch.py). Kör själv:

    python -m altdata.mfn_clean selftest large   # mät faktisk besparing mot din cache
"""
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Varje mönster matchar BÖRJAN på en boilerplate-sektion. Vi klipper texten
# vid den TIDIGASTE träffen (inte varje enskild) – enklare och säkrare än att
# försöka nästla ut flera separata block; värsta fall är att vi behåller lite
# för mycket, aldrig att vi klipper bort riktigt innehåll av misstag.
_BOILERPLATE_TRIGGERS = [
    # MAR-informationsplikten (lagstadgad formulering, sv + en)
    r"är skyldig[t]?\s+att\s+offentliggöra\s+enligt\s+(?:EU:s\s+)?marknadsmissbruksförordning",
    r"obliged\s+to\s+(?:make\s+(?:this\s+information\s+)?public|disclose\s+the\s+information)\s+"
    r"pursuant\s+to\s+(?:the\s+)?(?:EU\s+)?Market\s+Abuse\s+Regulation",
    # IR-kontaktblock (sv + en)
    r"för\s+(?:mer|ytterligare)\s+information[,]?\s*(?:vänligen\s+)?kontakta",
    r"for\s+(?:more|further)\s+information[,]?\s*(?:please\s+)?contact",
    # Certified Adviser-notis (First North)
    r"certifierad\s+rådgivare\s+är",
    r"certified\s+adviser\s+is",
]
_BOILERPLATE_RE = re.compile("|".join(f"(?:{p})" for p in _BOILERPLATE_TRIGGERS), re.I)

# Titelmönster för PM-kategorier utan investeringssignal (se modulens docstring
# för varför just dessa två och inte fler).
_ROUTINE_TITLE_RE = re.compile(
    r"kallelse\s+till\s+årsstämma"
    r"|kallelse\s+till\s+ordinarie\s+bolagsstämma"
    r"|finansiell\s+kalender"
    r"|datum\s+för\s+delårsrapport",
    re.I,
)

_ROUTINE_SCORE = {"sentiment": 0, "materiality": 0, "category": "other",
                   "guidance": 0, "ceo_tone": 0, "rationale": "Rutin-PM (auto, ingen modell anropad).",
                   "auto": True}


def strip_boilerplate(text: str) -> str:
    """Klipper text vid den första kända boilerplate-triggern. Oförändrad om
    ingen trigger hittas (vanligast för korta PM som saknar footer helt).
    Klipper vid närmast FÖREGÅENDE radbrytning (inte exakt vid träffen) så vi
    inte lämnar en avhuggen mening kvar sist i texten – rent kosmetiskt, ändrar
    inget om VAD som klipps bort."""
    if not text:
        return text
    m = _BOILERPLATE_RE.search(text)
    if not m:
        return text
    cut = m.start()
    nl = text.rfind("\n", 0, cut)
    if nl != -1:
        cut = nl
    return text[:cut].rstrip()


def is_routine(item: dict) -> bool:
    """True för en SMAL, säker delmängd administrativa PM (se docstring).
    Kallas innan ett LLM-anrop görs alls –träff = ingen token spenderas."""
    title = str(item.get("title") or "")
    return bool(_ROUTINE_TITLE_RE.search(title))


def routine_score(item: dict) -> dict:
    d = dict(_ROUTINE_SCORE)
    d["id"] = item.get("id")
    return d


def clean_item_text(item: dict) -> str:
    """Det som FAKTISKT ska skickas till modellen (ersätter rå item['text'])."""
    return strip_boilerplate(item.get("text") or "")


def selftest(segment: Optional[str] = None) -> None:
    """Mäter FAKTISK besparing mot redan hämtad MFN-cache – inget nätanrop,
    inga LLM-anrop. Visar: andel PM där boilerplate hittades + snittantal
    tecken sparade, samt hur många PM som klassas 'routine' (helt gratis)."""
    import json
    from altdata.sentiment import _load_cached_releases
    seg = segment or config.DEFAULT_SEGMENT
    items = _load_cached_releases(seg)
    if not items:
        print(f"Inga cachade PM för '{seg}' i OOS-fönstret – kör mfn_fetch.py fetch {seg} först.")
        return

    n = len(items)
    stripped_hits = 0
    chars_before = chars_after = 0
    routine_hits = 0
    example = None
    for it in items:
        raw = it.get("text") or ""
        trimmed = strip_boilerplate(raw)
        chars_before += len(raw)
        chars_after += len(trimmed)
        if len(trimmed) < len(raw):
            stripped_hits += 1
            if example is None and len(raw) - len(trimmed) > 50:
                example = (it, raw, trimmed)
        if is_routine(it):
            routine_hits += 1

    saved_chars = chars_before - chars_after
    print(f"[mfn_clean selftest] {n:,} PM ({seg})".replace(",", " "))
    print(f"  Boilerplate-träff: {stripped_hits:,}/{n:,} PM ({stripped_hits / n:.0%})".replace(",", " "))
    print(f"  Tecken: {chars_before:,} -> {chars_after:,}  "
          f"({saved_chars:,} sparade, {saved_chars / max(chars_before, 1):.0%} av totalen)"
          .replace(",", " "))
    print(f"  'Routine' (helt gratis, inget LLM-anrop): {routine_hits:,}/{n:,} PM ({routine_hits / n:.0%})"
          .replace(",", " "))
    # Grov token-uppskattning i linje med sentiment.py:s estimate_cost() (~4 tecken/token).
    tok_before = chars_before / 4.0
    tok_after_effective = (chars_after - sum(
        len(it.get("text") or "") for it in items if is_routine(it)
    )) / 4.0
    if tok_before:
        print(f"  Ungefärlig input-token-besparing (boilerplate + routine-skip): "
              f"{(1 - tok_after_effective / tok_before):.0%}")
    if example:
        it, raw, trimmed = example
        print(f"\n  Exempel ({it.get('ticker', '?')}, {it.get('published', '')[:10]}): "
              f"'{it.get('title', '')[:60]}'")
        print(f"    Före ({len(raw)} tecken): ...{raw[-200:]}")
        print(f"    Efter ({len(trimmed)} tecken): ...{trimmed[-120:]}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        selftest(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
