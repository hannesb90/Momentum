"""
backtest_bear_hedge.py – testar om en Bear-ETF (invers, dagligt ombalanserad)
är ett bättre ställe för NYTT KAPITAL under en klassificerad björnmarknad än
dagens beteende (kontanter), med "sell out" samma vecka regimen vänder.

Bakgrund: backtestern (backtest/backtester.py) skalar redan ner exponeringen
mot kontanter i bear (_market_exposure_factor, MARKET_FILTER_EXPOSURE) via
backtest/regime.py:classify_regimes() - en enkel SMA-trend/lutning-klassificerare
på ett likaviktat marknadsproxy. Kontanterna där tjänar 0% tills regimen vänder.
Frågan: skulle en riktig invers ETF (t.ex. XACT-BEAR.ST, -1x OMXS30, dagligen
ombalanserad) göra bättre ifrån sig - AKTIVT tjäna på nedgången i stället för
att bara stå still - eller äts fördelen upp av volatilitetsdecay (samma
mekanik data/data_loader.py redan flaggar för Bull/Bear-produkter generellt:
"daglig ombalansering ger decay över tid")?

Det här är MEDVETET en annan fråga än "long-short för att fånga hela
momentumpremien" (för stort/opraktiskt att bygga in i en ISK-baserad app) -
det här är en avgränsad, regim-gated, tidsbegränsad hedge FÖR NYTT KAPITAL,
med en tydlig exit-regel (sell out vid regimskifte). Byggd som ett fristående
test (backtest/accumulation.py:simulate_regime_hedge_accumulation), INTE
inbakad i backtest/backtester.py än - det är nästa steg om det här visar
en robust fördel.

Kräver nätåtkomst till Yahoo Finance - körs på Pi:n:

    python backtest_bear_hedge.py
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
# Bred svensk marknadsproxy för regimklassificeringen - SAMMA metod (SMA-trend/
# lutning på ett likaviktat index) som backtestern kör på hela Sverige-universumet,
# fast här förenklat till EN bred indexfond (classify_regimes() likaviktar bara
# vad den får in - med en enda ticker blir "likavikten" helt enkelt den fondens
# egen avkastning, ett rimligt förenklat proxy för just den här frågan).
MARKET_PROXY_TICKER = "XACT-SVERIGE.ST"
# (ticker, namn) - körs som separata varianter mot samma kontant-baslinje.
# XACT Bear 2 är den HÄVSTÅNGADE (-2x OMXS30) varianten av samma mekanik -
# dagligt ombalanserad, samma volatilitetsdecay-oro men KVADRERAD (decay
# skalar ~kvadratiskt med hävstången, inte linjärt) - relevant eftersom
# -1x redan förlorade mot kontanter (se körningen som ledde hit).
HEDGE_VARIANTS = [
    ("XACT-BEAR.ST",   "XACT Bear (-1x OMXS30, dagligen ombalanserad)"),
    ("XACT-BEAR-2.ST", "XACT Bear 2 (-2x OMXS30, dagligen ombalanserad)"),
]


def _fmt_pct(x):
    return f"{x:+.1%}" if x is not None else "  n/a"


def _diagnose_tickers(panel):
    """Per-ticker giltigt datumintervall - visar VARFÖR simuleringens fönster
    startar där det gör (se accumulation.py:simulate_regime_hedge_accumulation,
    som klipper bort allt före core_ticker's egen första giltiga notering;
    tidigare kraschade/gav -100% resultat tyst i stället)."""
    print("\n[diagnos] per-ticker giltigt intervall:")
    for t in panel.columns:
        c = panel[t].dropna()
        if c.empty:
            print(f"    {t:<16} INGEN giltig prisdata")
            continue
        print(f"    {t:<16} {c.index.min().date()} → {c.index.max().date()} ({len(c)} veckor)")


def _print_result(label, r, regime_word="bear"):
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
    print(f"[backtest_bear_hedge] hämtar veckodata för: {', '.join(tickers)}")
    prices = fetch_weekly_data(tickers, start="2005-01-01", end=None, use_cache=True)
    missing = [t for t in tickers if t not in prices]
    if missing:
        print(f"[backtest_bear_hedge] ingen prisdata för: {', '.join(missing)} - kan inte köra.")
        return

    panel = normalize_weekly_panel(pd.DataFrame({t: prices[t]["Close"] for t in tickers}))
    if CORE_TICKER not in panel.columns:
        print("[backtest_bear_hedge] kärna saknas efter normalisering - kan inte köra.")
        return
    _diagnose_tickers(panel)

    # Bygg regimklassificeringen på den REDAN NORMALISERADE panelen - inte rå
    # prices[...] direkt. classify_regimes() bygger sin marknadsproxy på det
    # index den får in; matchar det inte panel:s måndagsankrade veckogrid
    # (samma veckodags-anknytningsbugg som normalize_weekly_panel() finns till
    # för att fixa, se backtest/accumulation.py) blir en exakt-datum-reindex
    # mot panel.index tom - precis det som kraschade förra körningen.
    proxy_df = {MARKET_PROXY_TICKER: panel[[MARKET_PROXY_TICKER]].rename(columns={MARKET_PROXY_TICKER: "Close"})}
    regime = classify_regimes(proxy_df)
    regime = regime.reindex(panel.index).ffill().dropna()
    if len(regime) == 0:
        print("[backtest_bear_hedge] regimserien blev tom efter normalisering - kan inte köra.")
        return
    n_bear = int((regime == "bear").sum())
    print(f"[backtest_bear_hedge] regimklassificering ({MARKET_PROXY_TICKER}, {config.REGIME_SMA_WEEKS}v SMA): "
          f"{n_bear} veckor klassade som bear av {len(regime)} totalt "
          f"({n_bear / len(regime):.0%}).")

    variants = [(None, "Kontanter under bear (dagens beteende)")] + \
               [(t, f"{name} under bear") for t, name in HEDGE_VARIANTS if t in panel.columns]
    skipped = [name for t, name in HEDGE_VARIANTS if t not in panel.columns]
    if skipped:
        print(f"[backtest_bear_hedge] hoppar över (saknar prisdata efter normalisering): {', '.join(skipped)}")

    results_own = {}
    for hedge_ticker, label in variants:
        r = simulate_regime_hedge_accumulation(CORE_TICKER, panel, regime, hedge_ticker=hedge_ticker)
        if r is None:
            print(f"[backtest_bear_hedge] {label}: < 3 år gemensam historik - kan inte testa.")
            continue
        results_own[hedge_ticker] = (label, r)
    if len(results_own) < 2:   # kontanter + minst en hedge-variant krävs för jämförelse
        print("[backtest_bear_hedge] för få jämförbara varianter - avbryter.")
        return

    print("\n  EGET FÖNSTER (respektive variants maximala tillgängliga historik):\n")
    for hedge_ticker, (label, r) in results_own.items():
        _print_result(label, r)

    matched_start = max(r["start"] for _, r in results_own.values())
    results_matched = {}
    for hedge_ticker, (label, _) in results_own.items():
        r = simulate_regime_hedge_accumulation(CORE_TICKER, panel, regime, hedge_ticker=hedge_ticker,
                                                start=matched_start)
        if r is None:
            print(f"\n[backtest_bear_hedge] {label}: för kort efter klippning till {matched_start}.")
            continue
        results_matched[hedge_ticker] = (label, r)
    if len(results_matched) < 2:
        print("[backtest_bear_hedge] för få varianter kvar efter fönster-matchning - avbryter.")
        return

    any_r = next(iter(results_matched.values()))[1]
    print(f"\n  MATCHAT FÖNSTER: {any_r['start']} → {any_r['end']} ({any_r['years']} år)\n")
    for hedge_ticker, (label, r) in results_matched.items():
        _print_result(label, r)

    print("\n(NAV-CAGR/Sharpe/MaxDD är insättnings-neutrala. Skillnaden mellan raderna "
          "ISOLERAR bear-hedgens effekt - allt annat (kärnans egna köp under bull/sidledes, "
          "kostnader) är identiskt mellan varianterna. XACT Bear 2 är HÄVSTÅNGAD (-2x) - "
          "samma dagliga ombalanserings-decay som -1x-varianten, men den skalar ungefär "
          "kvadratiskt med hävstången, inte linjärt, så en eventuell förlust mot kontanter "
          "väntas vara STÖRRE här, inte mindre. OBS: klassificeringen "
          "(backtest.regime.classify_regimes) är EN metod bland flera möjliga - en snävare/"
          "bredare SMA hade gett andra bear-fönster. Det här mäter den befintliga, redan i "
          "produktion använda klassificeraren, inte ett optimerat facit.)")


if __name__ == "__main__":
    main()
