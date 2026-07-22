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
    python altdata/quality_screener.py report      # berika med värdering → 'hög kvalitet OCH billig'
    python altdata/quality_screener.py chart        # rita värderingsdiagram av de poängsatta
    python altdata/quality_screener.py one SAAB-B.ST   # ett bolag (test)

Manuellt spår (INGA API-krediter – kör i valfri webbaserad AI-chatt istället):
    python altdata/quality_screener.py manual_prompt VOLV-B.ST   # skriv ut klistra-in-prompt
    python altdata/quality_screener.py manual_import VOLV-B.ST   # klistra in AI:ns JSON-svar

Batch-läge (10-50 bolag i EN AI-konversation, t.ex. Gemini/stort kontextfönster):
    python altdata/quality_screener.py batch_prompt ABB.ST,ALFA.ST,AAK.ST [fil.txt]
    python altdata/quality_screener.py batch_import [fil-med-svaret.txt]   # utan filnamn: klistra in

Chunkat batch-läge (stora listor -> flera 10-bolagsfiler i en zip, motverkar
tyst AI-trunkering av för stora batchar):
    python altdata/quality_screener.py batch_prompt_chunks ABB.ST,ALFA.ST,... [chunk_size] [fil.zip]
    python altdata/quality_screener.py batch_import <en-chunks-svarsfil>   # en gång per chunk
