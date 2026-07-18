"""
backtest_bull_hedge.py – SPEGELVÄND fråga mot backtest_bear_hedge.py: är en
Bull-ETF (hävstångad, dagligt ombalanserad) ett bättre ställe för NYTT KAPITAL
under en klassificerad tjurmarknad än dagens beteende (köp kärnan direkt), med
"sell out" (deleverage in i kärnan) samma vecka regimen vänder?

Bakgrund: användaren pekade på verklig Avanza-data (XACT Bull 2 +1214% "Max"
mot ett mycket lägre jämförelseindex) som stöd för att hävstång SLÅR index
över tid - en riktig iakttagelse, men den gäller EN LÅNG, RELATIVT JÄMN
uppgångsperiod (låg realiserad volatilitet, mest samma riktning dag efter
dag). Volatilitetsdecay (se backtest_bear_hedge.py:s docstring och
data/data_loader.py) är en funktion av VOLATILITET/CHOP, inte av riktning -
i en jämn trend kan daglig ombalansering tvärtom GYNNA en hävstångad
position (compoundingen jobbar för dig). Bear-testet mätte specifikt de
CHOPPIGASTE veckorna (bear-klassade, hög volatilitet) - fel miljö för att
döma hävstång i allmänhet. Det här testet isolerar i stället just BULL-
klassade veckor (per backtest.regime.classify_regimes, samma klassificerare
som redan används i produktion) och mäter om hävstången faktiskt betalar
sig DÄR, i stället för att anta det åt endera hållet.

Byggd på samma motor som Bear-testet (backtest/accumulation.py:
simulate_regime_hedge_accumulation, nu generaliserad med target_regime=
"bull", baseline_is_cash=False - "dagens beteende" i bull är redan att köpa
kärnan direkt, ingen kontantparkering att jämföra mot). INTE inbakad i
backtest/backtester.py än - nästa steg om det här visar en robust fördel.

Kräver nätåtkomst till Yahoo Finance - körs på Pi:n:

    python backtest_bull_hedge.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pandas as pd  # noqa: E402
import config  # noqa: E402
from data.data_loader import fetch_weekly_data  # noqa: E402
from backtest.regime import classify_regimes  # noqa: E402
from backtest.accumulation import normalize_weekly_panel, simulate_regime_hedge_accumulation  # noqa: E402

CORE_TICKER, CORE_NAME = getattr(config, "PORTFOLIO_CORE_ETF", ("IUSQ.DE", "iShares MSCI ACWI"))
# Samma marknadsproxy/klassificerare som backtest_bear_hedge.py - för
# jämförbarhet mellan de två testerna (samma regimserie, bara spegelvänt
# vilken etikett som triggar overlayen).
MARKET_PROXY_TICKER = "XACT-SVERIGE.ST"
# Tickers verifierade via WebSearch mot Handelsbankens faktablad (gissar
# inte hävstångsgrad): XACT Bull = +1,5x OMXS30, XACT Bull 2 = +2x OMXS30,
# båda dagligen ombalanserade.
HEDGE_VARIANTS = [
    ("XACT-BULL.ST",   "XACT Bull (+1,5x OMXS30, dagligen ombalanserad)"),
    ("XACT-BULL-2.ST", "XACT Bull 2 (+2x OMXS30, dagligen ombalanserad)"),
]


def _fmt_pct(x):
    return f"{x:+.1%}" if x is not None else "  n/a"


def _diagnose_tickers(panel):
    """Per-ticker giltigt datumintervall - se backtest_bear_hedge.py:s
    motsvarighet för varför det här visas (förklarar fönstrets gränser)."""
    print("\n[diagnos] per-ticker giltigt intervall:")
    for t in panel.columns:
        c = panel[t].dropna()
        if c.empty:
            print(f"    {t:<16} INGEN giltig prisdata")
            continue
        print(f"    {t:<16} {c.index.min().date()} → {c.index.max().date()} ({len(c)} veckor)")


def _print_result(label, r, regime_word="bull"):
    s = r["nav_stats"]
    print(f"  {label}")
    print(f"    fönster {r['start']} → {r['end']} ({r['years']} år) · "
          f"NAV-CAGR {s['CAGR']} · Sharpe {s['Sharpe']} · MaxDD {s['Max Drawdown']} · "
          f"slutvärde {r['end_value']:,.0f} av {r['total_contributed']:,.0f} insatt "
          f"({_fmt_pct(r['gain_over_contributed'])})".replace(",", " "))
    print(f"    {regime_word}-månader (nytt kapital dit): {r['target_contrib_months']} · "
          f"sell-out-händelser: {r['sellouts']}")


def main():
    hedge_tickers = [t for t, _ in HEDGE_VARIANTS]
    tickers = [CORE_TICKER, MARKET_PROXY_TICKER] + hedge_tickers
    print(f"[backtest_bull_hedge] hämtar veckodata för: {', '.join(tickers)}")
    prices = fetch_weekly_data(tickers, start="2005-01-01", end=None, use_cache=True)
    missing = [t for t in tickers if t not in prices]
    if missing:
        print(f"[backtest_bull_hedge] ingen prisdata för: {', '.join(missing)} - kan inte köra.")
        return

    panel = normalize_weekly_panel(pd.DataFrame({t: prices[t]["Close"] for t in tickers}))
    if CORE_TICKER not in panel.columns:
        print("[backtest_bull_hedge] kärna saknas efter normalisering - kan inte köra.")
        return
    _diagnose_tickers(panel)

    # Se backtest_bear_hedge.py för varför regimen MÅSTE byggas på den redan
    # normaliserade panelen (veckodags-anknytningsbugg annars - accumulation.py).
    proxy_df = {MARKET_PROXY_TICKER: panel[[MARKET_PROXY_TICKER]].rename(columns={MARKET_PROXY_TICKER: "Close"})}
    regime = classify_regimes(proxy_df)
    regime = regime.reindex(panel.index).ffill().dropna()
    if len(regime) == 0:
        print("[backtest_bull_hedge] regimserien blev tom efter normalisering - kan inte köra.")
        return
    n_bull = int((regime == "bull").sum())
    print(f"[backtest_bull_hedge] regimklassificering ({MARKET_PROXY_TICKER}, {config.REGIME_SMA_WEEKS}v SMA): "
          f"{n_bull} veckor klassade som bull av {len(regime)} totalt "
          f"({n_bull / len(regime):.0%}).")

    variants = [(None, "Kärnan direkt under bull (dagens beteende)")] + \
               [(t, f"{name} under bull") for t, name in HEDGE_VARIANTS if t in panel.columns]
    skipped = [name for t, name in HEDGE_VARIANTS if t not in panel.columns]
    if skipped:
        print(f"[backtest_bull_hedge] hoppar över (saknar prisdata efter normalisering): {', '.join(skipped)}")

    results_own = {}
    for hedge_ticker, label in variants:
        r = simulate_regime_hedge_accumulation(CORE_TICKER, panel, regime, hedge_ticker=hedge_ticker,
                                                target_regime="bull", baseline_is_cash=False)
        if r is None:
            print(f"[backtest_bull_hedge] {label}: < 3 år gemensam historik - kan inte testa.")
            continue
        results_own[hedge_ticker] = (label, r)
    if len(results_own) < 2:   # baslinjen + minst en hedge-variant krävs för jämförelse
        print("[backtest_bull_hedge] för få jämförbara varianter - avbryter.")
        return

    print("\n  EGET FÖNSTER (respektive variants maximala tillgängliga historik):\n")
    for hedge_ticker, (label, r) in results_own.items():
        _print_result(label, r)

    matched_start = max(r["start"] for _, r in results_own.values())
    results_matched = {}
    for hedge_ticker, (label, _) in results_own.items():
        r = simulate_regime_hedge_accumulation(CORE_TICKER, panel, regime, hedge_ticker=hedge_ticker,
                                                target_regime="bull", baseline_is_cash=False, start=matched_start)
        if r is None:
            print(f"\n[backtest_bull_hedge] {label}: för kort efter klippning till {matched_start}.")
            continue
        results_matched[hedge_ticker] = (label, r)
    if len(results_matched) < 2:
        print("[backtest_bull_hedge] för få varianter kvar efter fönster-matchning - avbryter.")
        return

    any_r = next(iter(results_matched.values()))[1]
    print(f"\n  MATCHAT FÖNSTER: {any_r['start']} → {any_r['end']} ({any_r['years']} år)\n")
    for hedge_ticker, (label, r) in results_matched.items():
        _print_result(label, r)

    print("\n(NAV-CAGR/Sharpe/MaxDD är insättnings-neutrala. Skillnaden mellan raderna "
          "ISOLERAR bull-hedgens effekt - allt annat (kärnans egna köp under bear/sidledes, "
          "kostnader) är identiskt mellan varianterna. Till skillnad från Bear-testet är "
          "BASLINJEN här inte kontanter (det finns ingen kontantparkering att jämföra mot i "
          "bull - dagens beteende är redan full exponering) utan att köpa kärnan direkt - "
          "hedge-varianterna vinner alltså bara om hävstångscompoundingen under just de "
          "BULL-klassade veckorna slår kärnans egen avkastning där, netto efter decay. OBS: "
          "klassificeringen (backtest.regime.classify_regimes) är EN metod bland flera "
          "möjliga - en snävare/bredare SMA hade gett andra bull-fönster. Det här mäter den "
          "befintliga, redan i produktion använda klassificeraren, inte ett optimerat facit.)")


if __name__ == "__main__":
    main()
