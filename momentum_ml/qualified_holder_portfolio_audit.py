"""Walk-forward-test av topp-10 plus en tillfällig qualified-holder-plats.

Kärnmodellens tio val köps alltid. Samtliga tidigare innehav som just fallit
ur topp-10 får ligga kvar som extra innehav om kursen är över SMA20 och deras
26-veckorsavkastning slår likaviktat universum. Kandidaterna löper ut efter
4/8/13 veckor. Alla positioner likaviktas; inget extra kapital antas.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import pandas as pd

import config
from data.data_loader import (
    fetch_weekly_data, filter_active_universe, filter_liquid_universe,
    load_sweden_universe,
)

DELAYS = (4, 8, 13)
ONEWAY_COST = (
    float(getattr(config, "COMMISSION", .0015))
    + float(getattr(config, "SLIPPAGE", .001))
    + float(getattr(config, "SPREAD_MIN", 0.0))
)


def metrics(returns: pd.Series):
    returns = returns.dropna()
    nav = (1 + returns).cumprod()
    years = len(returns) / 52
    cagr = nav.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
    vol = returns.std(ddof=1)
    sharpe = returns.mean() / vol * np.sqrt(52) if vol > 0 else np.nan
    maxdd = (nav / nav.cummax() - 1).min()
    return cagr, sharpe, maxdd, nav.iloc[-1]


def simulate(core_by_date, ranks_by_date, px, idx, delay=0,
             breadth_counts=None):
    dates = sorted(set(core_by_date).intersection(px.index))
    active = {}
    previous_core = set()
    previous_weights = {}
    returns, extra_counts, chosen = [], [], []

    for i, date in enumerate(dates[:-1]):
        core = core_by_date[date]
        core_set = set(core)
        pos = px.index.get_loc(date)

        if breadth_counts is not None:
            n_extra = int(breadth_counts.get(date, 0))
            holdings = list(ranks_by_date[date])[:10 + n_extra]
            extras = holdings[10:]
        elif delay:
            for ticker in previous_core - core_set:
                if ticker not in px or pos < 26:
                    continue
                p = px[ticker].iloc[pos]
                sma = px[ticker].iloc[pos - 19:pos + 1].mean()
                rel = p / px[ticker].iloc[pos - 26] - idx.iloc[pos] / idx.iloc[pos - 26]
                if pd.notna(p) and p > sma and rel > 0:
                    active[ticker] = i + delay
            active = {
                t: expiry for t, expiry in active.items()
                if expiry > i and t not in core_set
            }
            # Samtliga samtidiga qualified holders får plats. Sorteringen gör
            # endast rapporteringen deterministisk; inget bolag väljs bort.
            ranks = ranks_by_date[date]
            extras = sorted(
                active, key=lambda t: ranks.get(t, -np.inf), reverse=True)
            holdings = core + extras
        else:
            extras = []
            holdings = core

        weights = {t: 1 / len(holdings) for t in holdings}
        next_date = dates[i + 1]
        gross = 0.0
        valid = True
        for ticker, weight in weights.items():
            p0, p1 = px.at[date, ticker], px.at[next_date, ticker]
            if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                valid = False
                break
            gross += weight * (p1 / p0 - 1)
        turnover = sum(
            abs(weights.get(t, 0) - previous_weights.get(t, 0))
            for t in set(weights) | set(previous_weights))
        net = gross - turnover * ONEWAY_COST if valid else np.nan
        returns.append((next_date, net))
        extra_counts.append((date, len(extras)))
        chosen.append(tuple(extras))
        previous_weights = weights
        previous_core = core_set

    ret = pd.Series(dict(returns)).sort_index()
    counts = pd.Series(dict(extra_counts), dtype=float)
    return ret, counts, chosen


def main():
    seg = config.SEGMENTS["large"]
    rd = Path(config.anchor(seg["results_dir"]))
    sig = pd.read_csv(rd / "signals.csv", parse_dates=["Date"])
    rank_col = "prob_rank" if "prob_rank" in sig else "prob_up"

    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(
        data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()

    core_by_date, ranks_by_date = {}, {}
    for date, group in sig.groupby("Date"):
        available = group[group["ticker"].isin(px.columns)].sort_values(
            rank_col, ascending=False)
        selected = available[available["pred_signal"] == 1].head(10)
        if len(selected) == 10:
            core_by_date[date] = selected["ticker"].tolist()
            ranks_by_date[date] = dict(zip(available["ticker"], available[rank_col]))

    variants = {0: simulate(core_by_date, ranks_by_date, px, idx, 0)}
    variants.update({
        delay: simulate(core_by_date, ranks_by_date, px, idx, delay)
        for delay in DELAYS
    })
    # Matchad breddkontroll för den på förhand låsta 4v-regeln: lika många
    # aktier varje vecka, men extraplatsen fylls av nästa färska modellrank.
    matched_breadth = simulate(
        core_by_date, ranks_by_date, px, idx, 0,
        breadth_counts=variants[4][1].to_dict())
    periods = {
        "UTVECKLING <2024": lambda x: x[x.index < "2024-01-01"],
        "KONTROLL 2024+": lambda x: x[x.index >= "2024-01-01"],
    }
    print(f"Transaktionskostnad {ONEWAY_COST:.2%} per omsatt krona; "
          "ordinarie topp-10 missas aldrig.")
    print("period               modell   CAGR  Sharpe   MaxDD  slutvärde  extra")
    for period, select in periods.items():
        for delay, (ret, counts, _) in variants.items():
            cagr, sharpe, maxdd, nav = metrics(select(ret))
            label = "topp10" if delay == 0 else f"topp10+Q/{delay}v"
            period_counts = select(counts)
            print(f"{period:<21}{label:<12}{cagr:>7.2%}{sharpe:>8.2f}"
                  f"{maxdd:>8.2%}{nav:>11.3f}{period_counts.mean():>8.2f}")
        cagr, sharpe, maxdd, nav = metrics(select(matched_breadth[0]))
        period_counts = select(matched_breadth[1])
        print(f"{period:<21}{'matchad bredd':<12}{cagr:>7.2%}{sharpe:>8.2f}"
              f"{maxdd:>8.2%}{nav:>11.3f}{period_counts.mean():>8.2f}")

    # Fyra veckor låstes av den föregående eventstudien innan 10+1-testet.
    selected = 4
    base = metrics(periods["KONTROLL 2024+"](variants[0][0]))
    diversification_control = metrics(
        periods["KONTROLL 2024+"](matched_breadth[0]))
    test = metrics(periods["KONTROLL 2024+"](variants[selected][0]))
    approved = (
        test[0] > max(base[0], diversification_control[0])
        and test[1] > max(base[1], diversification_control[1])
        and test[2] >= max(base[2], diversification_control[2])
    )
    print(f"\nFörhandsvald karantän: {selected} veckor")
    print("BESLUT:", "GODKÄND FÖR SHADOW" if approved else "FÖRKASTAD")


if __name__ == "__main__":
    main()