"""
import sys
import json
import re
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import claude_headless as ch   # headless Claude Code (prenumerationen, ingen API-nyckel)

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
    '  "moat_types": lista av VILKEN/VILKA TYP(ER) av konkurrensfördel ur denna fasta '
    'lista (Hamilton Helmers "7 Powers") – ANGE ALDRIG en typ du inte konkret kan '
    'motivera ur texten, tom lista [] om moat är null/obedömbart eller ingen typ passar:\n'
    '    "scale_economies" (kostnad per enhet sjunker med volym – stordrift ger '
    'omöjlig-att-matcha prissättning för mindre konkurrenter),\n'
    '    "network_economies" (produkten blir mer värd ju fler som använder den – '
    'plattformar/marknadsplatser),\n'
    '    "counter_positioning" (en affärsmodell etablerade konkurrenter INTE kan '
    'kopiera utan att skada sin egen befintliga verksamhet/intäktsström),\n'
    '    "switching_costs" (dyrt/krångligt/riskabelt för en BEFINTLIG kund att byta '
    'bort – inlåsning, INTE bara att produkten är bra),\n'
    '    "branding" (varumärket ger en prispremie/lojalitet UTÖVER vad den underliggande '
    'produkten motiverar),\n'
    '    "cornered_resource" (unik tillgång till en specifik resurs – patent, licens, '
    'nyckelperson, exklusivt kontrakt, råvarufyndighet),\n'
    '    "process_power" (svårkopierad operationell/tillverkningsexpertis byggd upp '
    'över lång tid, inte bara "vi är bra på vad vi gör")\n'
    '  Nyckeltal UR TEXTEN (MSEK resp. miljoner aktier), null om ej angivet. Leta NOGA '
    'i resultaträkningen/finansiella sammandraget – dessa siffror STÅR nästan alltid där:\n'
    '  "revenue_msek" (omsättning/nettoomsättning senaste 12m/år),\n'
    '  "ebitda_msek" (EBITDA om det anges explicit), '
    '"ebit_msek" (rörelseresultat/EBIT – ange ALLTID om resultaträkningen finns), '
    '"net_result_msek" (årets/periodens resultat), "shares_million" (antal aktier)\n'
    '  "mentioned_investors": lista på namngivna fonder/kända investerare i texten (annars [])\n'
    '  "red_flags": lista (t.ex. emissionsberoende, många aktier, förlust utan väg till vinst)\n'
    '  "pitch": caset i EN mening en 10-åring förstår\n'
    '  "memo": 2-3 meningar om varför det kan vara undervärderat och vad som krävs för omvärdering\n'
    'Exempel: {"understand":4,"global":5,"scalable":4,"moat":3,"moat_types":["switching_costs"],'
    '"sales":null,"mgmt":4,'
    '"market":4,"profit_path":2,"under_radar":4,"revenue_msek":120,"ebitda_msek":-15,'
    '"ebit_msek":-19,"net_result_msek":-22,"shares_million":18,'
    '"mentioned_investors":["Carnegie Fonder"],'
    '"red_flags":["ännu ej lönsamt"],"pitch":"...","memo":"..."}'
)

_SCORE_KEYS = ["understand", "global", "scalable", "moat", "sales", "mgmt",
               "market", "profit_path", "under_radar"]

# ── Batch-läge: flera bolag i EN AI-konversation (t.ex. Gemini, stort
# kontextfönster) istället för ett anrop per bolag. Splittar _SYSTEM vid
# dess kända ankarfraser för att ÅTERANVÄNDA exakt samma fältbeskrivningar
# programmatiskt – schemat kan då ALDRIG driva isär mellan enkel-/batch-läge
# (en manuell dubblettsträng hade varit en tickande bugg vid nästa ändring
# av _SYSTEM som glömde uppdatera batch-varianten).
_FIELD_DESC_ANCHOR = "Svara ENDAST med ett giltigt JSON-objekt (ingen prosa/fences) med fälten:\n"
_EXAMPLE_ANCHOR = "Exempel: {"


def _batch_system_prompt() -> str:
    role_desc, rest = _SYSTEM.split(_FIELD_DESC_ANCHOR, 1)
    field_desc = rest.split(_EXAMPLE_ANCHOR, 1)[0]
    return (
        role_desc
        + "Du kommer att bedöma FLERA bolag i det här meddelandet, avgränsade med rader "
          "på formen '=== TICKER: X.ST ==='. Bedöm VARJE bolag HELT OBEROENDE av de "
          "övriga – dra inga jämförelser eller slutsatser mellan bolagen.\n\n"
          "Svara ENDAST med en giltig JSON-LISTA (ingen prosa, inga kodstaket) – EN post "
          "per bolag ovan, I SAMMA ORDNING de gavs. Varje post ska ha fältet \"ticker\" "
          "(exakt som i avgränsaren) plus:\n"
        + field_desc
        + 'Exempel för TVÅ bolag: [{"ticker":"ABC.ST","understand":4,"global":5,'
          '"scalable":4,"moat":3,"sales":null,"mgmt":4,"market":4,"profit_path":2,'
          '"under_radar":4,"revenue_msek":120,"ebitda_msek":-15,"ebit_msek":-19,'
          '"net_result_msek":-22,"shares_million":18,'
          '"mentioned_investors":["Carnegie Fonder"],"red_flags":["ännu ej lönsamt"],'
          '"pitch":"...","memo":"..."}, {"ticker":"XYZ.ST","understand":3,"global":2,'
          '"scalable":3,"moat":2,"sales":3,"mgmt":3,"market":3,"profit_path":4,'
          '"under_radar":2,"revenue_msek":890,"ebitda_msek":45,"ebit_msek":30,'
          '"net_result_msek":21,"shares_million":40,"mentioned_investors":[],'
          '"red_flags":[],"pitch":"...","memo":"..."}]'
    )


def _company_context(ticker: str):
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        return None
    items = json.loads(p.read_text()).get("items", [])
    if not items:
        return None
    items = sorted(items, key=lambda it: it.get("published", ""), reverse=True)
    # Rapport-valet: is_report_pm FÖRST (den kan skilja en riktig rapport från
    # en INBJUDAN till rapportpresentationen/prisutmärkelse-PM – en lärdom
    # mfn_fundamentals redan betalat för; den gamla råa nyckelordsmatchen
    # kunde ge LLM:en en siffer-lös inbjudan som "senaste rapport" och
    # kvalitetsbetyget byggdes då på fel underlag). Nyckelordsmatchen behålls
    # bara som fallback för titelformer utanför is_report_pm:s mönster
    # (t.ex. engelska "year-end"/"interim").
    from altdata.mfn_fundamentals import is_report_pm
    rep = next((it for it in items if is_report_pm(it)), None)
    if rep is None:
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


def _composite(s: dict):
    """Snitt av de BEDÖMBARA kvalitetsbetygen (1-5). INGET bedömbart → None,
    inte 0.0: LLM-betygen är 1-5 så äkta minimum är 1.0 – ett 0.0-composite
    var alltid en 'kunde inte bedömas'-sentinel, men nedströms percentil-
    rankning kan inte skilja sentinel från betyg och rankade bolaget som
    SÄMST i universumet i stället för obetygsatt."""
    vals = [s[k] for k in _SCORE_KEYS if isinstance(s.get(k), (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None


def _norm_composite(s: dict) -> dict:
    """Normalisera CACHADE poster: äldre cache-filer (skrivna innan _composite
    returnerade None) bär 0.0-sentinelen – översätt till None vid läsning så
    gamla filer inte behöver skrivas om."""
    if not s.get("composite"):   # 0, 0.0 eller None → obetygsatt
        s["composite"] = None
    return s


def score_company(ticker: str, name: str, client=None) -> dict:
    """client-parametern är kvar bara för bakåtkompatibla anrop – används
    inte längre. LLM-anropet görs via headless Claude Code (claude_headless.py,
    din Claude-prenumeration, ingen Anthropic-API-nyckel) i stället för
    Anthropic-SDK:t – ingen sökning/verktyg behövs, ren textbedömning av
    underlaget nedan (samma princip som portfolio_commentary.py:s syntes)."""
    cp = _cache_path(ticker)
    if cp.exists():
        return _norm_composite(json.loads(cp.read_text()))
    ctx = _company_context(ticker)
    if not ctx:
        return None
    prompt = f"{_SYSTEM}\n\nBOLAG: {name} ({ticker})\n\nUNDERLAG (MFN):\n{ctx}"
    parsed = ch.run(prompt, "", timeout=120, model=config.CLAUDE_MODEL_FAST)
    if "error" in parsed:
        print(f"[quality] {ticker}: {parsed['error']}")
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
    rows, scored, missing = [], 0, 0
    for i, (t, name) in enumerate(cands, 1):
        if not (Path(config.MFN_CACHE_DIR) / f"{t}.json").exists():
            missing += 1
            continue
        s = score_company(t, name)
        if not s:
            continue
        scored += 1
        rows.append(s)
        if i % 20 == 0:
            print(f"  ...{i}/{len(cands)} ({scored} poängsatta)")
    if missing:
        print(f"[screen] {missing} kandidater saknar MFN-cache – kör mfn_fetch först för full täckning.")
    rows.sort(key=lambda r: (r.get("composite") or 0), reverse=True)
    out = Path(config.QUALITY_CACHE_DIR).parent.parent / "results" / "quality_shortlist.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ticker", "name", "composite", *_SCORE_KEYS, "moat_types", "revenue_msek", "ebitda_msek",
            "net_result_msek", "shares_million", "pitch"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            # moat_types är en Python-lista – JSON-sträng i CSV:n (läsbar,
            # entydig att json.loads() tillbaka), inte Python-repr.
            row = dict(r)
            row["moat_types"] = json.dumps(row.get("moat_types") or [], ensure_ascii=False)
            w.writerow(row)
    print(f"\n[screen] kortlista sparad: {out}  ({scored} bolag)")
    print("\n  TOPP 15 (composite):")
    for r in rows[:15]:
        print(f"   {r['composite']:>4}  {r['ticker']:<12} {str(r['name'])[:26]:<26} {str(r.get('pitch',''))[:60]}")
    print("\n  OBS: detta är ett URVAL byggt på textbedömning, inte ett bevisat edge. "
          "Gör din egen djupanalys på topparna.")


def _market_caps(tickers) -> dict:
    """Auktoritativt börsvärde (MSEK) per ticker - Avanza först
    (avanza.market_cap_msek, keyIndicators.marketCapital), Yahoo som
    fallback om Avanza-sökningen inte matchar tickern. Slår 'kurs ×
    Claude-extraherat aktieantal' som ofta saknas → många 'okänd'. Cachat
    på disk för alltid - en engångskostnad, inte en nattlig batch. Cachar
    bara träffar, så en ny körning kan fylla luckor (t.ex. efter ett
    nätverksfel)."""
    from altdata import avanza
    cache = Path(config.QUALITY_CACHE_DIR) / "_marketcaps.json"
    caps = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [t for t in tickers if t not in caps]
    if todo:
        print(f"[report] hämtar börsvärde för {len(todo)} bolag (Avanza→Yahoo, cachas)...")
        for i, t in enumerate(todo, 1):
            mc = None
            try:
                mc = avanza.market_cap_msek(t)
            except Exception:  # noqa: BLE001
                mc = None
            if mc is None:
                try:
                    import yfinance as yf
                    fi = yf.Ticker(t).fast_info
                    raw = fi.get("market_cap") if hasattr(fi, "get") else getattr(fi, "market_cap", None)
                    if not raw:
                        raw = yf.Ticker(t).info.get("marketCap")
                    mc = round(float(raw) / 1e6, 1) if raw else None   # SEK → MSEK
                except Exception:
                    mc = None
            if mc:
                caps[t] = mc
            if i % 25 == 0:
                cache.write_text(json.dumps(caps))     # delcheckpoint mot avbrott
        cache.write_text(json.dumps(caps))
    return caps


def _zone_by_multiple(mult, cheap, fair):
    """billig <= cheap, rimlig <= fair, annars dyr. okänd om multipeln saknas."""
    if mult is None:
        return "okänd"
    if mult <= cheap:
        return "billig"
    if mult <= fair:
        return "rimlig"
    return "dyr"


def _valuation(mcap, earnings, revenue):
    """Ger (multipel, bas, zon) för ett bolag – som OT/EV-S gör:
      • lönsamt (vinst > 0) → vinstmultipel (börsvärde/vinst), trösklar 12/18.
      • förlust (vinst <= 0) men har omsättning → P/S (börsvärde/omsättning), så
        ÄVEN förlustbolag får billig/dyr-stämpel (EBITDA-multipel är meningslös vid
        negativ vinst).
      • annars → okänd."""
    if mcap is not None and earnings is not None and earnings > 0:
        mult = round(mcap / earnings, 1)
        return mult, "vinst", _zone_by_multiple(mult, config.QUALITY_MULT_CHEAP, config.QUALITY_MULT_FAIR)
    if mcap is not None and isinstance(revenue, (int, float)) and revenue > 0:
        mult = round(mcap / revenue, 1)
        return mult, "P/S", _zone_by_multiple(mult, config.QUALITY_PS_CHEAP, config.QUALITY_PS_FAIR)
    return None, "", "okänd"


def _earnings(s: dict):
    """Vinst-stege: EBITDA → EBIT/rörelseresultat → årets resultat. Returnerar
    (vinst_msek, bas) med första tillgängliga, annars (None, None). Låter oss ge en
    zon åt bolag där EBITDA saknas men ett annat resultatmått finns (gratis, ur cache)."""
    for key, basis in (("ebitda_msek", "EBITDA"), ("ebit_msek", "EBIT"),
                       ("net_result_msek", "resultat")):
        v = s.get(key)
        if isinstance(v, (int, float)):
            return float(v), basis
    return None, None


def report() -> None:
    """Berikar de poängsatta bolagen med VÄRDERING (börsvärde, EBITDA-multipel, zon) och
    ger kärn-listan: HÖG KVALITET **och** BILLIG. `composite` mäter bara kvalitet – först
    när vi väger in värderingen hittar vi 'bra bolag till lågt pris' (din kärnregel)."""
    import csv
    from data.data_loader import fetch_weekly_data

    # cache/quality/ delas med de AGGREGERADE hjälpfilerna (_marketcaps.json,
    # _eodhd.json, _tradingview.json, _quant.json m.fl.) - inte bara per-bolag-
    # poster. Verkligt fel: glob("*.json") plockade upp t.ex. _tradingview.json
    # (en flat {ticker: mcap}-dict, inte ett bolags score-schema) som en
    # "poängsatt post", vilket kraschade _market_caps() med KeyError: 'ticker'.
    # Samma leading-underscore-filter som tradingview.py:s _scored_tickers()
    # redan använder för samma katalog.
    scored = [_norm_composite(json.loads(p.read_text()))
              for p in Path(config.QUALITY_CACHE_DIR).glob("*.json")
              if not p.stem.startswith("_")]
    if not scored:
        print("[report] inga poängsatta bolag – kör 'score' först.")
        return
    # EODHD (pålitlig fundamentals-källa) om den fyllts – prioriteras för BÅDE
    # börsvärde och EBITDA. Faller tillbaka på Yahoo, sen Claude-extraheringen.
    ep = Path(config.QUALITY_CACHE_DIR) / "_eodhd.json"
    eodhd = json.loads(ep.read_text()) if ep.exists() else {}
    # TradingView (gratis, inofficiell) fyller luckor efter EODHD, före Yahoo.
    tp = Path(config.QUALITY_CACHE_DIR) / "_tradingview.json"
    tvdata = json.loads(tp.read_text()) if tp.exists() else {}
    # Auktoritativt börsvärde från Yahoo för ALLA poängsatta (löser 'okänd' pga saknat aktieantal).
    caps = _market_caps([s["ticker"] for s in scored])
    priced = [s for s in scored if s.get("shares_million")]
    data = fetch_weekly_data([s["ticker"] for s in priced], use_cache=True) if priced else {}
    rows = []
    for s in scored:
        mcap = mult = None
        ex = eodhd.get(s["ticker"]) or {}
        ex_sek = ex.get("currency") in (None, "SEK")   # icke-SEK → använd inte EODHD-siffrorna
        tv = tvdata.get(s["ticker"]) or {}
        tv_sek = tv.get("currency") in (None, "SEK")   # OMXSTO noterar i SEK; annat → hoppa
        mcap = ex.get("mcap_msek") if ex_sek else None                 # 1:a hand: EODHD
        if mcap is None and tv_sek:
            mcap = tv.get("mcap_msek")                                 # 2:a hand: TradingView
        if mcap is None:
            mcap = caps.get(s["ticker"])                               # 3:e hand: Yahoo marketCap
        if mcap is None and s.get("shares_million"):                   # 4:e hand: kurs × aktieantal
            d = data.get(s["ticker"])
            if d is not None and not d.empty:
                mcap = round(float(d["Close"].iloc[-1]) * float(s["shares_million"]), 1)
        # Vinst: EODHD:s EBITDA först, sen TradingViews, annars Claude-stegen (EBITDA→EBIT→resultat).
        if ex_sek and isinstance(ex.get("ebitda_msek"), (int, float)):
            earnings, src = ex["ebitda_msek"], "EBITDA·EODHD"
        elif tv_sek and isinstance(tv.get("ebitda_msek"), (int, float)):
            earnings, src = tv["ebitda_msek"], "EBITDA·TV"
        else:
            earnings, src = _earnings(s)
        # Zon: vinstmultipel om lönsamt, annars P/S (även förlustbolag får stämpel).
        revenue = s.get("revenue_msek")
        if revenue is None and tv_sek and isinstance(tv.get("revenue_msek"), (int, float)):
            revenue = tv["revenue_msek"]
        mult, vbasis, zone = _valuation(mcap, earnings, revenue)
        r = dict(s)
        r["mcap_msek"] = mcap
        r["earnings_msek"] = earnings
        r["earnings_basis"] = (src if vbasis == "vinst" else vbasis) or ""
        r["ebitda_multiple"] = mult                    # multipel på vald bas (vinst el. P/S)
        r["zone"] = zone
        r["loss"] = 1 if (earnings is not None and earnings <= 0) else 0
        # Platta ut listfälten till strängar så CSV/frontend slipper Python-repr.
        r["red_flags"] = "; ".join(map(str, s.get("red_flags") or []))
        r["mentioned_investors"] = "; ".join(map(str, s.get("mentioned_investors") or []))
        rows.append(r)

    rows.sort(key=lambda r: (r.get("composite") or 0), reverse=True)
    out = Path(config.RESULTS_DIR) / "quality_shortlist.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ticker", "name", "composite", "zone", "loss", "mcap_msek", "ebitda_multiple",
            "earnings_basis", *_SCORE_KEYS, "revenue_msek", "ebitda_msek", "ebit_msek",
            "net_result_msek", "shares_million", "pitch", "memo", "red_flags",
            "mentioned_investors"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[report] berikad kortlista sparad: {out}  ({len(rows)} bolag)")

    # Kärn-listan: hög kvalitet OCH billig/rimlig värdering (positiv EBITDA).
    sweet = [r for r in rows
             if (r.get("composite") or 0) >= 4.0 and r.get("zone") in ("billig", "rimlig")]
    print(f"\n  🎯 HÖG KVALITET (composite ≥ 4.0) **OCH** BILLIG/RIMLIG (vinst- el. P/S-multipel) – {len(sweet)} st:")
    if not sweet:
        print("     (inga träffar – vidga filtren eller se hela CSV:n för zon-fördelningen.)")
    for r in sweet:
        mc = f"{r['mcap_msek']:>7.0f}" if r.get("mcap_msek") is not None else "      ?"
        mu = f"{r['ebitda_multiple']:>4.1f}x" if r.get("ebitda_multiple") is not None else "   ?"
        tag = f"[{r['zone']}·{r.get('earnings_basis') or '?'}]" + (" ⚠förlust" if r.get("loss") else "")
        print(f"   {r['composite']:>4}  {r['ticker']:<12} {str(r['name'])[:22]:<22} "
              f"börsv {mc} MSEK  {mu}  {tag}  {str(r.get('pitch',''))[:36]}")

    def _fmt(r):
        mc = f"{r['mcap_msek']:>7.0f}" if r.get("mcap_msek") is not None else "      ?"
        mu = f"{r['ebitda_multiple']:>4.1f}x" if r.get("ebitda_multiple") is not None else "   ?"
        tag = f"[{r['zone']}·{r.get('earnings_basis') or '?'}]" + (" ⚠förlust" if r.get("loss") else "")
        return (f"   {r['composite']:>4}  {r['ticker']:<12} {str(r['name'])[:22]:<22} "
                f"börsv {mc} MSEK  {mu}  {tag}  {str(r.get('pitch',''))[:36]}")

    # Bästa KVALITET bland de faktiskt BILLIGA/RIMLIGA (även under 4.0) – kärn-tratten.
    value = sorted([r for r in rows if r.get("zone") in ("billig", "rimlig")],
                   key=lambda r: (r.get("composite") or 0), reverse=True)
    print(f"\n  💰 BÄSTA KVALITET BLAND DE BILLIGA/RIMLIGA (vinst- el. P/S-multipel) – topp {min(12, len(value))} av {len(value)}:")
    for r in value[:12]:
        print(_fmt(r))

    # Förvinst-case: går ännu back men hög kvalitet, billig/rimlig PÅ P/S OCH tydlig väg till vinst.
    turn = sorted([r for r in rows if r.get("loss")
                   and r.get("zone") in ("billig", "rimlig")
                   and (r.get("composite") or 0) >= 4.0
                   and isinstance(r.get("profit_path"), (int, float)) and r["profit_path"] >= 4],
                  key=lambda r: (r.get("composite") or 0), reverse=True)
    print(f"\n  🚀 FÖRVINST-CASE ATT BEVAKA (förlust men billig på P/S + väg till vinst) – {len(turn)} st:")
    for r in turn[:12]:
        print(_fmt(r))

    # Zon-fördelning så du ser var kvaliteten sitter.
    from collections import Counter
    z = Counter(r["zone"] for r in rows)
    losscnt = sum(1 for r in rows if r.get("loss"))
    print("\n  Zon-fördelning (alla poängsatta):")
    for zone in ("billig", "rimlig", "dyr", "okänd"):
        if z.get(zone):
            print(f"     {zone:<14} {z[zone]:>3}")
    print(f"     (varav förlustbolag, zonade på P/S: {losscnt})")
    print("\n  OBS: värdering bygger på nyckeltal Claude extraherat UR RAPPORTTEXTEN "
          "(kan sakna/vara föråldrade) × senaste kurs. Verifiera topparna manuellt.")


def plot_positioning() -> None:
    """OT Analytics-style: börsvärde (y) vs EBITDA (x), bubbla=omsättning, x12/x18."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from data.data_loader import fetch_weekly_data

    scored = [json.loads(p.read_text()) for p in Path(config.QUALITY_CACHE_DIR).glob("*.json")]
    usable = [s for s in scored if s.get("ebitda_msek") is not None and s.get("shares_million")]
    # Ladda priser EN gång för alla tickers (annars cache-miss per ticker → 100+ Yahoo-anrop).
    data = fetch_weekly_data([s["ticker"] for s in usable], use_cache=True) if usable else {}
    pts = []
    for s in usable:
        d = data.get(s["ticker"])
        if d is None or d.empty:
            continue
        mcap = float(d["Close"].iloc[-1]) * float(s["shares_million"])   # MSEK (kurs × milj. aktier)
        pts.append((float(s["ebitda_msek"]), mcap, float(s.get("revenue_msek") or 0), s["ticker"]))
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
    out = Path(config.RESULTS_DIR) / "quality_positioning.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out, dpi=140)
    print(f"[chart] sparad: {out}  ({len(pts)} bolag med EBITDA+aktier)")


