"""Ackumuleringstest: 10 000 kr/mån finansierar nya toppval.

Jämför omedelbar topp-10-exit med en 4v qualified-holder-karantän. Båda får
100 000 kr startkapital och 10 000 kr första signalveckan varje månad.
Kassaflöden neutraliseras i TWR/CAGR och inkluderas korrekt i XIRR.
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

START_CAPITAL = 100_000.0
MONTHLY = 10_000.0
QUARANTINE_WEEKS = 4
COST = (
    float(getattr(config, "COMMISSION", .0015))
    + float(getattr(config, "SLIPPAGE", .001))
    + float(getattr(config, "SPREAD_MIN", 0.0))
)


def xirr(cashflows):
    start = cashflows[0][0]
    years = np.array([(d - start).days / 365.25 for d, _ in cashflows])
    flows = np.array([v for _, v in cashflows], dtype=float)
    lo, hi = -0.999, 10.0
    def npv(rate):
        return np.sum(flows / (1 + rate) ** years)
    if npv(lo) * npv(hi) > 0:
        return np.nan
    for _ in range(120):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def stats(twr, cashflows, end_value):
    r = twr.dropna()
    nav = (1 + r).cumprod()
    years = len(r) / 52
    cagr = nav.iloc[-1] ** (1 / years) - 1
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(52)
    maxdd = (nav / nav.cummax() - 1).min()
    cf = list(cashflows) + [(r.index[-1], end_value)]
    return cagr, sharpe, maxdd, xirr(cf)


def simulate(core_by_date, ranks_by_date, px, idx, quarantine):
    dates = sorted(set(core_by_date).intersection(px.index))
    units, expiry = {}, {}
    cash = 0.0
    prev_after_flow = None
    twr, flows = [], []
    prior_core = set()
    months = pd.DatetimeIndex(dates).to_period("M")

    for i, date in enumerate(dates):
        pos = px.index.get_loc(date)
        core = core_by_date[date]
        core_set = set(core)
        value_before = cash + sum(
            n * px.at[date, t] for t, n in units.items()
            if t in px and pd.notna(px.at[date, t]))
        if prev_after_flow and prev_after_flow > 0:
            twr.append((date, value_before / prev_after_flow - 1))

        # Nya avhopp får karantän endast om trenden är intakt vid beslutet.
        if quarantine and pos >= 26:
            for t in prior_core - core_set:
                if t not in px:
                    continue
                p = px.at[date, t]
                sma = px[t].iloc[pos - 19:pos + 1].mean()
                rel = p / px[t].iloc[pos - 26] - idx.iloc[pos] / idx.iloc[pos - 26]
                if pd.notna(p) and p > sma and rel > 0:
                    expiry[t] = i + QUARANTINE_WEEKS
        expiry = {t: e for t, e in expiry.items() if e > i and t not in core_set}
        allowed = core_set | set(expiry)

        # Sälj endast icke tillåtna innehav; karantän kräver aldrig finansiering.
        for t in list(units):
            if t not in allowed:
                p = px.at[date, t]
                if pd.notna(p):
                    cash += units.pop(t) * p * (1 - COST)

        contribution = 0.0
        if i == 0:
            contribution = START_CAPITAL
        elif months[i] != months[i - 1]:
            contribution = MONTHLY
        if contribution:
            cash += contribution
            flows.append((date, -contribution))

        # All kassa går till ordinarie topp-10, aldrig till legacy-innehav.
        # Gap mot 10% av värdet gör att nya/högst underviktade val fylls först.
        total = cash + sum(units.get(t, 0) * px.at[date, t] for t in units)
        target = total / 10
        gaps = {
            t: max(0.0, target - units.get(t, 0) * px.at[date, t])
            for t in core if pd.notna(px.at[date, t]) and px.at[date, t] > 0
        }
        while cash > 0.01 and gaps and max(gaps.values()) > 0:
            # Vid lika gap prioriteras högst modellrank.
            t = max(gaps, key=lambda x: (gaps[x], ranks_by_date[date].get(x, 0)))
            amount = min(cash, gaps[t])
            p = px.at[date, t]
            units[t] = units.get(t, 0) + amount * (1 - COST) / p
            cash -= amount
            gaps[t] = 0.0

        prev_after_flow = cash + sum(
            n * px.at[date, t] for t, n in units.items())
        prior_core = core_set

    series = pd.Series(dict(twr)).sort_index()
    final_values = {
        t: n * px.at[dates[-1], t] for t, n in units.items()
        if pd.notna(px.at[dates[-1], t])
    }
    return series, flows, prev_after_flow, len(units), len(expiry), final_values


def main():
    seg = config.SEGMENTS["large"]
    rd = Path(config.anchor(seg["results_dir"]))
    sig = pd.read_csv(rd / "signals.csv", parse_dates=["Date"])
    rank_col = "prob_rank" if "prob_rank" in sig else "prob_up"
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_liquid_universe(
        filter_active_universe(data),
        min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame(
        {t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()

    core, ranks = {}, {}
    for date, g in sig.groupby("Date"):
        g = g[g["ticker"].isin(px.columns)].sort_values(rank_col, ascending=False)
        chosen = g[g["pred_signal"] == 1].head(10)
        if len(chosen) == 10:
            core[date] = chosen["ticker"].tolist()
            ranks[date] = dict(zip(g["ticker"], g[rank_col]))

    results = {
        "omedelbar exit": simulate(core, ranks, px, idx, False),
        "10+n / 4v": simulate(core, ranks, px, idx, True),
    }
    print(f"Start {START_CAPITAL:,.0f} kr + {MONTHLY:,.0f} kr/mån; "
          f"köpkostnad {COST:.2%}.")
    print("period            modell             TWR-CAGR Sharpe   MaxDD")
    for period, condition in (
        ("UTVECKLING", lambda s: s.index < "2024-01-01"),
        ("KONTROLL 2024+", lambda s: s.index >= "2024-01-01"),
    ):
        for label, (ret, flows, end_value, held, legacy, final_values) in results.items():
            mask = condition(ret)
            # Period-XIRR kräver separat startvärde och flödesbok; TWR är den
            # rena alpha-jämförelsen. Full XIRR visas bara för hela historiken.
            cagr, sharpe, maxdd, _ = stats(ret[mask], [(ret[mask].index[0], -1)], 1)
            print(f"{period:<18}{label:<19}{cagr:>8.2%}{sharpe:>7.2f}"
                  f"{maxdd:>8.2%}")
    for label, (ret, flows, end_value, held, legacy, final_values) in results.items():
        _, _, _, irr = stats(ret, flows, end_value)
        print(f"HELA {label:<19} XIRR {irr:>7.2%}, slutvärde "
              f"{end_value:,.0f} kr, innehav {held} (legacy {legacy})")
        top = sorted(final_values.items(), key=lambda x: x[1], reverse=True)[:5]
        print("  största slutvärden:", ", ".join(
            f"{t} {v:,.0f}" for t, v in top))


if __name__ == "__main__":
    main()
