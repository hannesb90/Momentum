"""
quality_screener.py – Kvalitativ fundamental SÅLLNING (diskretionär tratt, EJ backtest).

Operationaliserar din checklista för tidiga, oupptäckta microcaps: läser varje
bolags senaste MFN-rapport + PM och låter Claude (Sonnet) poängsätta de kvalitativa
kriterierna (10-årings-test, global ambition, moat, ledning/skin-in-the-game,
säljkultur, adresserbar marknad, väg till lönsamhet, "under radarn") OCH extrahera
nyckeltal (omsättning, EBITDA, resultat, antal aktier) ur rapporttexten – så att vi
kan rita OT Analytics-style värderingsdiagram (börsvärde vs EBITDA, bubbla=omsättning,
x12/x18-multiplar) helt gratis.

VIKTIGT: detta KAN INTE backtestas/valideras statistiskt – det är en tratt som tar
fram en kortlista + case-underlag åt dig, byggd på DIN bedömning. Använd som urval,
inte som bevis. Hård regel i prompten: bedöm/extrahera ENBART det som står i texten;
hitta inte på (null när det inte går att belägga).

Körs på Pi:n EFTER mfn_fetch (för microcap-universumet):
    python altdata/mfn_fetch.py fetch small        # (+ ev. micro/nano-fetch)
    python altdata/quality_screener.py score       # poängsätt universumet (cachas per bolag)
    python altdata/quality_screener.py chart        # rita värderingsdiagram av de poängsatta
    python altdata/quality_screener.py one SAAB-B.ST   # ett bolag (test)
"""
import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from altdata.sentiment import _client, _parse_content   # återanvänd nyckel + robust JSON-parse

_REPORT_KW = ("delårsrapport", "bokslut", "kvartalsrapport", "halvårsrapport",
              "årsredovisning", "year-end", "interim", "q1", "q2", "q3", "q4")

_SYSTEM = (
    "Du är en erfaren svensk småbolagsinvesterare som letar tidiga, oupptäckta bolag "
    "med 10-bagger-potential. Du läser ett bolags senaste rapport + pressmeddelanden "
    "och bedömer det mot en checklista. ABSOLUT KRAV: basera ALLT enbart på den givna "
    "texten. Hittar du inte stöd för ett kriterium i texten – sätt null. Hitta ALDRIG "
    "på siffror, ägande, ledning eller marknad.\n\n"
    "Svara ENDAST med ett giltigt JSON-objekt (ingen prosa/fences) med fälten:\n"
    '  Kvalitativa betyg 1-5 (5=utmärkt), null om ej bedömbart ur texten:\n'
    '  "understand" (lätt att förstå – 10-årings-testet), "global" (global ambition),\n'
    '  "scalable" (skalbar affärsmodell), "moat" (konkurrensfördel/unikt erbjudande),\n'
    '  "sales" (säljkultur/förmåga att ta betalt), "mgmt" (ledning/styrelse + skin in '
    'the game om nämnt), "market" (tydlig & stor adresserbar marknad), '
    '"profit_path" (lönsam eller tydlig väg dit), "under_radar" (fortf. oupptäckt)\n'
    '  Nyckeltal UR TEXTEN (MSEK resp. miljoner aktier), null om ej angivet:\n'
    '  "revenue_msek" (omsättning senaste 12m/år), "ebitda_msek" (EBITDA/rörelseresultat '
    'senaste 12m/år), "net_result_msek", "shares_million" (antal aktier)\n'
    '  "mentioned_investors": lista på namngivna fonder/kända investerare i texten (annars [])\n'
    '  "red_flags": lista (t.ex. emissionsberoende, många aktier, förlust utan väg till vinst)\n'
    '  "pitch": caset i EN mening en 10-åring förstår\n'
    '  "memo": 2-3 meningar om varför det kan vara undervärderat och vad som krävs för omvärdering\n'
    'Exempel: {"understand":4,"global":5,"scalable":4,"moat":3,"sales":null,"mgmt":4,'
    '"market":4,"profit_path":2,"under_radar":4,"revenue_msek":120,"ebitda_msek":-15,'
    '"net_result_msek":-22,"shares_million":18,"mentioned_investors":["Carnegie Fonder"],'
    '"red_flags":["ännu ej lönsamt"],"pitch":"...","memo":"..."}'
)

_SCORE_KEYS = ["understand", "global", "scalable", "moat", "sales", "mgmt",
               "market", "profit_path", "under_radar"]


def _company_context(ticker: str):
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return None
    items = json.loads(p.read_text()).get("items", [])
    if not items:
        return None
    items = sorted(items, key=lambda it: it.get("published", ""), reverse=True)
    rep = next((it for it in items
                if any(k in it.get("title", "").lower() for k in _REPORT_KW)), None)
    docs = ([rep] if rep else []) + [it for it in items[:4] if it is not rep]
    text = ""
    for it in docs:
        text += f"\n--- {it.get('published','')[:10]} | {it.get('title','')} ---\n{it.get('text','')}\n"
    return text[: config.QUALITY_MAX_CHARS]