def _bench_ticker() -> str:
    return config.SEGMENTS.get("small", {}).get("index_ticker", "XACT-SMABOLAG.ST")


def snapshot(label=None) -> None:
    """Fryser dagens kärn-lista (hög kvalitet + billig/rimlig) med ingångskurs →
    results/quality_ledger.csv. Detta är ENDA ärliga sättet att mäta om screenern
    slår index: framåt-spårning. Backtest går inte (diskretionär tratt, survivorship,
    + LLM:en 'vet' utfallet via träningsdata = look-ahead)."""
    import csv
    import datetime
    import pandas as pd
    from data.data_loader import fetch_weekly_data

    src = Path(config.RESULTS_DIR) / "quality_shortlist.csv"
    if not src.exists():
        print("[snapshot] kör 'report' först (results/quality_shortlist.csv saknas).")
        return
    df = pd.read_csv(src)
    pick = df[(df["composite"] >= 4.0) & (df["zone"].isin(["billig", "rimlig"]))]
    if pick.empty:   # fall tillbaka: bästa kvalitet bland de billiga/rimliga
        pick = df[df["zone"].isin(["billig", "rimlig"])].sort_values("composite", ascending=False).head(10)
    if pick.empty:
        print("[snapshot] inga billiga/rimliga bolag att frysa – vidga i 'report' först.")
        return
    bench = _bench_ticker()
    tickers = list(dict.fromkeys(list(pick["ticker"]) + [bench]))
    data = fetch_weekly_data(tickers, use_cache=True)

    def last_close(t):
        d = data.get(t)
        if d is None:
            return None
        s = d["Close"].dropna()
        return round(float(s.iloc[-1]), 4) if len(s) else None

    bench_px = last_close(bench)
    today = datetime.date.today().isoformat()
    label = label or today
    rows = []
    for _, r in pick.iterrows():
        px = last_close(r["ticker"])
        if px is None:
            continue
        rows.append({"snapshot": label, "date": today, "ticker": r["ticker"],
                     "name": r.get("name"), "composite": r.get("composite"),
                     "zone": r.get("zone"), "entry_price": px,
                     "bench_ticker": bench, "bench_entry": bench_px})
    if not rows:
        print("[snapshot] inga ingångskurser (Yahoo?) – avbryter.")
        return
    ledger = Path(config.RESULTS_DIR) / "quality_ledger.csv"
    exists = ledger.exists()
    with open(ledger, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if not exists:
            w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"[snapshot] '{label}': frös {len(rows)} bolag @ {today} (index {bench}) → {ledger}")
    print("  Kör 'track' om några veckor/månader för att se avkastning vs index.")


