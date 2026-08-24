"""instrument_master v2: REPARERAD Skatteverket-parsning och entitetsmatchning.

Atgardar tva rotorsaker, identifierade i PREMODEL_AUDIT_2026-08-08.md, INTE med
sarskilda regler for de sju kanda fallen utan med generell, korrekt logik:

BUG-FIX 1 - AKTIESLAGSKONFLATION: Skatteverkets sidor beskriver ofta FLERA
vardepapper (stamaktie, preferensaktie, C-aktie, D-aktie, SDB/depabevis) for
SAMMA bolag i en och samma handelsetabell. Den gamla koden valde helt enkelt
den SENASTE "avnoterad"-handelsen pa sidan, oavsett vilket aktieslag den
gallde. Fix: varje handelse aktieslagstaggas via regex, och nar en handelse
ska kopplas till ett SPECIFIKT Bors data/EODHD-instrument (vars eget aktieslag
harleds ur kodsuffixet -A/-B/-C/-D/-PREF/-SDB) anvands ENDAST handelser vars
aktieslag ar ANTINGEN otaggat (antas galla huvudklassen) ELLER matchar
malinstrumentets eget aktieslag.

BUG-FIX 2 - BYTEN-ALIAS-FELET: bytestabellens 'fran'-falt (foregangarens namn
i en foretagshandelse: uppkop, utdelning-i-natura, avknoppning) anvandes
felaktigt som om det vore ETT ALTERNATIVT NAMN FOR SIDANS EGET BOLAG i
namnmatchningen. Det later t.ex. Millicoms egen sida (som i sin bytestabell
har "Kinnevik -> Millicom, Inlosen") matcha mot KINNEVIKS ISIN via namnet
"Kinnevik". Fix: byten anvands ENDAST i den separata, redan befintliga
efterfoljar-fallbacken (via 'till', for att spara en traffytta om bolaget
bytt namn/gatt upp i ett annat) - ALDRIG som direkt namnvariant for sidans
EGEN identitet.

Fristaende v2-kod. Legacy lases READ-ONLY. Genomsoker HELA universumet pa
nytt (1648 sidor) - ingen manuell specialregel for de sju kanda fallen.
"""
from __future__ import annotations

import difflib
import glob
import gzip
import html as H
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

LEGACY = Path("/home/hannesb/momentum_prod_work/momentum_ml")
LC = LEGACY / "cache"
EOD = LC / "eodhd_archive/ST"
V2 = Path("/home/hannesb/momentum_v2")
PAGES = V2 / "raw/skatteverket/pages"
LEG_PAGES = LC / "aktiehistorik"
MASTER = V2 / "docs/probes/instrument_master.json"
SAKNAS = V2 / "docs/probes/missing_price_history.json"
DIFF_RAPPORT = V2 / "docs/probes/instrument_master_v2_diff.json"

_MAN = {"januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
        "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11,
        "december": 12}
_DATUM = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MAN) + r")(?:\s+(\d{4}))?\b", re.I)
_AVNOT = re.compile(r"avnoterad|avnotering|avregistrerad", re.I)
_NYNOT = re.compile(r"ny\s+notering|nynotering", re.I)
_NAMN = re.compile(r"namnändring\s+från\s+(.+?)\s+till\s+(.+?)(?:\s+\d|\.|$)", re.I)
_ORG = re.compile(r"[Oo]rganisationsnummer[^0-9]{0,60}(\d{6})-?(\d{4})")

