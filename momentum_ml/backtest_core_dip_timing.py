"""
backtest_core_dip_timing.py – testar en fråga som ALDRIG testats tidigare:
ska kärnans MÅNADSINSÄTTNING tajmas mot en nedgång i stället för att alltid
köpas rakt av på insättningsdagen (lönedagen, ~25:e varje månad)?

Dagens next_buy()/simulate_accumulation() (se backtest/accumulation.py) köper
ALLTID hela insättningen samma vecka pengarna kommer in - aldrig tajmat mot
kursrörelse. Frågan restes explicit (inte en gissning): "om jag ska stoppa in
10 000 kr i månaden i bred kärna, borde det inte kunna trigga köp efter t.ex.
nedgång 2%? Hold cash på insättningsdagen, annars jämka med nästa insättning."

Två delar testas, båda på DAGLIG upplösning (inte de vecko-staplar resten av
backtestmotorn använder - en enskild veckas rörelse överskrider ofta 2% själv,
så vecko-bars skulle dölja/förvränga exakt den signal som testas här):

  1. DIP-TAJMAD INSÄTTNING vs. schemalagt köp. Från insättningsdagen: håll
     kontant tills priset fallit >= tröskel% från INSÄTTNINGSDAGENS EGET pris
     (referensen "sedan vi fick lönen"), köp DÅ. Ingen nedgång innan NÄSTA
     insättningsdag -> köp ändå, den dagen (jämkas in - väntar aldrig längre
     än en cykel, exakt disciplinen som beskrevs).
  2. PAYDAY-EFFEKT (diagnostik). Finns det systematiskt ANNORLUNDA avkastning
     kring insättningsdagarna (bred marknad, många får lön samtidigt och
     köper samma vecka - jfr "turn-of-the-month"-effekten i akademisk
     litteratur)? Om ja talar det EMOT att vänta - man missar då ett
     flödesdrivet uppsving just de dagarna. Ren deskriptiv statistik, inget
     handelsbeslut byggs på den här delen.

Kärn-instrumentet testas på EUNL.DE (iShares Core MSCI World) ensamt - 88% av
PORTFOLIO_CORE_SPLIT och den dominerande komponenten; att lägga till IS3N.DE
(EM, 12%) skulle bara späda ut samma signal, inte ändra svaret. Kräver
nätåtkomst till Yahoo Finance - körs på Pi:n:

    python backtest_core_dip_timing.py
"""
import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from backtest.backtester import MomentumBacktester  # noqa: E402

TICKER = "EUNL.DE"          # iShares Core MSCI World - se PORTFOLIO_CORE_SPLIT
START = "2010-01-01"
CONTRIB = float(config.NEXT_BUY_DEFAULT_AMOUNT)   # 10 000 - EUR-siffra rakt av, som accumulation.py
COST_ONEWAY = float(config.ETF_ROT_COST_ONEWAY)
THRESHOLDS = [0.01, 0.02, 0.03, 0.05]
PAYDAY_DOM = 25             # svensk lönedag-konvention: 25:e (eller närmast handelsdag efter)

CACHE = Path(__file__).parent / "cache" / f"dip_timing_daily_{TICKER.replace('.', '_')}.pkl"


def fetch_daily(ticker: str, start: str) -> pd.Series:
    if CACHE.exists():
        print(f"[cache] Laddar {CACHE}")
        return pickle.loads(CACHE.read_bytes())
    import yfinance as yf
    print(f"[yfinance] Hämtar daglig data för {ticker} sedan {start} ...")
    df = yf.download(ticker, start=start, interval="1d", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"][ticker].dropna()
    else:
        close = df["Close"].dropna()
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(close))
    return close


def payday_dates(idx: pd.DatetimeIndex) -> list:
    """Första handelsdag med dag-i-månaden >= PAYDAY_DOM, en per kalendermånad."""
    df = pd.DataFrame({"date": idx}, index=idx.to_period("M"))
    dates = []
    for _, grp in df.groupby(level=0):
        cand = grp["date"][grp["date"].dt.day >= PAYDAY_DOM]
        if len(cand):
            dates.append(cand.iloc[0])
    return dates


def _nav_stats(nav_daily: pd.Series) -> dict:
    """Resampla till vecka (samma konvention som accumulation.py) innan
    MomentumBacktester._compute_stats, som hårdkodar 52 veckor/år."""
    nav_w = nav_daily.resample("W-MON").last().ffill()
    return MomentumBacktester._compute_stats(nav_w, 1.0)