def track() -> None:
    """Läser quality_ledger.csv och visar varje snapshots avkastning vs index
    till dags dato (likaviktad, ingen ombalansering). Screenerns riktiga scorecard."""
    import pandas as pd
    from data.data_loader import fetch_weekly_data

    ledger = Path(config.RESULTS_DIR) / "quality_ledger.csv"
    if not ledger.exists():
        print("[track] ingen ledger än – kör 'snapshot' först.")
        return
    led = pd.read_csv(ledger)
    tickers = list(dict.fromkeys(list(led["ticker"]) + list(led["bench_ticker"].dropna().unique())))
    data = fetch_weekly_data(tickers, use_cache=True)

    def cur(t):
        d = data.get(t)
        if d is None:
            return None
        s = d["Close"].dropna()
        return float(s.iloc[-1]) if len(s) else None

    print("\n  KVALITETS-SCREENERN vs INDEX (framåt-spårning, likaviktad)\n")
    for label, g in led.groupby("snapshot"):
        rets = [cur(r["ticker"]) / r["entry_price"] - 1
                for _, r in g.iterrows()
                if cur(r["ticker"]) and r["entry_price"]]
        if not rets:
            continue
        port = sum(rets) / len(rets)
        be = g["bench_entry"].dropna()
        bt = g["bench_ticker"].dropna()
        bench_ret = None
        if len(be) and len(bt):
            bc = cur(bt.iloc[0])
            if bc:
                bench_ret = bc / float(be.iloc[0]) - 1
        line = f"  {str(label):<12} {len(rets):>2} bolag   portfölj {port:+.1%}"
        if bench_ret is not None:
            line += f"   index {bench_ret:+.1%}   alfa {port - bench_ret:+.1%}"
        print(line)
    print("\n  (Enkel framåt-scorecard – ingen ombalansering. Fler snapshots över tid = mer robust.)")


