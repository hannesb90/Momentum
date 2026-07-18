"""
altdata/fund_theme_classifier.py – nischtema-klassificering av fonder inom
Avanzas BREDA "blandkategorier" (t.ex. "Teknologi" 95 fonder – blandar
halvledare, AI, moln, robotik och cybersäkerhet i en enda hink; se
avanza.fund_categories()). Låter headless Claude (Haiku – enkel
klassificering i hög volym, samma val som quality_screener.py, se
config.CLAUDE_MODEL_FAST) läsa de RIKTIGA fondnamnen och tagga varje fond
med ett specifikt nischtema, i stället för att vi handplockar en liten
fast lista (global_theme_momentum.py:s 10 nischfonder täcker bara det vi
redan råkade tänka på).

Inom varje nischtema väljs sedan en PRIMÄR fond: lägst totalavgift
(managementFee + productFee) bland fonder med tillräckligt ägarantal
(numberOfOwners >= config.FUND_THEME_MIN_OWNERS, en likviditets-/
förtroende-proxy – en nischfond med 3 ägare är sannolikt otillräckligt
handlad). Det är den konkreta kopplingen mellan avgift och urval du bad om.

REN KLASSIFICERING, ALDRIG SIGNAL – samma disciplin som resten av altdata/:
detta rankar inte fonder mot varandra på förväntad avkastning, bara
kategoriserar dem och väljer billigast inom en kategori en människa/annan
kod redan bestämt är "samma tema".

RENA kategorier (PURE_CATEGORIES: försvarsindustri/ädelmetaller/... – där
Avanzas kategorinamn redan ÄR temat) tas med rakt av utan LLM-kostnad.
Skrivningen MERGAR med befintlig fil (ny körning vinner per orderbookId,
primärval räknas om över hela den mergade mängden) – en enkategorikörning
klipper aldrig bort andra kategoriers rader. Temanamnen styrs mot en
KANONISK vokabulär (CANONICAL_THEMES) för stabilitet mellan körningar.

Förutsätter cache/avanza_fund_categories.csv (kör avanza.fund_categories()
först).

    python altdata/fund_theme_classifier.py classify                    # alla bland- + rena kategorier
    python altdata/fund_theme_classifier.py classify teknologi          # bara en blandkategori
    python altdata/fund_theme_classifier.py classify försvarsindustri   # bara en ren kategori (pass-through)
"""
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
import claude_headless as ch  # noqa: E402

# De Avanza-subCategories som empiriskt blandar flera olika nischteman
# (VERIFIERAT via fund_categories()-körning 2026-07-18 – breda hinkar där
# en enda kategorinamn inte räcker som temanamn).
MIXED_CATEGORIES = ("teknologi", "sjukvård", "energi", "industri", "strategi", "multi-asset")

# RENA kategorier som redan ÄR ett tema – tas med rakt av (pass-through,
# ingen LLM-kostnad, kategorinamnet blir temanamnet). Utan detta TAPPADES
# t.ex. Försvar helt ur temamomentumet när den datadrivna vägen tog över
# från den handplockade listan (verkligt fall: ASWC.L Future of Defence,
# ett faktiskt innehav, försvann ur rankningen – försvarsindustri
# klassificeras aldrig eftersom den inte är en blandkategori). "nuclear"
# utelämnas MEDVETET: överlappar "Uran & Kärnkraft" som energi-
# klassificeringen redan producerar – två named teman för samma sak vore
# dubbelräkning i rankningen.
PURE_CATEGORIES = {
    "försvarsindustri": "Försvar",
    "ädelmetaller": "Ädelmetaller",
    "industrimetaller": "Industrimetaller",
    "infrastruktur": "Infrastruktur",
    "kraftförsörjning": "Kraftförsörjning",
}

BATCH_SIZE = 10   # sänkt från 15 (verklig körning: 2/7 batchar fick timeout på 15)
BATCH_TIMEOUT = 180   # höjt från 120 (samma orsak)
MIN_OWNERS = getattr(config, "FUND_THEME_MIN_OWNERS", 200)

