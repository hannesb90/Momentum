"""
altdata/value_screener.py – TOKEN-FRI Buffett-inspirerad värdeskreener ur EGEN
hårddata (altdata/mfn_fundamentals.py + altdata/mfn_pdf.py). Till skillnad
från quality_screener.py (LLM, kvalitativ tratt) och quant_screener.py
(TradingView-scanner) kommer nyckeltalen HÄRIFRÅN – ingen extern
fundamentals-tjänst, ingen token. Enda nätanropet är Yahoo-kurser för
börsvärde (samma källa som resten av pipelinen redan använder).

Grundat i väldokumenterade, publikt citerade Buffett-kriterier (INTE
gissat – se research i konversationen som föregick byggandet):
    ROE              > 15% konsekvent (helst över flera år)
    Skuldsättning    Debt/Equity < 0.5 (konservativt; vi använder Skulder/
                     Eget kapital som en grövre proxy – "Skulder" inkluderar
                     även icke-räntebärande poster som leverantörsskulder,
                     inte bara lånat kapital, så detta överskattar
                     hävstången något – dokumenterad förenkling)
    "Owner earnings" nettoresultat + avskrivningar (Buffetts formel drar även
                     av investeringar ± rörelsekapitalförändring, som vi INTE
                     extraherar ur MFN-texten – vår version är alltså en
                     ÖVRE gräns/approximation, inte den riktiga owner
                     earnings-siffran. Avskrivningar saknas ofta → default 0
                     vid saknad data, en KONSERVATIV underskattning, aldrig
                     en överskattning)
    Margin of safety börsvärde/owner earnings under en tröskel-multipel
                     (VALUE_MULT_CHEAP/FAIR i config.py – egna trösklar,
                     INTE samma som quality_screener.py:s EBITDA-baserade,
                     eftersom owner earnings är lägre än EBITDA)
    Tillväxt         intäktstillväxt (YoY), + konsistens över de senaste
                     rapporterna vi faktiskt har (kräver flera
                     fundamentals-rader per bolag – ofullständigt tills
                     PDF-backfillen/historiken byggts ut mer)

Samma percentil-rank-mönster som quant_screener.py (tål saknad data och
olika skalor – saknat värde = neutralt 0.5, se _ranks()).

Kräver att fundamentals_from_mfn.csv/fundamentals_from_pdf.csv redan
genererats för segmentet (mfn_fundamentals.py extract / mfn_pdf.py
backfill) – annars blir kortlistan tom, ingen krasch.

    python altdata/value_screener.py score large       # bygg value_shortlist.csv
    python altdata/value_screener.py coverage large     # vilka bolag saknar vi värde för?
"""
import sys
import csv
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Normalisering av redovisningsenhet → MSEK, så ROE/skuldsättning/owner
# earnings räknas på samma skala oavsett om ett enskilt bolag rapporterar i
# Mkr, tkr eller kkr. Okänd/saknad enhet antas redan vara Mkr (vanligast i
# den extraherade datan) – en dokumenterad approximation, inte en krasch.
_UNIT_TO_MSEK = {"mkr": 1.0, "msek": 1.0, "tkr": 0.001, "tsek": 0.001, "kkr": 0.001}


def _num(v):
    try:
        if v is None or v == "":
            return None
        f = float(v)
        # pandas fyller saknade kolumner med NaN (float('nan') är INTE None
        # och passerar annars som ett "värde" → ett bolag utan equity såg
        # felaktigt komplett ut i coverage, och NaN skulle poisona ROE/owner
        # earnings). NaN != NaN → detta fångar det.
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _to_msek(value, unit) -> Optional[float]:
    v = _num(value)
    if v is None:
        return None
    factor = _UNIT_TO_MSEK.get(str(unit or "").strip().lower(), 1.0)
    return v * factor