def lookback(months=6, n=5) -> None:
    """ILLUSTRATIV bakåtblick (EJ giltig backtest): ta dagens n bolag med 'billig'-
    stämpel + högst kvalitet, och visa hur en likaviktad portfölj utvecklats de
    senaste `months` månaderna vs index. VARNING: look-ahead + survivorship – vi
    väljer dagens billiga överlevare och tittar bakåt. Underhållande, inte bevis."""
    import pandas as pd
    import datetime
    from data.data_loader import fetch_weekly_data

    src = Path(config.RESULTS_DIR) / "quality_shortlist.csv"
    if not src.exists():
        print("[lookback] kör 'report' först (results/quality_shortlist.csv saknas).")
        return
    df = pd.read_csv(src)
    pick = df[df["zone"] == "billig"].sort_values("composite", ascending=False).head(n)
    if len(pick) < n:   # för få billiga → fyll på med rimliga (högsta composite)
        extra = df[(df["zone"] == "rimlig") & (~df["ticker"].isin(pick["ticker"]))] \
            .sort_values("composite", ascending=False)
        pick = pd.concat([pick, extra]).head(n)
    if pick.empty:
        print("[lookback] inga billiga/rimliga bolag – kör 'report' först.")
        return
    bench = _bench_ticker()
    tickers = list(dict.fromkeys(list(pick["ticker"]) + [bench]))
    data = fetch_weekly_data(tickers, use_cache=True)
    cutoff = pd.Timestamp(datetime.date.today()) - pd.Timedelta(days=int(months * 30.4))

    def window(t):
        d = data.get(t)
        if d is None:
            return None
        s = d["Close"].dropna()
        if s.empty:
            return None
        s.index = pd.to_datetime(s.index)
        past = s[s.index <= cutoff]
        full = len(past) > 0
        p0 = float(past.iloc[-1]) if full else float(s.iloc[0])   # fallback: äldsta kurs
        p1 = float(s.iloc[-1])
        return p0, p1, (p1 / p0 - 1), full

    def zone_then(mult_now, p0, p1, basis):
        """Dåtidens multipel/zon: multipeln skalar med priset (aktier konstant), så
        mult_då = mult_nu × pris_då/pris_nu. Visar om 'billig'-stämpeln fanns DÅ eller
        bara uppstod för att kursen sedan föll."""
        if mult_now is None or pd.isna(mult_now) or not p1:
            return None, None
        mult_t = round(float(mult_now) * p0 / p1, 1)
        is_ps = str(basis) == "P/S"
        cheap, fair = ((config.QUALITY_PS_CHEAP, config.QUALITY_PS_FAIR) if is_ps
                       else (config.QUALITY_MULT_CHEAP, config.QUALITY_MULT_FAIR))
        return mult_t, _zone_by_multiple(mult_t, cheap, fair)

    print(f"\n  BAKÅTBLICK {months}m – dagens {len(pick)} 'billig'+kvalitet, likaviktad")
    print("  ⚠ EJ giltig backtest: look-ahead + survivorship (dagens billiga överlevare)")
    print("  Kolumnen 'zon då' = hade bolaget stämpeln FÖR 6 MÅN SEDAN (rekonstruerad multipel)?\n")
    rets, billig_then = [], 0
    for _, r in pick.iterrows():
        w = window(r["ticker"])
        if not w:
            print(f"   {r['ticker']:<12} {str(r['name'])[:22]:<22} ingen kursdata")
            continue
        p0, p1, ret, full = w
        rets.append(ret)
        mt, zt = zone_then(r.get("ebitda_multiple"), p0, p1, r.get("earnings_basis"))
        if zt == "billig":
            billig_then += 1
        zt_str = f"{zt} ({mt}x)" if zt else "?"
        flag = "" if full else " ⚠kort hist."
        print(f"   {r['ticker']:<12} {str(r['name'])[:22]:<22} comp {r['composite']:>4}  "
              f"{p0:>7.2f}→{p1:>7.2f} {ret:>+6.1%}   zon då: {zt_str:<16} nu: {r.get('zone')}{flag}")
    if not rets:
        print("  (ingen kursdata för urvalet)")
        return
    port = sum(rets) / len(rets)
    srt = sorted(rets)
    med = srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2
    ex_top = [x for x in rets if x != max(rets)]
    bw = window(bench)
    print("  " + "-" * 66)
    line = f"   PORTFÖLJ (likavikt, {len(rets)} bolag):  snitt {port:+.1%}   median {med:+.1%}"
    if bw:
        line += f"   index {bw[2]:+.1%}"
    print(line)
    if ex_top:
        print(f"   Utan bästa namnet: snitt {sum(ex_top)/len(ex_top):+.1%}  "
              f"(så mycket hängde på en enda vinnare)")
    print(f"\n   >>> Hade 'billig'-stämpel FÖR {months} MÅN SEDAN: {billig_then} av {len(rets)} <<<")
    print("   Resten blev 'billiga' först EFTER att kursen föll – stämpeln är alltså delvis")
    print("   en konsekvens av nedgången, inte en signal som fanns att agera på då.")
    print("\n   Enda ärliga testet: 'snapshot' idag → 'track' framåt.")


