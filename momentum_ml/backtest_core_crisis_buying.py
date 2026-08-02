"""
backtest_core_crisis_buying.py – uppföljning på backtest_core_dip_timing.py
(#21, förkastat: 1-5%-dippar mot FÖRRA insättningsdagens pris gav ingen edge).
Frågan som restes efteråt, i tre delar:

  1. "Hur STOR ska dippen vara?" - #21 testade bara 1-5% (en enskild månads
     brus). Måste rimligen vara en annan sak att köpa tungt vid en RIKTIG
     krasch (-20%+ från toppen) - testat här mot lång historik, inte bara
     16 år EUNL.DE.
  2. "Funkar det brett index, inte bara värdepapper?" - testat på TVÅ breda,
     långa index (S&P 500 sedan 1927, MSCI World Total Return sedan 1972),
     inte bara den enskilda ETF:en portföljen faktiskt äger.
  3. "Vänta med köp i en kraftig björnmarknad?" - en ANNAN fråga än #21
     (som testade "vänta på en liten nedgång inom EN månad"). Det här är
     "pausa/parkera helt under en KLASSIFICERAD björnregim, släpp in när
     den vänder" - redan byggd maskin (backtest/regime.py:classify_regimes +
     backtest/accumulation.py:simulate_regime_hedge_accumulation, se
     backtest_bear_hedge.py) men ALDRIG körd mot den passiva kärnan (bara
     mot frågan "hedge:a AKTIVT med en invers ETF i bear" - en annan,
     smalare fråga). Körs här mot en ren "köp alltid"-baslinje.

DEL 1+2 (krisdjup): egen analys, kräver INTE köp-och-behåll-simulatorn -
mäter i stället framåtavkastning (1/3/5/10 år) efter att index passerat en
viss nedgångströskel, mot en obetingad baslinje (alla dagar). Långa serier
ger statistisk kraft #21 saknade (n=198 där; här upp till tusentals
händelser för grunda trösklar, färre men fortfarande flera för -30/-40%).

DEL 3 (björnpaus): återanvänder simulate_regime_hedge_accumulation som
ALDRIG körts med hedge_ticker=None mot en ren alltid-köp-baslinje för just
kärnan (bara mot invers-ETF-hedgen tidigare, se backtest_bear_hedge.py).

Kräver nätåtkomst till Yahoo Finance - körs på Pi:n:

    python backtest_core_crisis_buying.py
"""
import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from data.data_loader import fetch_weekly_data  # noqa: E402
from backtest.regime import classify_regimes  # noqa: E402
from backtest.accumulation import (  # noqa: E402
    normalize_weekly_panel, simulate_accumulation, simulate_regime_hedge_accumulation,
)

LONG_SERIES = {
    "^GSPC": ("S&P 500 (USA, sedan 1927)", "1927-01-01"),
    "^990100-USD-STRD": ("MSCI World Total Return (bred, sedan 1972)", "1972-01-01"),
}
DRAWDOWN_THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
HORIZONS_TRADING_DAYS = {"1 år": 252, "3 år": 756, "5 år": 1260, "10 år": 2520}
CACHE_DIR = Path(__file__).parent / "cache"


