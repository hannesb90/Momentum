"""
altdata/quant_screener.py – TOKEN-FRI kvantitativ betygsättning ur HÅRD DATA.

Att bränna Claude-tokens på siffror (marginal, tillväxt, ROE, värdering) är slöseri –
det är hård data. Vi hämtar finansiella nyckeltal GRATIS från TradingViews scanner och
räknar ett kvant-betyg via tvärsnitts-percentiler (rank mot hela universumet). Reservera
LLM-tokens för det GENUINT kvalitativa (moat, ledning, 10-årings-testet) i quality_screener.

Betyget väger fyra faktorer:
    Kvalitet  (40%): brutto-/EBITDA-/nettomarginal, ROE, ROIC        (högre = bättre)
    Tillväxt  (20%): omsättningstillväxt                             (högre = bättre)
    Trygghet  (15%): skuld/eget-kapital (lägre), kassalikviditet     (balansräkning)
    Värdering (25%): P/S och EV/EBITDA                               (lägre = billigare)
    → composite 0–100, rankat. 100 = bäst i universumet på hård data.

Percentil-rank tål saknad data och olika skalor. Saknat värde = neutralt (0.5).

VIKTIGT – körs på Pi:n (molnet saknar nät). Gratis, inget token.

    python altdata/quant_screener.py probe VOLV-B.ST SAAB-B.ST   # verifiera att fälten kommer
    python altdata/quant_screener.py fetch                       # alla → cache/quality/_quant.json
    python altdata/quant_screener.py score                       # → results/quant_shortlist.csv
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

try:
    import requests
except ImportError:
    requests = None

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# TradingView-scannerns fältnamn (best effort – 'probe' visar vilka som faktiskt svarar).
_COLS = [
    "description", "market_cap_basic", "currency", "sector",
    "total_revenue", "total_revenue_yoy_growth_ttm", "revenue_growth",
    "gross_margin_ttm", "ebitda_margin_ttm", "net_margin_ttm",
    "return_on_equity", "return_on_invested_capital",
    "debt_to_equity", "current_ratio",
    "enterprise_value_ebitda_ttm", "price_sales_ratio",
]
# Fältnamnet för omsättningstillväxt varierar – prova flera, ta första med värde.
_GROWTH_FIELDS = ["total_revenue_yoy_growth_ttm", "revenue_growth"]

# Faktor-grupper: (fält, riktning). +1 = högre bättre, -1 = lägre bättre.
_QUALITY = [("gross_margin_ttm", 1), ("ebitda_margin_ttm", 1), ("net_margin_ttm", 1),
            ("return_on_equity", 1), ("return_on_invested_capital", 1)]
_GROWTH = [("_growth", 1)]                     # _growth injiceras i score() (coalesce ovan)
_SAFETY = [("debt_to_equity", -1), ("current_ratio", 1)]
_VALUE = [("price_sales_ratio", -1), ("enterprise_value_ebitda_ttm", -1)]
_WEIGHTS = {"quality": 0.40, "growth": 0.20, "safety": 0.15, "value": 0.25}


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _finite(v):
    """Som _num men slänger även ±inf (sanerings-sentinel i ranken, se score())."""
    import math
    return v if isinstance(v, (int, float)) and math.isfinite(v) else None


def _fetch_all() -> dict:
    """Scanner: alla svenska aktier (type=stock) med nyckeltals-kolumnerna. Returnerar
    {vår_ticker: {kolumn: värde}} för Nasdaq Stockholm-noteringar i SEK."""
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"}],
            "columns": _COLS, "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
            "range": [0, 4000], "options": {"lang": "en"}}
    r = requests.post(config.TRADINGVIEW_SCAN_URL, json=body,
                      headers={"User-Agent": _UA, "Content-Type": "application/json"}, timeout=45)
    r.raise_for_status()
    out = {}
    for row in r.json().get("data") or []:
        s, d = row.get("s", ""), (row.get("d") or [])
        if not s.startswith(config.TRADINGVIEW_EXCHANGE + ":"):
            continue
        rec = {c: (d[i] if i < len(d) else None) for i, c in enumerate(_COLS)}
        if rec.get("currency") and str(rec["currency"]).upper() != "SEK":
            continue
        ticker = s.split(":", 1)[1].replace("_", "-") + ".ST"
        out[ticker] = rec
    return out


def _fetch_symbols(tickers) -> dict:
    """Hämtar nyckeltal för specifika tickers (probe)."""
    if requests is None:
        raise RuntimeError("paketet 'requests' saknas – pip install requests")
    def tv(t):
        b = t[:-3] if t.upper().endswith(".ST") else t
        return f"{config.TRADINGVIEW_EXCHANGE}:{b.replace('-', '_').replace('.', '_')}"
    rev = {tv(t): t for t in tickers}
    body = {"symbols": {"tickers": list(rev.keys()), "query": {"types": []}}, "columns": _COLS}
    r = requests.post(config.TRADINGVIEW_SCAN_URL, json=body,
                      headers={"User-Agent": _UA, "Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    out = {}
    for row in r.json().get("data") or []:
        s, d = row.get("s", ""), (row.get("d") or [])
        out[rev.get(s, s)] = {c: (d[i] if i < len(d) else None) for i, c in enumerate(_COLS)}
    return out


def probe(tickers) -> None:
    res = _fetch_symbols(tickers)
    if not res:
        print("[probe] inga träffar – scannern kan ha ändrat fältnamn.")
        return
    for t in tickers:
        rec = res.get(t)
        if not rec:
            print(f"  {t:<12} ingen träff")
            continue
        print(f"\n  {t}  ({rec.get('description')})")
        for c in _COLS[1:]:
            print(f"    {c:<32} {rec.get(c)}")
    miss = [c for c in _COLS[1:] if all(res[t].get(c) is None for t in res)]
    if miss:
        print(f"\n  OBS: dessa fält kom tomma för ALLA (fel fältnamn?): {miss}")
    else:
        print("\n  Alla fält gav värden – kör 'fetch' för hela universumet.")


def fetch() -> None:
    cache = Path(config.QUALITY_CACHE_DIR) / "_quant.json"
    try:
        data = _fetch_all()
    except Exception as e:  # noqa: BLE001
        print(f"[fetch] kunde inte hämta: {e}  (körs på Pi:n)")
        return
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False))
    print(f"[fetch] {len(data)} bolag med nyckeltal → {cache}")


def _ranks(vals: dict) -> dict:
    """ticker→percentil [0,1] bland de som HAR värdet; saknat = 0.5 (neutralt).
    LIKA värden får MEDELRANKEN (annars avgjorde godtycklig sorteringsordning –
    dict-ordning – vilka av dem som fick 0.3 vs 0.7: icke-deterministiskt betyg
    för bolag med identiska nyckeltal, upptäckt i matematik-granskning)."""
    present = sorted(((t, v) for t, v in vals.items() if isinstance(v, (int, float))),
                     key=lambda x: x[1])
    n = len(present)
    out = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and present[j + 1][1] == present[i][1]:
            j += 1
        pct = ((i + j) / 2 + 0.5) / n          # medelrank för alla med samma värde
        for k in range(i, j + 1):
            out[present[k][0]] = pct
        i = j + 1
    for t in vals:
        out.setdefault(t, 0.5)
    return out


def _sector_blend_ranks(vals: dict, sector_of) -> dict:
    """Global percentil blandad med SEKTOR-percentil (config.SECTOR_RANK_BLEND)
    – samma motivering och matematik som value_screener._sector_blend_ranks:
    värdering/skuld är sektor-strukturella (banker ser alltid 'billiga' och
    'skuldsatta' ut mot SaaS). Sektor med < SECTOR_RANK_MIN_PEERS bolag →
    ren global rank. blend=0 → exakt _ranks() (gamla beteendet)."""
    blend = float(getattr(config, "SECTOR_RANK_BLEND", 0.5))
    min_peers = int(getattr(config, "SECTOR_RANK_MIN_PEERS", 5))
    global_r = _ranks(vals)
    if blend <= 0:
        return global_r
    by_sec = {}
    for t, v in vals.items():
        by_sec.setdefault(str(sector_of(t) or ""), {})[t] = v
    out = {}
    for sec, sub in by_sec.items():
        n_present = sum(1 for v in sub.values() if isinstance(v, (int, float)))
        if sec and n_present >= min_peers:
            sec_r = _ranks(sub)
            for t in sub:
                out[t] = (1 - blend) * global_r[t] + blend * sec_r[t]
        else:
            for t in sub:
                out[t] = global_r[t]
    return out


def _group_score(data, factors, sector_relative: bool = False) -> dict:
    """Medel-percentil över faktorerna i en grupp (riktning: -1 inverterar).
    sector_relative=True → sektor-blandad rank (för värdering/skuld, se
    _sector_blend_ranks); sektorn läses ur TradingView-datan själv."""
    sector_of = (lambda t: data.get(t, {}).get("sector")) if sector_relative else None
    parts = []
    for field, direction in factors:
        vals = {t: (_num(rec.get(field)) if direction > 0
                    else (-_num(rec.get(field)) if _num(rec.get(field)) is not None else None))
                for t, rec in data.items()}
        parts.append(_sector_blend_ranks(vals, sector_of) if sector_relative else _ranks(vals))
    return {t: sum(p[t] for p in parts) / len(parts) for t in data}


def score(min_rev_msek=100) -> None:
    import csv
    cache = Path(config.QUALITY_CACHE_DIR) / "_quant.json"
    if not cache.exists():
        print("[score] ingen _quant.json – kör 'fetch' först.")
        return
    raw = json.loads(cache.read_text())
    if not raw:
        print("[score] tom cache.")
        return
    # Filtrera bort det som gör kvant-betyg meningslöst: pre-revenue-skal (biotech/
    # prospektering med ~0 omsättning → skräp-marginaler). Omsättningsgolvet
    # (min_rev_msek) FÅNGAR REDAN det här fallet - ett genuint binärt kliniskt
    # lotteri (pre-revenue) har typiskt ~0 omsättning och exkluderas av
    # revenue-filtret ensamt.
    #
    # BUGG (fixad, 2026-07-23): en tidigare version uteslöt DÄRUTÖVER hela
    # sektorn "Health Care" blankt - fångade rätt de genuina pre-revenue-
    # lotterierna, men rev med sig ETABLERADE, lönsamma bolag som råkar bära
    # samma sektor-etikett (Swedencare: djurhälsoprodukter, 2 683 Mkr
    # omsättning; Bonesupport/Senzime: säljande medtech, inte pre-klinisk
    # forskning). Sektorn i sig säger inget om binärt-lotteri-risken -
    # omsättningsgolvet gör det jobbet redan, mer träffsäkert.
    min_rev = min_rev_msek * 1e6
    data, drop_rev = {}, 0
    for t, rec in raw.items():
        rev = _num(rec.get("total_revenue"))
        if rev is None or rev < min_rev:            # för lite omsättning → ej betygsättbart
            drop_rev += 1
            continue
        rec["_growth"] = next((rec[f] for f in _GROWTH_FIELDS
                               if isinstance(rec.get(f), (int, float))), None)
        # ── Matematisk sanering av inverterade kvoter (hittad i granskning) ──
        # · Negativ D/E = NEGATIVT eget kapital. Efter -1-inverteringen i _SAFETY
        #   rankades det som SÄKRAST i universumet (dubbel-negation: -(-5) = +5,
        #   sorterar högst) – i verkligheten är negativt EK värre än varje positiv
        #   skuldsättning → +inf (sämst i ranken). Och ROE på negativt EK är
        #   teckenvänt nonsens (förlust/negativt = "positiv" kvot) → None (neutral),
        #   samma regel som value_screener._metrics kräver equity > 0.
        de = _num(rec.get("debt_to_equity"))
        if de is not None and de < 0:
            rec["debt_to_equity"] = float("inf")
            rec["return_on_equity"] = None
        # · Negativ EV/EBITDA har TVÅ orsaker med MOTSATT innebörd: negativ EBITDA
        #   (förlustbolag → -1-inverteringen rankade det som BILLIGAST – fel) eller
        #   negativt EV (kassa > börsvärde → genuint extremt billigt – rätt).
        #   Disambiguera via EBITDA-marginalen: marginal < 0 → förlust → sämst
        #   (+inf); marginal okänd → None (gissa inte); marginal > 0 → negativt EV,
        #   äkta billig → behåll (inverteras korrekt till toppen).
        ev = _num(rec.get("enterprise_value_ebitda_ttm"))
        if ev is not None and ev < 0:
            margin = _num(rec.get("ebitda_margin_ttm"))
            if margin is not None and margin < 0:
                rec["enterprise_value_ebitda_ttm"] = float("inf")
            elif margin is None:
                rec["enterprise_value_ebitda_ttm"] = None
        data[t] = rec
    if not data:
        print("[score] inga bolag kvar efter filter.")
        return
    print(f"[score] filter: −{drop_rev} med < {min_rev_msek} MSEK omsättning → {len(data)} betygsatta")
    groups = {"quality": _group_score(data, _QUALITY), "growth": _group_score(data, _GROWTH),
              "safety": _group_score(data, _SAFETY, sector_relative=True),
              "value": _group_score(data, _VALUE, sector_relative=True)}
    rows = []
    for t, rec in data.items():
        comp = sum(_WEIGHTS[g] * groups[g][t] for g in _WEIGHTS)
        rows.append({
            "ticker": t, "name": rec.get("description") or t,
            "quant_score": round(comp * 100, 1),
            "quality": round(groups["quality"][t] * 100),
            "growth": round(groups["growth"][t] * 100),
            "safety": round(groups["safety"][t] * 100),
            "value": round(groups["value"][t] * 100),
            "mcap_msek": (round(_num(rec.get("market_cap_basic")) / 1e6, 1)
                          if _num(rec.get("market_cap_basic")) else None),
            "ebitda_margin": _num(rec.get("ebitda_margin_ttm")),
            "rev_growth": _num(rec.get("_growth")),
            # inf är sanerings-sentinel för ranken (se ovan) – skriv None i CSV:n.
            "roe": _finite(rec.get("return_on_equity")),
            "ps": _finite(rec.get("price_sales_ratio")),
            "ev_ebitda": _finite(rec.get("enterprise_value_ebitda_ttm")),
        })
    rows.sort(key=lambda r: r["quant_score"], reverse=True)
    out = Path(config.anchor(config.RESULTS_DIR)) / "quant_shortlist.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[score] {len(rows)} bolag rankade → {out}\n")
    print("  TOPP 20 (kvant-betyg på hård data, token-fritt):")
    print(f"  {'#':>3} {'ticker':<12}{'namn':<26}{'betyg':>6}{'kval':>5}{'tillv':>6}{'värd':>5}")
    for i, r in enumerate(rows[:20], 1):
        print(f"  {i:>3} {r['ticker']:<12}{str(r['name'])[:25]:<26}"
              f"{r['quant_score']:>6}{r['quality']:>5}{r['growth']:>6}{r['value']:>5}")


_AVANZA_QUALITY = [("_net_margin", 1), ("roe_avanza", 1)]
_AVANZA_GROWTH = [("_rev_growth", 1)]
_AVANZA_SAFETY = [("debt_equity_avanza", -1)]
_AVANZA_VALUE = [("_ps", -1)]
_AVANZA_WEIGHTS = {"quality": 0.40, "growth": 0.20, "safety": 0.15, "value": 0.25}


def score_avanza(segment: str = "small", min_rev_msek: float = 10) -> None:
    """Samma tvärsnitts-percentil-metodik som score() (TROTS delad kod:
    _group_score/_ranks importeras rakt av, ingen omimplementerad matte),
    men källan är fundamentals_from_avanza.csv i stället för TradingViews
    scanner – VERKLIGT FALL 2026-07-22: "Fundamenta i kontext" saknades
    HELT för småbolagsinnehav (SECARE.ST/PLEJD.ST/ACCON.ST m.fl.), och
    Avanza-önskad-som-primärkälla-policyn gäller.

    TUNNARE än score(): TradingView-scannern ger 5 kvalitetsfaktorer
    (brutto-/EBITDA-/nettomarginal, ROE, ROIC) + kassalikviditet + EV/EBITDA
    – fundamentals_from_avanza.csv har BARA revenue/net_profit/equity/
    liabilities/eps/roe_avanza/debt_equity_avanza (ingen EBITDA, ingen
    ROIC, ingen kassalikviditet). Kvalitet blir här nettomarginal+ROE
    (2 faktorer i st.f. 5), Värdering blir bara P/S (ingen EV/EBITDA går
    att räkna utan EBITDA). Hellre en tunnare men ÄRLIG betygsgrund än
    att hitta på siffror pipelinen inte har – se docstringen ovan i
    filen om varför Health Care/pre-revenue exkluderas, samma regel här.

    Marknadsvärde/aktiepris hämtas INTE live från Avanza (skulle vara
    ~475 anrop á 0.5s paus = flera minuter) – shares_outstanding
    (redan i fundamentals-filen) × senaste veckostängning i segmentets
    EGNA prices.csv (redan nattligt cachad av huvudpipelinen) räcker.

    Skriver till segmentets EGEN results_dir (till skillnad från score(),
    som alltid skriver till config.RESULTS_DIR/"large") – /api/quant
    måste därför läsas segment-medvetet (se api/main.py)."""
    import csv
    import pandas as pd
    from data.data_loader import load_sweden_universe

    seg_cfg = config.SEGMENTS.get(segment)
    if seg_cfg is None:
        print(f"[score_avanza] okänt segment '{segment}'.")
        return
    results_dir = Path(config.anchor(seg_cfg["results_dir"]))
    fund_path = results_dir / "fundamentals_from_avanza.csv"
    prices_path = results_dir / "prices.csv"
    if not fund_path.exists():
        print(f"[score_avanza] {fund_path} saknas – kör 'python -m altdata.avanza extract {segment}' först.")
        return
    if not prices_path.exists():
        print(f"[score_avanza] {prices_path} saknas – kör huvudpipelinen (main.py) först.")
        return

    _, sector_map, _, name_map = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])

    fund = pd.read_csv(fund_path)
    fund = fund.sort_values("published")
    latest = fund.groupby("ticker").tail(1).set_index("ticker")  # senaste raden per bolag

    prices = pd.read_csv(prices_path)
    latest_px = prices.sort_values("date").groupby("ticker")["close"].last()

    data: dict = {}
    drop_rev = drop_px = 0
    for t, rec in latest.iterrows():
        sector = sector_map.get(t, "")
        # BUGG (fixad, 2026-07-23): uteslöt tidigare hela sektorn "Health Care"
        # blankt (samma fälla som score() hade, se dess kommentar för
        # resonemanget) - rev med sig lönsamma konsumenthälsobolag (Swedencare)
        # och säljande medtech (Bonesupport, Senzime), inte bara genuina
        # pre-revenue kliniska lotterier. Omsättningsgolvet nedan gör det
        # jobbet mer träffsäkert på egen hand.
        # revenue/net_profit är REDAN i Mkr (miljoner, se kolumnen
        # revenue_unit i fundamentals_from_avanza.csv) - INTE rå SEK. Både
        # min_rev_msek-tröskeln och _ps nedan måste jämföra Mkr mot Mkr,
        # inte rå SEK mot Mkr (verklig bugg: en första version multiplicerade
        # tröskeln med 1e6 och tappade 355/430 bolag av misstag).
        revenue = _num(rec.get("revenue"))
        if revenue is None or revenue < min_rev_msek:
            drop_rev += 1
            continue
        px = latest_px.get(t)
        shares = _num(rec.get("shares_outstanding"))
        if px is None or shares is None:
            drop_px += 1
            continue
        rev_prior = _num(rec.get("revenue_prior"))
        net_profit = _num(rec.get("net_profit"))
        mcap = px * shares                    # rå SEK (pris × antal aktier)
        mcap_msek = mcap / 1e6                 # Mkr, samma enhet som revenue
        row = {
            "sector": sector,
            "_rev_growth": ((revenue - rev_prior) / rev_prior * 100)
                           if rev_prior not in (None, 0) else None,
            "_net_margin": (net_profit / revenue * 100) if net_profit is not None else None,
            "_ps": (mcap_msek / revenue) if revenue else None,
            "roe_avanza": _num(rec.get("roe_avanza")),
            "debt_equity_avanza": _num(rec.get("debt_equity_avanza")),
            "mcap_msek": round(mcap_msek, 1),
        }
        # Samma sanering som score(): negativ D/E = negativt eget kapital,
        # värre än varje positiv skuldsättning, inte "säkrast" via dubbel-negation.
        de = row["debt_equity_avanza"]
        if de is not None and de < 0:
            row["debt_equity_avanza"] = float("inf")
            row["roe_avanza"] = None
        data[t] = row
    if not data:
        print(f"[score_avanza] inga bolag kvar efter filter (−{drop_rev} omsättning, "
              f"−{drop_px} saknar pris/aktieantal).")
        return
    print(f"[score_avanza] {segment}: filter −{drop_rev} < {min_rev_msek} MSEK omsättning, "
          f"−{drop_px} saknar pris/aktieantal → {len(data)} betygsatta")

    groups = {"quality": _group_score(data, _AVANZA_QUALITY),
              "growth": _group_score(data, _AVANZA_GROWTH),
              "safety": _group_score(data, _AVANZA_SAFETY, sector_relative=True),
              "value": _group_score(data, _AVANZA_VALUE, sector_relative=True)}
    rows = []
    for t, rec in data.items():
        comp = sum(_AVANZA_WEIGHTS[g] * groups[g][t] for g in _AVANZA_WEIGHTS)
        rows.append({
            "ticker": t, "name": name_map.get(t, t),
            "quant_score": round(comp * 100, 1),
            "quality": round(groups["quality"][t] * 100),
            "growth": round(groups["growth"][t] * 100),
            "safety": round(groups["safety"][t] * 100),
            "value": round(groups["value"][t] * 100),
            "mcap_msek": rec["mcap_msek"],
            "ebitda_margin": None,   # ej beräkningsbar från Avanza-fundamenta, se docstring
            "rev_growth": rec["_rev_growth"],
            "roe": _finite(rec["roe_avanza"]),
            "ps": _finite(rec["_ps"]),
            "ev_ebitda": None,       # ej beräkningsbar från Avanza-fundamenta, se docstring
            "quant_source": "avanza",
        })
    rows.sort(key=lambda r: r["quant_score"], reverse=True)
    out = results_dir / "quant_shortlist.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[score_avanza] {len(rows)} bolag rankade → {out}\n")
    print("  TOPP 15 (kvant-betyg, Avanza-fundamenta):")
    for i, r in enumerate(rows[:15], 1):
        print(f"  {i:>3} {r['ticker']:<12}{str(r['name'])[:25]:<26}{r['quant_score']:>6}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe(sys.argv[2:] or ["VOLV-B.ST", "SAAB-B.ST", "EVO.ST"])
    elif cmd == "fetch":
        fetch()
    elif cmd == "score":
        score(float(sys.argv[2]) if len(sys.argv) > 2 else 100)
    elif cmd == "score_avanza":
        score_avanza(sys.argv[2] if len(sys.argv) > 2 else "small",
                     float(sys.argv[3]) if len(sys.argv) > 3 else 10)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
