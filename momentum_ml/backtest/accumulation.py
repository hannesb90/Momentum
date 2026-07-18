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


def _weekly_closes(weights: Dict[str, float], prices: Dict[str, "pd.DataFrame"]) -> pd.DataFrame:
    """Close-panel för EXAKT tickers i weights, avgränsat till datum där ALLA
    har pris (kortaste seriens inception styr fönstret - transparent i
    resultatet, aldrig dolt/extrapolerat bakåt).

    BUGG (fixad, verkligt fall: EM+Europa/4-vägssplitten gav "<3 år gemensam
    historik" trots att EXSA.DE (2008-2026) och IS3N.DE (2014-2026) VAR för
    sig hade 0 interna luckor). yfinance:s per-ticker veckostaplar kan vara
    ankrade på olika veckodagar (skiljer sig per instrument/handelskalender
    även inom SAMMA batch-nedladdning) - en strikt datum-för-datum-join
    (gamla koden) matchade då nästan ingenting, trots att båda serierna var
    kompletta var för sig. Fixen: normalisera varje serie till en gemensam
    veckokalender (måndagsankrad) FÖRE join, med ffill för veckor där
    resamplingen inte träffar en exakt kursdag - absorberar veckodags-
    skillnaden i stället för att låta den tysta bort nästan hela överlappet."""
    cols = {}
    for t in weights:
        df = prices.get(t)
        s = None if df is None or "Close" not in df else df["Close"].dropna()
        if s is None or s.empty:
            return pd.DataFrame()
        cols[t] = s.sort_index().resample("W-MON").last().ffill()
    panel = pd.DataFrame(cols).sort_index()
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
) -> Optional[Dict]:
    """
    next_buy()s FAKTISKA tema-satellit-mekanik: varje kontributionsmånad,
    plocka den KAUSALT högst rankade tickern i `universe` enligt `rel` just
    DEN dagen (ingen framtidsdata - `rel` måste redan vara beräknad
    point-in-time, t.ex. via etf_rotation.py:s _scores()), lägg HELA
    insättningen där. Säljer ALDRIG en tidigare köpt position även om den
    tappar rank senare - portföljen ackumulerar över åren vilka "månadens
    vinnare" än råkade vara, exakt vad next_buy()/_candidates() gör
    (theme_pick = topp-1 varje gång, ingen ombalansering).

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

    Returnerar samma struktur som simulate_accumulation(), plus `picks`:
    {ticker: antal månader den vann insättningen} - visar KONCENTRATIONEN
    (rider rotationen på några få vinnare, eller sprids den brett?).
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
    if len(idx) < MIN_WEEKS:
        return None

    months = idx.to_period("M")
    is_contrib_week = ~months.duplicated()

    units: Dict[str, float] = {}
    nav = 1.0
    prev_value: Optional[float] = None
    nav_series, value_series, dates = [], [], []
    total_contributed = 0.0
    picks: Dict[str, int] = {}

    def _px(date, t):
        v = prices.at[date, t] if t in prices.columns else None
        return float(v) if v is not None and pd.notna(v) and v > 0 else None

    for i, date in enumerate(idx):
        value_before = sum(u * (_px(date, t) or 0.0) for t, u in units.items())

        if prev_value is not None and prev_value > 0:
            nav *= (1.0 + (value_before / prev_value - 1.0))

        if is_contrib_week[i]:
            target = None
            if risk_on is None or bool(risk_on.loc[date]):
                cand = rel.loc[date, [t for t in universe if t in rel.columns]].dropna()
                if not cand.empty:
                    top = cand.sort_values(ascending=False).index[0]
                    if _px(date, top) is not None:
                        target = top
            if target is None:
                target = fallback_ticker
            p = _px(date, target) if target else None
            if p is not None:
                units[target] = units.get(target, 0.0) + (monthly_contribution * (1.0 - cost_oneway)) / p
                picks[target] = picks.get(target, 0) + 1
            total_contributed += monthly_contribution
            value_after = sum(u * (_px(date, t) or 0.0) for t, u in units.items())
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
    }