def _load_fundamentals(segment: Optional[str]) -> Dict[str, dict]:
    """Per ticker: senaste kända rapportrad + tillväxtkonsistens över de
    senaste (upp till 4) rapporterna vi faktiskt har. De två CSV:erna
    (mfn/pdf) är disjunkta by construction (mfn_pdf.py backfillar bara PM
    där text-extraktionen gav noll fält) – ingen dubblettrisk vid concat."""
    import pandas as pd

    seg = config.SEGMENTS.get(segment) if segment else None
    seg = seg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    results_dir = Path(config.anchor(seg["results_dir"]))

    frames = []
    for fname in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv"):
        p = results_dir / fname
        if p.exists():
            try:
                frames.append(pd.read_csv(p))
            except Exception:  # noqa: BLE001
                pass
    if not frames:
        return {}
    df = pd.concat(frames, ignore_index=True)
    if "ticker" not in df.columns or "published" not in df.columns:
        return {}
    df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True)
    df = df.dropna(subset=["ticker", "published"]).sort_values("published")

    out: Dict[str, dict] = {}
    for t, g in df.groupby("ticker"):
        g = g.sort_values("published")
        latest = g.iloc[-1].to_dict()
        recent = g.tail(4)
        flags = []
        for _, r in recent.iterrows():
            rev, rev_prior = _num(r.get("revenue")), _num(r.get("revenue_prior"))
            if rev is not None and rev_prior not in (None, 0):
                flags.append(rev > rev_prior)
        out[t] = {
            "latest": latest,
            "n_reports": len(g),
            "growth_consistency": (sum(flags) / len(flags)) if flags else None,
        }
    return out


def _metrics(entry: dict, price: Optional[float]) -> dict:
    from altdata.mfn_fundamentals import annualization_factor

    latest = entry["latest"]
    net_profit = _to_msek(latest.get("net_profit"), latest.get("net_profit_unit"))
    equity = _to_msek(latest.get("equity"), latest.get("equity_unit"))
    liabilities = _to_msek(latest.get("liabilities"), latest.get("liabilities_unit"))
    da = _to_msek(latest.get("depreciation_amortization"), latest.get("depreciation_amortization_unit"))
    shares = _num(latest.get("shares_outstanding"))
    revenue = _to_msek(latest.get("revenue"), latest.get("revenue_unit"))
    revenue_prior = _to_msek(latest.get("revenue_prior"), latest.get("revenue_unit"))

    # ÅRSJUSTERING (verifierad matematik-bugg innan detta fanns): resultat/
    # avskrivningar från en DELÅRSrapport är flödesmått för en del av året –
    # dividerat rakt av mot eget kapital (stock) gav ett Q1-bolag ~4x för låg
    # ROE (nästan inget klarade 15%-barren) och ~4x för dyr owner-earnings-
    # multipel (allt zonades 'dyr'). Skala till årstakt via periodspann ur
    # rapporttiteln (Q→x4, H1→x2, 9M→x4/3, Helår/okänd→x1 – okänd är
    # konservativt åt köpsidan). Balansposter (equity/liabilities) och
    # YoY-tillväxt (kvot av SAMMA period) skalas INTE.
    factor = annualization_factor(latest.get("period"))
    np_annual = net_profit * factor if net_profit is not None else None
    da_annual = da * factor if da is not None else None

    # Negativt eget kapital gör både ROE och Skuld/EK meningslösa (tecknet
    # vänder, ett katastrofbolag kan se ut att ha "positiv" ROE på negativt
    # kapital) → kräver equity > 0, inte bara != 0.
    roe = (np_annual / equity) if (np_annual is not None and equity is not None and equity > 0) else None
    debt_equity = (liabilities / equity) if (liabilities is not None and equity is not None and equity > 0) else None

    owner_earnings = None
    if np_annual is not None:
        owner_earnings = np_annual + (da_annual or 0.0)   # da saknas ofta -> 0, konservativ underskattning

    rev_growth = None
    if revenue is not None and revenue_prior not in (None, 0):
        rev_growth = (revenue - revenue_prior) / abs(revenue_prior)

    # Börsvärde (MSEK) = pris (SEK/aktie, RÅTT tal) × aktieantal (RÅTT antal,
    # INTE MSEK) / 1e6 – aktieantalet har ingen Mkr-liknande skala.
    mcap_msek = (price * shares / 1e6) if (price is not None and shares) else None
    oe_yield = (owner_earnings / mcap_msek) if (owner_earnings is not None and mcap_msek) else None
    mult = (mcap_msek / owner_earnings) if (owner_earnings and owner_earnings > 0 and mcap_msek) else None

    zone = "okänd"
    if mult is not None:
        if mult <= config.VALUE_MULT_CHEAP:
            zone = "billig"
        elif mult <= config.VALUE_MULT_FAIR:
            zone = "rimlig"
        else:
            zone = "dyr"
    elif owner_earnings is not None and owner_earnings <= 0:
        zone = "förlust"

    return {
        "roe": roe, "debt_equity": debt_equity, "owner_earnings_msek": owner_earnings,
        "owner_earnings_yield": oe_yield, "mult": mult, "zone": zone,
        "rev_growth_yoy": rev_growth, "mcap_msek": mcap_msek,
        "n_reports": entry["n_reports"], "growth_consistency": entry["growth_consistency"],
        "published": latest.get("published"),
        # Transparens: vilken rapportperiod och årsfaktor som låg bakom talen –
        # så en manuell koll av value_shortlist.csv kan se om ett bolag är
        # helårs- eller uppskalad kvartalsdata.
        "period": latest.get("period"), "annual_factor": round(factor, 2),
    }