# KANONISK temavokabulär – prompten instruerar modellen att välja EXAKT
# ett av dessa namn när något passar, och bara uppfinna ett nytt när inget
# gör det. Skälet är STABILITET, inte smak: två skarpa körningar mot samma
# fonder gav olika etiketter för samma sak ("Future Mobility" vs "Framtidig
# mobilitet", "Förnybar energi" vs "CleanTech", "Blockchain & Kryptovalutor"
# vs "Kryptovalutor & Blockchain") – och nedströms strängmatchning
# (portfolio._ROTATION_GROUP_TO_NICHE_THEME, temamomentumets rankning över
# tid) dör TYST när namnet driver mellan körningar.
CANONICAL_THEMES = (
    "Halvledare", "AI & Robotik", "AI-infrastruktur", "Molntjänster",
    "Cybersäkerhet", "Kvantdatorer", "Rymdteknik", "Dronteknologi",
    "Bioteknik", "Medicinsk utrustning", "Läkemedel",
    "Förnybar energi", "Solenergi", "Väte", "Olja & Gas", "Uran & Kärnkraft",
    "Batterier & Elbilar", "Blockchain", "Kryptovalutor", "Fintech",
    "Internet", "E-handel", "Spel & Esports", "Internet of Things",
    "Smart Cities", "Vatten & Infrastruktur", "Gruvdrift & Metaller",
    "Jordbruk & Livsmedelsteknik",
)

_SYSTEM = """Du är en fondanalytiker. För VARJE fond nedan (bara namnet att gå på):
avgör vilket SPECIFIKT investeringstema fonden representerar bäst.

VÄLJ I FÖRSTA HAND EXAKT ETT av dessa etablerade temanamn (ordagrant,
ändra aldrig stavning/ordföljd – nedströms system matchar på exakt sträng):
""" + ", ".join(f'"{t}"' for t in CANONICAL_THEMES) + """

Bara om INGET av namnen ovan passar fonden får du ange ett nytt, kort
temanamn på svenska.

Om fonden är ett BRETT bransch-/landsindex utan tydlig nisch (t.ex. "iShares
Global Technology", ett helt lands aktiemarknad, en aktivt förvaltad fond utan
tema i namnet) – svara "Bred/diversifierad" i stället för att hitta på ett tema.
Gissa ALDRIG på fondens verkliga innehav utöver vad NAMNET säger.

Svara ENDAST med kompakt JSON, en nyckel per orderbookId (som sträng), ingen markdown:
  {"123456": "Halvledare", "789012": "Bred/diversifierad", ...}

Fonder:
"""


def _load_categories() -> List[dict]:
    p = Path(config.anchor("cache")) / "avanza_fund_categories.csv"
    if not p.exists():
        print(f"[fund_theme] {p} saknas – kör 'python -m altdata.avanza fund_categories' först.")
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _classify_batch(funds: List[dict]) -> Dict[str, str]:
    lines = [f'  {{"orderbookId": "{f["orderbookId"]}", "name": "{f["name"]}"}}' for f in funds]
    prompt = _SYSTEM + "\n".join(lines)
    result = ch.run(prompt, "", timeout=BATCH_TIMEOUT, model=config.CLAUDE_MODEL_FAST)
    if "error" in result:
        print(f"[fund_theme] batch ({len(funds)} fonder) misslyckades: {result['error']}")
        return {}
    return {k: v for k, v in result.items() if isinstance(v, str)}


def _classify_with_retry(funds: List[dict]) -> Dict[str, str]:
    """En gång om (verkligt fall: 2/7 batchar fick timeout på 120s/15-fonder
    – höjt till 180s/10 nu, men EN kort omförsök här kostar nästan inget
    och räddar data om det ändå händer igen)."""
    got = _classify_batch(funds)
    missing = [f for f in funds if f["orderbookId"] not in got]
    if missing:
        print(f"  {len(missing)} fonder saknade svar, försöker en gång till...")
        got.update(_classify_batch(missing))
    return got


def _fee(r):
    try:
        return float(r.get("managementFee") or 0) + float(r.get("productFee") or 0)
    except (TypeError, ValueError):
        return 999.0


def _owners(r):
    try:
        return int(float(r.get("numberOfOwners") or 0))
    except (TypeError, ValueError):
        return 0