# ---------------------------------------------------------- AKTIESLAG ------
# Ordning kritisk: "preferensaktie" måste testas FÖRE de enskilda bokstäverna
# (annars matchar t.ex. "B-aktie" i "...serie B-aktier..." innan preferens
# hinner testas om båda förekommer i samma mening).
#   "aktie" följs i källtexten av valfri svensk böjning: aktie/aktier/aktien/
#   aktierna/aktiens/aktieägare/aktieägarna/aktiekonvertibler m.fl. Mönstren
#   matchar därför stammen "aktie" utan avslutande \b (endast inledande \b för
#   att undvika att t.ex. "xyz-aktie" felaktigt matchar hyfsat mitt i ett ord).
#   Verifierat mot samtliga böjningsformer i raw/skatteverket/pages/*.html.
_SLAG_MONSTER = [
    ("PREF", re.compile(r"preferensaktie|pref-?aktie", re.I)),
    ("SDB", re.compile(r"\bsdb\b|depåbevis", re.I)),
    ("C", re.compile(r"\bc-aktie|serie\s+c\b", re.I)),
    ("D", re.compile(r"\bd-aktie|serie\s+d\b", re.I)),
    ("A", re.compile(r"\ba-aktie|serie\s+a\b", re.I)),
    ("B", re.compile(r"\bb-aktie|serie\s+b\b", re.I)),
]
#   Svenskt elidat sammansatt uttryck: "Stam- och Preferensaktie" (stammens
#   "aktie"-led utelämnas eftersom det delas med efterföljande ord). Utan
#   detta missas t.ex. Oscar Properties (OP) rad "Stam- och Preferensaktie
#   samt Preferensaktie av serie B är avnoterade..." helt för stamaktien -
#   den taggades PREF (första träff i _SLAG_MONSTER) trots att händelsen
#   uttryckligen även gäller stamaktien, vilket tystade bort en KORREKT
#   avnoteringssignal för målinstrumentet OP (som saknar aktieslagssuffix).
#   Verifierat mot samtliga 4 förekomster i korpusen (raw + legacy-fallback):
#   alla är genuina gemensamma stam+preferens-händelser, ingen falsk träff.
_STAMAKTIE = re.compile(r"\bstamaktie|\bstam-\s*och\b", re.I)


def tagga_aktieslag(text: str) -> str | None:
    """None = otaggat (antas gälla huvudklassen/den enda klassen på sidan)."""
    if _STAMAKTIE.search(text):
        return None
    for tagg, mönster in _SLAG_MONSTER:
        if mönster.search(text):
            return tagg
    return None


def kod_till_aktieslag(kod: str) -> str | None:
    """Härleder målinstrumentets eget aktieslag ur EODHD/Börsdata-kodsuffixet."""
    k = kod.upper()
    if "PREF" in k:
        return "PREF"
    if "SDB" in k:
        return "SDB"
    m = re.search(r"-([A-D])$", k)
    return m.group(1) if m else None


def kompatibel(event_slag: str | None, mal_slag: str | None) -> bool:
    """En otaggad händelse (event_slag=None) antas alltid gälla huvudklassen.
    En explicit taggad händelse måste matcha målets EGET aktieslag exakt."""
    return event_slag is None or event_slag == mal_slag


def _txt(h: str) -> str:
    return H.unescape(re.sub(r"<[^>]+>", " ", h)).replace("\xa0", " ")


def _tabeller(h: str) -> list:
    ut = []
    for tm in re.finditer(r"<table[^>]*>(.*?)</table>", h, re.S | re.I):
        rader = []
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tm.group(1), re.S | re.I):
            c = [_txt(x).strip() for x in
                 re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rm.group(1), re.S | re.I)]
            if c:
                rader.append(c)
        if rader:
            ut.append(rader)
    return ut


