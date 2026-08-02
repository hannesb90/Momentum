"""
tune_cashflow_inflection.py – testar tesen "bolag omvärderas vid övergången
till positivt operativt kassaflöde" (CFO-inflektion, en vanlig "turnaround"-
tes: tidigare kassaflödesnegativa bolag ska ge en omvärderings-pop när de
blir positiva).

Metodik (samma familj som #19, tune_hold_forever_fundamentals.py): hitta
händelser (första övergången CFO<0 -> CFO>0 per bolag, årsdata), mät
framåtavkastning från händelsen mot ett likaviktat universumsindex, jämfört
med en slumpmässig baslinje för SAMMA bolag (kontrollerar för
bolagsvals-effekter, inte bara "var universumet starkt just då").

DATABEGRÄNSNING (ärlig, kontrollerad innan bygget): yfinance ger bara ~4-5 år
ÅRSDATA kassaflöde per bolag som standard (ingen betald källa krävs, men
historiken är kort) - en genuin övergång måste falla INOM det fönstret för
att synas alls. Det ger ett litet, snedvridet urval (bara SENA/NYA
övergångar, inte t.ex. dotcom- eller finanskris-eran) - resultatet är en
indikation, inte ett representativt svep över flera decennier/regimer som
#19:s prisdata-test hade råd med.

Publiceringsdatum approximeras (periodslut + REPORT_LAG_DAYS) - yfinance ger
bara periodslutet, inte det faktiska rapportdatumet. Samma typ av grov
point-in-time-approximation som fundamentals_from_avanza.csv redan använder
(se tune_hold_forever_fundamentals.py:s docstring).

Kräver nätåtkomst till Yahoo Finance - körs på Pi:n:

    python tune_cashflow_inflection.py
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from data.data_loader import (  # noqa: E402
    fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe,
)

REPORT_LAG_DAYS = 90     # ungefärlig publiceringsfördröjning efter periodslut (årsrapport, grovt)
# Korta horisonter (1-8v) tillagda på användarens begäran: en omvärdering vid
# flödespositivitet borde synas i NÄRA anslutning till rapporten, inte bara
# på 13v+. OBS known_date är en GROV approximation (periodslut + 90 dagar,
# ingen exakt rapportdag finns billigt tillgänglig - yfinance.get_earnings_dates
# kräver lxml OCH saknar historik så långt tillbaka som 2022-2023 för många av
# dessa bolag) - så en 1-veckors-siffra mäter "veckan kring vår GISSADE
# rapportdag", inte nödvändigtvis den FAKTISKA rapportveckan. Se resultatens
# tolkning: tillförlitligheten avtar ju kortare horisonten är, av just detta skäl.
HORIZONS_WEEKS = [1, 2, 4, 8, 13, 26, 52, 104]
N_RANDOM_BASELINE = 3    # slumpmässiga jämförelsedatum per bolag (samma bolag, andra tidpunkter)
CACHE_DIR = Path(__file__).parent / "cache" / "cfo_inflection"


def fetch_cfo_history(ticker: str):
    cache = CACHE_DIR / f"{ticker.replace('.', '_')}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    import yfinance as yf
    try:
        cf = yf.Ticker(ticker).cashflow
        if cf is None or cf.empty or "Operating Cash Flow" not in cf.index:
            result = None
        else:
            s = cf.loc["Operating Cash Flow"].dropna()
            s.index = pd.DatetimeIndex(s.index).tz_localize(None)
            result = s.sort_index()
    except Exception:
        result = None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(result))
    return result


def find_first_transition(cfo: pd.Series):
    """Första gången CFO går från negativt (föregående rapport) till positivt
    (denna rapport). Returnerar periodslutdatumet eller None."""
    dates = sorted(cfo.index)
    for i in range(1, len(dates)):
        if cfo.loc[dates[i - 1]] < 0 and cfo.loc[dates[i]] > 0:
            return dates[i]
    return None


def main():
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=None)
    print(f"[tune_cashflow_inflection] {len(tickers)} tickers i universumet - hämtar kassaflödeshistorik "
          f"(cachad lokalt, en gång per ticker)...")

    events = []   # (ticker, period_end, known_date)
    n_no_cf, n_no_transition = 0, 0
    for i, t in enumerate(tickers):
        cfo = fetch_cfo_history(t)
        if cfo is None or len(cfo) < 2:
            n_no_cf += 1
            continue
        d = find_first_transition(cfo)
        if d is None:
            n_no_transition += 1
            continue
        events.append((t, d, d + pd.Timedelta(days=REPORT_LAG_DAYS)))
        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1}/{len(tickers)} bolag genomsökta, {len(events)} övergångar hittade hittills")

    print(f"\n[tune_cashflow_inflection] {len(events)} bolag med en CFO-negativ->positiv-övergång synlig "
          f"inom yfinance kassaflödeshistorik (av {len(tickers)} totalt; {n_no_cf} saknade kassaflödesdata, "
          f"{n_no_transition} hade data men ingen sådan övergång i fönstret).")
    if not events:
        print("Inga övergångar hittade - avbryter.")
        return

    ev_tickers = sorted({t for t, _, _ in events})
    print(f"[tune_cashflow_inflection] hämtar veckopriser för {len(ev_tickers)} händelsebolag "
          f"+ resten av universumet (index)...")
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx_level = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    weeks = px.index

    def _week_pos(date):
        p = weeks.searchsorted(date, side="left")
        return p if p < len(weeks) else None

    def _fwd_excess(ticker, week_pos, h):
        p1i = week_pos + h
        if ticker not in px.columns or p1i >= len(weeks):
            return None
        p0, p1 = px[ticker].iloc[week_pos], px[ticker].iloc[p1i]
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            return None
        r = p1 / p0 - 1
        b = idx_level.iloc[p1i] / idx_level.iloc[week_pos] - 1
        return r - b

    rows = []
    rng = np.random.default_rng(42)
    for t, period_end, known_date in events:
        wp = _week_pos(known_date)
        if wp is None or t not in px.columns:
            continue
        rows.append({"ticker": t, "period_end": period_end, "known_date": known_date,
                      "week_pos": wp, "kind": "event"})
        # Slumpmässiga jämförelsedatum för SAMMA bolag (samma bolagsval, andra
        # tidpunkter) - kontrollerar för "det här är helt enkelt ett bolag
        # som gått bra/dåligt", inte bara händelsens tajmning.
        valid_range = px[t].dropna().index
        valid_range = valid_range[valid_range >= weeks[104]]  # kräv ~2 år historik innan
        if len(valid_range) == 0:
            continue
        for _ in range(N_RANDOM_BASELINE):
            rd = valid_range[rng.integers(0, len(valid_range))]
            rwp = _week_pos(rd)
            if rwp is not None:
                rows.append({"ticker": t, "period_end": rd, "known_date": rd,
                             "week_pos": rwp, "kind": "random"})

    ev_df = pd.DataFrame(rows)
    print(f"\n[tune_cashflow_inflection] {len(ev_df[ev_df['kind'] == 'event'])} händelser med prisdata "
          f"({ev_df['ticker'].nunique()} unika bolag) + {len(ev_df[ev_df['kind'] == 'random'])} "
          f"slumpmässiga jämförelsepunkter för samma bolag.\n")

    header = f"  {'grupp':<10}{'n':>6}" + "".join(f"{f'{h}v exc':>10}{f'{h}v win%':>9}{f'{h}v n':>7}" for h in HORIZONS_WEEKS)
    print("=" * len(header))
    print("  CFO-inflektion (första negativ->positiv) vs. slumpmässiga datum, SAMMA bolag")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for kind, label in [("event", "händelse"), ("random", "slump (kontroll)")]:
        sub = ev_df[ev_df["kind"] == kind]
        cells = f"  {label:<10}{sub['ticker'].nunique():>6}"
        for h in HORIZONS_WEEKS:
            excs = [_fwd_excess(r["ticker"], r["week_pos"], h) for _, r in sub.iterrows()]
            excs = [e for e in excs if e is not None]
            if not excs:
                cells += f"{'–':>10}{'–':>9}{'–':>7}"
            else:
                cells += f"{np.median(excs):>+10.1%}{np.mean([e > 0 for e in excs]):>8.0%} {len(excs):>7}"
        print(cells)
    print("-" * len(header))

    print("\n  Enskilda händelser (bolag, ungefärligt känt-datum, 52v excess):")
    for _, r in ev_df[ev_df["kind"] == "event"].sort_values("known_date").iterrows():
        e52 = _fwd_excess(r["ticker"], r["week_pos"], 52)
        e52s = f"{e52:+.1%}" if e52 is not None else "  n/a (för nära datans slut)"
        print(f"    {r['ticker']:<14} {r['known_date'].date()}   52v excess: {e52s}")

    print("\n  Läsning: håller re-rating-tesen ska 'händelse'-raden slå 'slump (kontroll)'-raden -")
    print("  annars är det bara att dessa specifika bolag generellt gått bra/dåligt, inte att")
    print("  SJÄLVA ÖVERGÅNGEN utlöste en omvärdering. OBS litet, snedvridet urval (bara")
    print("  övergångar synliga inom yfinance ~4-5 års gratis-historik) - se docstring.")


if __name__ == "__main__":
    main()
