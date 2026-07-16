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
    python altdata/value_screener.py diagnose large      # varför saknas net_profit/equity? (kör coverage först)
"""
import sys
import csv
import json
import re
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


def _seg_market_cap_and_dir(segment: Optional[str]):
    """segment: 'large'/'small' (config.SEGMENTS) ELLER 'quality' (Small+
    Micro+NANO Cap – SAMMA specialfall som altdata/avanza.py._resolve_universe
    och mfn_fetch.py redan använder; Nano exkluderas medvetet ur 'small' i
    config.py, men det är ett skäl att inte TA POSITIONER där, inte ett skäl
    att avstå värde-screening). 'quality' skriver till en EGEN results/
    quality/-mapp, rör aldrig large/small:s filer. Returnerar
    (market_cap_lista, results_dir)."""
    if segment == "quality":
        return config.QUALITY_MARKET_CAP, Path(config.anchor("results/quality"))
    seg_cfg = config.SEGMENTS.get(segment) if segment else None
    seg_cfg = seg_cfg or config.SEGMENTS[config.DEFAULT_SEGMENT]
    return seg_cfg["market_cap"], Path(config.anchor(seg_cfg["results_dir"]))


def _to_msek(value, unit) -> Optional[float]:
    v = _num(value)
    if v is None:
        return None
    factor = _UNIT_TO_MSEK.get(str(unit or "").strip().lower(), 1.0)
    return v * factor


def _load_fundamentals(segment: Optional[str]) -> Dict[str, dict]:
    """Per ticker: senaste kända rapportrad + tillväxtkonsistens över de
    senaste (upp till 4) rapporterna vi faktiskt har.

    SAMMA RAPPORT (pm_id) kan förekomma i BÅDA MFN-CSV:erna med KOMPLEMENTÄRA
    fält: texten gav revenue/net_profit, PDF-backfillen balansräkningen
    (equity/liabilities/aktieantal). Sedan backfillen blev nyckelfälts-
    medveten (mfn_pdf._KEY_FIELDS) är de INTE längre disjunkta – raderna slås
    därför ihop FÄLTVIS per pm_id, med text-raden (fundamentals_from_mfn,
    läses först) som vinnare där båda har ett värde: narrativ-extraktion är
    verifierad mot fler skarpa exempel än tabell-extraktion, samma prioritet
    som mfn_pdf.backfill() själv använder mellan narrativ- och tabellträffar
    i en och samma PDF. Utan sammanslagningen hade 'latest = sista raden'
    slumpmässigt sett BARA enas fält och modellen tappat de andras.

    ANDRA STEGET – altdata/avanza.py (fundamentals_from_avanza.csv): Avanzas
    egna pm_id ('avanza-TICKER-ÅR-RTYPE') matchar ALDRIG ett äkta MFN-pm_id,
    så pm_id-mergen ovan slår aldrig ihop dem. Avanza kopplas i stället in
    via altdata/fund_merge.fill_from_avanza: fyller BARA NaN-celler i
    text-rader med samma (ticker, årsbärande period), eller läggs till som
    egna rader för perioder text-källorna helt saknar – text-rader slås
    ALDRIG ihop med varandra och behåller sina egna published-stämplar (se
    fund_merge-modulens docstring för de tre buggar den designen ersatte)."""
    import pandas as pd

    _, results_dir = _seg_market_cap_and_dir(segment)

    frames = []
    for fname in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv"):
        p = results_dir / fname
        if p.exists():
            try:
                frames.append(pd.read_csv(p))
            except Exception:  # noqa: BLE001
                pass
    if frames:
        text_df = pd.concat(frames, ignore_index=True)
        # Fältvis sammanslagning per pm_id: groupby().first() tar per kolumn det
        # FÖRSTA icke-NaN-värdet i gruppen – radordningen (mfn före pdf, bevarad
        # av sort=False + stabil ordning inom grupp) ger text-raden företräde.
        if "pm_id" in text_df.columns:
            has_id = text_df["pm_id"].notna()
            merged = text_df[has_id].groupby("pm_id", as_index=False, sort=False).first()
            text_df = pd.concat([merged, text_df[~has_id]], ignore_index=True)
    else:
        text_df = pd.DataFrame()

    avanza_p = results_dir / "fundamentals_from_avanza.csv"
    avanza_df = pd.DataFrame()
    if avanza_p.exists():
        try:
            avanza_df = pd.read_csv(avanza_p)
        except Exception:  # noqa: BLE001
            pass

    from altdata.fund_merge import fill_from_avanza
    df = fill_from_avanza(text_df, avanza_df)
    if df.empty or "ticker" not in df.columns or "published" not in df.columns:
        return {}

    df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True)
    df = df.dropna(subset=["ticker", "published"]).sort_values("published")

    from altdata.mfn_fundamentals import annualization_factor

    out: Dict[str, dict] = {}
    for t, g in df.groupby("ticker"):
        g = g.sort_values("published")
        latest = g.iloc[-1].to_dict()
        recent = g.tail(4)
        flags = []
        roe_flags = []
        for _, r in recent.iterrows():
            rev, rev_prior = _num(r.get("revenue")), _num(r.get("revenue_prior"))
            if rev is not None and rev_prior not in (None, 0):
                flags.append(rev > rev_prior)
            # ROE-KONSISTENS över rapporterna (Buffetts krav är "konsekvent hög
            # ROE över tid", inte en punktmätning): räkna ROE per historisk
            # rapport med SAMMA matematik som _metrics (enhetskonvertering +
            # årsuppräkning av flödesmåttet, equity > 0-regeln). Kräver ≥ 2
            # beräkningsbara rapporter, annars None (säger inget om konsistens).
            np_i = _to_msek(r.get("net_profit"), r.get("net_profit_unit"))
            eq_i = _to_msek(r.get("equity"), r.get("equity_unit"))
            if np_i is not None and eq_i is not None and eq_i > 0:
                roe_i = (np_i * annualization_factor(r.get("period"))) / eq_i
                roe_flags.append(roe_i >= config.VALUE_ROE_GOOD)
        # KRAVLISTE-underlag (OT-stil) ur ALLT vi extraherat, över rapporterna:
        # EBIT-marginal + trend, EPS-trend, nettoskuld, operativt kassaflöde,
        # utdelning. Allt enhets-normaliserat; saknat = None (ärligt obedömbart).
        margins, eps_vals = [], []
        dividend_any = False
        for _, r in recent.iterrows():
            ebit_i = _to_msek(r.get("ebit"), r.get("ebit_unit"))
            rev_i = _to_msek(r.get("revenue"), r.get("revenue_unit"))
            if ebit_i is not None and rev_i not in (None, 0.0):
                margins.append(ebit_i / rev_i)
            e_i = _num(r.get("eps"))
            if e_i is None:
                e_i = _num(r.get("eps_basic"))
            if e_i is not None:
                eps_vals.append(e_i)
            d_i = _num(r.get("dividend"))
            if d_i is not None and d_i > 0:
                dividend_any = True
        # UPPVÄRDERINGS-REFERENS (OT: "tidigare uppvärdering i relation till
        # resultat"): en jämförelserapport ~2,5 år före den senaste, med
        # beräkningsbar årsuppräknad vinst > 0 – används av _price_risk() för
        # att dekomponera kursutvecklingen i vinsttillväxt × multipel-
        # expansion. Fönstret (config.VALUE_RERATING_WINDOW_MONTHS) hellre än
        # en exakt punkt: rapportdatum ligger var som helst i kvartalet, och
        # kravet np_annual > 0 (förluståret kan inte dekomponeras meningsfullt)
        # gör att närmsta användbara rapport i fönstret väljs.
        old_ref = None
        lo_mo, hi_mo = getattr(config, "VALUE_RERATING_WINDOW_MONTHS", (20, 40))
        latest_pub = g.iloc[-1]["published"]
        target_days = (lo_mo + hi_mo) / 2 * 30.44
        best_dist = None
        for _, r in g.iterrows():
            age_days = (latest_pub - r["published"]).days
            if not (lo_mo * 30.44 <= age_days <= hi_mo * 30.44):
                continue
            np_old = _to_msek(r.get("net_profit"), r.get("net_profit_unit"))
            if np_old is None:
                continue
            np_old_annual = np_old * annualization_factor(r.get("period"))
            if np_old_annual <= 0:
                continue
            dist = abs(age_days - target_days)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                old_ref = {"published": r["published"], "np_annual": np_old_annual}
        out[t] = {
            "latest": latest,
            "old_ref": old_ref,
            "n_reports": len(g),
            "growth_consistency": (sum(flags) / len(flags)) if flags else None,
            "roe_consistency": (sum(roe_flags) / len(roe_flags)) if len(roe_flags) >= 2 else None,
            "ebit_margin": margins[-1] if margins else None,
            "ebit_margin_trend": (margins[-1] - margins[0]) if len(margins) >= 2 else None,
            "eps_trend": (eps_vals[-1] - eps_vals[0]) if len(eps_vals) >= 2 else None,
            "net_debt_msek": _to_msek(latest.get("net_debt"), latest.get("net_debt_unit")),
            "op_cf_msek": _to_msek(latest.get("operating_cash_flow"),
                                   latest.get("operating_cash_flow_unit")),
            "dividend_any": dividend_any,
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
    # Capex (om extraherad): gör owner earnings ETT steg närmare Buffetts
    # formel (np + D&A − capex). abs() eftersom investeringar ibland anges med
    # minustecken (kassaflödeskonvention) – de är alltid ett AVDRAG här; ett
    # teckenfel får aldrig ÖKA owner earnings. Saknas capex → gamla övre-
    # gräns-approximationen (dokumenterad i modulens docstring).
    capex = _to_msek(latest.get("capex"), latest.get("capex_unit"))
    capex_annual = abs(capex) * factor if capex is not None else None

    # Negativt eget kapital gör både ROE och Skuld/EK meningslösa (tecknet
    # vänder, ett katastrofbolag kan se ut att ha "positiv" ROE på negativt
    # kapital) → kräver equity > 0, inte bara != 0.
    roe = (np_annual / equity) if (np_annual is not None and equity is not None and equity > 0) else None
    debt_equity = (liabilities / equity) if (liabilities is not None and equity is not None and equity > 0) else None

    owner_earnings = None
    if np_annual is not None:
        owner_earnings = np_annual + (da_annual or 0.0) - (capex_annual or 0.0)
        # da saknas ofta -> 0 (konservativ underskattning); capex saknas ofta -> 0
        # (då blir OE en övre gräns – dokumenterad approximation)

    # PLAUSIBILITETSSPÄRR (upptäckt via skarp PDF-backfill-data: verkliga
    # exempel med ROE 656%/12545%/21950% och D/E -377.11 – fysiskt omöjliga
    # tal, inte äkta resultat). Grundorsaken är sannolikt en fel matchad
    # tabellrad eller en skalglidning i extraktionen (equity/net_profit/
    # aktieantal) – men OAVSETT mekanism ska en implausibel siffra ALDRIG nå
    # rankningen som om den vore sanning. Bara historiskt verifierade
    # extremfall (t.ex. en turn-around-kvartal på nästan obefintligt kapital)
    # kan ge trecifrig ROE på riktigt – 300% är redan en generös gräns.
    # D/E kan per definition (equity > 0 ovan) aldrig vara negativt – en
    # negativ siffra betyder alltid att 'liabilities' själv är korrupt.
    _ROE_MAX = 3.0     # 300 %
    _DE_MAX = 30.0     # skulder 30x eget kapital – redan extrem hävstång
    if roe is not None and abs(roe) > _ROE_MAX:
        roe = None
    if debt_equity is not None and not (0 <= debt_equity <= _DE_MAX):
        debt_equity = None

    rev_growth = None
    if revenue is not None and revenue_prior not in (None, 0):
        rev_growth = (revenue - revenue_prior) / abs(revenue_prior)

    # Börsvärde (MSEK) = pris (SEK/aktie, RÅTT tal) × aktieantal (RÅTT antal,
    # INTE MSEK) / 1e6 – aktieantalet har ingen Mkr-liknande skala.
    mcap_msek = (price * shares / 1e6) if (price is not None and shares) else None
    oe_yield = (owner_earnings / mcap_msek) if (owner_earnings is not None and mcap_msek) else None
    # Plausibilitetsspärr (samma motivering som ROE/D-E ovan): en verklig
    # skarp körning gav en multipel på 1,12e-05x ("billig", ser ut som ett
    # skrikande köp) – owner earnings kan inte rimligen vara >200% av hela
    # börsvärdet på ett år för ett fungerande bolag; det är ett extraktions-
    # fel (fel rad/skala i net_profit eller aktieantal), inte ett äkta case.
    if oe_yield is not None and abs(oe_yield) > 2.0:
        owner_earnings = oe_yield = None
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
        "roe_consistency": entry.get("roe_consistency"),
        "capex_included": capex is not None,   # transparens: äkta OE eller övre gräns?
        "np_annual": np_annual,                # internt: uppvärderings-dekomponeringen
        "published": latest.get("published"),
        # Transparens: vilken rapportperiod och årsfaktor som låg bakom talen –
        # så en manuell koll av value_shortlist.csv kan se om ett bolag är
        # helårs- eller uppskalad kvartalsdata.
        "period": latest.get("period"), "annual_factor": round(factor, 2),
    }


def _price_risk(price_df, np_annual_now, old_ref) -> dict:
    """Pris-baserade riskmått ur veckoserien (OT-komponenterna volatilitet +
    'tidigare uppvärdering i relation till resultat'):

    vol_52w: årsvolatilitet = std(veckoavkastningar senaste 52v) × √52.
    Kräver ≥ 30 avkastningspunkter, annars None (säger inget om risk).

    Uppvärderings-dekomponering: kursförändring över ~2,5 år (old_ref från
    _load_fundamentals) delas i vinsttillväxt × multipelexpansion:
        multipelexpansion = (pris_nu/pris_då) / (vinst_nu/vinst_då)
    > 1 betyder att aktien blivit dyrare PER VINSTKRONA – uppgången är
    uppvärdering, inte resultat. Flaggas (rerated_up) när kursen stigit
    minst VALUE_RERATING_MIN_PRICE_CHG OCH expansionen ≥ MAX_EXPANSION.

    ÄRLIGA BEGRÄNSNINGAR (medvetna, dokumenterade):
    · Per-aktie-pris mot TOTAL vinst antar oförändrat aktieantal – kraftig
      utspädning underskattar expansionen (flaggar för LITE, aldrig fel håll).
    · Kräver vinst > 0 i båda ändar – förlust-till-vinst-resor kan inte
      dekomponeras och flaggas ALDRIG (hellre omarkerad än felmarkerad).
    Saknas data → alla fält None/False: en aktie utesluts aldrig ur
    Buffett-grinden på gissad grund, bara på beräknad."""
    out = {"vol_52w": None, "price_chg_30m": None, "earn_chg_30m": None,
           "mult_expansion_30m": None, "rerated_up": False, "high_vol": False}
    if price_df is None or "Close" not in price_df:
        return out
    closes = price_df["Close"].dropna()
    if closes.empty:
        return out
    if getattr(closes.index, "tz", None) is not None:
        closes = closes.tz_localize(None)

    rets = closes.pct_change().dropna().tail(52)
    if len(rets) >= 30:
        vol = float(rets.std() * (52 ** 0.5))
        out["vol_52w"] = round(vol, 3)
        out["high_vol"] = vol > float(getattr(config, "VALUE_VOL_MAX", 0.60))

    if old_ref and np_annual_now is not None and np_annual_now > 0:
        pub = old_ref["published"]
        if getattr(pub, "tz", None) is not None or getattr(pub, "tzinfo", None) is not None:
            pub = pub.tz_localize(None)
        before = closes[closes.index <= pub]
        # kursserien måste faktiskt nå tillbaka: senaste veckan FÖRE
        # referensrapporten får inte ligga mer än ~3 månader före den
        # (annars jämförs mot en helt annan tidpunkt än rapporten)
        if not before.empty and (pub - before.index[-1]).days <= 92:
            price_then, price_now = float(before.iloc[-1]), float(closes.iloc[-1])
            if price_then > 0:
                price_ratio = price_now / price_then
                earn_ratio = np_annual_now / old_ref["np_annual"]
                out["price_chg_30m"] = round(price_ratio - 1, 3)
                out["earn_chg_30m"] = round(earn_ratio - 1, 3)
                if earn_ratio > 0:
                    expansion = price_ratio / earn_ratio
                    out["mult_expansion_30m"] = round(expansion, 2)
                    out["rerated_up"] = bool(
                        (price_ratio - 1) >= float(getattr(config, "VALUE_RERATING_MIN_PRICE_CHG", 0.50))
                        and expansion >= float(getattr(config, "VALUE_RERATING_MAX_EXPANSION", 1.5)))
    return out


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


def _sector_blend_ranks(vals: Dict[str, Optional[float]], sector_of,
                        blend: Optional[float] = None,
                        min_peers: Optional[int] = None) -> Dict[str, float]:
    """Blandar global percentil med SEKTOR-percentil (config.SECTOR_RANK_BLEND)
    för sektor-strukturella faktorer (värdering, skuld): en bank ska inte se
    "billig" ut bara för att banker som grupp handlas till lägre multiplar än
    SaaS – jämför den mot ANDRA banker också. Sektorer med färre än
    SECTOR_RANK_MIN_PEERS bolag (med värdet) faller tillbaka på ren global
    rank (en 2-bolags-sektor ger ingen meningsfull intern percentil).
    blend=0 → exakt _ranks() (gamla beteendet, regressionsgaranti)."""
    if blend is None:
        blend = float(getattr(config, "SECTOR_RANK_BLEND", 0.5))
    if min_peers is None:
        min_peers = int(getattr(config, "SECTOR_RANK_MIN_PEERS", 5))
    global_r = _ranks(vals)
    if blend <= 0:
        return global_r
    by_sec: Dict[str, Dict[str, Optional[float]]] = {}
    for t, v in vals.items():
        by_sec.setdefault(str(sector_of(t) or ""), {})[t] = v
    out: Dict[str, float] = {}
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


def _checklist(r: dict):
    """KVALITETSKRAVLISTAN (OT-analytics-inspirerad): tio binära krav prövade
    mot ALLT vi extraherat ur rapporterna. Varje krav är uppfyllt (True),
    underkänt (False) eller obedömbart (None – data saknas, räknas ALDRIG som
    vare sig plus eller minus). checklist_score = andel uppfyllda av de
    BEDÖMBARA, i procent; kräver ≥ 4 bedömbara för att alls ge en siffra
    (två gröna bockar av två bedömbara är inte "100% kvalitet").
    Returnerar (score_0_100|None, "uppfyllda/bedömbara", missade-krav-namn)."""
    crit = {
        "tillväxt": (r["rev_growth_yoy"] > 0) if r.get("rev_growth_yoy") is not None else None,
        "tillväxt-konsistens": (r["growth_consistency"] >= 0.75)
                               if r.get("growth_consistency") is not None else None,
        "ROE sektor-topp": r["meets_roe_bar"] if r.get("roe") is not None else None,
        "ROE-konsistens": (r["roe_consistency"] >= 0.75)
                          if r.get("roe_consistency") is not None else None,
        "EBIT-marginal≥10%": (r["ebit_margin"] >= 0.10) if r.get("ebit_margin") is not None else None,
        "marginaltrend": (r["ebit_margin_trend"] > 0) if r.get("ebit_margin_trend") is not None else None,
        # Balans: nettokassa (net_debt < 0) uppfyller direkt, annars skuld-barren.
        "balans": (True if (r.get("net_debt_msek") is not None and r["net_debt_msek"] < 0)
                   else (r["meets_debt_bar"] if r.get("debt_equity") is not None else None)),
        "kassaflöde+": (r["op_cf_msek"] > 0) if r.get("op_cf_msek") is not None else None,
        "EPS-trend": (r["eps_trend"] > 0) if r.get("eps_trend") is not None else None,
        "värdering": (r["zone"] in ("billig", "rimlig")) if r.get("zone") not in (None, "okänd") else None,
    }
    passed = [k for k, v in crit.items() if v is True]
    failed = [k for k, v in crit.items() if v is False]
    n_ass = len(passed) + len(failed)
    score100 = round(100 * len(passed) / n_ass) if n_ass >= 4 else None
    return score100, f"{len(passed)}/{n_ass}", ";".join(failed)


# Faktor-grupper, samma vikt-mönster som quant_screener.py – men egna vikter
# som lutar mer mot Buffetts uttalade prioritering (varaktig hög avkastning +
# konservativ skuldsättning + rimligt pris) än quant_screener.py:s bredare
# kvalitet/tillväxt/trygghet/värdering-split. Justerbart, ingen helig siffra.
_WEIGHTS = {"quality": 0.30, "safety": 0.20, "growth": 0.20, "value": 0.30}

# GICS-sektorer utan prissättningsmakt – vinsten är en funktion av externa
# råvarupriser, inte en varaktig konkurrensfördel (Buffetts egen uttalade
# och dokumenterade hållning mot rena råvarubolag). VERIFIERAT konkret fall:
# Lundin Gold (LUG.ST, sektor 'Materials') rankades som en av modellens
# bästa köp mitt under rekordhögt guldpris – trailing ROE/owner-earnings-
# yield fångar bara att marginalerna råkar vara på cykeltopp just nu, inte
# att de är VARAKTIGA. roe_consistency (senaste 4 rapporterna) gör det
# SNARARE VÄRRE: några kvartal i följd med samma medvind ser "konsekvent"
# bra ut fast det bara är exponering mot samma pris, inte kvalitet.
# 'Materials' i data/sweden_universe.csv (GICS) omfattar gruv-/metall-/
# skogs-/kemibolag (48 st), 'Energy' olje-/gasbolag (23 st) – verifierat
# mot den faktiska CSV:n, inte gissat. Rör INTE value_score/topplistan
# (transparens: alla bolag syns fortfarande, rankade som vanligt) – bara de
# två "här är modellens bästa idéer"-gaterna nedan.
_COMMODITY_SECTORS = {"Energy", "Materials"}


# VERIFIERAT (currency_check MEDIO.ST mot Medistim ASAs riktiga bokslut,
# 2026-07-15): Avanzas companyFinancialsByYear/Quarter returnerar RÅA belopp
# i bolagets EGEN noteringsvaluta (Medistim/norsk primärnotering: NOK 699,8
# Mkr FY2025 - vår lagrade "699.767 Mkr" är en EXAKT träff mot NOK-talet,
# INTE ett SEK-konverterat värde), men taggas alltid generiskt "Mkr" oavsett
# faktisk valuta. Priset (Yahoo) är BEKRÄFTAT också NOK för samma ticker.
# Konsekvens: ROE/D-E/owner_earnings_yield/mult/zon är KVOTER (täljare och
# nämnare i SAMMA valuta, NOK/NOK) - därför INTE valutaförvrängda, Buffett-
# barren/"billig"-klassningen är matematiskt giltig även för dessa bolag.
# Det som ÄR fel: varje ABSOLUT "Mkr"-märkt siffra (revenue_msek,
# owner_earnings_msek, mcap_msek) är vilseledande märkt - den är i själva
# verket MNOK, inte MSEK. Snarare än att GISSA en FX-kurs (samma varning som
# mfn_fundamentals.py redan gör för USD: fel kurs vore värre än att bara
# märka rätt) läggs valutan in explicit så den aldrig tyst antas vara SEK.
def _currency_cache_path() -> Path:
    return Path(config.anchor("cache")) / "_ticker_currency.json"


def _ticker_currency(ticker: str, cache: dict) -> str:
    """Cachad (för alltid - en notering byter aldrig handelsvaluta) valuta
    per ticker. `cache` muteras in-place av anroparen, som även ansvarar för
    att skriva den till disk (samma delcheckpoint-mönster som
    quality_screener._market_caps()). Default 'SEK' om Yahoo-uppslaget
    misslyckas - matchar det gamla, implicita antagandet för de facto
    SEK-rapporterande bolag (>90% av universumet), ingen ny risk för dem."""
    if ticker in cache:
        return cache[ticker]
    cur = "SEK"
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        c = fi.get("currency") if hasattr(fi, "get") else getattr(fi, "currency", None)
        if not c:
            c = yf.Ticker(ticker).info.get("currency")
        if c:
            cur = c
    except Exception:  # noqa: BLE001
        pass
    cache[ticker] = cur
    return cur


def score(segment: Optional[str] = None) -> None:
    from data.data_loader import fetch_weekly_data, load_sweden_universe

    seg_name = segment or config.DEFAULT_SEGMENT
    fund = _load_fundamentals(seg_name)
    if not fund:
        print(f"[value_screener] ingen fundamentals-data för segment '{seg_name}' – "
              f"kör mfn_fundamentals.py extract / mfn_pdf.py backfill först.")
        return

    market_cap, results_dir = _seg_market_cap_and_dir(seg_name)
    _, sector_map, _, name_map = load_sweden_universe(min_market_cap=market_cap)

    tickers = list(fund.keys())
    prices = fetch_weekly_data(tickers, use_cache=True)

    # Valuta per ticker (se modulkommentaren ovan _ticker_currency) – cachad
    # för alltid, delcheckpoint var 25:e NYA uppslag (mönster ur
    # quality_screener._market_caps) mot avbrott mitt i en stor körning.
    cur_cache_path = _currency_cache_path()
    currency_cache = json.loads(cur_cache_path.read_text()) if cur_cache_path.exists() else {}
    new_lookups = 0

    rows = []
    for t in tickers:
        p = prices.get(t)
        price = float(p["Close"].dropna().iloc[-1]) if (p is not None and not p["Close"].dropna().empty) else None
        m = _metrics(fund[t], price)
        # OT-riskmåtten (volatilitet + uppvärderings-dekomponering) ur samma
        # veckoserie som priset ovan – inga extra nätanrop.
        m.update(_price_risk(p, m.get("np_annual"), fund[t].get("old_ref")))
        m["ticker"] = t
        m["name"] = name_map.get(t, t)
        was_cached = t in currency_cache
        m["currency"] = _ticker_currency(t, currency_cache)
        if not was_cached:
            new_lookups += 1
            if new_lookups % 25 == 0:
                cur_cache_path.parent.mkdir(parents=True, exist_ok=True)
                cur_cache_path.write_text(json.dumps(currency_cache, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
        # Kravliste-underlaget (marginal/EPS/nettoskuld/kassaflöde/utdelning)
        # följer med från _load_fundamentals till radnivån.
        for k in ("ebit_margin", "ebit_margin_trend", "eps_trend",
                  "net_debt_msek", "op_cf_msek", "dividend_any"):
            m[k] = fund[t].get(k)
        rows.append(m)

    if new_lookups:
        cur_cache_path.parent.mkdir(parents=True, exist_ok=True)
        cur_cache_path.write_text(json.dumps(currency_cache, ensure_ascii=False, indent=2),
                                  encoding="utf-8")

    roe_vals = {r["ticker"]: r["roe"] for r in rows}
    # ROE-konsistens (andel av senaste rapporterna som klarade barren) rankas
    # SOM EN EGEN kvalitetsfaktor och snittas med punkt-ROE:n – Buffetts krav
    # är VARAKTIGT hög avkastning, inte en bra period. Saknad konsistens
    # (< 2 beräkningsbara rapporter) = 0.5 neutral, straffar inte tunn historik.
    cons_vals = {r["ticker"]: r.get("roe_consistency") for r in rows}
    debt_vals = {r["ticker"]: (-r["debt_equity"] if r["debt_equity"] is not None else None) for r in rows}
    growth_vals = {r["ticker"]: r["rev_growth_yoy"] for r in rows}
    value_vals = {r["ticker"]: r["owner_earnings_yield"] for r in rows}   # högre yield = billigare

    roe_rank, cons_rank = _ranks(roe_vals), _ranks(cons_vals)
    # Skuld + värdering är sektor-strukturella (banker/fastighet har hög D/E
    # och låga multiplar av naturen) → sektor-blandad rank för VÄRDE-SCORET.
    # Konsistens/tillväxt förblir GLOBALA i scoret – de är inte lika
    # sektor-bundna. roe_rank (ovan) är OCKSÅ kvar global, men bara för
    # quality_component i value_score-scoret (transparens/regressionsgaranti,
    # rör inte topplistan). Skuld- OCH roe-BARREN (den hårda Buffett-grinden,
    # se meets_roe_bar/meets_debt_bar nedan) använder däremot en EGEN
    # sektor-blandad rank vardera – ett flatt globalt krav (ROE ≥ 15%, D/E ≤
    # 0.5) straffar strukturellt reglerade/kapitalintensiva sektorer (banker:
    # Basel-kapitalkrav dämpar ROE jämfört med olevererade tillväxtbolag,
    # samtidigt som inlåning bokförs som skuld) – jämför bankerna mot VARANDRA
    # i stället.
    debt_rank = _sector_blend_ranks(debt_vals, sector_map.get)
    roe_bar_rank = _sector_blend_ranks(roe_vals, sector_map.get)
    growth_rank = _ranks(growth_vals)
    value_rank = _sector_blend_ranks(value_vals, sector_map.get)

    for r in rows:
        t = r["ticker"]
        quality_component = (roe_rank[t] + cons_rank[t]) / 2
        comp = (_WEIGHTS["quality"] * quality_component + _WEIGHTS["safety"] * debt_rank[t]
                + _WEIGHTS["growth"] * growth_rank[t] + _WEIGHTS["value"] * value_rank[t])
        r["value_score"] = round(comp * 100, 1)
        # Sektor-relativa barrer (se kommentaren ovanför roe_bar_rank/debt_rank) –
        # inte globala absoluta trösklar. Bankernas ROE dämpas strukturellt av
        # Basel-kapitalkrav och deras D/E är strukturellt hög (inlåning=skuld);
        # ett flatt globalt krav underkände praktiskt taget hela sektorn oavsett
        # faktisk hälsa (verkligt fall: Swedbank/Avanza Bank Holding).
        #
        # BUGG (fixad, verkligt fall Swedbank/Avanza): bool(...) kollapsade
        # SAKNAD data till False – samma som en bekräftad UNDERKÄND bar.
        # Swedbank saknar roe (extraktionslucka, troligen bankens balansräkning
        # passar inte industri-schemat) och flaggades ändå "ROE under barren";
        # Avanza saknar debt_equity och flaggades "skuld över barren" – i
        # BÅDA fallen fanns ingen siffra att döma av alls. None = obedömbart
        # ska ALDRIG räknas som en underkänd bar, samma disciplin som
        # _checklist() redan använder ("data saknas, räknas ALDRIG som vare
        # sig plus eller minus"). _fund_status() i portfolio.py läser redan
        # `is False` (inte falsy) så None flaggas korrekt INTE som ett
        # problem där – men _load_scores_uncached() måste också sluta
        # kollapsa den tomma CSV-strängen till False vid inläsning (separat fix).
        r["meets_roe_bar"] = (None if r["roe"] is None
                               else bool(roe_bar_rank[t] >= config.VALUE_ROE_RANK_SAFE))
        r["meets_debt_bar"] = (None if r["debt_equity"] is None
                                else bool(debt_rank[t] >= config.VALUE_DEBT_RANK_SAFE))
        r["checklist_score"], r["checklist"], r["checklist_miss"] = _checklist(r)
        r["commodity_sector"] = sector_map.get(t) in _COMMODITY_SECTORS

    rows.sort(key=lambda r: r["value_score"], reverse=True)

    out = results_dir / "value_shortlist.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ticker", "name", "value_score", "zone", "mult", "roe", "debt_equity",
            "owner_earnings_msek", "owner_earnings_yield", "rev_growth_yoy",
            "growth_consistency", "roe_consistency", "capex_included",
            "checklist_score", "checklist", "checklist_miss",
            "ebit_margin", "ebit_margin_trend", "eps_trend", "net_debt_msek", "op_cf_msek",
            "n_reports", "mcap_msek", "currency", "meets_roe_bar",
            "meets_debt_bar", "commodity_sector",
            "vol_52w", "high_vol", "price_chg_30m", "earn_chg_30m",
            "mult_expansion_30m", "rerated_up", "period", "annual_factor", "published"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"[value_screener] {len(rows)} bolag rankade → {out}")

    n_commodity = sum(1 for r in rows if r["commodity_sector"])
    n_rerated = sum(1 for r in rows if r["rerated_up"])
    n_highvol = sum(1 for r in rows if r["high_vol"])
    # OT-grinden i sin helhet: hårda kvalitetsbarren + SÄKERHETSMARGINAL
    # (config.BUFFETT_BUY_ZONES, default bara 'billig' – "uppsida med marginal
    # när jag köper") + ej råvarusektor + ej uppvärderad utan resultat + ej
    # extremvolatil. Rör INTE value_score/topplistan (transparens).
    buy_zones = tuple(getattr(config, "BUFFETT_BUY_ZONES", ("billig",)))
    buffett = [r for r in rows if r["meets_roe_bar"] and r["meets_debt_bar"]
               and r["zone"] in buy_zones and not r["commodity_sector"]
               and not r["rerated_up"] and not r["high_vol"]]
    n_foreign = sum(1 for r in rows if r["currency"] != "SEK")
    print(f"\n  🎯 KLARAR BUFFETT-BARREN (ROE bättre än sektor-percentil "
          f"{config.VALUE_ROE_RANK_SAFE:.0%}, skuld bättre än sektor-percentil "
          f"{config.VALUE_DEBT_RANK_SAFE:.0%}, zon {'/'.join(buy_zones)} "
          f"(säkerhetsmarginal), EJ råvarusektor ({n_commodity} uteslutna), EJ uppvärderad "
          f"utan resultat ({n_rerated} uteslutna), EJ extremvolatil (> "
          f"{getattr(config, 'VALUE_VOL_MAX', 0.60):.0%}/år, {n_highvol} uteslutna)) "
          f"– {len(buffett)} st ({n_foreign} icke-SEK bolag i hela universumet – kvoterna "
          f"(ROE/D-E/multipel) gäller oavsett valuta, men Mkr-summorna nedan är i BOLAGETS "
          f"EGEN valuta för dem, se 'currency'-kolumnen i CSV:n):")
    for r in buffett[:15]:
        cur_tag = f" [{r['currency']}]" if r["currency"] != "SEK" else ""
        print(f"   {r['value_score']:>5.1f}  {r['ticker']:<12} {str(r['name'])[:24]:<24} "
              f"ROE {r['roe']:.0%}  D/E {r['debt_equity']:.2f}  {r['mult']}x [{r['zone']}]{cur_tag}")

    print(f"\n  TOPP 20 (value_score, hela universumet):")
    for i, r in enumerate(rows[:20], 1):
        roe_s = f"{r['roe']:.0%}" if r["roe"] is not None else "  ?"
        de_s = f"{r['debt_equity']:.2f}" if r["debt_equity"] is not None else "   ?"
        cur_tag = f" [{r['currency']}]" if r["currency"] != "SEK" else ""
        print(f"  {i:>3} {r['ticker']:<12}{str(r['name'])[:22]:<22}"
              f"{r['value_score']:>6.1f}  ROE {roe_s:>4}  D/E {de_s:>5}  [{r['zone']}]{cur_tag}")

    n_thin = sum(1 for r in rows if r["n_reports"] < 2)
    print(f"\n  OBS: {n_thin}/{len(rows)} bolag har bara 1 känd rapport – tillväxtkonsistens "
          f"okänd för dem tills fler perioder finns i fundamentals-CSV:erna.")

    ck = [r for r in rows if r.get("checklist_score") is not None]
    strong = sorted([r for r in ck if r["checklist_score"] >= 70 and not r["commodity_sector"]],
                    key=lambda r: -r["checklist_score"])
    print(f"\n  KVALITETSKRAVLISTAN (OT-stil, 10 krav, EJ råvarusektor): {len(ck)} bolag "
          f"bedömbara (≥4 prövbara krav), {len(strong)} klarar ≥70%:")
    for r in strong[:15]:
        print(f"   {r['checklist_score']:>3}%  {r['checklist']:<6} {r['ticker']:<12} "
              f"{str(r['name'])[:22]:<22} missar: {r['checklist_miss'] or '–'}")


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
    market_cap, results_dir = _seg_market_cap_and_dir(seg_name)
    tickers, sector_map, cap_map, name_map = load_sweden_universe(min_market_cap=market_cap)
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

    out = results_dir / "value_coverage.csv"
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


def diagnose(segment: Optional[str] = None, fields: str = "net_profit,equity", limit: int = 8) -> None:
    """Visar ALLA rader (mfn/pdf/avanza, alla perioder, en rad per rapport)
    för ett urval bolag som coverage() flaggat 'delvis' med NÅGOT av de
    angivna fälten saknat i den SENASTE raden. Kräver att coverage(segment)
    körts först (läser dess value_coverage.csv) – ingen egen omberäkning.

    Till skillnad från coverage()s sammanfattning (som bara räknar) visar
    detta VARJE enskild rapportrad per bolag, så man ser VARFÖR fältet
    saknas: genomgående (källorna har det aldrig för bolaget – t.ex. en
    utlandsnoterad korsnotering) eller bara i den allra SENASTE perioden
    (t.ex. en färsk kvartalsrad utan balansräkning som skymmer en äldre,
    komplett årsrad – _load_fundamentals väljer bara den senaste raden).

        python altdata/value_screener.py diagnose large
        python altdata/value_screener.py diagnose large net_profit,equity 12
    """
    import pandas as pd

    seg_name = segment or config.DEFAULT_SEGMENT
    _, results_dir = _seg_market_cap_and_dir(seg_name)

    cov_path = results_dir / "value_coverage.csv"
    if not cov_path.exists():
        print(f"Ingen {cov_path} – kör 'coverage {seg_name}' först.")
        return
    cov = pd.read_csv(cov_path)
    wanted_fields = [f.strip() for f in fields.split(",") if f.strip()]
    pattern = "|".join(wanted_fields)
    sub = cov[(cov["status"] == "delvis") & cov["missing"].str.contains(pattern, na=False, regex=True)]
    sample = sub["ticker"].head(limit).tolist()
    print(f"[diagnose] {len(sample)} av {len(sub)} bolag ('delvis', saknar {'/'.join(wanted_fields)}): "
          f"{sample}\n")
    if not sample:
        return

    frames = []
    for fname, src in [("fundamentals_from_mfn.csv", "mfn"), ("fundamentals_from_pdf.csv", "pdf"),
                       ("fundamentals_from_avanza.csv", "avanza")]:
        p = results_dir / fname
        if p.exists():
            try:
                d = pd.read_csv(p)
            except Exception:  # noqa: BLE001
                continue
            d["_src"] = src
            frames.append(d)
    if not frames:
        print("Inga fundamentals-CSV:er hittades.")
        return
    df = pd.concat(frames, ignore_index=True, sort=False)

    cols = ["_src", "published", "period", "revenue", "net_profit", "equity",
           "liabilities", "shares_outstanding"]
    cols = [c for c in cols if c in df.columns]
    for t in sample:
        rows = df[df["ticker"] == t].sort_values("published")
        print(f"=== {t} ({len(rows)} rader totalt) ===")
        print(rows[cols].to_string(index=False))
        print()


# Nordiska dubbelnoteringar i sweden_universe.csv: ett norskt/danskt/finskt
# bolags PRIMÄRNOTERING rapporterar i sitt HEMLANDS valuta (NOK/DKK/EUR), men
# vi handlar det via en SVENSK sekundärnotering ('...O.ST'-mönstret,
# verifierat i avanza.py: EQNRO/YARO/ORKO/BNORO/AKERO m.fl. – Oslo Børs-
# primärnoteringar sekundärnoterade i Stockholm). mfn_fundamentals.py:s
# regex-extraktion är MEDVETET valuta-blind (bara SEK-enhetsord: Mkr/MSEK/
# tkr/TSEK/kkr, se modulens docstring) – riktig risk ENDAST om MFN:s
# svenskspråkiga pressmeddelande om t.ex. Medistim ASA råkar återge NOK-
# beloppet med en SEK-liknande enhetsfras ("...MSEK"/"...kronor") istället
# för att skriva ut NOK/MNOK/kroner, vilket _to_msek då tyst skulle tolka
# som SEK. INTE VERIFIERAT mot riktig cachad text – currency_check() nedan
# dumpar det faktiska pressmeddelande-utdraget + priskällans valuta så
# frågan kan avgöras mot verklig data, inte gissas.
def currency_check(ticker: str, segment: Optional[str] = None) -> None:
    """Diagnostik: finns en valutakrock för ETT bolag (typiskt en nordisk
    sekundärnotering, t.ex. 'MEDIO.ST'/Medistim ASA, NOK-rapporterande)?
    Visar (1) priskällans valuta (Yahoo, live), (2) alla lagrade
    fundamentals-rader för tickern källa-för-källa, (3) ett råutdrag ur det
    senaste rapport-PM:et på MFN så den FAKTISKA enhetsfrasen syns svart på
    vitt. Rör ingenting, inget nätanrop utöver EN Yahoo-uppslagning.

        python altdata/value_screener.py currency_check MEDIO.ST
    """
    import pandas as pd

    seg_name = segment or config.DEFAULT_SEGMENT
    _, results_dir = _seg_market_cap_and_dir(seg_name)

    print(f"[currency_check] {ticker}\n")

    print("== 1. Priskällans valuta (Yahoo, live) ==")
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        cur = info.get("currency") if hasattr(info, "get") else getattr(info, "currency", None)
        if not cur:
            cur = yf.Ticker(ticker).info.get("currency")
        print(f"  {ticker}: valuta={cur!r}" +
              (" -- OBS: INTE SEK, men fundamentas Mkr/MSEK-tolkning antar SEK!"
               if cur and cur != "SEK" else ""))
    except Exception as e:  # noqa: BLE001
        print(f"  kunde inte slå upp ({e})")

    print("\n== 2. Lagrade fundamentals-rader, källa för källa ==")
    any_rows = False
    for fname, src in [("fundamentals_from_mfn.csv", "mfn (textextraktion, SEK-enheter antas)"),
                       ("fundamentals_from_pdf.csv", "pdf (tabellextraktion, SEK-enheter antas)"),
                       ("fundamentals_from_avanza.csv", "avanza (Avanzas egna, RÅA SEK enligt deras API)")]:
        p = results_dir / fname
        if not p.exists():
            continue
        try:
            d = pd.read_csv(p)
        except Exception:  # noqa: BLE001
            continue
        rows = d[d["ticker"] == ticker] if "ticker" in d.columns else d.iloc[0:0]
        if rows.empty:
            continue
        any_rows = True
        cols = [c for c in ("published", "period", "revenue", "revenue_unit",
                            "net_profit", "net_profit_unit", "equity", "equity_unit")
               if c in rows.columns]
        print(f"  -- {src} --")
        print("  " + rows[cols].sort_values("published").to_string(index=False).replace("\n", "\n  "))
    if not any_rows:
        print("  (ingen lagrad fundamentals-rad för tickern i något segment)")

    print("\n== 3. Råutdrag ur senaste rapport-PM (MFN-cache, ingen tolkning) ==")
    from altdata.mfn_fundamentals import is_report_pm
    p = Path(config.MFN_CACHE_DIR) / f"{ticker}.json"
    if not p.exists():
        print(f"  ingen MFN-cache för {ticker} ({p})")
        return
    items = json.loads(p.read_text(encoding="utf-8")).get("items", [])
    reports = sorted([it for it in items if is_report_pm(it)],
                     key=lambda it: it.get("published", ""), reverse=True)
    if not reports:
        print("  inget rapport-liknande PM i cachen")
        return
    it = reports[0]
    text = it.get("text") or ""
    print(f"  {it.get('published','')[:10]} | {it.get('title','')}")
    # Utdrag runt varje "omsättning/nettoomsättning"-liknande omnämnande -
    # här ska den RIKTIGA enhetsfrasen (kronor/kr/NOK/kroner/...) synas.
    hits = list(re.finditer(r"(?:omsättning|nettoomsättning|revenue)", text, re.I))
    if not hits:
        print("  (hittade ingen 'omsättning'-liknande fras i texten - se hela PM:et manuellt)")
        print(f"  {text[:600]}")
        return
    for m in hits[:3]:
        lo, hi = max(0, m.start() - 30), min(len(text), m.end() + 120)
        print(f"  ...{text[lo:hi]!r}...")
    print("\n  Klistra in hela sektion 2+3 – avgör om enhetsordet ovan verkligen "
          "är SEK/kronor eller om det är NOK/kroner i svensk språkdräkt.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    seg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "score":
        score(seg)
    elif cmd == "coverage":
        coverage(seg)
    elif cmd == "diagnose":
        fields = sys.argv[3] if len(sys.argv) > 3 else "net_profit,equity"
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 8
        diagnose(seg, fields, limit)
    elif cmd == "currency_check":
        if len(sys.argv) < 3:
            print("Ange en ticker: python altdata/value_screener.py currency_check MEDIO.ST")
            return
        currency_check(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