def _sv_datum(text: str, ar: int):
    # Käll-HTML tappar ibland mellanslaget efter "den" (t.ex. "den11 augusti",
    # 5 förekomster i hela korpusen) - troligen en bortstädad inline-tagg utan
    # ersättande mellanslag. Rent mekanisk reparation av mellanslaget, ändrar
    # inget innehåll. Utan den missar _DATUM hela träffen (\b kräver
    # ordgräns, men "n" och "1" är båda \w-tecken - ingen gräns däremellan).
    text = re.sub(r"\bden(\d)", r"den \1", text, flags=re.I)
    m = _DATUM.search(text)
    if not m:
        return None
    import datetime
    try:
        return datetime.date(int(m.group(3)) if m.group(3) else ar,
                             _MAN[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return None


def tolka_sida(h: str) -> dict | None:  # noqa: C901
    t = _tabeller(h)
    hs = next((tb for tb in t if [x.strip().lower() for x in tb[0]][:2] == ["år", "kommentarer"]),
              None)
    if hs is None or len(hs) < 2:
        return None
    txt = _txt(h)
    mo = _ORG.search(txt)
    orgnr = f"{mo.group(1)}-{mo.group(2)}" if mo else None

    statustext = hs[1][1] if len(hs[1]) > 1 else ""
    if re.search(r"\bavnoterad\b", statustext, re.I):
        status = "avnoterad"
    elif re.search(r"\bnoterad\b", statustext, re.I):
        status = "noterad"
    else:
        status = "okänd"

    handelser, namnbyten = [], []
    for r in hs[2:]:
        if len(r) < 2 or not r[0].strip():
            continue
        try:
            ar = int(r[0].strip())
        except ValueError:
            continue
        s = r[1].strip()
        d = _sv_datum(s, ar)
        slag = tagga_aktieslag(s)
        nm = _NAMN.search(s)
        if nm:
            namnbyten.append({"fran": nm.group(1).strip(), "till": nm.group(2).strip(), "ar": ar})
            typ = "namnändring"
        elif _AVNOT.search(s):
            typ = "avnotering"
        elif _NYNOT.search(s):
            typ = "notering"
        else:
            typ = "övrigt"
        handelser.append({"ar": ar, "datum": d, "typ": typ, "text": s, "aktieslag": slag})

    # bytestabell: "Aktie | Anledning | Nummer" - ENDAST för efterföljarspårning
    byten = []
    bt = next((tb for tb in t if [x.strip().lower() for x in tb[0]][:2] == ["aktie", "anledning"]),
              None)
    if bt:
        for r in bt[1:]:
            if len(r) < 2 or not r[0].strip():
                continue
            par = re.split(r"\s+-\s+", r[0])
            byten.append({"fran": par[0].strip(), "till": par[1].strip() if len(par) > 1 else None,
                          "anledning": r[1].strip()})

    nots_alla = [e for e in handelser if e["typ"] == "notering"]
    forsta = min(nots_alla, key=lambda e: (e["ar"], e["datum"] or "")) if nots_alla else None

    return {"orgnr": orgnr, "status": status, "handelser": handelser,
            "forsta_notering": forsta["datum"] if forsta else None,
            "forsta_notering_ar": forsta["ar"] if forsta else None,
            "forsta_ar": min((e["ar"] for e in handelser), default=None),
            "sista_ar": max((e["ar"] for e in handelser), default=None),
            "namnbyten": namnbyten, "byten": byten, "n_handelser": len(handelser)}


def valj_avnotering(handelser: list, status: str, mal_slag: str | None) -> dict | None:
    """Senaste avnoteringshändelse som är KOMPATIBEL med målets aktieslag.
    Händelser för ett ANNAT explicit taggat aktieslag ignoreras helt - de
    beskriver ett annat värdepapper, inte det vi spårar."""
    if status == "noterad":
        return None
    kompatibla = [e for e in handelser if e["typ"] == "avnotering"
                 and kompatibel(e["aktieslag"], mal_slag)]
    return kompatibla[0] if kompatibla else None          # nyast-först, verifierat i sidordningen


# ------------------------------------------------------------------ namn ---
def norm(s) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(publ\.?\)|\bpubl\b", " ", s)
    s = re.sub(r"\b(ab|abp|asa|a/s|plc|inc|oyj|holding|group|the|of|och)\b", " ", s)
    s = re.sub(r"\bser(ie)?\.?\s*[a-d]\b", " ", s)
    s = re.sub(r"[^a-z0-9åäöéü ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def isin_ok(x) -> str | None:
    s = (x or "").strip().upper()
    return s if len(s) == 12 and s[:2].isalpha() else None


def bygg_index() -> dict:
    namn2isin: dict = {}
    isin2eod: dict = {}
    namn2eod: dict = {}
    kallor = Counter()

    for p in sorted(glob.glob(str(LC / "borsapi/companies_all_*.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        for x in (d.get("data") or []):
            z = isin_ok(x.get("isin"))
            n = norm(x.get("name"))
            if z and n:
                namn2isin.setdefault(n, set()).add(z)
                kallor["borsapi"] += 1

    bd = json.loads((V2 / "docs/probes/instruments_live.json").read_text(encoding="utf-8"))
    for x in bd:
        z = isin_ok(x.get("isin"))
        n = norm(x.get("name"))
        if z and n:
            namn2isin.setdefault(n, set()).add(z)
            kallor["borsdata"] += 1

    for p in glob.glob(str(LC / "mfn/*.json")):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        poster = d.get("items") if isinstance(d, dict) else (d if isinstance(d, list) else [])
        for it in (poster or [])[:6]:
            if not isinstance(it, dict):
                continue
            zs = [isin_ok(z) for z in (it.get("isins") or [])]
            nm = norm(it.get("author_name"))
            for z in zs:
                if z and nm:
                    namn2isin.setdefault(nm, set()).add(z)
                    kallor["mfn"] += 1

    for grupp, fil in (("active", "active_catalogue.json"), ("delisted", "delisted_catalogue.json")):
        for x in json.loads((EOD / fil).read_text(encoding="utf-8")):
            post = {"code": x.get("Code"), "namn": x.get("Name"), "typ": x.get("Type"),
                    "grupp": grupp, "isin": isin_ok(x.get("Isin"))}
            if post["isin"]:
                isin2eod.setdefault(post["isin"], []).append(post)
            n = norm(x.get("Name"))
            if n:
                namn2eod.setdefault(n, []).append(post)
    return {"namn2isin": namn2isin, "isin2eod": isin2eod, "namn2eod": namn2eod,
            "kallor": dict(kallor)}


_UNIVERSUM = set(json.loads(
    (V2 / "validated/prices/prices_validated.json").read_text(encoding="utf-8")).keys())
_VOLYM_CACHE: dict = {}


def medelvolym(post: dict) -> float:
    """Genomsnittlig daglig handelsvolym - fallback-tie-break, se los_upp."""
    key = (post["grupp"], post["code"])
    if key in _VOLYM_CACHE:
        return _VOLYM_CACHE[key]
    sub = "delisted" if post["grupp"] == "delisted" else "active"
    p = EOD / sub / "eod" / f"{post['code']}.json.gz"
    v = 0.0
    if p.exists():
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                d = json.load(f)
            vols = [x.get("volume") or 0 for x in d]
            v = sum(vols) / len(vols) if vols else 0.0
        except Exception:  # noqa: BLE001
            v = 0.0
    _VOLYM_CACHE[key] = v
    return v


def välj_kandidat(kandidatposter: list) -> dict:
    """Flera ISIN kan legitimt dela normaliserat bolagsnamn (flera noterade
    aktieslag med SKILDA riktiga ISIN, t.ex. Sagax har A/B/D/PREF som fyra
    olika värdepapper). Kontrollerat empiriskt: för varje sådant bolag är
    ALLTID exakt EN klass redan medlem i det etablerade Spår A-universumet
    (validated/prices/prices_validated.json, byggt oberoende via Nasdaq
    Stockholm marketId 1/2/3). Det är den relevanta, entydiga
    disambigueringsgrunden - INTE en volymgissning, som visade sig ge fel
    svar för Sagax (SAGA-D hade marginellt högre medelvolym än SAGA-B, trots
    att SAGA-B är den faktiskt spårade instrumentet)."""
    i_universum = [p for p in kandidatposter if p["code"] in _UNIVERSUM]
    if len(i_universum) == 1:
        return i_universum[0]
    if len(i_universum) > 1:
        # bör inte inträffa (en klass per bolag i universumet), men om det gör
        # det: fall tillbaka på volym bland just dessa, deterministiskt.
        return max(i_universum, key=medelvolym)
    return max(kandidatposter, key=medelvolym)


def los_upp(namn_varianter: list, idx: dict) -> tuple:
    """Endast SIDANS EGNA namn/namnbyten - ALDRIG byten-tabellens 'fran' (se
    BUG-FIX 2 i moduldocstringen).

    BUG-FIX 3 (upptäckt vid granskning av denna reparation): ett bolagsnamn
    kan legitimt peka på FLERA verkliga ISIN (flera noterade aktieslag, t.ex.
    SBB-B och SBB-D är olika värdepapper med olika ISIN). Den ursprungliga
    koden itererade en Python-`set` av ISIN-kandidater, vilket är
    HASH-ORDNINGSBEROENDE och alltså INTE deterministiskt mellan körningar -
    en helt annan sorts fel än aktieslagskonflationen, men med samma
    symptom (fel aktieslag kopplas till bolagets historik). Kandidaterna
    sorteras nu deterministiskt, och om fler än en har en EODHD-post väljs
    den med högst genomsnittlig handelsvolym (se `medelvolym`)."""
    n2i, i2e, n2e = idx["namn2isin"], idx["isin2eod"], idx["namn2eod"]
    for i, nv in enumerate(namn_varianter):
        n = norm(nv)
        if not n:
            continue
        etikett = "eget namn" if i == 0 else "alt. namn"
        kandidater = sorted(z for z in n2i.get(n, ()) if z in i2e)
        if kandidater:
            if len(kandidater) == 1:
                return i2e[kandidater[0]][0], f"ISIN via {etikett}"
            poster = [i2e[z][0] for z in kandidater]
            bäst = välj_kandidat(poster)
            metod_tagg = "universum" if bäst["code"] in _UNIVERSUM else "volym"
            return bäst, f"ISIN via {etikett} ({metod_tagg}disambiguerad, {len(kandidater)} kandidater)"
        if n in n2e:
            return n2e[n][0], f"exakt namn ({etikett})"
    nycklar = sorted(n2e)
    for i, nv in enumerate(namn_varianter):
        n = norm(nv)
        if len(n) < 6:
            continue
        nara = difflib.get_close_matches(n, nycklar, n=1, cutoff=0.90)
        if nara:
            return n2e[nara[0]][0], "fuzzy namn"
    return None, None


# BUG-FIX 4 (upptäckt vid granskning av denna reparation) - AVKNOPPNINGS-
# KONFLATION I EFTERFÖLJARFALLBACKEN: byten-tabellens 'till'-fält användes
# som efterföljarkandidat oavsett anledning. Men en rad med anledning
# "Utdelning" (eller köpoptioner/inköpsrätter/återköp/unit/likvidation/
# teckningsoptioner m.fl.) beskriver INTE att ursprungsbolaget blev/gick upp
# i målbolaget - den beskriver att AKTIEÄGARNA dessutom fick målbolagets
# aktier utdelade (avknoppning). Ursprungsbolaget fortsätter existera som en
# EGEN, separat identitet. Det gav SCA:s egen sida (byten: "SCA AB ->
# Essity AB, Utdelning") fel koppling till ESSITY-B istället för SCA:s egen
# SCA-B, och MTG:s egen sida fel koppling till NENT-B istället för MTG:s
# egen kod. Ytterligare generellt tecken på avknoppning, oavsett angiven
# anledning: om samma 'fran' på en och samma sida pekar mot FLERA olika
# 'till'-mål kan inget av dem vara EN entydig efterföljare (t.ex. Kinnevik
# -> Transcom/Invik/MTG/Netcom/Korsnäs, samtliga "Utdelning"/"Inlösen" från
# samma fran - ett tydligt en-till-flera-mönster, inte en identitetsövergång).
_EJ_KONTINUITET = re.compile(
    r"utdelning|ink[öo]psr[äa]tt|k[öo]poption|återköp|\bunit\b|likvidation|"
    r"teckningsoption|inlösenrätt|säljrätt|förlagsbevis|skuldebrev|avskiljbar",
    re.I)


def _efterfoljare_kandidater(byten: list) -> list:
    mal_per_fran: dict = {}
    for by in byten:
        if by.get("till"):
            mal_per_fran.setdefault(norm(by.get("fran")), set()).add(by["till"])
    ut = []
    for by in byten:
        till = by.get("till")
        if not till:
            continue
        if _EJ_KONTINUITET.search(by.get("anledning") or ""):
            continue
        if len(mal_per_fran.get(norm(by.get("fran")), ())) > 1:
            continue
        ut.append(till)
    return ut


# BUG-FIX 5 (upptäckt vid granskning av denna reparation) - UPPKÖPS-
# KONFLATION I EFTERFÖLJARFALLBACKEN: en byten-rad med anledning "Inlösen"/
# "Uppköp"/"Byte" kan lika gärna beskriva att ETT REDAN ETABLERAT, separat
# bolag KÖPTE UPP/löste in ursprungsbolaget, som en genuin namnbytes-
# kontinuitet. Skillnaden är osynlig i anledningsfältet men syns i TIDEN:
# en genuin efterföljare (nytt namn/ny notering) börjar handlas KRING
# ursprungets sista år - ett redan etablerat uppköpande bolag har handlats
# långt innan. Gav Gambro AB (avnoterad 2006, uppköpt av ABB via "Inlösen")
# fel koppling till ABB Ltd (handlats sedan 1999, dvs 7 år FÖRE Gambros
# avnotering) - hade fått Gambros datum skriva över ABBs egen post och
# felaktigt trunkera ABBs fortsatt aktiva prisserie vid 2006.
_TIDSMARGINAL_AR = 2


def _rimlig_efterfoljare(kandidat_post: dict, ursprung_sista_ar: int | None) -> bool:
    if not ursprung_sista_ar:
        return True  # inget att jämföra mot - inget skäl att avvisa
    serie = har_serie(kandidat_post)
    if not serie:
        return True
    kandidat_start_ar = int(serie["forsta"][:4])
    return kandidat_start_ar >= ursprung_sista_ar - _TIDSMARGINAL_AR


def har_serie(post: dict) -> dict | None:
    if not post:
        return None
    sub = "delisted" if post["grupp"] == "delisted" else "active"
    p = EOD / sub / "eod" / f"{post['code']}.json.gz"
    if not p.exists():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    if not d:
        return None
    return {"forsta": d[0]["date"], "sista": d[-1]["date"], "n": len(d)}


def alla_sidor() -> dict:
    ut = {}
    for f in PAGES.glob("*.html"):
        ut.setdefault(f.stem.split("__")[0], f)
    for f in LEG_PAGES.glob("_probe_*_html.html"):
        m = re.match(r"_probe_(.+?)_4_", f.name)
        if m:
            ut.setdefault(m.group(1), f)
    return ut


def main() -> None:  # noqa: C901
    gammal_master = json.loads(MASTER.read_text(encoding="utf-8")) if MASTER.exists() else []
    gammal_by_slug = {r["slug"]: r for r in gammal_master}

    idx_bolag = json.loads((LEG_PAGES / "_company_index.json").read_text(encoding="utf-8"))
    bolag = []
    for x in idx_bolag:
        u = x.get("url", "")
        if "/aktiehistorik/" not in u or "beskrivning" in u:
            continue
        m = re.search(r"/([^/]+)\.4\.[0-9a-f]+\.html$", u)
        if m:
            bolag.append({"namn": x.get("name"), "slug": m.group(1), "url": u})
    sidor = alla_sidor()
    print(f"index {len(bolag)} bolag | sidor tillgängliga {len(sidor)}")

    idx = bygg_index()
    print(f"identifierarindex: namn→ISIN {len(idx['namn2isin'])} namn "
          f"(källor {idx['kallor']}), ISIN→EODHD {len(idx['isin2eod'])}, "
          f"namn→EODHD {len(idx['namn2eod'])}")

    master, metoder = [], Counter()
    tagg_stat = Counter()
    for b in bolag:
        p = sidor.get(b["slug"])
        f = tolka_sida(p.read_text(encoding="utf-8", errors="replace")) if p else None
        rad = {"slug": b["slug"], "namn": b["namn"], "url": b["url"]}
        if f is None:
            rad["status"] = "ej tolkbar"
            master.append(rad)
            metoder["ej tolkbar sida"] += 1
            continue

        # BUG-FIX 2: endast sidans EGET namn + egna namnbyten som sökvarianter.
        # byten-tabellens 'fran' används ALDRIG här.
        varianter = [b["namn"]]
        for nb in f["namnbyten"]:
            varianter += [nb.get("fran"), nb.get("till")]
        efterfoljare = _efterfoljare_kandidater(f["byten"])
        post, metod = los_upp([v for v in varianter if v], idx)
        if post is None and efterfoljare:
            # BUG-FIX 5: pröva varje kandidat separat och hoppa över de som
            # inte är tidsmässigt rimliga (se _rimlig_efterfoljare ovan).
            # Jämförelseåret hämtas via BUG-FIX 1:s egen kompatibilitetslogik
            # (endast avnoteringshändelser förenliga med KANDIDATENS eget
            # aktieslag räknas) - annars fångar en aktieslagsspecifik
            # händelse (t.ex. "SDB avnoterad" vid en ren SDB->direktnoterad
            # AB-konvertering, som INTE rör stamaktiens fortsatta handel)
            # fel och avvisar en genuin, kontinuerlig efterföljare (VEF Ltd
            # SDB -> VEF AB, samma instrument sedan 2015, bara SDB-omslaget
            # avvecklat 2021).
            for kandidatnamn in efterfoljare:
                kp, km = los_upp([kandidatnamn], idx)
                if kp is None:
                    continue
                kp_slag = kod_till_aktieslag(kp["code"])
                kompatibel_avn = valj_avnotering(f["handelser"], f["status"], kp_slag)
                ursprung_ar = kompatibel_avn["ar"] if kompatibel_avn else None
                if not _rimlig_efterfoljare(kp, ursprung_ar):
                    continue
                post, metod = kp, f"efterföljare ({km})"
                break
        metoder[metod or "INGEN TRÄFF"] += 1

        # BUG-FIX 1: aktieslagskompatibel avnotering, bestämd EFTER att målets
        # eget aktieslag är känt (kräver post/EODHD-kod).
        mal_slag = kod_till_aktieslag(post["code"]) if post else None
        avn = valj_avnotering(f["handelser"], f["status"], mal_slag)
        for e in f["handelser"]:
            if e["typ"] == "avnotering":
                tagg_stat[e["aktieslag"] or "otaggad/huvudklass"] += 1

        rad.update({
            "orgnr": f["orgnr"], "status": f["status"],
            "avnoterad_datum": avn["datum"] if avn else None,
            "avnoterad_ar": avn["ar"] if avn else None,
            "avnoterad_orsak": (avn["text"][:300] if avn else None),
            "avnoterad_aktieslag_matchning": mal_slag,
            "forsta_notering": f["forsta_notering"], "forsta_notering_ar": f["forsta_notering_ar"],
            "forsta_ar": f["forsta_ar"], "sista_ar": f["sista_ar"],
            "namnbyten": f["namnbyten"], "byten": f["byten"], "n_handelser": f["n_handelser"],
            "eodhd": post, "metod": metod, "serie": har_serie(post),
        })
        master.append(rad)

    # BUG-FIX 6 (upptäckt vid granskning av denna reparation) -
    # KODÅTERANVÄNDNINGS-DISAMBIGUERING: när FLERA Skatteverket-sidor pekar
    # mot SAMMA EODHD-kod (äkta kodåteranvändning: en gammal instans
    # avnoterad, en ny instans senare noterad under samma kod, ELLER en
    # kvarvarande matchningskonflikt) avgjorde nedströms kod (kod2post/
    # avnoterad i build_validated_prices.py) tidigare ARBITRÄRT vilken
    # sidas avnoteringsdatum som vann - sist i listan skrev över, oavsett
    # om det stämde. Gav t.ex. Gränges (GRNG, fortsatt noterat 2026) och
    # AcadeMedia (ACAD, fortsatt noterat 2026) fel trunkeringsdatum från en
    # annan, äldre post med samma kod. Fix: samtliga rader med samma kod
    # DELAR samma underliggande prisserie (serien beror bara på koden), så
    # dess FAKTISKA status är entydig - eodhd.grupp=="active" betyder
    # koden inte är avnoterad alls (None vinner alltid, oavsett vad en
    # enskild gammal sida påstår); annars vinner den rad vars datum ligger
    # NÄRMAST seriens sista handelsdag (delisting sker per definition nära
    # sista handelsdagen). Ingen trolig kandidat (>400 dagars avstånd, t.ex.
    # PFE/Pfizer där Pharmacia-uppköpet 2003 INTE är samma händelse som
    # Pfizers egen senare avnotering) ger hellre None (dokumenterad lucka,
    # jfr COLL/KDEV) än ett datum som sannolikt är fel. Rör ENDAST koder
    # med fler än en matchande sida - lämnar >1600 entydiga rader orörda.
    kod_grupper: dict = {}
    for r in master:
        kod = (r.get("eodhd") or {}).get("code")
        if kod:
            kod_grupper.setdefault(kod, []).append(r)

    for kod, rader in kod_grupper.items():
        if len(rader) < 2:
            continue
        eodhd0 = rader[0].get("eodhd") or {}
        serie0 = rader[0].get("serie")
        if eodhd0.get("grupp") == "active":
            bast = (None, None, None)
        elif serie0:
            sista = date.fromisoformat(serie0["sista"][:10])
            kandidater = [r for r in rader if r.get("avnoterad_datum")]
            if not kandidater:
                continue
            n = min(kandidater, key=lambda r: abs(
                (sista - date.fromisoformat(r["avnoterad_datum"][:10])).days))
            avstand = abs((sista - date.fromisoformat(n["avnoterad_datum"][:10])).days)
            bast = ((n["avnoterad_datum"], n["avnoterad_ar"], n["avnoterad_orsak"])
                    if avstand <= 400 else (None, None, None))
        else:
            continue
        for r in rader:
            r["avnoterad_datum"], r["avnoterad_ar"], r["avnoterad_orsak"] = bast

    # BUG-FIX 7 (CODEX_SECOND_OPINION_V2_ABC.md, fynd B-2) - SAMMA ISIN, OLIKA
    # EODHD-KOD: EODHD byter ibland ticker vid ett bolagsnamnbyte och SKAPAR EN
    # NY KOD med HELA historiken bakåtfylld, samtidigt som den gamla koden
    # finns kvar som "delisted" och fortfarande refereras av en äldre
    # Skatteverket-sida. Utan omdirigering ger det två separata rader i
    # instrument_master för SAMMA instrument (t.ex. Ledstiernan AB -> EMPIR-B
    # (delisted, 1998-2023) och mySafety Group AB -> SAFETY-B (active,
    # 1998-2026, samma ISIN SE0010769182, samma startdatum) - identisk
    # underliggande prisserie, bara den nya kodens är en superset). Nedströms
    # (Börsdata-insId-matchning, fundamenta) fick den gamla koden då en egen,
    # felaktig avnoteringsstatus. Fix: när en ISIN har flera EODHD-koder och
    # EN är "active" med en serie som TIDSMÄSSIGT TÄCKER (start <= start,
    # slut >= slut) en annans "delisted"-serie, omdirigeras den delisted
    # radens eodhd-attribuering och avnoteringsstatus till den aktiva koden -
    # den är bevisligen samma instrument, inte en egen avnoterad identitet.
    # Radens EGEN historiska text (namnbyten, byten, url) bevaras oförändrad.
    isin_grupper: dict = {}
    for r in master:
        isin = (r.get("eodhd") or {}).get("isin")
        if isin:
            isin_grupper.setdefault(isin, []).append(r)

    for isin, rader in isin_grupper.items():
        koder = {(r.get("eodhd") or {}).get("code") for r in rader}
        if len(koder) < 2:
            continue
        aktiva = [r for r in rader if (r.get("eodhd") or {}).get("grupp") == "active"]
        if len(aktiva) != 1:
            continue  # entydig omdirigering kräver exakt en aktiv kandidat
        akt = aktiva[0]
        akt_serie = akt.get("serie")
        if not akt_serie:
            continue
        akt_start, akt_slut = akt_serie["forsta"], akt_serie["sista"]
        for r in rader:
            if r is akt or (r.get("eodhd") or {}).get("grupp") != "delisted":
                continue
            serie = r.get("serie")
            if not serie or not (serie["forsta"] >= akt_start and serie["sista"] <= akt_slut):
                continue  # inte en dokumenterad superset - omdirigera inte
            r["eodhd"] = akt["eodhd"]
            r["serie"] = akt["serie"]
            r["avnoterad_datum"] = r["avnoterad_ar"] = r["avnoterad_orsak"] = None
            r["metod"] = f"omdirigerad (samma ISIN, tickerbyte hos EODHD) -> {akt['slug']}"

    MASTER.write_text(json.dumps(master, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nUPPLÖSNINGSMETOD ({len(master)} bolag):")
    for k, v in metoder.most_common():
        print(f"  {str(k):34s} {v:>5d}")
    print(f"\nAKTIESLAG PÅ AVNOTERINGSHÄNDELSER (samtliga sidor, före kompatibilitetsfiltrering):")
    for k, v in tagg_stat.most_common():
        print(f"  {k:20s} {v:>5d}")

    # ---------------- diff mot gamla instrument_master.json -------------
    diff = {"nya_avnoterad": [], "borttagna_avnoterad": [], "andrat_datum": []}
    for r in master:
        gammal = gammal_by_slug.get(r["slug"])
        if not gammal:
            continue
        g_datum = gammal.get("avnoterad_datum")
        n_datum = r.get("avnoterad_datum")
        if g_datum != n_datum:
            if g_datum and not n_datum:
                diff["borttagna_avnoterad"].append({"namn": r["namn"], "kod": (r.get("eodhd") or {}).get("code"),
                                                     "gammalt_datum": g_datum, "orsak_borttagen": gammal.get("avnoterad_orsak")})
            elif n_datum and not g_datum:
                diff["nya_avnoterad"].append({"namn": r["namn"], "kod": (r.get("eodhd") or {}).get("code"),
                                              "nytt_datum": n_datum})
            else:
                diff["andrat_datum"].append({"namn": r["namn"], "kod": (r.get("eodhd") or {}).get("code"),
                                             "gammalt": g_datum, "nytt": n_datum})
    print(f"\nDIFF MOT FÖREGÅENDE instrument_master.json:")
    print(f"  avnotering BORTTAGEN (var fel, är nu null): {len(diff['borttagna_avnoterad'])}")
    for x in diff["borttagna_avnoterad"]:
        print(f"    {x['kod']!s:10s} {x['namn'][:36]:36s} var {x['gammalt_datum']}  "
              f"({(x['orsak_borttagen'] or '')[:50]})")
    print(f"  avnotering TILLKOMMEN (fanns inte förut): {len(diff['nya_avnoterad'])}")
    for x in diff["nya_avnoterad"][:15]:
        print(f"    {x['kod']!s:10s} {x['namn'][:36]:36s} nytt {x['nytt_datum']}")
    print(f"  avnoteringsDATUM ÄNDRAT (samma bolag, annat datum): {len(diff['andrat_datum'])}")
    for x in diff["andrat_datum"][:15]:
        print(f"    {x['kod']!s:10s} {x['namn'][:36]:36s} {x['gammalt']} -> {x['nytt']}")

    DIFF_RAPPORT.write_text(json.dumps(diff, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nartefakt: {MASTER}\n            {DIFF_RAPPORT}")


if __name__ == "__main__":
    main()