def _ranks(vals: Dict[str, Optional[float]]) -> Dict[str, float]:
    """ticker→percentil [0,1] bland de som HAR värdet; saknat = 0.5 (neutralt).
    Samma mönster som quant_screener.py – tål saknad data/olika skalor.
    LIKA värden får MEDELRANKEN (annars avgjorde godtycklig sorteringsordning
    vilka av dem som hamnade högre – icke-deterministiskt betyg för bolag med
    identiska nyckeltal, upptäckt i matematik-granskning)."""
    present = sorted(((t, v) for t, v in vals.items() if isinstance(v, (int, float))),
                      key=lambda x: x[1])
    n = len(present)
    out: Dict[str, float] = {}
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


# Faktor-grupper, samma vikt-mönster som quant_screener.py – men egna vikter
# som lutar mer mot Buffetts uttalade prioritering (varaktig hög avkastning +
# konservativ skuldsättning + rimligt pris) än quant_screener.py:s bredare
# kvalitet/tillväxt/trygghet/värdering-split. Justerbart, ingen helig siffra.
_WEIGHTS = {"quality": 0.30, "safety": 0.20, "growth": 0.20, "value": 0.30}


def score(segment: Optional[str] = None) -> None:
    from data.data_loader import fetch_weekly_data, load_sweden_universe

    seg_name = segment or config.DEFAULT_SEGMENT
    fund = _load_fundamentals(seg_name)
    if not fund:
        print(f"[value_screener] ingen fundamentals-data för segment '{seg_name}' – "
              f"kör mfn_fundamentals.py extract / mfn_pdf.py backfill först.")
        return

    seg_cfg = config.SEGMENTS.get(seg_name, config.SEGMENTS[config.DEFAULT_SEGMENT])
    _, _, _, name_map = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])

    tickers = list(fund.keys())
    prices = fetch_weekly_data(tickers, use_cache=True)

    rows = []
    for t in tickers:
        p = prices.get(t)
        price = float(p["Close"].dropna().iloc[-1]) if (p is not None and not p["Close"].dropna().empty) else None
        m = _metrics(fund[t], price)
        m["ticker"] = t
        m["name"] = name_map.get(t, t)
        rows.append(m)

    roe_vals = {r["ticker"]: r["roe"] for r in rows}
    debt_vals = {r["ticker"]: (-r["debt_equity"] if r["debt_equity"] is not None else None) for r in rows}
    growth_vals = {r["ticker"]: r["rev_growth_yoy"] for r in rows}
    value_vals = {r["ticker"]: r["owner_earnings_yield"] for r in rows}   # högre yield = billigare

    roe_rank, debt_rank = _ranks(roe_vals), _ranks(debt_vals)
    growth_rank, value_rank = _ranks(growth_vals), _ranks(value_vals)

    for r in rows:
        t = r["ticker"]
        comp = (_WEIGHTS["quality"] * roe_rank[t] + _WEIGHTS["safety"] * debt_rank[t]
                + _WEIGHTS["growth"] * growth_rank[t] + _WEIGHTS["value"] * value_rank[t])
        r["value_score"] = round(comp * 100, 1)
        r["meets_roe_bar"] = bool(r["roe"] is not None and r["roe"] >= config.VALUE_ROE_GOOD)
        r["meets_debt_bar"] = bool(r["debt_equity"] is not None and r["debt_equity"] <= config.VALUE_DEBT_EQUITY_SAFE)

    rows.sort(key=lambda r: r["value_score"], reverse=True)

    out = Path(config.anchor(seg_cfg["results_dir"])) / "value_shortlist.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ticker", "name", "value_score", "zone", "mult", "roe", "debt_equity",
            "owner_earnings_msek", "owner_earnings_yield", "rev_growth_yoy",
            "growth_consistency", "n_reports", "mcap_msek", "meets_roe_bar",
            "meets_debt_bar", "period", "annual_factor", "published"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"[value_screener] {len(rows)} bolag rankade → {out}")

    buffett = [r for r in rows if r["meets_roe_bar"] and r["meets_debt_bar"]
               and r["zone"] in ("billig", "rimlig")]
    print(f"\n  🎯 KLARAR BUFFETT-BARREN (ROE ≥ {config.VALUE_ROE_GOOD:.0%}, "
          f"D/E ≤ {config.VALUE_DEBT_EQUITY_SAFE}, billig/rimlig owner-earnings-multipel) "
          f"– {len(buffett)} st:")
    for r in buffett[:15]:
        print(f"   {r['value_score']:>5.1f}  {r['ticker']:<12} {str(r['name'])[:24]:<24} "
              f"ROE {r['roe']:.0%}  D/E {r['debt_equity']:.2f}  {r['mult']}x [{r['zone']}]")

    print(f"\n  TOPP 20 (value_score, hela universumet):")
    for i, r in enumerate(rows[:20], 1):
        roe_s = f"{r['roe']:.0%}" if r["roe"] is not None else "  ?"
        de_s = f"{r['debt_equity']:.2f}" if r["debt_equity"] is not None else "   ?"
        print(f"  {i:>3} {r['ticker']:<12}{str(r['name'])[:22]:<22}"
              f"{r['value_score']:>6.1f}  ROE {roe_s:>4}  D/E {de_s:>5}  [{r['zone']}]")

    n_thin = sum(1 for r in rows if r["n_reports"] < 2)
    print(f"\n  OBS: {n_thin}/{len(rows)} bolag har bara 1 känd rapport – tillväxtkonsistens "
          f"okänd för dem tills fler perioder finns i fundamentals-CSV:erna.")


