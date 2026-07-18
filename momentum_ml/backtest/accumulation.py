"""
backtest/accumulation.py – "bara påfyllnad, aldrig sälj"-backtest.

Skiljer sig fundamentalt från backtester.py (som simulerar en HANDLANDE
strategi – köper/säljer/roterar positioner varje vecka) och benchmark.py
(engångsinsatt, likaviktat köp-och-behåll). Ingen av dem speglar vad
next_buy() FAKTISKT gör med kärnan/hinkarna: en fast MÅNADSINSÄTTNING
fördelas mot GAPET till målvikt (_dynamic_fill_split/_fill_split i
portfolio.py), aldrig genom att sälja en övervikt. Den skillnaden spelar
roll – "köp enda global fond slog varje aktiv variant" (next_buy()s
kärn-motivering) byggde på aktie-holdout och ETF-rotationens OOS-svep,
INGET av dem testade just den här insättnings-mekaniken eller en rimlig
regionsfördelning (se backtest_core_allocation.py, som använder detta
modulet för att faktiskt testa den frågan).

simulate_accumulation() är medvetet ALLMÄN (vilken korg av tickers/målvikter
som helst) – inte hårdkodad till kärn-ETF:erna, så samma motor kan senare
peka på andra frågor (sektorvikter, enskilda innehav, satellit-korgar).
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from backtest.backtester import MomentumBacktester

MIN_WEEKS = 156   # ~3 år gemensam historik - kortare är för brusigt för att säga något


def normalize_weekly_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Normaliserar en flerkolumns pris-/score-panel till en GEMENSAM
    måndagsankrad veckokalender, per kolumn, med ffill för veckor
    resamplingen inte träffar en exakt kursdag.

    BUGG (fixad, verkligt fall: backtest_theme_satellite.py:s första körning
    rapporterade "33.2 år" för fönstret 2009-2026, dvs dubbelt så många
    rader som kalenderveckor faktiskt fanns). Roten: yfinance:s per-ticker
    veckostaplar kan vara ankrade på olika veckodagar (skiljer sig per
    instrument/handelskalender även inom SAMMA batch-nedladdning) - en rå
    multi-ticker-panel (t.ex. etf_rotation.py:s _panel(), som bara gör
    ffill(limit=1) utan att normalisera till en gemensam kalender) får då
    ~dubbelt så många rader som verkliga veckor, med olika tickers värden
    utspridda på nästan-dubblerade datum. Det förstör INTE bara vecko-/
    år-räkningen (kosmetiskt) utan även rel_mom:s .shift(w)-fönster: en
    "52-veckors" lookback blir bara ~26 KALENDERveckor om indexet är
    dubblerat - en tyst, allvarlig snedvridning av själva momentum-måttet,
    inte bara rapporteringen av det. Samma fix som simulate_accumulation()
    redan använder via denna funktion - kör den på VARJE panel innan
    momentum/NAV beräknas på den."""
    cols = {}
    for t in panel.columns:
        s = panel[t].dropna()
        if s.empty:
            continue
        cols[t] = s.sort_index().resample("W-MON").last().ffill()
    return pd.DataFrame(cols).sort_index()


def _weekly_closes(weights: Dict[str, float], prices: Dict[str, "pd.DataFrame"]) -> pd.DataFrame:
    """Close-panel för EXAKT tickers i weights, avgränsat till datum där ALLA
    har pris (kortaste seriens inception styr fönstret - transparent i
    resultatet, aldrig dolt/extrapolerat bakåt). Se normalize_weekly_panel()
    för varför måndags-normaliseringen krävs innan join."""
    cols = {}
    for t in weights:
        df = prices.get(t)
        s = None if df is None or "Close" not in df else df["Close"]
        if s is None or s.dropna().empty:
            return pd.DataFrame()
        cols[t] = s
    panel = normalize_weekly_panel(pd.DataFrame(cols))
    return panel.dropna(how="any")