# Mobila tangentbord (iOS "smarta citattecken" m.fl.) ersätter tyst raka
# citattecken med kurviga vid inklistring genom vissa appar - trasar sönder
# JSON-strukturen (json.loads kräver ASCII '"'). Verkligt fall: en batch-
# import misslyckades med "Expecting ',' delimiter" mitt i en annars giltig
# lista, spårat till just detta. Normaliserar tyst istället för att be
# användaren strida mot sin telefons autokorrigering.
_SMART_QUOTES = str.maketrans({
    "“": '"', "”": '"',   # “ ”
    "‘": "'", "’": "'",   # ‘ ’
})


def _normalize_pasted_json(raw: str) -> str:
    return raw.translate(_SMART_QUOTES)


def _read_stdin_utf8() -> str:
    """Läser stdin som RÅA bytes och avkodar explicit UTF-8 – kringgår
    sys.stdin.read()s lokal-beroende avkodning (locale.getpreferredencoding()).
    Verkligt fall: en i övrigt giltig JSON-lista kraschade "Expecting ','
    delimiter" på EXAKT samma teckenposition varje gång (inte smarta
    citattecken – den fixen ändrade ingenting), ett tydligt tecken på
    deterministisk byte/tecken-glidning snarare än slumpmässig korruption.
    En del SSH-klienter (bl.a. vissa iOS-appar) skickar inte LANG/LC_* över
    SSH, vilket kan få Python att falla tillbaka på en icke-UTF-8-avkodning
    och tyst förskjuta positionerna för varje svenskt specialtecken (ö/ä/å)
    i den inklistrade texten."""
    return sys.stdin.buffer.read().decode("utf-8", errors="replace")