def simulate_scheduled(close: pd.Series, paydays: list) -> dict:
    """Baslinje: köp HELA insättningen på insättningsdagen, ingen tajmning -
    exakt vad next_buy()/simulate_accumulation() gör idag."""
    units = 0.0
    contributed = 0.0
    nav = 1.0
    prev_value = None
    nav_series, dates = [], []
    entry_prices = []

    payday_set = set(paydays)
    for d in close.index:
        px = close.loc[d]
        value_before = units * px
        if prev_value is not None and prev_value > 0:
            nav *= (1.0 + (value_before / prev_value - 1.0))
        if d in payday_set:
            units += (CONTRIB * (1.0 - COST_ONEWAY)) / px
            contributed += CONTRIB
            entry_prices.append(px)
            value_after = units * px
        else:
            value_after = value_before
        prev_value = value_after
        nav_series.append(nav)
        dates.append(d)

    nav_s = pd.Series(nav_series, index=pd.DatetimeIndex(dates))
    end_value = units * close.iloc[-1]
    return {
        "label": "Schemalagt (baslinje - dagens beteende)",
        "nav_stats": _nav_stats(nav_s),
        "end_value": end_value,
        "contributed": contributed,
        "avg_entry": float(np.mean(entry_prices)),
        "n_cycles": len(entry_prices),
        "triggered_early": None,
        "avg_wait_days": None,
    }


def simulate_dip_timed(close: pd.Series, paydays: list, threshold: float) -> dict:
    """Från varje insättningsdag: håll kontant tills priset fallit >=
    threshold under insättningsdagens EGNA pris (referensen), köp DÅ. Ingen
    trigger innan nästa insättningsdag -> tvångsköp DÅ, INNAN den dagens
    egen nya insättning läggs till (jämkas in, väntar aldrig längre än en
    cykel - `pending` kan därför aldrig omfatta mer än en cykels insättning
    åt gången).

    BUGG (fixad under utveckling, se konversationen): en tidigare version
    höll reda på "vilken cykel äger den här dagen" via en dag->cykel-
    uppslagning byggd cykel för cykel - men en insättningsdag är BÅDA
    slutdatum för föregående cykel OCH startdatum för nästa, och den senare
    cykeln skrev tyst över den förras post för samma dag i uppslagningen.
    Föregående cykels tvångsköp-deadline (`d == end_d`) kunde då ALDRIG
    utvärderas - villkoret kollades bara mot NÄSTA cykels (fel) referens-
    pris. Ouppfylld pending "smälte samman" tyst med nästa insättning i
    stället för att tvångsköpas, och `value_after` i inget-köp-grenen
    återanvände dessutom det FÖRE-insättning beräknade `value_before` trots
    att `pending`-variabeln redan hunnit räknas upp - en dold miljonbugg som
    injicerade en falsk ~+100% NAV-dag varje gång två cyklers pending
    kolliderade (syntes som orimligt högt NAV-CAGR, ~4x baslinjen, trots
    nästan identiskt slutvärde). Löst genom att processa varje dag i EN
    sekventiell loop (ingen förbyggd dag->cykel-karta): tvångsköp
    föregående pending FÖRST om dagen är en insättningsdag, LÄGG SEN till
    dagens nya insättning - så `pending` aldrig kan spänna över mer än en
    cykel, och value_after räknas alltid om EFTER dagens händelser."""
    units = 0.0
    contributed = 0.0
    pending = 0.0
    ref_px = None
    nav = 1.0
    prev_value = None
    nav_series, dates = [], []
    entry_prices = []
    n_triggered_early = 0
    n_cycles = 0
    wait_days = []
    cycle_start = None

    payday_set = set(paydays)
    last_day = close.index[-1]

    for d in close.index:
        px = close.loc[d]
        value_before = units * px + pending
        if prev_value is not None and prev_value > 0:
            nav *= (1.0 + (value_before / prev_value - 1.0))

        is_payday = d in payday_set
        if is_payday and pending > 0:
            # Tvångsköp FÖREGÅENDE cykels pending innan dagens nya insättning
            # läggs till - "jämkas in", garanterat senast här.
            units += (pending * (1.0 - COST_ONEWAY)) / px
            entry_prices.append(px)
            n_cycles += 1
            wait_days.append((d - cycle_start).days)
            pending = 0.0

        if is_payday:
            pending += CONTRIB
            contributed += CONTRIB
            ref_px = px
            cycle_start = d
        elif pending > 0 and ref_px is not None and px <= ref_px * (1.0 - threshold):
            units += (pending * (1.0 - COST_ONEWAY)) / px
            entry_prices.append(px)
            n_cycles += 1
            n_triggered_early += 1
            wait_days.append((d - cycle_start).days)
            pending = 0.0
        elif pending > 0 and d == last_day:
            # Datans slut nådd med pending kvar (sista, ofullständiga cykeln) -
            # tvångsköp här, ingen "nästa insättningsdag" att jämka mot.
            units += (pending * (1.0 - COST_ONEWAY)) / px
            entry_prices.append(px)
            n_cycles += 1
            wait_days.append((d - cycle_start).days)
            pending = 0.0

        value_after = units * px + pending
        prev_value = value_after
        nav_series.append(nav)
        dates.append(d)

    nav_s = pd.Series(nav_series, index=pd.DatetimeIndex(dates))
    end_value = units * close.iloc[-1] + pending
    return {
        "label": f"Dip-tajmad (-{threshold:.0%} från insättningsdagens pris, jämkas mot nästa)",
        "nav_stats": _nav_stats(nav_s),
        "end_value": end_value,
        "contributed": contributed,
        "avg_entry": float(np.mean(entry_prices)) if entry_prices else None,
        "n_cycles": n_cycles,
        "triggered_early": n_triggered_early,
        "avg_wait_days": float(np.mean(wait_days)) if wait_days else None,
    }