def classify(category_filter: Optional[str] = None) -> None:
    rows = _load_categories()
    if not rows:
        return
    # Vilka kategorier LLM-klassificeras vs tas rakt av (pass-through)?
    if category_filter is None:
        mixed, pure = MIXED_CATEGORIES, dict(PURE_CATEGORIES)
    elif category_filter in PURE_CATEGORIES:
        mixed, pure = (), {category_filter: PURE_CATEGORIES[category_filter]}
    else:
        mixed, pure = (category_filter,), {}

    # En fond kan förekomma på flera kategori-rader (t.ex. både "teknologi" och
    # "hållbarhet") – dedupa på orderbookId så vi bara klassificerar/betalar en gång.
    by_id: Dict[str, dict] = {}
    for r in rows:
        if r.get("category_value") in mixed and r.get("orderbookId"):
            by_id.setdefault(r["orderbookId"], r)
    funds = list(by_id.values())

    themes: Dict[str, str] = {}
    if funds:
        print(f"[fund_theme] klassificerar {len(funds)} fonder ur {mixed} (Haiku, {BATCH_SIZE}/anrop)...")
        for i in range(0, len(funds), BATCH_SIZE):
            batch = funds[i:i + BATCH_SIZE]
            print(f"  batch {i // BATCH_SIZE + 1}/{-(-len(funds) // BATCH_SIZE)}...")
            themes.update(_classify_with_retry(batch))

    # Denna körnings rader: LLM-klassificerade först, pass-through-rena sedan
    # (LLM-resultatet vinner om en fond råkar ligga i båda sorterna).
    run_rows: Dict[str, dict] = {}
    for f in funds:
        theme = themes.get(f["orderbookId"], "Kunde inte klassificera")
        run_rows[f["orderbookId"]] = {**f, "theme": theme}
    n_pure = 0
    for r in rows:
        cat = r.get("category_value")
        if cat in pure and r.get("orderbookId") and r["orderbookId"] not in run_rows:
            run_rows[r["orderbookId"]] = {**r, "theme": pure[cat]}
            n_pure += 1
    if not run_rows:
        print(f"[fund_theme] inga fonder hittade för kategori(er) {mixed or tuple(pure)} "
              f"i avanza_fund_categories.csv.")
        return
    if n_pure:
        print(f"[fund_theme] +{n_pure} fonder rakt av från rena kategorier "
              f"({', '.join(sorted(set(pure.values())))}) – ingen LLM-kostnad")

    # MERGE, inte överskrivning (samma bugg-mönster som redan fixats i
    # avanza.sectors_extract): en enkategorikörning ('classify teknologi')
    # ska ALDRIG tyst klippa bort tidigare körningars energi-/sjukvårds-rader
    # ur filen – då tappar global_theme_momentum.py teman utan varning.
    # Ny körning vinner per orderbookId; primärvalen räknas därefter om över
    # HELA den mergade mängden (gamla is_primary_pick-flaggor är inte
    # giltiga längre när medlemslistorna per tema kan ha ändrats).
    out = Path(config.anchor("cache")) / "fund_niche_themes.csv"
    merged: Dict[str, dict] = {}
    if out.exists():
        try:
            for r in csv.DictReader(open(out, encoding="utf-8")):
                if r.get("orderbookId"):
                    merged[r["orderbookId"]] = r
        except Exception:  # noqa: BLE001
            merged = {}
    merged.update(run_rows)
    all_rows = list(merged.values())

    # Primär fond per tema: lägst totalavgift bland de med tillräckligt
    # ägarantal (likviditets-/förtroende-proxy) – annars billigast oavsett.
    by_theme: Dict[str, list] = {}
    for r in all_rows:
        if r["theme"] in ("Bred/diversifierad", "Kunde inte klassificera"):
            continue
        by_theme.setdefault(r["theme"], []).append(r)

    primary_ids = set()
    for theme, members in by_theme.items():
        liquid = [m for m in members if _owners(m) >= MIN_OWNERS]
        pool = liquid or members  # hellre billigast av alla än inget primärval
        best = min(pool, key=_fee)
        primary_ids.add((theme, best["orderbookId"]))

    for r in all_rows:
        r["is_primary_pick"] = (r["theme"], r["orderbookId"]) in primary_ids

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["orderbookId", "name", "countryCode", "riskScore",
                                          "numberOfOwners", "category_value", "category_display",
                                          "theme", "managementFee", "productFee", "is_primary_pick"])
        w.writeheader()
        for r in sorted(all_rows, key=lambda x: x.get("orderbookId") or ""):
            w.writerow({k: r.get(k, "") for k in w.fieldnames})

    n_broad = sum(1 for r in all_rows if r["theme"] == "Bred/diversifierad")
    n_failed = sum(1 for r in all_rows if r["theme"] == "Kunde inte klassificera")
    print(f"\n[fund_theme] {len(run_rows)} fonder i denna körning, {len(all_rows)} totalt i filen "
          f"-> {len(by_theme)} nischteman, {n_broad} bred/diversifierad, {n_failed} misslyckades -> {out}")
    print("\n  PRIMÄRVAL PER TEMA (billigast bland tillräckligt ägda, hela filen):")
    for theme, members in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
        best = next(m for m in members if (theme, m["orderbookId"]) in primary_ids)
        print(f"   {theme:<28} {len(members):>2} fond(er) – primär: {best['name']} "
              f"(avgift {_fee(best):.2%}, {_owners(best)} ägare)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "classify":
        classify(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