def fetch_daily(ticker: str, start: str) -> pd.Series:
    cp = CACHE_DIR / f"crisis_daily_{ticker.replace('^', '').replace('.', '_').replace('-', '_')}.pkl"
    if cp.exists():
        return pickle.loads(cp.read_bytes())
    import yfinance as yf
    print(f"[yfinance] Hämtar daglig data för {ticker} sedan {start} ...")
    df = yf.download(ticker, start=start, interval="1d", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"][ticker].dropna()
    else:
        close = df["Close"].dropna()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(pickle.dumps(close))
    return close


def drawdown_events(close: pd.Series, threshold: float) -> list:
    """Dagar där nedgången från ATH (expanding max) FÖRST passerar -threshold
    - en "cooldown" (måste ha återhämtat sig till -threshold/2 sedan senaste
    händelsen) förhindrar att SAMMA krasch räknas dussintals gånger bara för
    att den ligger kvar djupt i flera månader."""
    ath = close.cummax()
    dd = close / ath - 1.0
    events = []
    armed = True
    for i in range(len(dd)):
        d = dd.iloc[i]
        if armed and d <= -threshold:
            events.append(i)
            armed = False
        elif not armed and d >= -threshold / 2:
            armed = True
    return events


def forward_returns(close: pd.Series, positions: list, horizon_days: int) -> np.ndarray:
    vals = close.values
    out = []
    for p in positions:
        j = p + horizon_days
        if j < len(vals):
            out.append(vals[j] / vals[p] - 1.0)
    return np.array(out)


def analyze_drawdown_depth(label: str, close: pd.Series) -> None:
    print(f"\n===== {label}: framåtavkastning efter olika krisdjup =====")
    print(f"  fönster {close.index[0].date()} → {close.index[-1].date()} ({len(close)} dagar)\n")

    # Baslinje: framåtavkastning från VARJE handelsdag (obetingad - "köpte du
    # en helt slumpmässig dag"), samma horisonter.
    all_positions = list(range(len(close)))
    baseline = {h: forward_returns(close, all_positions, d) for h, d in HORIZONS_TRADING_DAYS.items()}

    header = f"  {'tröskel':>8} {'n':>5}" + "".join(f" {h:>16}" for h in HORIZONS_TRADING_DAYS)
    print(header)
    for t in DRAWDOWN_THRESHOLDS:
        ev = drawdown_events(close, t)
        if len(ev) < 2:
            print(f"  {t:>7.0%} {len(ev):>5}  (för få händelser - hoppar)")
            continue
        row = f"  {t:>7.0%} {len(ev):>5}"
        for h, d in HORIZONS_TRADING_DAYS.items():
            r = forward_returns(close, ev, d)
            if len(r) == 0:
                row += f" {'(ingen data)':>16}"
            else:
                row += f" {np.median(r):>+15.1%}"
        print(row)
    base_row = f"  {'(alla dagar)':>8} {len(close):>5}"
    for h in HORIZONS_TRADING_DAYS:
        base_row += f" {np.median(baseline[h]):>+15.1%}"
    print(base_row)
    print("  (median framåtavkastning per horisont, från händelsedagen resp. från EN slumpmässig dag)")


def bear_pause_vs_always_buy() -> None:
    """DEL 3: pausa nya köp helt under en klassificerad björnregim (kärnans
    kapital parkeras i kontanter, släpps in samma vecka regimen vänder) vs.
    köpa rakt igenom oavsett regim - ALDRIG testat mot just den baslinjen
    tidigare (backtest_bear_hedge.py testade bara "kontanter vs. invers ETF
    UNDER bear", inte "kontanter i bear vs. alltid investerad")."""
    print("\n===== DEL 3: pausa köp i klassificerad björnregim vs. köp alltid (kärnan) =====")
    core_ticker, core_name = config.PORTFOLIO_CORE_ETF
    proxy_ticker = "XACT-SVERIGE.ST"
    tickers = [core_ticker, proxy_ticker]
    prices = fetch_weekly_data(tickers, start="2005-01-01", end=None, use_cache=True)
    missing = [t for t in tickers if t not in prices]
    if missing:
        print(f"  HOPPAD (saknar prisdata för: {', '.join(missing)})")
        return

    panel = normalize_weekly_panel(pd.DataFrame({t: prices[t]["Close"] for t in tickers}))
    if core_ticker not in panel.columns:
        print("  HOPPAD (kärnan saknas efter normalisering)")
        return

    proxy_df = {proxy_ticker: panel[[proxy_ticker]].rename(columns={proxy_ticker: "Close"})}
    regime = classify_regimes(proxy_df)
    regime = regime.reindex(panel.index).ffill().dropna()
    n_bear = int((regime == "bear").sum())
    print(f"  Regimklassificering ({proxy_ticker}, {config.REGIME_SMA_WEEKS}v SMA): "
          f"{n_bear} veckor bear av {len(regime)} ({n_bear / len(regime):.0%}).\n")

    r_pause = simulate_regime_hedge_accumulation(core_ticker, panel, regime, hedge_ticker=None,
                                                  target_regime="bear", baseline_is_cash=True)
    r_always = simulate_accumulation({core_ticker: 1.0}, prices, start=r_pause["start"] if r_pause else None)

    def _fmt_pct(x):
        return f"{x:+.1%}" if x is not None else "  n/a"

    for label, r in [("Pausa köp i björnregim (parkera kontant, släpp in vid vändning)", r_pause),
                      ("Köp alltid (ingen regimhänsyn - dagens next_buy())", r_always)]:
        if r is None:
            print(f"  {label:<70} HOPPAD (för kort historik)")
            continue
        s = r["nav_stats"]
        extra = f" · björn-månader: {r['target_contrib_months']} · sell-outs: {r['sellouts']}" \
            if "target_contrib_months" in r else ""
        print(f"  {label}")
        print(f"    fönster {r['start']} → {r['end']} ({r['years']} år) · NAV-CAGR {s['CAGR']} · "
              f"Sharpe {s['Sharpe']} · MaxDD {s['Max Drawdown']} · slutvärde {r['end_value']:,.0f} av "
              f"{r['total_contributed']:,.0f} insatt ({_fmt_pct(r['gain_over_contributed'])}){extra}"
              .replace(",", " "))


def main():
    for ticker, (label, start) in LONG_SERIES.items():
        close = fetch_daily(ticker, start)
        analyze_drawdown_depth(label, close)

    print("\n[EUNL.DE] (den faktiska instrumentet portföljen äger - kort historik, cross-check)")
    eunl = fetch_daily("EUNL.DE", "2010-01-01")
    analyze_drawdown_depth("EUNL.DE (iShares Core MSCI World, sedan 2010)", eunl)

    bear_pause_vs_always_buy()

    print("\n(Alla trösklar mäter samma sak: 'är framåtavkastningen bättre om du köper EFTER att\n"
          " index redan fallit X% från toppen, jämfört med en slumpmässig dag?' - inte en\n"
          " handelsstrategi i sig (kräver EN engångssumma redo att investeras, inte en\n"
          " återkommande månadsinsättning som #21). DEL 3 är däremot direkt jämförbar med\n"
          " #21/dagens next_buy() - insättnings-neutral NAV, samma kostnadsmodell.)")


if __name__ == "__main__":
    main()