def simulate_accumulation(
    weights: Dict[str, float],
    prices: Dict[str, "pd.DataFrame"],
    monthly_contribution: float = None,
    cost_oneway: float = None,
    start: Optional[str] = None,
) -> Optional[Dict]:
    """
    Simulerar ENDAST köp, aldrig sälj – en fast `monthly_contribution` per
    kalendermånad fördelas proportionellt mot gapet till målvikt
    (max(0, målvikt * totalt_efter - nuvarande_värde)), exakt disciplinen
    next_buy()/_dynamic_fill_split kör i skarpt läge. Slår ALLA målvikter
    redan täckta (inget gap kvar) faller insättningen tillbaka på ren
    målviktsfördelning (samma tiebreaker-princip som _dynamic_fill_split).

    weights: {ticker: målvikt}, bör summera till ~1.0.
    prices: {ticker: DataFrame med 'Close'} i INSTRUMENTENS EGEN valuta.
    Jämförda scenarier i samma körning måste dela valuta (här: EUR,
    Xetra-UCITS) - FX är identisk för alla varianter och behöver därför
    inte modelleras för en RELATIV jämförelse.
    cost_oneway: spread+courtage per köp (None → config.ETF_ROT_COST_ONEWAY,
    samma kostnadsdisciplin som ETF-rotationen).

    Returnerar None om < MIN_WEEKS gemensam historik. Annars:
      nav_stats:  MomentumBacktester._compute_stats på en syntetisk,
                  insättnings-NEUTRAL NAV-serie (start 1.0) - CAGR/Sharpe/
                  Sortino/MaxDD jämförbara scenarier emellan även om de fått
                  olika mycket pengar insatta vid olika tidpunkter.
      end_value:  faktiskt EUR-slutvärde av att verkligen satt in
                  `monthly_contribution` varje månad i just DENNA korg -
                  den praktiska "hur mycket pengar hade jag haft"-siffran.
      total_contributed, gain_over_contributed: slutvärde/insatt - 1.
      start, end, years, weeks: det GEMENSAMMA fönster som faktiskt testades.

    start: valfritt - klipp bort allt FÖRE detta datum (t.ex. för att jämföra
    ett scenario mot ett ANNAT scenarios kortare fönster rakt av, i stället
    för respektive scenarios egna maximala historik - se
    backtest_core_allocation.py:s "MATCHAT FÖNSTER"-sektion).
    """
    monthly_contribution = float(monthly_contribution or getattr(config, "NEXT_BUY_DEFAULT_AMOUNT", 10000))
    cost_oneway = float(cost_oneway if cost_oneway is not None else getattr(config, "ETF_ROT_COST_ONEWAY", 0.0015))
    wsum = sum(weights.values()) or 1.0
    weights = {t: w / wsum for t, w in weights.items()}   # normalisera, ifall vikterna inte redan summerar till 1

    closes = _weekly_closes(weights, prices)
    if start is not None:
        closes = closes[closes.index >= pd.Timestamp(start)]
    if len(closes) < MIN_WEEKS:
        return None

    months = closes.index.to_period("M")
    is_contrib_week = ~months.duplicated()   # första veckan i varje kalendermånad

    units = {t: 0.0 for t in weights}
    nav = 1.0
    prev_value: Optional[float] = None
    nav_series, value_series, dates = [], [], []
    total_contributed = 0.0

    for i, date in enumerate(closes.index):
        px = closes.loc[date]
        value_before = sum(units[t] * px[t] for t in weights)

        if prev_value is not None and prev_value > 0:
            nav *= (1.0 + (value_before / prev_value - 1.0))
        # (första veckan: nav stannar på 1.0 - inget bas-värde att räkna avkastning mot ännu)

        if is_contrib_week[i]:
            total_after = value_before + monthly_contribution
            gaps = {t: max(0.0, weights[t] * total_after - units[t] * px[t]) for t in weights}
            gsum = sum(gaps.values())
            if gsum <= 0:   # inget innehav underviktat → målvikten styr (tiebreaker)
                alloc = {t: weights[t] * monthly_contribution for t in weights}
            else:
                alloc = {t: monthly_contribution * gaps[t] / gsum for t in weights}
            for t in weights:
                if px[t] > 0:
                    units[t] += (alloc[t] * (1.0 - cost_oneway)) / px[t]
            total_contributed += monthly_contribution
            value_after = sum(units[t] * px[t] for t in weights)   # inkl. kostnadsdraget ovan
        else:
            value_after = value_before

        prev_value = value_after
        nav_series.append(nav)
        value_series.append(value_after)
        dates.append(date)

    nav_s = pd.Series(nav_series, index=pd.DatetimeIndex(dates))
    nav_stats = MomentumBacktester._compute_stats(nav_s, 1.0)
    end_value = value_series[-1]

    return {
        "nav_stats": nav_stats,
        "end_value": round(end_value, 0),
        "total_contributed": round(total_contributed, 0),
        "gain_over_contributed": round(end_value / total_contributed - 1.0, 4) if total_contributed > 0 else None,
        "start": dates[0].strftime("%Y-%m-%d"),
        "end": dates[-1].strftime("%Y-%m-%d"),
        "weeks": len(dates),
        "years": round(len(dates) / 52, 1),
    }


