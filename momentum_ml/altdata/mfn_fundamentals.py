"""
altdata/mfn_fundamentals.py – Regex-extraherar HÅRDA finansiella siffror
direkt ur MFN-pressmeddelandenas text: en bred kanonisk taxonomi (revenue,
gross_profit, ebitda/adjusted_ebitda, ebit/adjusted_ebit, ebita/adjusted_ebita,
pbt, net_profit, eps/eps_basic/eps_diluted, kassaflödesmått, balansräknings-
poster, marginal-/avkastningsmått, utdelning, totalresultat, jämförelse-
störande poster, avskrivningar (för "owner earnings"), utestående aktier
(för P/E och P/B) – de två sistnämnda lagda till för Buffett-inspirerad
värderingsscreening). Ingen AI, inget nätanrop – bara mönstermatchning mot
vanliga svenska OCH engelska rapporteringsfraser ("Nettoomsättningen uppgick
till 125,3 (110,2) Mkr" ELLER "Rörelseresultatet uppgick till MSEK 724 (871)"
– båda enhet-ordningarna stöds, se nedan).

SYFTE: undersöka om vi kan täcka hela eller delar av Börsdata Pro+ GRATIS
genom att plocka siffrorna som redan finns i MFN-texten, i stället för att
betala för/sätta upp Börsdata-API:et. Resten (det regex missar) kan fyllas
manuellt.

ÄRLIGT (inte gissat): täckningen beror HELT på om bolaget klistrar in sin
fulla rapportnarrativ i själva MFN-PM:et eller bara publicerar en kort
announcement + PDF-länk (se mfn_fetch.py:s 'types'-kommando). Denna modul
kan ALDRIG läsa en PDF-bilaga. Kärnfälten (revenue/ebit/ebitda/net_profit/
eps/margin) är verifierade mot faktiska exempel ur skarp cache (Saabs
rapporter avslöjade "enhet-FÖRE-talet"-stilen och "procent" utskrivet i
stället för "%"). Den UTÖKADE taxonomin nedan (gross_profit, adjusted_*,
kassaflöde, balansposter, ROE/ROA/ROCE, utdelning, ...) kommer från en
tillhandahållen kanonisk synonymlista och är INTE ännu verifierad mot skarp
text – kör om selftest/misses efter denna ändring för att se faktisk effekt.

Två kända, medvetna avvägningar (inte buggar, men värda att känna till):
  · "Rörelseförlust" mappas till samma fält som EBIT (ebit) trots att en
    förlust ofta anges som ett POSITIVT tal ("Rörelseförlusten uppgick till
    5 Mkr" = EBIT -5, inte +5) – vi negerar INTE automatiskt eftersom vi inte
    kan skilja "förlust angiven som positivt tal" från "förlust redan angiven
    med minustecken" utan att se fler riktiga exempel.
  · "Justerat rörelseresultat" (adjusted_ebit) och bara "Rörelseresultat"
    (ebit) kan båda träffa SAMMA mening om en rapport bara nämner det
    justerade talet ("Justerat rörelseresultat uppgick till 20 Mkr" ger både
    ebit=20 OCH adjusted_ebit=20) – ett känt överlapp, inte en krasch.

    python -m altdata.mfn_fundamentals selftest large   # TRÄFFGRAD mot din cache
    python -m altdata.mfn_fundamentals misses large 2   # miss-PM med enhets-token kvar
    python -m altdata.mfn_fundamentals extract large    # bygg fundamentals_from_mfn.csv
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# ── Nummer/enhet-mönster (svensk notation: komma decimal, ev. mellanslag som
# tusentalsavgränsare, ev. minustecken) ────────────────────────────────────
# OBS: mellanslag/hårt mellanslag – INTE \s. \s matchar även \n/\t, vilket i
# skarp körning fångade en rad-brytning MITT I ett tal (HTML-tabell stripad
# till text) och kraschade _parse_num ("2\n271", "-8\n.8"). Ett riktigt tal
# spänner aldrig en radbrytning.
_NBSP = "\xa0"
_NUM = rf"-?\d[\d {_NBSP}]*(?:,\d+)?"
_UNIT = r"Mkr|MSEK|mkr|msek|tkr|TSEK|kkr|miljoner kronor"
_EPS_UNIT = r"kr|kronor|SEK"
# "%" ELLER utskrivet "procent" – Saabs rapporter (och sannolikt fler) skriver
# ut ordet i löptext-punktlistor ("minskade med 3 procent till...").
_PCT = r"%|procent"
# "ökade/minskade/steg/föll" tar ofta en "med X%"-klausul FÖRE "till" ("ökade
# med 12,4% till 125,3 Mkr") – vanligare i verklig text än verbet + "till"
# direkt (upptäckt genom selftest mot skarp cache: revenue hade en misstänkt
# LÄGRE träffgrad än net_profit/ebit trots att omsättning nästan alltid nämns
# – detta var orsaken, inte att siffran saknades).
_CONNECT = (
    r"uppgick till|uppgår till"
    # "uppgår till" (presens) – balansräkningsposter (Eget kapital, Skulder,
    # Antal aktier, ...) är en ÖGONBLICKSBILD vid periodens slut, inte ett
    # avslutat periodresultat, och skrivs därför ofta i presens ("Eget
    # kapital uppgår till...") snarare än perfekt/imperfekt ("uppgick
    # till..."). Lades till när shares_outstanding (nästan alltid presens)
    # byggdes – gynnar även övriga balansposter som redan fanns i taxonomin.
    rf"|(?:ökade|minskade|steg|föll)(?:\s+med\s+{_NUM}\s*(?:{_PCT}))?\s+till"
    r"|blev|var|på"
)
# Etiketten följs ibland av en parentetisk förkortning ("Rörelseresultatet
# (EBIT) uppgick till..."), en periods-kvalificerare ("...för perioden/
# kvartalet uppgick till...") och/eller "efter/före utspädning" (resultat per
# aktie) innan konnektorn.
_LABEL_TAIL = (
    r"(?:\s*\([^)]{1,15}\))?"
    r"(?:\s+för\s+(?:perioden|kvartalet|räkenskapsåret|helåret))?"
    r"(?:\s+(?:efter|före)\s+utspädning)?"
    r"\s+"
)


def _num_pattern_post(label_alts: str, unit: str = _UNIT, unit_optional: bool = False) -> re.Pattern:
    """'<etikett> uppgick till 125,3 (110,2) Mkr' – enheten kommer EFTER både
    aktuell siffra och jämförelseperioden i parentes. Jämförelseperioden är
    valfri. unit_optional=True för fält där etiketten SJÄLV redan säger vad
    som räknas (t.ex. "Antal aktier uppgår till 12 500 000" – "aktier"
    upprepas normalt aldrig efter talet, till skillnad från Mkr/kr som
    nästan alltid står ut skrivna). Görs ENDAST valfritt i post-varianten –
    i pre-varianten (_num_pattern_pre) är enheten det enda ankaret för VAR
    talet börjar, för riskabelt att göra valfritt där."""
    unit_group = rf"\s*(?P<unit>{unit})" + ("?" if unit_optional else "")
    return re.compile(
        rf"\b(?:{label_alts}){_LABEL_TAIL}(?:{_CONNECT})\s+"
        rf"(?P<val>{_NUM})"
        rf"(?:\s*\(\s*(?P<cmp>{_NUM})\s*\))?"
        rf"{unit_group}",
        re.I,
    )


def _num_pattern_pre(label_alts: str, unit: str = _UNIT) -> re.Pattern:
    """'<etikett> uppgick till MSEK 724 (871)' – enheten kommer FÖRE talen.
    Minst lika vanligt som post-varianten i tabell-/punktlisteformat (Saabs
    rapporter skriver konsekvent så: "Rörelseresultatet uppgick till MSEK
    724 (871)") – upptäckt via ett skarpt exempel där post-mönstret gav noll
    träff på ett bolag som uppenbart skriver ut alla nyckeltal."""
    return re.compile(
        rf"\b(?:{label_alts}){_LABEL_TAIL}(?:{_CONNECT})\s+"
        rf"(?P<unit>{unit})\s+"
        rf"(?P<val>{_NUM})"
        rf"(?:\s*\(\s*(?P<cmp>{_NUM})\s*\))?",
        re.I,
    )


def _flex(label: str) -> str:
    """Svenskt substantiv(-fras) – tillåt valfri böjningssuffix på VARJE ord,
    inte bara det sista (annars missar "Kassaflöde från..." när texten
    faktiskt skriver "Kassaflödet från..." – upptäckt via ett misslyckat
    testfall innan detta fanns). "Nettoomsättning" matchar alltså även
    "Nettoomsättningen"/"Nettoomsättningens", och "Kassaflöde från den
    löpande verksamheten" matchar även "Kassaflödet från den löpande
    verksamheten"."""
    return r"\s+".join(re.escape(w) + r"\w*" for w in label.split(" "))


def _fixed(label: str) -> str:
    """Bara den exakta frasen – används för KORTA VERSAL-AKRONYMER (EBIT,
    EPS, PBT, ROE...) och engelska fraser. Kritiskt för akronymer: '\\w*'
    skulle annars låta "EBIT" äta sig in i "EBITDA" och stjäla dess tal
    (verifierat: \\bEBIT\\b matchar INTE inuti "EBITDA" utan property, men en
    trailing \\w* bryter den garantin)."""
    return re.escape(label)


def _labels(flex: List[str] = (), fixed: List[str] = ()) -> str:
    return "|".join([_flex(l) for l in flex] + [_fixed(l) for l in fixed])


# ── Kanonisk taxonomi (svenska + engelska synonymer per fält) ──────────────
_VALUE_FIELDS: Dict[str, str] = {
    "revenue": _labels(
        flex=["Nettoomsättning", "Omsättning", "Intäkter", "Rörelsens intäkter",
              "Försäljning", "Nettoförsäljning", "Koncernens omsättning",
              "Försäljningsintäkter"],
        fixed=["Revenue", "Net Sales", "Sales", "Turnover", "Operating Revenue",
               "Operating Revenues"],
    ),
    "gross_profit": _labels(
        flex=["Bruttoresultat", "Bruttovinst"],
        fixed=["Gross Profit"],
    ),
    "ebitda": _labels(
        flex=["Rörelseresultat före avskrivningar",
              "Rörelseresultat före av- och nedskrivningar"],
        fixed=["EBITDA"],
    ),
    "adjusted_ebitda": _labels(
        fixed=["Justerad EBITDA", "Adjusted EBITDA", "Adj EBITDA", "Underlying EBITDA",
               "Underliggande EBITDA"],
    ),
    "ebit": _labels(
        # Rörelseförlust: se modul-docstringens avvägning om tecken.
        flex=["Rörelseresultat", "Rörelsens resultat", "Rörelsevinst", "Rörelseförlust"],
        fixed=["EBIT", "Operating Profit", "Operating Income", "Operating Earnings",
               "Earnings Before Interest and Tax"],
    ),
    "adjusted_ebit": _labels(
        flex=["Justerat rörelseresultat", "Underliggande rörelseresultat"],
        fixed=["Justerat EBIT", "Adjusted EBIT", "Underlying EBIT"],
    ),
    "ebita": _labels(fixed=["EBITA"]),
    "adjusted_ebita": _labels(fixed=["Justerad EBITA", "Adjusted EBITA"]),
    "pbt": _labels(
        flex=["Resultat före skatt", "Vinst före skatt", "Resultat innan skatt"],
        fixed=["Profit Before Tax", "Earnings Before Tax", "EBT"],
    ),
    "net_profit": _labels(
        flex=["Årets resultat", "Periodens resultat", "Resultat efter skatt",
              "Vinst efter skatt", "Nettoresultat", "Koncernens resultat",
              "Resultat hänförligt till moderbolagets aktieägare",
              "Resultat hänförligt till moderföretagets aktieägare"],
        fixed=["Net Income", "Net Profit", "Profit for the Year", "Profit for the Period",
               "Net Earnings", "Profit Attributable to Owners"],
    ),
    "cash_flow": _labels(flex=["Kassaflöde"], fixed=["Cash Flow"]),
    "operating_cash_flow": _labels(
        flex=["Kassaflöde från den löpande verksamheten"],
        fixed=["Cash Flow from Operating Activities"],
    ),
    "free_cash_flow": _labels(flex=["Fritt kassaflöde"], fixed=["Free Cash Flow"]),
    "equity": _labels(flex=["Eget kapital"], fixed=["Equity"]),
    "assets": _labels(flex=["Tillgångar"], fixed=["Assets"]),
    "liabilities": _labels(flex=["Skulder"], fixed=["Liabilities"]),
    "net_debt": _labels(flex=["Nettoskuld"], fixed=["Net Debt"]),
    "dividend": _labels(flex=["Utdelning"], fixed=["Dividend"]),
    "comprehensive_income": _labels(
        flex=["Totalresultat"],
        fixed=["Total Comprehensive Income", "Comprehensive Income"],
    ),
    "special_items": _labels(
        flex=["Jämförelsestörande poster", "Engångsposter", "Exceptionella poster"],
        fixed=["Items Affecting Comparability", "Exceptional Items", "Non-recurring Items"],
    ),
    # Lagt till för "owner earnings" (Buffett-modellen: nettoresultat +
    # avskrivningar − investeringar ± rörelsekapitalförändring) – utan
    # avskrivningar går owner earnings inte att räkna ur den redan
    # extraherade hårddatan. "Avskrivningar och nedskrivningar"/
    # "Av- och nedskrivningar" inkluderar teknisk sett även nedskrivningar
    # (impairment), inte bara ren avskrivning – en medveten förenkling
    # (samma post används ändå oftast SOM D&A-raden i svenska resultat-
    # räkningar, se AAK-exemplet i extract_table_facts-dokumentationen).
    "depreciation_amortization": _labels(
        flex=["Avskrivningar", "Avskrivningar och nedskrivningar", "Av- och nedskrivningar",
              "Avskrivningar på materiella och immateriella anläggningstillgångar"],
        fixed=["Depreciation and Amortization", "Depreciation", "Amortization", "D&A"],
    ),
}
# Två mönster per fält (enhet-efter, enhet-före) – första träff vinner.
_FIELD_PATTERNS: Dict[str, List[re.Pattern]] = {
    field: [_num_pattern_post(labels), _num_pattern_pre(labels)]
    for field, labels in _VALUE_FIELDS.items()
}

_EPS_FIELDS: Dict[str, str] = {
    "eps": _labels(flex=["Resultat per aktie", "Vinst per aktie"], fixed=["EPS"]),
    "eps_basic": _labels(flex=["Resultat per aktie före utspädning"], fixed=["Basic EPS"]),
    "eps_diluted": _labels(flex=["Resultat per aktie efter utspädning"], fixed=["Diluted EPS"]),
}
_EPS_PATTERNS: Dict[str, List[re.Pattern]] = {
    field: [_num_pattern_post(labels, _EPS_UNIT), _num_pattern_pre(labels, _EPS_UNIT)]
    for field, labels in _EPS_FIELDS.items()
}

# Utestående aktier – för P/E och P/B (Buffett-modellen). EGET fält, INTE
# _VALUE_FIELDS: ett aktieantal är inget penningvärde och har aldrig ett
# Mkr/MSEK-liknande enhetsord, bara "aktier"/"shares" – kräver därför sitt
# eget enhetsmönster, precis som EPS har _EPS_UNIT i stället för _UNIT.
# OVERIFIERAT ännu mot skarp text (samma status som modulens övriga
# utökade taxonomi tills selftest/misses körts om) – "Genomsnittligt antal
# aktier" (används för EPS-beräkning) och "Antal aktier vid periodens
# utgång" (faktiskt utestående, rätt för P/E-jämförelse mot ett aktuellt
# pris) särskiljs INTE här, en medveten förenkling: de skiljer sig bara
# marginellt om inga nyemissioner/återköp skett under perioden.
_SHARE_UNIT = r"aktier|shares"
_SHARE_FIELDS: Dict[str, str] = {
    "shares_outstanding": _labels(
        flex=["Antal aktier", "Antal utestående aktier", "Totalt antal aktier",
              "Antal registrerade aktier", "Genomsnittligt antal aktier"],
        fixed=["Number of Shares", "Shares Outstanding", "Outstanding Shares",
               "Total Number of Shares", "Weighted Average Number of Shares"],
    ),
}
_SHARE_PATTERNS: Dict[str, List[re.Pattern]] = {
    # unit_optional=True i post-varianten: "Antal aktier uppgår till
    # 12 500 000" upprepar aldrig "aktier" efter talet – etiketten säger
    # redan vad som räknas. Pre-varianten ("aktier 12 500 000", ovanligt i
    # svensk text) behåller kravet på enhetsordet som ankare.
    field: [_num_pattern_post(labels, _SHARE_UNIT, unit_optional=True),
            _num_pattern_pre(labels, _SHARE_UNIT)]
    for field, labels in _SHARE_FIELDS.items()
}


def _pct_pattern(label_alts: str) -> re.Pattern:
    return re.compile(
        rf"\b(?:{label_alts}){_LABEL_TAIL}(?:{_CONNECT})\s+(?P<val>{_NUM})\s*(?:{_PCT})", re.I)


_PCT_FIELDS: Dict[str, str] = {
    "ebit_margin_pct": _labels(flex=["Rörelsemarginal", "EBIT-marginal"],
                                fixed=["Operating Margin", "EBIT Margin"]),
    "equity_ratio_pct": _labels(flex=["Soliditet"], fixed=["Equity Ratio"]),
    "roe_pct": _labels(flex=["Avkastning på eget kapital"], fixed=["Return on Equity", "ROE"]),
    "roa_pct": _labels(flex=["Avkastning på totalt kapital"], fixed=["Return on Assets", "ROA"]),
    "roce_pct": _labels(flex=["Avkastning på sysselsatt kapital"],
                         fixed=["Return on Capital Employed", "ROCE"]),
}
_PCT_PATTERNS: Dict[str, re.Pattern] = {
    field: _pct_pattern(labels) for field, labels in _PCT_FIELDS.items()
}

# ── Tabellformat (resultaträkning/balansräkning/kassaflödesanalys ur PDF-
# bilagor) – helt annat mönster än ovanstående narrativa "X uppgick till Y
# (Z) Mkr"-meningar. Verifierat mot en riktig AAK-årsredovisnings
# resultaträkning (sida 124 av 190, hämtad via mfn_pdf.py:s dump_page):
#   "Nettoomsättning 26 46.021 45.052"
#   "Rörelseresultatet (EBIT) uppgick till..." <- INTE denna stil här
# Tabellens tal använder PUNKT som tusentalsavgränsare (annan konvention än
# löptexten som använder mellanslag/hårt mellanslag) – därför ett separat
# talmönster. Minustecknet varierar också (vanlig ASCII-hyphen på vissa
# rader, en annan dash-glyf på andra – sett i samma tabell: "-33.399" och
# "­41.678" [not\xadASCII-tecken]) – ett tecken-set täcker alla varianter.
_TABLE_MINUS = "[-‐‑‒–—−­]"
_TABLE_NUM = rf"{_TABLE_MINUS}?\d{{1,3}}(?:\.\d{{3}})*(?:,\d+)?"
# Etiketten följs ofta av en eller flera not-referenser (små heltal, ev.
# kommaseparerade: "5, 15, 26") INNAN de två faktiska kolumnvärdena – detta
# valfria kluster hoppas över. Kritiskt: kravet på att raden SLUTAR direkt
# efter exakt två tal (radankrat med $/re.M) gör att en femårs-
# sammanfattningstabell (t.ex. sida 10: "Nettoomsättning 35.452 50.425
# 46.028 45.052 46.021" – FEM kolumner) INTE matchar alls, i stället för att
# råka plocka fel kolumnpar – bekräftat manuellt mot den riktiga sida-10-
# texten (ingen träff, för många tal kvar efter etiketten för att mönstret
# ska nå radslutet).
_TABLE_NOTE = r"\d{1,3}(?:,\s*\d{1,3})*"
_TABLE_TAIL = r"(?:\s*\([^)]{1,15}\))?"  # t.ex. "Resultat per aktie ... (kr)"


def _table_row_pattern(label_alts: str) -> re.Pattern:
    # OBS: INGET ^-krav på radstart – pdfplumber klistrar ofta in
    # vänster-navigeringstext FÖRE själva raden på samma textrad
    # ("Vår strategi Nettoomsättning 26 46.021 45.052" – bekräftat i en
    # riktig AAK-resultaträkning). $-kravet (radslut, re.M) räcker för att
    # utesluta femårs-sammanfattningstabeller.
    return re.compile(
        rf"\b(?:{label_alts})\b{_TABLE_TAIL}\s+"
        rf"(?:{_TABLE_NOTE}\s+)?"
        rf"(?P<val>{_TABLE_NUM})\s+(?P<cmp>{_TABLE_NUM})\s*$",
        re.I | re.M,
    )


_TABLE_FIELD_PATTERNS: Dict[str, re.Pattern] = {
    field: _table_row_pattern(labels) for field, labels in _VALUE_FIELDS.items()
}
_TABLE_EPS_PATTERNS: Dict[str, re.Pattern] = {
    field: _table_row_pattern(labels) for field, labels in _EPS_FIELDS.items()
}
_TABLE_SHARE_PATTERNS: Dict[str, re.Pattern] = {
    field: _table_row_pattern(labels) for field, labels in _SHARE_FIELDS.items()
}


def _parse_table_num(s: str) -> float:
    for ch in "‐‑‒–—−­":
        s = s.replace(ch, "-")
    return float(s.replace(".", "").replace(",", "."))


def extract_table_facts(text: str) -> Dict[str, dict]:
    """Samma fälttaxonomi som extract_hard_facts(), men för TABELLFORMATERAD
    text (PDF-extraherade resultat-/balansräkningar) i stället för
    pressmeddelande-narrativ. Avsedd att köras UTÖVER extract_hard_facts()
    på PDF-text, inte i stället för – se mfn_pdf.py:s backfill() som slår
    ihop båda (narrativ-träff vinner om båda hittar samma fält)."""
    if not text:
        return {}
    out: Dict[str, dict] = {}
    for field, pat in {**_TABLE_FIELD_PATTERNS, **_TABLE_EPS_PATTERNS, **_TABLE_SHARE_PATTERNS}.items():
        m = pat.search(text)
        if not m:
            continue
        try:
            val = _parse_table_num(m.group("val"))
            cmp = _parse_table_num(m.group("cmp"))
        except ValueError:
            continue
        out[field] = {"value": val, "prior_period": cmp}
    return out

# ── Period-detektering ur titeln (svenska IR-titlar är starkt standardiserade) ─
_Q_RE = re.compile(r"\bQ([1-4])\b", re.I)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_MONTHRANGE_RE = re.compile(r"\b(januari|april|juli|oktober)[\s\-–]+(mars|juni|september|december)\b", re.I)
# Utskrivet ordningstal ("det ANDRA kvartalet 2023") – minst lika vanligt i
# svenska rapporttitlar som "Q2" (upptäckt via ett skarpt exempel: AAK:s
# "delårsrapport för det andra kvartalet 2023" gav tom period innan detta).
_QORD_RE = re.compile(r"\b(första|andra|tredje|fjärde)\s+kvartalet\b", re.I)
_QORD_TO_Q = {"första": "Q1", "andra": "Q2", "tredje": "Q3", "fjärde": "Q4"}
_FULLYEAR_KW = re.compile(r"bokslutskommuniké|helår(?:et|srapport)?", re.I)
_MONTH_TO_Q = {"januari": "Q1", "april": "Q2", "juli": "Q3", "oktober": "Q4"}

# Rapport-liknande PM (för att inte slösa regex-sökningar på ordernyheter etc.
# och för att selftest ska mäta rätt nämnare). Titlar, inte MFN:s 'type'-fält
# (det senare är inte verifierat – se mfn_fetch.py 'types').
_REPORT_TITLE_RE = re.compile(
    r"delårsrapport|kvartalsrapport|bokslutskommuniké|årsrapport|årsredovisning"
    r"|niomånadersrapport|halvårsrapport"
    # "Bolag X:s resultat för januari-september 2010" – ett äldre/alternativt
    # titelmönster (upptäckt i en riktig Saab-PM) som inte innehåller något av
    # orden ovan alls och annars faller helt utanför nämnaren – varken hit
    # eller miss, bara osynligt exkluderad.
    r"|resultat för\s+(?:januari|februari|mars|april|maj|juni|juli|augusti"
    r"|september|oktober|november|december|första|andra|tredje|fjärde)", re.I)
# En rapport-TITEL fångar även INBJUDNINGAR till presentationen av rapporten
# ("AAK bjuder in till presentation av delårsrapporten...") – dessa nämner
# rapportordet men innehåller per definition ALDRIG siffrorna (upptäckt via
# ett skarpt miss-exempel i selftest, inte en regex-lucka att laga). Utesluts
# explicit så nämnaren mäter faktiska rapport-PM, inte inbjudningar till dem.
_INVITATION_TITLE_RE = re.compile(
    r"bjuder in till|inbjuder till|inbjudan till|kallar till\s+(?:telefon|press)"
    # "Press- och analytikerkonferens i samband med publiceringen/offentlig-
    # görandet av X:s delårsrapport..." – en annan, minst lika vanlig
    # inbjudningsformulering (upptäckt via tre riktiga AAK-exempel ur
    # diagnose_empty som felaktigt räknades som missade rapporter, trots att
    # de per definition ALDRIG innehåller siffror – bara datum/tid för en
    # telefonkonferens).
    r"|press-?\s*(?:och\s+)?analytikerkonferens|telefonkonferens\s+i\s+samband\s+med",
    re.I)


def _parse_num(s: str) -> float:
    return float(s.replace(" ", "").replace(_NBSP, "").replace(",", "."))


def is_report_pm(item: dict) -> bool:
    title = str(item.get("title") or "")
    return bool(_REPORT_TITLE_RE.search(title)) and not _INVITATION_TITLE_RE.search(title)


def detect_period(title: str) -> Optional[str]:
    year_m = _YEAR_RE.search(title)
    year = year_m.group(1) if year_m else None
    # Bokslutskommuniké/helår kollas FÖRST: Q4-titlar innehåller ofta BÅDA
    # ("...fjärde kvartalet och bokslutskommuniké 2022") – helår är den mer
    # specifika signalen (bolaget klassar själva releasen som årssummeringen)
    # och ska vinna, inte kvartalsordet som råkar stå bredvid.
    if _FULLYEAR_KW.search(title):
        return f"Helår {year}" if year else "Helår"
    q_m = _Q_RE.search(title)
    if q_m:
        return f"Q{q_m.group(1)} {year}" if year else f"Q{q_m.group(1)}"
    qord_m = _QORD_RE.search(title)
    if qord_m:
        q = _QORD_TO_Q.get(qord_m.group(1).lower())
        if q:
            return f"{q} {year}" if year else q
    mr = _MONTHRANGE_RE.search(title)
    if mr:
        q = _MONTH_TO_Q.get(mr.group(1).lower())
        if q:
            return f"{q} {year}" if year else q
    return None


def _first_match(patterns: List[re.Pattern], text: str) -> Optional[re.Match]:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m
    return None


def _apply_patterns(out: Dict[str, dict], patterns_by_field: Dict[str, List[re.Pattern]], text: str) -> None:
    """Delad loop-kropp för _FIELD_PATTERNS/_EPS_PATTERNS/_SHARE_PATTERNS –
    samma post/pre-mönsterpar, samma defensiva _parse_num-hantering."""
    for field, patterns in patterns_by_field.items():
        m = _first_match(patterns, text)
        if not m:
            continue
        # Defensivt: en regex-träff garanterar inte ett parsbart tal (t.ex. ett
        # okänt HTML-strippnings-artefakt vi inte förutsett) – ett fält som inte
        # går att tolka ska hoppas över, aldrig krascha hela extraktionen.
        try:
            val = _parse_num(m.group("val"))
        except ValueError:
            continue
        d = {"value": val, "unit": m.group("unit")}
        if m.group("cmp"):
            try:
                d["prior_period"] = _parse_num(m.group("cmp"))
            except ValueError:
                pass
        out[field] = d


def extract_hard_facts(text: str) -> Dict[str, dict]:
    """{"revenue": {"value": 125.3, "unit": "Mkr", "prior_period": 110.2}, ...}
    Tomt dict om inget matchar (vanligast för PM som bara länkar en PDF)."""
    if not text:
        return {}
    out: Dict[str, dict] = {}
    _apply_patterns(out, _FIELD_PATTERNS, text)
    _apply_patterns(out, _EPS_PATTERNS, text)
    _apply_patterns(out, _SHARE_PATTERNS, text)
    for field, pat in _PCT_PATTERNS.items():
        m = pat.search(text)
        if not m:
            continue
        try:
            out[field] = {"value": _parse_num(m.group("val"))}
        except ValueError:
            pass
    return out


def _report_items(segment: Optional[str]) -> List[dict]:
    """Alla rapport-liknande PM i cachen (oavsett OOS-fönster – detta är inte
    en backtest-signal, bara datainsamling)."""
    from data.data_loader import load_sweden_universe
    seg = config.SEGMENTS.get(segment) if segment else None
    seg = seg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    cache_dir = Path(config.MFN_CACHE_DIR)
    out, seen = [], set()
    for t in tickers:
        p = cache_dir / f"{t}.json"
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for it in d.get("items", []):
            if it.get("id") in seen or not is_report_pm(it):
                continue
            seen.add(it.get("id"))
            it = dict(it)
            it["ticker"] = t
            out.append(it)
    return out


def selftest(segment: Optional[str] = None) -> None:
    """Mäter FAKTISK träffgrad mot redan hämtad cache. Inget nätanrop."""
    items = _report_items(segment)
    if not items:
        print("Inga rapport-liknande PM i cachen – kör mfn_fetch.py fetch <segment> först.")
        return
    hit, miss = 0, 0
    field_hits: Counter = Counter()
    miss_example = None
    hit_example = None
    for it in items:
        facts = extract_hard_facts(it.get("text") or "")
        if facts:
            hit += 1
            for f in facts:
                field_hits[f] += 1
            if hit_example is None:
                hit_example = (it, facts)
        else:
            miss += 1
            if miss_example is None:
                miss_example = it

    n = len(items)
    print(f"[mfn_fundamentals selftest] {n:,} rapport-liknande PM".replace(",", " "))
    print(f"  Minst 1 fält extraherat: {hit:,} ({hit / n:.0%})".replace(",", " "))
    print(f"  Inget extraherat (troligen bara 'se bifogad PDF'): {miss:,} ({miss / n:.0%})"
          .replace(",", " "))
    print("\n  Träffar per fält:")
    for f, c in field_hits.most_common():
        print(f"    {f:<20}{c:>6}  ({c / n:.0%})")

    if hit_example:
        it, facts = hit_example
        print(f"\n  Exempel PÅ TRÄFF ({it.get('ticker')}, {it.get('published', '')[:10]}): "
              f"'{it.get('title', '')[:60]}'")
        for f, d in facts.items():
            extra = f" (fg. period {d['prior_period']})" if "prior_period" in d else ""
            print(f"    {f}: {d['value']} {d.get('unit', '')}{extra}")
    if miss_example:
        print(f"\n  Exempel PÅ MISS ({miss_example.get('ticker')}, "
              f"{miss_example.get('published', '')[:10]}): '{miss_example.get('title', '')[:60]}'")
        txt = miss_example.get("text") or ""
        print(f"    text ({len(txt)} tecken): {txt[:200]}")

    print("\n  Dom: hög träffgrad (>60-70%) -> bär en stor del av hård-datan gratis, fyll")
    print("  resten manuellt. Låg träffgrad -> de flesta bolag länkar bara en PDF här;")
    print("  Börsdata (eller manuell inmatning för ett litet urval nyckelbolag) behövs.")


def extract(segment: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """Bygger <segmentets results_dir>/fundamentals_from_mfn.csv av alla lyckade
    extraktioner. VIKTIGT: skriver till segmentets EGEN results_dir (samma
    mönster som resten av pipelinen: results/ för large, results/small/ för
    small) – en tidigare version skrev alltid till samma fil oavsett segment,
    så 'extract small' körd efter 'extract large' skrev tyst över den."""
    items = _report_items(segment)
    rows = []
    for it in items:
        facts = extract_hard_facts(it.get("text") or "")
        if not facts:
            continue
        row = {"ticker": it.get("ticker"), "published": it.get("published"),
               "period": detect_period(it.get("title") or ""), "pm_id": it.get("id"),
               "title": it.get("title")}
        for field, d in facts.items():
            row[field] = d.get("value")
            row[f"{field}_unit"] = d.get("unit", "")
            if "prior_period" in d:
                row[f"{field}_prior"] = d["prior_period"]
        rows.append(row)

    if not rows:
        print("Inga extraherade rader – kör 'selftest' först för att se varför.")
        return

    cols = ["ticker", "published", "period", "pm_id", "title"]
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)

    if out_path:
        out = Path(out_path)
    else:
        seg = config.SEGMENTS.get(segment) if segment else None
        seg = seg or config.SEGMENTS[config.DEFAULT_SEGMENT]
        out = Path(config.anchor(seg["results_dir"])) / "fundamentals_from_mfn.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"[extract] {len(rows)} rader ({len(items)} rapport-PM genomsökta, "
          f"{len(rows) / max(len(items), 1):.0%} träffgrad) -> {out}")


_UNIT_HINT_RE = re.compile(rf"\b(?:{_UNIT})\b", re.I)


def _sentences_with_unit(text: str, context: int = 90) -> List[str]:
    """Korta textsnuttar runt varje förekomst av en enhets-token (Mkr/MSEK/...)
    – kompakt sätt att visa VARFÖR en PM missade utan att klistra in hela
    texten. Överlappande träffar slås ihop så samma mening inte upprepas."""
    spans = [(max(0, m.start() - context), min(len(text), m.end() + context))
             for m in _UNIT_HINT_RE.finditer(text)]
    merged: List[List[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [text[s:e].replace("\n", " ") for s, e in merged]


def misses(segment: Optional[str] = None, n: int = 2) -> None:
    """Hittar rapport-PM som MISSADE extraktion men som ändå innehåller en
    enhets-token (Mkr/MSEK/...) någonstans i texten – ett starkt tecken på att
    siffrorna FINNS men frasen inte känns igen än, till skillnad från äkta
    PDF-only-annonser (som redan identifierats via tidigare selftest-körningar
    och inte är värda att visa igen – de har inga enhets-token alls). Skriver
    ut kompakta snuttar runt varje siffra i stället för hela PM:et, så
    resultatet går att klistra tillbaka utan att svämma över."""
    items = _report_items(segment)
    candidates = []
    for it in items:
        text = it.get("text") or ""
        if extract_hard_facts(text):
            continue
        if _UNIT_HINT_RE.search(text):
            candidates.append(it)
    if not candidates:
        print("Inga miss-PM med enhets-token hittades – de kvarvarande missarna är "
              "sannolikt äkta PDF-only-annonser (inga siffror i texten alls).")
        return
    print(f"[mfn_fundamentals misses] {len(candidates)} miss-PM innehåller en enhets-token "
          f"(Mkr/MSEK/...) men gav noll extraherade fält – visar {min(n, len(candidates))}:\n")
    for it in candidates[:n]:
        print("=" * 78)
        print(f"{it.get('ticker')}  {it.get('published', '')[:10]}  '{it.get('title', '')}'")
        print("-" * 78)
        for snip in _sentences_with_unit(it.get("text") or "")[:10]:
            print(f"  ...{snip}...")
        print()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    seg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "selftest":
        selftest(seg)
    elif cmd == "extract":
        extract(seg)
    elif cmd == "misses":
        misses(seg, int(sys.argv[3]) if len(sys.argv) > 3 else 2)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