def manual_prompt(ticker: str) -> None:
    """Skriver ut ett klistra-in-färdigt AI-prompt för ETT bolag – för manuell
    bedömning i en WEBBASERAD AI (claude.ai, ChatGPT m.fl.) UTAN att förbruka
    API-krediter (webbchatten går på ett separat abonnemang, inte API-nyckeln).
    Använd t.ex. för Large/Mid Cap eller Health Care – sektorer/cap-nivåer
    kvalitetsscreenern annars aldrig rör (se config.QUALITY_MARKET_CAP och
    medtech-exkluderingen i _candidates), vilket gör att soft_signals.py:s
    destillation extrapolerar dit helt utan facit-stöd (facit-täckningsspärren
    faller då tillbaka på lexikon-läge för just de bolagen).

    EXAKT samma system-prompt och kontext-urval som score_company() – svaret
    blir alltså likvärdigt ett riktigt API-anrop.

        python -m altdata.quality_screener manual_prompt VOLV-B.ST
        # ... klistra HELA utskriften som EN fråga i webb-AI:n ...
        python -m altdata.quality_screener manual_import VOLV-B.ST   # klistra JSON-svaret, Ctrl-D
    """
    from data.data_loader import load_sweden_universe
    ticker = ticker.upper()
    _, _, _, name_map = load_sweden_universe(min_market_cap=None)
    name = name_map.get(ticker, ticker)
    if _cache_path(ticker).exists():
        print(f"{ticker} har redan en cachad bedömning – radera "
              f"{_cache_path(ticker)} först om du vill skriva över den.")
        return
    ctx = _company_context(ticker)
    if not ctx:
        print(f"Ingen MFN-text cachad för {ticker} – kör "
              f"'python -m altdata.mfn_fetch fetch <segment>' först.")
        return
    print("=" * 78)
    print("KLISTRA IN ALLT NEDANFÖR SOM EN (1) FRÅGA I EN WEBBASERAD AI-CHATT:")
    print("=" * 78)
    print(_SYSTEM)
    print()
    print(f"BOLAG: {name} ({ticker})\n\nUNDERLAG (MFN):\n{ctx}")
    print("=" * 78)
    print(f"Klistra sedan in AI:ns JSON-svar med:\n"
          f"  python -m altdata.quality_screener manual_import {ticker}")


def manual_import(ticker: str) -> None:
    """Importerar ett manuellt inhämtat AI-svar (se manual_prompt) till
    samma cache-fil/format som score_company() skulle skrivit – bolaget blir
    därmed ett fullvärdigt facit-bolag för quality_screener report/chart OCH
    soft_signals train (inkl. dess facit-täckningsspärr). Taggat
    'manual_import': true för spårbarhet, annars identiskt.

        python -m altdata.quality_screener manual_import VOLV-B.ST
        # (klistra in JSON-svaret, avsluta med Ctrl-D / Ctrl-Z+Enter)
    """
    from data.data_loader import load_sweden_universe
    ticker = ticker.upper()
    print(f"Klistra in AI:ns JSON-svar för {ticker}, avsluta med Ctrl-D (Ctrl-Z, Enter på Windows):")
    raw = _normalize_pasted_json(_read_stdin_utf8())
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        print("Hittade inget JSON-objekt i inklistringen – inget sparat.")
        return
    try:
        parsed = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        print(f"Ogiltig JSON ({e}) – inget sparat.")
        return
    if not isinstance(parsed, dict):
        print("Svaret måste vara ett JSON-objekt – inget sparat.")
        return
    _, _, _, name_map = load_sweden_universe(min_market_cap=None)
    parsed["ticker"] = ticker
    parsed["name"] = name_map.get(ticker, ticker)
    parsed["composite"] = _composite(parsed)
    parsed["manual_import"] = True
    if parsed["composite"] is None:
        print("VARNING: inget bedömbart kriterium i svaret (composite=None) – "
              "sparas ändå, men räknas inte som facit av soft_signals.")
    cp = _cache_path(ticker)
    cp.write_text(json.dumps(parsed, ensure_ascii=False))
    print(f"Sparat -> {cp}  (composite={parsed['composite']})")


def _batch_blocks(tickers: List[str]) -> tuple:
    """Bygger (ticker, prompt-block)-par för varje ticker som HAR cachad
    MFN-text och INTE redan är bedömd, plus listorna över uteslutna. Delad
    mellan batch_prompt och batch_prompt_chunks så exkluderingslogiken
    aldrig kan driva isär mellan de två."""
    from data.data_loader import load_sweden_universe
    tickers = [t.strip().upper() for t in tickers if t.strip()]
    _, _, _, name_map = load_sweden_universe(min_market_cap=None)

    already, no_text, blocks = [], [], []
    for t in tickers:
        if _cache_path(t).exists():
            already.append(t)
            continue
        ctx = _company_context(t)
        if not ctx:
            no_text.append(t)
            continue
        name = name_map.get(t, t)
        blocks.append((t, f"=== TICKER: {t} ===\nBOLAG: {name} ({t})\n\nUNDERLAG (MFN):\n{ctx}"))
    return blocks, already, no_text


_BATCH_FOOTER = ("\n\n=== SLUT PÅ BOLAG ===\nSvara nu med EN giltig JSON-lista, en post per "
                 "bolag ovan i SAMMA ORDNING, inget annat (ingen prosa, inga kodstaket).")


def batch_prompt(tickers: List[str], out_path: Optional[str] = None) -> None:
    """Skriver EN textfil med FLERA bolags underlag samlat – för en AI med
    stort kontextfönster (Gemini m.fl.), 10-50 bolag i EN konversation
    istället för en fråga per bolag (manual_prompt). Hoppar tyst-men-synligt
    över tickers som redan är bedömda (samma skydd som manual_prompt) eller
    saknar cachad MFN-text.

    VARNING (verkligt fall): stora batchar (~78 bolag) kan få AI:n att tyst
    trunkera svaret utan felmeddelande (Gemini svarade en gång bara för 19
    av 78, som en i övrigt fullt giltig – men ofullständig – JSON-lista).
    Överväg batch_prompt_chunks för partier över ~15-20 bolag istället.

        python -m altdata.quality_screener batch_prompt ABB.ST,ALFA.ST,AAK.ST
        python -m altdata.quality_screener batch_prompt ABB.ST,ALFA.ST batch.txt
    """
    blocks, already, no_text = _batch_blocks(tickers)

    if already:
        print(f"Hoppar över (redan bedömda): {sorted(already)}")
    if no_text:
        print(f"Hoppar över (ingen cachad MFN-text – kör mfn_fetch först): {sorted(no_text)}")
    if not blocks:
        print("Inget att skriva – alla angivna tickers hoppades över.")
        return

    full = _batch_system_prompt() + "\n\n" + "\n\n".join(b for _, b in blocks) + _BATCH_FOOTER

    out = Path(out_path) if out_path else Path(config.anchor("cache")) / "quality_batch_prompt.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(full, encoding="utf-8")
    print(f"{len(blocks)} bolag skrivna -> {out}")
    print("Klistra in HELA filens innehåll (eller ladda upp filen) som EN fråga i en "
          "AI-chatt med stort kontextfönster (t.ex. Gemini). Importera svaret med:\n"
          f"  python -m altdata.quality_screener batch_import  (klistra JSON-listan, Ctrl-D)\n"
          f"  python -m altdata.quality_screener batch_import <fil-med-svaret>")


