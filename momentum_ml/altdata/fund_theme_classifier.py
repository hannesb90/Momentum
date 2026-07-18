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

Förutsätter cache/avanza_fund_categories.csv (kör avanza.fund_categories()
först).

    python altdata/fund_theme_classifier.py classify              # alla blandkategorier
    python altdata/fund_theme_classifier.py classify teknologi    # bara en kategori (test)
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
# en enda kategorinamn inte räcker som temanamn). Rena kategorier som redan
# ÄR ett tema (t.ex. "nuclear", "ädelmetaller") behöver ingen omklassning.
MIXED_CATEGORIES = ("teknologi", "sjukvård", "energi", "industri", "strategi", "multi-asset")

BATCH_SIZE = 10   # sänkt från 15 (verklig körning: 2/7 batchar fick timeout på 15)
BATCH_TIMEOUT = 180   # höjt från 120 (samma orsak)
MIN_OWNERS = getattr(config, "FUND_THEME_MIN_OWNERS", 200)

_SYSTEM = """Du är en fondanalytiker. För VARJE fond nedan (bara namnet att gå på):
avgör vilket SPECIFIKT investeringstema fonden representerar bäst. Exempel på bra,
specifika teman: "Halvledare", "AI & Robotik", "Molntjänster", "Cybersäkerhet",
"Bioteknik", "Medicinsk utrustning", "Läkemedel", "Förnybar energi", "Olja & Gas",
"Batterier & Elbilar", "Rymdteknik", "Kvantdatorer", "Fintech", "Vatten &
Infrastruktur", "Gruvdrift & Metaller", "Jordbruk & Livsmedelsteknik".

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


def classify(category_filter: Optional[str] = None) -> None:
    rows = _load_categories()
    if not rows:
        return
    cats = (category_filter,) if category_filter else MIXED_CATEGORIES
    # En fond kan förekomma på flera kategori-rader (t.ex. både "teknologi" och
    # "hållbarhet") – dedupa på orderbookId så vi bara klassificerar/betalar en gång.
    by_id: Dict[str, dict] = {}
    for r in rows:
        if r.get("category_value") in cats and r.get("orderbookId"):
            by_id.setdefault(r["orderbookId"], r)
    funds = list(by_id.values())
    if not funds:
        print(f"[fund_theme] inga fonder hittade för kategori(er) {cats} i avanza_fund_categories.csv.")
        return
    print(f"[fund_theme] klassificerar {len(funds)} fonder ur {cats} (Haiku, {BATCH_SIZE}/anrop)...")

    themes: Dict[str, str] = {}
    for i in range(0, len(funds), BATCH_SIZE):
        batch = funds[i:i + BATCH_SIZE]
        print(f"  batch {i // BATCH_SIZE + 1}/{-(-len(funds) // BATCH_SIZE)}...")
        themes.update(_classify_with_retry(batch))

    out_rows = []
    for f in funds:
        theme = themes.get(f["orderbookId"], "Kunde inte klassificera")
        out_rows.append({**f, "theme": theme})

    # Primär fond per tema: lägst totalavgift bland de med tillräckligt
    # ägarantal (likviditets-/förtroende-proxy) – annars billigast oavsett.
    by_theme: Dict[str, list] = {}
    for r in out_rows:
        if r["theme"] in ("Bred/diversifierad", "Kunde inte klassificera"):
            continue
        by_theme.setdefault(r["theme"], []).append(r)

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

    primary_ids = set()
    for theme, members in by_theme.items():
        liquid = [m for m in members if _owners(m) >= MIN_OWNERS]
        pool = liquid or members  # hellre billigast av alla än inget primärval
        best = min(pool, key=_fee)
        primary_ids.add(best["orderbookId"])

    for r in out_rows:
        r["is_primary_pick"] = r["orderbookId"] in primary_ids

    out = Path(config.anchor("cache")) / "fund_niche_themes.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["orderbookId", "name", "countryCode", "riskScore",
                                          "numberOfOwners", "category_value", "category_display",
                                          "theme", "managementFee", "productFee", "is_primary_pick"])
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})

    n_themes = len(by_theme)
    n_broad = sum(1 for r in out_rows if r["theme"] == "Bred/diversifierad")
    n_failed = sum(1 for r in out_rows if r["theme"] == "Kunde inte klassificera")
    print(f"\n[fund_theme] {len(out_rows)} fonder -> {n_themes} nischteman, "
          f"{n_broad} bred/diversifierad, {n_failed} misslyckades -> {out}")
    print("\n  PRIMÄRVAL PER TEMA (billigast bland tillräckligt ägda):")
    for theme, members in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
        best = next(m for m in members if m["orderbookId"] in primary_ids)
        print(f"   {theme:<28} {len(members):>2} fond(er) – primär: {best['name']} "
              f"(avgift {_fee(best):.2%}, {_owners(best)} ägare)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "classify":
        classify(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