def simulate_rotating_accumulation(
    universe: list,
    rel: "pd.DataFrame",
    prices: "pd.DataFrame",
    monthly_contribution: float = None,
    cost_oneway: float = None,
    risk_on: Optional["pd.Series"] = None,
    fallback_ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    take_profit_gain: Optional[float] = None,
) -> Optional[Dict]:
    """
    next_buy()s FAKTISKA tema-satellit-mekanik: varje kontributionsmånad,
    plocka den KAUSALT högst rankade tickern i `universe` enligt `rel` just
    DEN dagen (ingen framtidsdata - `rel` måste redan vara beräknad
    point-in-time, t.ex. via etf_rotation.py:s _scores()), lägg HELA
    insättningen där. Säljer ALDRIG en tidigare köpt position (utöver ev.
    take_profit_gain nedan) även om den tappar rank senare - portföljen
    ackumulerar över åren vilka "månadens vinnare" än råkade vara, exakt
    vad next_buy()/_candidates() gör (theme_pick = topp-1 varje gång,
    ingen ombalansering).

    Detta är MEDVETET en annan strategi än etf_rotation.py:s backtest()
    (som SÄLJER/roterar bort positioner som faller ur topp-K var 4:e
    vecka) - den senare är redan testad och dömd "slog aldrig index
    netto" i next_buy()s egen kärn-motivering, men det är en annan
    mekanik än den next_buy() FAKTISKT kör för tema-satelliten. Den här
    funktionen testar den verkliga mekaniken, inte en närliggande.

    risk_on: valfri kausal bool-serie (SAMMA index som rel/prices) - False
    en given vecka → hela insättningen går till `fallback_ticker` i stället
    (mirrorar next_buy()s "risk-off → kronorna går till kärnan"). None =
    ingen regim-gate (temat får alltid pengar).
    fallback_ticker: måste finnas i `prices` om risk_on används, eller om
    `universe` saknar en giltig kandidat en given månad.

    take_profit_gain: valfri tröskel (t.ex. 0.90 = +90%) - samma disciplin
    som appens EGNA säljvakt (config.TAKEPROFIT_GAIN, default 0.50), fast
    utan dess eskaleringsstege (bevaka → ta hem vinsten → sälj) - en enkel
    platt tröskel. Kollas VARJE vecka (inte bara kontributionsmånader) mot
    en viktad SNITTKOSTNAD per ticker (flera köp av samma tema över åren,
    olika pris varje gång, ger en genomsnittlig anskaffningskostnad - inte
    bara senaste priset). Passerar en hållen tema-position tröskeln säljs
    HELA positionen (kostnad_oneway på säljbenet också) och behållningen
    läggs i en väntande kontantpott - INTE direkt till `fallback_ticker`.
    Ett sålt innehav är bara friställt kapital: det slussas in i SAMMA "var
    ska nästa krona in"-beslut som nästa månads vanliga insättning (kan gå
    tillbaka till ett tema om rotationen fortfarande gynnar ett, inte en
    särbehandlad genväg rakt till kärnan). Väntande kontanter räknas in i
    portföljvärdet (och drar därmed ner NAV-avkastningen medan de väntar,
    precis som verklig oinvesterad kassa gör) men räknas ALDRIG in i
    `total_contributed` igen - det är återinvesterat kapital, inte ny
    insättning. Kärnan själv omfattas ALDRIG av säljregeln - appen har
    ingen säljregel för den breda kärnan någonstans, bara för satelliter.
    None = ingen säljregel alls (gamla beteendet, ren köp-och-behåll).

    start/end: valfritt - klipper fönstret (start inklusive, end inklusive).
    Används för in-sample/OOS-svep (se backtest_theme_satellite.py:s
    sweep-läge) - samma disciplin som etf_rotation.py:s egen sweep().

    Returnerar samma struktur som simulate_accumulation(), plus `picks`
    ({ticker: antal månader den vann insättningen}, visar KONCENTRATIONEN)
    och `take_profits` ({ticker: antal gånger den träffade tröskeln}) om
    take_profit_gain angavs.
    """
    monthly_contribution = float(monthly_contribution or getattr(config, "NEXT_BUY_DEFAULT_AMOUNT", 10000))
    cost_oneway = float(cost_oneway if cost_oneway is not None else getattr(config, "ETF_ROT_COST_ONEWAY", 0.0015))

    cols = [t for t in universe if t in prices.columns]
    if fallback_ticker and fallback_ticker not in cols and fallback_ticker in prices.columns:
        cols = cols + [fallback_ticker]
    idx = rel.index.intersection(prices.index)
    if risk_on is not None:
        idx = idx.intersection(risk_on.index)
    idx = idx.sort_values()
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start)]
    if end is not None:
        idx = idx[idx <= pd.Timestamp(end)]
    if len(idx) < MIN_WEEKS:
        return None

    months = idx.to_period("M")
    is_contrib_week = ~months.duplicated()

    units: Dict[str, float] = {}
    cost_basis: Dict[str, float] = {}   # viktad snittkostnad/andel, BARA för icke-fallback-tickers
    pending_cash = 0.0   # sålt kapital som väntar på NÄSTA kontributionsbeslut (se take-profit nedan)
    nav = 1.0
    prev_value: Optional[float] = None
    nav_series, value_series, dates = [], [], []
    total_contributed = 0.0
    picks: Dict[str, int] = {}
    take_profits: Dict[str, int] = {}

    def _px(date, t):
        v = prices.at[date, t] if t in prices.columns else None
        return float(v) if v is not None and pd.notna(v) and v > 0 else None

    def _buy(t, kr, date):
        p = _px(date, t)
        if p is None or kr <= 0:
            return
        new_units = (kr * (1.0 - cost_oneway)) / p
        prev_units = units.get(t, 0.0)
        if t != fallback_ticker and take_profit_gain is not None:
            prev_kr = cost_basis.get(t, p) * prev_units
            total_units = prev_units + new_units
            cost_basis[t] = (prev_kr + kr * (1.0 - cost_oneway)) / total_units if total_units > 0 else None
        units[t] = prev_units + new_units

    for i, date in enumerate(idx):
        # TAKE-PROFIT: kollas VARJE vecka, innan resten av veckans logik - en
        # position kan passera tröskeln vilken vecka som helst, inte bara
        # kontributionsmånader. Behållningen läggs i `pending_cash` - INTE
        # direkt till kärnan. Ett sålt innehav är bara friställt kapital;
        # det slussas in i SAMMA "var ska nästa krona in"-beslut som den
        # vanliga insättningen nästa kontributionsvecka (kan alltså gå
        # tillbaka till ett tema om rotationen fortfarande gynnar ett, inte
        # en särbehandlad genväg rakt till kärnan).
        if take_profit_gain is not None:
            for t in [t for t, u in units.items() if t != fallback_ticker and u > 0]:
                p, cb = _px(date, t), cost_basis.get(t)
                if p is None or not cb or cb <= 0:
                    continue
                if p / cb - 1.0 >= take_profit_gain:
                    pending_cash += units[t] * p * (1.0 - cost_oneway)
                    units[t] = 0.0
                    cost_basis.pop(t, None)
                    take_profits[t] = take_profits.get(t, 0) + 1

        value_before = sum(u * (_px(date, t) or 0.0) for t, u in units.items()) + pending_cash

        if prev_value is not None and prev_value > 0:
            nav *= (1.0 + (value_before / prev_value - 1.0))

        if is_contrib_week[i]:
            invest_amount = monthly_contribution + pending_cash
            pending_cash = 0.0
            target = None
            if risk_on is None or bool(risk_on.loc[date]):
                cand = rel.loc[date, [t for t in universe if t in rel.columns]].dropna()
                if not cand.empty:
                    top = cand.sort_values(ascending=False).index[0]
                    if _px(date, top) is not None:
                        target = top
            if target is None:
                target = fallback_ticker
            if target and _px(date, target) is not None:
                _buy(target, invest_amount, date)
                picks[target] = picks.get(target, 0) + 1
            else:
                pending_cash += invest_amount   # ingen giltig target denna vecka - vänta till nästa
            total_contributed += monthly_contribution   # BARA ny insättning, inte återinvesterat sålt kapital
            value_after = sum(u * (_px(date, t) or 0.0) for t, u in units.items()) + pending_cash
        else:
            value_after = value_before

        prev_value = value_after
        nav_series.append(nav)
        value_series.append(value_after)
        dates.append(date)

    nav_s = pd.Series(nav_series, index=pd.DatetimeIndex(dates))
    nav_stats = MomentumBacktester._compute_stats(nav_s, 1.0)
    end_value = value_series[-1]

    return {
        "nav_stats": nav_stats,
        "end_value": round(end_value, 0),
        "total_contributed": round(total_contributed, 0),
        "gain_over_contributed": round(end_value / total_contributed - 1.0, 4) if total_contributed > 0 else None,
        "start": dates[0].strftime("%Y-%m-%d"),
        "end": dates[-1].strftime("%Y-%m-%d"),
        "weeks": len(dates),
        "years": round(len(dates) / 52, 1),
        "picks": dict(sorted(picks.items(), key=lambda kv: -kv[1])),
        "take_profits": dict(sorted(take_profits.items(), key=lambda kv: -kv[1])),
    }