def batch_prompt_chunks(tickers: List[str], chunk_size: int = 10, out_zip: Optional[str] = None) -> None:
    """Som batch_prompt, men delar upp i FLERA mindre, SJÄLVSTÄNDIGA filer
    (chunk_size bolag vardera, default 10) och paketerar dem i en zip.
    Byggd som svar på ett verkligt fel: en enda 78-bolagsbatch fick Gemini
    att tyst trunkera svaret till 19 bolag (en giltig men ofullständig
    JSON-lista, inget felmeddelande) – mindre, oberoende batchar är mycket
    svårare för en AI att av misstag trunkera eller tappa bort delar av.

    Exkluderingen (redan bedömda/ingen MFN-text) körs EN gång över HELA
    listan innan uppdelningen, inte per chunk – annars hade samma uteslutna
    ticker kunnat dyka upp i flera chunkars "hoppar över"-utskrift.
    Zip-arkivet innehåller en manifest.txt som visar vilka tickers som
    hamnade i vilken fil, till hjälp när du skickar/importerar chunk för
    chunk.

        python -m altdata.quality_screener batch_prompt_chunks ABB.ST,ALFA.ST,...
        python -m altdata.quality_screener batch_prompt_chunks ABB.ST,... 10 batches.zip
    """
    import zipfile

    blocks, already, no_text = _batch_blocks(tickers)

    if already:
        print(f"Hoppar över (redan bedömda): {sorted(already)}")
    if no_text:
        print(f"Hoppar över (ingen cachad MFN-text – kör mfn_fetch först): {sorted(no_text)}")
    if not blocks:
        print("Inget att skriva – alla angivna tickers hoppades över.")
        return

    chunks = [blocks[i:i + chunk_size] for i in range(0, len(blocks), chunk_size)]
    n_digits = len(str(len(chunks)))

    out = Path(out_zip) if out_zip else Path(config.anchor("cache")) / "quality_batch_prompts.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest_lines = [f"{len(blocks)} bolag i {len(chunks)} filer (chunk_size={chunk_size})\n"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, chunk in enumerate(chunks, start=1):
            fname = f"batch_{i:0{n_digits}d}_of_{len(chunks):0{n_digits}d}.txt"
            full = (_batch_system_prompt() + "\n\n" + "\n\n".join(b for _, b in chunk)
                    + _BATCH_FOOTER)
            zf.writestr(fname, full)
            tickers_in_chunk = [t for t, _ in chunk]
            manifest_lines.append(f"{fname}: {tickers_in_chunk}")
        zf.writestr("manifest.txt", "\n".join(manifest_lines))

    print(f"{len(blocks)} bolag skrivna i {len(chunks)} filer ({chunk_size} bolag/fil) -> {out}")
    print("Packa upp zip:en, klistra/ladda upp EN fil i taget i en AI-chatt (t.ex. Gemini). "
          "Importera varje svar för sig med:\n"
          f"  python -m altdata.quality_screener batch_import <fil-med-svaret>")


def batch_import(path: Optional[str] = None) -> None:
    """Importerar en AI:s svar på batch_prompt – en JSON-LISTA med en post
    per bolag (fältet 'ticker' i varje post avgör vilken cache-fil den
    skrivs till). Samma cache-format/plats som score_company()/manual_import
    – bolagen blir fullvärdiga facit-bolag för report/chart och
    soft_signals train (inkl. dess facit-täckningsspärr).

        python -m altdata.quality_screener batch_import              # klistra in, Ctrl-D
        python -m altdata.quality_screener batch_import svar.txt      # läs från fil
    """
    from data.data_loader import load_sweden_universe
    if path:
        p = Path(path)
        if not p.exists():
            print(f"Filen {p} finns inte.")
            return
        raw = p.read_text(encoding="utf-8")
    else:
        print("Klistra in AI:ns JSON-LISTA, avsluta med Ctrl-D (Ctrl-Z, Enter på Windows):")
        raw = _read_stdin_utf8()
    raw = _normalize_pasted_json(raw)

    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        print("Hittade ingen JSON-lista ([...]) i inklistringen/filen – inget sparat.")
        return
    try:
        parsed_list = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        print(f"Ogiltig JSON ({e}) – inget sparat.")
        return
    if not isinstance(parsed_list, list):
        print("Toppnivån måste vara en JSON-lista – inget sparat.")
        return

    _, _, _, name_map = load_sweden_universe(min_market_cap=None)
    saved, skipped = [], []
    for item in parsed_list:
        if not isinstance(item, dict) or not item.get("ticker"):
            skipped.append(str(item)[:60])
            continue
        t = str(item["ticker"]).strip().upper()
        item["ticker"] = t
        item["name"] = name_map.get(t, t)
        item["composite"] = _composite(item)
        item["manual_import"] = True
        _cache_path(t).write_text(json.dumps(item, ensure_ascii=False))
        saved.append((t, item["composite"]))

    print(f"Sparade {len(saved)} bolag:")
    for t, c in saved:
        print(f"  {t:<14} composite={c}")
    if skipped:
        print(f"Hoppade över {len(skipped)} poster utan giltig 'ticker': {skipped}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    if cmd == "score":
        screen()
    elif cmd == "report":
        report()
    elif cmd == "chart":
        plot_positioning()
    elif cmd == "snapshot":
        snapshot(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "track":
        track()
    elif cmd == "lookback":
        months = int(sys.argv[2]) if len(sys.argv) > 2 else 6
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        lookback(months, n)
    elif cmd == "one":
        from data.data_loader import load_sweden_universe
        _, _, _, nm = load_sweden_universe(min_market_cap=config.QUALITY_MARKET_CAP)
        t = sys.argv[2]
        print(json.dumps(score_company(t, nm.get(t, t)), ensure_ascii=False, indent=2))
    elif cmd == "manual_prompt" and len(sys.argv) > 2:
        manual_prompt(sys.argv[2])
    elif cmd == "manual_import" and len(sys.argv) > 2:
        manual_import(sys.argv[2])
    elif cmd == "batch_prompt" and len(sys.argv) > 2:
        batch_prompt(sys.argv[2].split(","), sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "batch_prompt_chunks" and len(sys.argv) > 2:
        chunk_size = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        batch_prompt_chunks(sys.argv[2].split(","), chunk_size,
                            sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "batch_import":
        batch_import(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