# Nyckelfält per härlett mått – för coverage-rapporten. Ett bolag kan inte
# få ett value_score på ett mått vars indata saknas, så vi listar exakt
# vad som fattas per bolag (så du vet vad du ev. behöver fylla manuellt).
_METRIC_INPUTS = {
    "ROE": ["net_profit", "equity"],
    "Skuld/EK": ["liabilities", "equity"],
    "Owner earnings": ["net_profit"],            # avskrivningar valfria (default 0)
    "Tillväxt": ["revenue", "revenue_prior"],
    "P/E-underlag": ["shares_outstanding"],
}


def coverage(segment: Optional[str] = None) -> None:
    """Korsar HELA segmentets universum mot den extraherade fundamentals-datan
    och visar VILKA BOLAG vi saknar värde för – så du vet vad som ev. måste
    fyllas manuellt eller hämtas om (mfn_fetch/backfill). Tre kategorier:
      1. INGEN rapportdata alls (inte i fundamentals-CSV:erna) – troligen
         PM som bara länkat en PDF vi inte lyckats extrahera, eller bolag
         utan MFN-cache.
      2. HAR data men saknar ett nyckelfält för ett mått (t.ex. har
         net_profit men inte equity → ingen ROE).
    Skriver results*/value_coverage.csv med per-bolag-status. Inget nätanrop."""
    from data.data_loader import load_sweden_universe

    seg_name = segment or config.DEFAULT_SEGMENT
    seg_cfg = config.SEGMENTS.get(seg_name, config.SEGMENTS[config.DEFAULT_SEGMENT])
    tickers, sector_map, cap_map, name_map = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
    # Fonder har inga bolagsfundamenta – exkludera (samma logik som quality_screener).
    universe = [t for t in tickers
                if cap_map.get(t) != "Fond" and sector_map.get(t) != "Fond"]

    fund = _load_fundamentals(seg_name)

    def _present(latest: dict, field: str) -> bool:
        return _num(latest.get(field)) is not None

    rows = []
    no_data, partial, full = [], [], []
    from collections import Counter
    missing_field_counts: Counter = Counter()

    for t in universe:
        name = name_map.get(t, t)
        entry = fund.get(t)
        if entry is None:
            no_data.append((t, name))
            rows.append({"ticker": t, "name": name, "status": "ingen data",
                         "n_reports": 0, "missing": "ALLT"})
            continue
        latest = entry["latest"]
        missing_metrics = []
        for metric, fields in _METRIC_INPUTS.items():
            miss = [f for f in fields if not _present(latest, f)]
            if miss:
                missing_metrics.append(f"{metric} (saknar {', '.join(miss)})")
                for f in miss:
                    missing_field_counts[f] += 1
        status = "komplett" if not missing_metrics else "delvis"
        (full if not missing_metrics else partial).append((t, name))
        rows.append({"ticker": t, "name": name, "status": status,
                     "n_reports": entry["n_reports"], "missing": "; ".join(missing_metrics)})

    out = Path(config.anchor(seg_cfg["results_dir"])) / "value_coverage.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    import csv as _csv
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["ticker", "name", "status", "n_reports", "missing"])
        w.writeheader()
        w.writerows(rows)

    n = len(universe)
    print(f"[value_screener coverage] segment '{seg_name}': {n} bolag (ex fonder)")
    print(f"  komplett (alla mått beräkningsbara): {len(full)} ({len(full)/max(n,1):.0%})")
    print(f"  delvis (data finns men något mått saknar indata): {len(partial)} ({len(partial)/max(n,1):.0%})")
    print(f"  INGEN data alls: {len(no_data)} ({len(no_data)/max(n,1):.0%})")

    if missing_field_counts:
        print("\n  Vanligast saknade fält (bland dem som HAR någon data):")
        for field, c in missing_field_counts.most_common():
            print(f"    {field:<24} saknas för {c} bolag")

    if no_data:
        print(f"\n  BOLAG UTAN NÅGON VÄRDE-DATA ({len(no_data)} st – manuell koll/omhämtning):")
        for t, name in sorted(no_data)[:40]:
            print(f"    {t:<14} {str(name)[:40]}")
        if len(no_data) > 40:
            print(f"    ... och {len(no_data) - 40} till (se {out})")

    print(f"\n  Full per-bolag-status skriven till: {out}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    seg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "score":
        score(seg)
    elif cmd == "coverage":
        coverage(seg)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