def simulate_regime_hedge_accumulation(
    core_ticker: str,
    prices: "pd.DataFrame",
    regime: "pd.Series",
    hedge_ticker: Optional[str] = None,
    monthly_contribution: float = None,
    cost_oneway: float = None,
    start: Optional[str] = None,
) -> Optional[Dict]:
    """
    Testar: i BEAR-regim (backtest.regime.classify_regimes - SAMMA klassificerare
    backtestern redan använder för _market_exposure_factor), ska nytt kapital
    parkeras i KONTANTER (dagens beteende, hedge_ticker=None) eller aktivt i en
    invers Bear-ETF (hedge_ticker="XACT-BEAR.ST" e.dyl.)? SÄLJER HELA
    hedge-positionen ("sell out") samma VECKA regimen lämnar bear - proceeds
    rullar direkt in i `core_ticker`, aldrig en kvardröjande satsning.

    hedge_ticker=None: bear-veckors insättning läggs i en väntande kontantpott
    (0% avkastning, exakt vad next_buy()/MARKET_FILTER_EXPOSURE faktiskt gör
    idag) - släpps in i kärnan samma vecka regimen lämnar bear. Detta är
    JÄMFÖRELSE-BASLINJEN, inte en gissning på vad "dagens beteende" gör.

    VARNING (se data/data_loader.py:load_sweden_universe-docstring och
    etf_rotation.py:leverage()): dagligt ombalanserade Bear/Bull-produkter har
    volatilitetsdecay i skakiga perioder - drabbar en -1x Bear-position också,
    inte bara hävstångsprodukter. Den här funktionen mäter NETTOEFFEKTEN
    (regimens faktiska varaktighet minus decay) på riktig data, gissar inte.

    regime: kausal serie (pd.Series av 'bull'/'bear'/'sideways', SAMMA index
    som prices) från backtest.regime.classify_regimes().
    """
    monthly_contribution = float(monthly_contribution or getattr(config, "NEXT_BUY_DEFAULT_AMOUNT", 10000))
    cost_oneway = float(cost_oneway if cost_oneway is not None else getattr(config, "ETF_ROT_COST_ONEWAY", 0.0015))

    idx = prices.index.intersection(regime.index)
    idx = idx.sort_values()
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start)]
    if len(idx) < MIN_WEEKS:
        return None

    months = idx.to_period("M")
    is_contrib_week = ~months.duplicated()

    units: Dict[str, float] = {}
    pending_cash = 0.0   # bara använd när hedge_ticker=None (kontant-baslinjen)
    nav = 1.0
    prev_value: Optional[float] = None
    nav_series, value_series, dates = [], [], []
    total_contributed = 0.0
    bear_contrib_months = 0
    sellouts = 0

    def _px(date, t):
        v = prices.at[date, t] if t in prices.columns else None
        return float(v) if v is not None and pd.notna(v) and v > 0 else None

    def _buy_core(date, kr):
        p = _px(date, core_ticker)
        if p is not None and kr > 0:
            units[core_ticker] = units.get(core_ticker, 0.0) + (kr * (1.0 - cost_oneway)) / p

    prev_regime = None
    for i, date in enumerate(idx):
        cur_regime = regime.loc[date] if date in regime.index else prev_regime

        # SELL OUT: regimen lämnade just bear -> lös upp hedge-positionen ELLER
        # den väntande kontantpotten samma vecka, in i kärnan. Väntar INTE till
        # nästa kontributionsvecka - "sell out i marknadsförändring" ska hända
        # direkt när regimen faktiskt vänder.
        if prev_regime == "bear" and cur_regime != "bear":
            if hedge_ticker and units.get(hedge_ticker, 0.0) > 0:
                p = _px(date, hedge_ticker)
                if p is not None:
                    proceeds = units[hedge_ticker] * p * (1.0 - cost_oneway)
                    units[hedge_ticker] = 0.0
                    _buy_core(date, proceeds)
                    sellouts += 1
            elif pending_cash > 0:
                _buy_core(date, pending_cash)
                pending_cash = 0.0
                sellouts += 1

        value_before = sum(u * (_px(date, t) or 0.0) for t, u in units.items()) + pending_cash
        if prev_value is not None and prev_value > 0:
            nav *= (1.0 + (value_before / prev_value - 1.0))

        if is_contrib_week[i]:
            if cur_regime == "bear":
                bear_contrib_months += 1
                if hedge_ticker:
                    p = _px(date, hedge_ticker)
                    if p is not None:
                        units[hedge_ticker] = units.get(hedge_ticker, 0.0) + \
                            (monthly_contribution * (1.0 - cost_oneway)) / p
                    else:
                        pending_cash += monthly_contribution   # hedge saknar pris denna vecka -> kontanter
                else:
                    pending_cash += monthly_contribution
            else:
                _buy_core(date, monthly_contribution)
            total_contributed += monthly_contribution
            value_after = sum(u * (_px(date, t) or 0.0) for t, u in units.items()) + pending_cash
        else:
            value_after = value_before

        prev_value = value_after
        prev_regime = cur_regime
        nav_series.append(nav)
        value_series.append(value_after)
        dates.append(date)

    nav_s = pd.Series(nav_series, index=pd.DatetimeIndex(dates))
    nav_stats = MomentumBacktester._compute_stats(nav_s, 1.0)
    end_value = value_series[-1]

    return {
        "nav_stats": nav_stats,
        "end_value": round(end_value, 0),
        "total_contributed": round(total_contributed, 0),
        "gain_over_contributed": round(end_value / total_contributed - 1.0, 4) if total_contributed > 0 else None,
        "start": dates[0].strftime("%Y-%m-%d"),
        "end": dates[-1].strftime("%Y-%m-%d"),
        "weeks": len(dates),
        "years": round(len(dates) / 52, 1),
        "bear_contrib_months": bear_contrib_months,
        "sellouts": sellouts,
    }