def payday_effect(close: pd.Series, paydays: list) -> None:
    """Deskriptiv diagnostik: genomsnittlig dagsavkastning kring
    insättningsdagarna vs. övriga dagar. Ingen handelsstrategi - bara
    kontext för om "vänta på nedgång" riskerar att missa ett systematiskt
    flödesdrivet uppsving runt lönedagen."""
    rets = close.pct_change().dropna()
    idx = rets.index
    payday_pos = {idx.searchsorted(d) for d in paydays if d in idx}

    offsets = range(-3, 4)
    print("\n  [Payday-effekt] Snittavkastning per handelsdags-offset från insättningsdagen:")
    print(f"  {'offset':>7} {'snittavk.':>10} {'n':>6}")
    for off in offsets:
        positions = [p + off for p in payday_pos if 0 <= p + off < len(rets)]
        if not positions:
            continue
        sample = rets.iloc[positions]
        print(f"  {off:>+7} {sample.mean():>+9.3%} {len(sample):>6}")
    print(f"  {'(alla dagar)':>7} {rets.mean():>+9.3%} {len(rets):>6}")


def _fmt_pct(x):
    return f"{x:+.1%}" if x is not None else "  n/a"


def main():
    close = fetch_daily(TICKER, START)
    print(f"[data] {TICKER}: {close.index[0].date()} -> {close.index[-1].date()} "
          f"({len(close)} handelsdagar)")

    paydays = payday_dates(close.index)
    print(f"[insättningsdagar] {len(paydays)} st, DOM>={PAYDAY_DOM} "
          f"(första: {paydays[0].date()}, sista: {paydays[-1].date()})")

    payday_effect(close, paydays)

    print(f"\n===== KÄRN-INSÄTTNING: schemalagt köp vs. dip-tajmad insättning ({TICKER}) =====")
    print(f"Månadsinsättning: {CONTRIB:,.0f} · kostnad/köp: {COST_ONEWAY:.2%} "
          f"· fönster {paydays[0].date()} -> {close.index[-1].date()}\n".replace(",", " "))

    baseline = simulate_scheduled(close, paydays)
    variants = [simulate_dip_timed(close, paydays, t) for t in THRESHOLDS]

    for r in [baseline] + variants:
        s = r["nav_stats"]
        extra = ""
        if r["triggered_early"] is not None:
            extra = (f" · triggade tidigt {r['triggered_early']}/{r['n_cycles']} cykler "
                     f"({r['triggered_early'] / r['n_cycles']:.0%}) · snittväntan {r['avg_wait_days']:.0f} dagar")
        print(f"  {r['label']}")
        print(f"    NAV-CAGR {s['CAGR']} · Sharpe {s['Sharpe']} · MaxDD {s['Max Drawdown']} · "
              f"snitt köpkurs {r['avg_entry']:.2f} · slutvärde {r['end_value']:,.0f} av "
              f"{r['contributed']:,.0f} insatt ({_fmt_pct(r['end_value'] / r['contributed'] - 1)})"
              f"{extra}".replace(",", " "))

    print("\n(NAV-CAGR/Sharpe/MaxDD är insättnings-NEUTRALA - jämförbara trots olika kapitalflöden,\n"
          " samma metod som backtest_core_allocation.py. \"Snitt köpkurs\" är den faktiska\n"
          " genomsnittliga anskaffningskursen - det direkta svaret på \"fick jag ett bättre pris\".\n"
          " Väntande kontanter ger 0% avkastning i simuleringen (samma konvention som\n"
          " bear-regimens kontantparkering i accumulation.py) - kostnaden av att vänta är alltså\n"
          " redan inräknad, inte gömd.)")


if __name__ == "__main__":
    main()