def _cache_path(ticker: str) -> Path:
    d = Path(config.QUALITY_CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{ticker}.json"


def _composite(s: dict) -> float:
    vals = [s[k] for k in _SCORE_KEYS if isinstance(s.get(k), (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def score_company(ticker: str, name: str, client=None) -> dict:
    cp = _cache_path(ticker)
    if cp.exists():
        return json.loads(cp.read_text())
    ctx = _company_context(ticker)
    if not ctx:
        return None
    client = client or _client()
    msg = client.messages.create(
        model=config.QUALITY_MODEL,
        max_tokens=1000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"BOLAG: {name} ({ticker})\n\nUNDERLAG (MFN):\n{ctx}"}],
    )
    parsed = _parse_content(msg)
    if not parsed:
        return None
    parsed["ticker"] = ticker
    parsed["name"] = name
    parsed["composite"] = _composite(parsed)
    cp.write_text(json.dumps(parsed, ensure_ascii=False))
    return parsed


def _candidates():
    from data.data_loader import load_sweden_universe
    tickers, sector_map, cap_map, name_map = load_sweden_universe(min_market_cap=config.QUALITY_MARKET_CAP)
    excl = set(config.QUALITY_EXCLUDE_SECTORS)
    out = []
    for t in tickers:
        if cap_map.get(t) == "Fond" or sector_map.get(t) == "Fond":
            continue
        if sector_map.get(t) in excl:
            continue
        if re.search(r"invest|förvalt", name_map.get(t, ""), re.I):   # investmentbolag
            continue
        out.append((t, name_map.get(t, t)))
    return out


def screen() -> None:
    import csv
    cands = _candidates()
    print(f"[screen] {len(cands)} kandidater (microcap, ex medtech/fond/investmentbolag)")
    client = _client()
    rows, scored, missing = [], 0, 0
    for i, (t, name) in enumerate(cands, 1):
        if not (Path(config.MFN_CACHE_DIR) / f"{t}.json").exists():
            missing += 1
            continue
        s = score_company(t, name, client)
        if not s:
            continue
        scored += 1
        rows.append(s)
        if i % 20 == 0:
            print(f"  ...{i}/{len(cands)} ({scored} poängsatta)")
    if missing:
        print(f"[screen] {missing} kandidater saknar MFN-cache – kör mfn_fetch först för full täckning.")
    rows.sort(key=lambda r: r.get("composite", 0), reverse=True)
    out = Path(config.QUALITY_CACHE_DIR).parent.parent / "results" / "quality_shortlist.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ticker", "name", "composite", *_SCORE_KEYS, "revenue_msek", "ebitda_msek",
            "net_result_msek", "shares_million", "pitch"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\n[screen] kortlista sparad: {out}  ({scored} bolag)")
    print("\n  TOPP 15 (composite):")
    for r in rows[:15]:
        print(f"   {r['composite']:>4}  {r['ticker']:<12} {str(r['name'])[:26]:<26} {str(r.get('pitch',''))[:60]}")
    print("\n  OBS: detta är ett URVAL byggt på textbedömning, inte ett bevisat edge. "
          "Gör din egen djupanalys på topparna.")


def plot_positioning() -> None:
    """OT Analytics-style: börsvärde (y) vs EBITDA (x), bubbla=omsättning, x12/x18."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from data.data_loader import fetch_weekly_data

    scored = [json.loads(p.read_text()) for p in Path(config.QUALITY_CACHE_DIR).glob("*.json")]
    pts = []
    for s in scored:
        ev, rev, sh = s.get("ebitda_msek"), s.get("revenue_msek"), s.get("shares_million")
        if ev is None or sh is None:
            continue
        try:
            data = fetch_weekly_data([s["ticker"]], use_cache=True)
            px = data[s["ticker"]]["Close"].iloc[-1]
        except Exception:
            continue
        mcap = px * sh   # MSEK (kurs × milj. aktier)
        pts.append((float(ev), float(mcap), float(rev or 0), s["ticker"]))
    if not pts:
        print("[chart] inga bolag med både EBITDA + antal aktier extraherade – kör 'score' först.")
        return
    fig, ax = plt.subplots(figsize=(12, 8))
    xs = [p[0] for p in pts]
    xmax = max(max(xs), 10) * 1.2
    line = [0, xmax]
    ax.plot(line, [0, xmax * 12], "--", color="#94a3b8", lw=1); ax.text(xmax, xmax*12, "x12", color="#64748b")
    ax.plot(line, [0, xmax * 18], "--", color="#cbd5e1", lw=1); ax.text(xmax, xmax*18, "x18", color="#94a3b8")
    sizes = [max(40, (p[2] ** 0.5) * 6) for p in pts]
    ax.scatter(xs, [p[1] for p in pts], s=sizes, alpha=0.45, color="#eab308", edgecolor="#a16207")
    for ev, mcap, rev, t in pts:
        ax.annotate(t, (ev, mcap), fontsize=7, alpha=0.8)
    ax.axvspan(min(min(xs), 0), 0, color="#fee2e2", alpha=0.5)   # hype/förlust-zon (EBITDA<0)
    ax.set_xlabel("Rörelseresultat/år (EBITDA) (MSEK)")
    ax.set_ylabel("Börsvärde (MSEK)")
    ax.set_title("Börsvärde vs EBITDA (bubbla = omsättning) – x12/x18-multiplar")
    ax.grid(True, alpha=0.2)
    out = Path("results/quality_positioning.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out, dpi=140)
    print(f"[chart] sparad: {out}  ({len(pts)} bolag med EBITDA+aktier)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    if cmd == "score":
        screen()
    elif cmd == "chart":
        plot_positioning()
    elif cmd == "one":
        from data.data_loader import load_sweden_universe
        _, _, _, nm = load_sweden_universe(min_market_cap=config.QUALITY_MARKET_CAP)
        t = sys.argv[2]
        print(json.dumps(score_company(t, nm.get(t, t)), ensure_ascii=False, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
