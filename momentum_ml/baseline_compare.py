"""
baseline_compare.py – Tillför ML:en något över ren regelbaserad momentum?

Kör på Pi:n från /opt/momentum/momentum_ml (tränar INGET – läser datacache +
senaste körningens results/signals.csv):

    /opt/momentum/venv/bin/python baseline_compare.py

Jämför, på exakt samma universum/kostnader/rebalansering/marknadsfilter:
  - Ren momentum: topp-N likaviktat rankat på relativ styrka (rs_26w/rs_13w/rs_4w),
    helt utan ML – den klassiska Jegadeesh-Titman-baslinjen.
  - ML (XS-target): strategins faktiska signaler från results/signals.csv.
  - Index: likaviktat köp-och-behåll (benchmark i alfa-kolumnen).

Om ren momentum matchar/slår ML är ML-lagret brus och vi bör förenkla eller
tänka om kring features/horisont. Om ML slår ren momentum tillför modellen edge.
"""
import sys
sys.path.insert(0, '.')
import pandas as pd
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)
from features.feature_engineering import build_all_features
from backtest.backtester import MomentumBacktester
from backtest.benchmark import benchmark_report


def momentum_signals(feats, col, n):
    """Topp-N likaviktat per vecka rankat på `col`. Long-format för backtestern."""
    panel = pd.DataFrame({t: f[col] for t, f in feats.items() if col in f})
    rows = []
    for date, row in panel.iterrows():
        valid = row.dropna()
        if valid.empty:
            continue
        top = set(valid.sort_values(ascending=False).head(n).index)
        w = 1.0 / max(len(top), 1)
        for t in panel.columns:
            inb = t in top
            rows.append({"Date": date, "ticker": t,
                         "pred_signal": int(inb), "position_size": w if inb else 0.0})
    return pd.DataFrame(rows).set_index("Date").sort_index()


def show(sig, data, label):
    bt = MomentumBacktester(sig, data, market_filter=True)
    bt.run()
    s = bt.statistics()
    b = benchmark_report(bt._results["portfolio_value"], data)
    # holdout (sista HOLDOUT_WEEKS) separat – det enda äkta out-of-sample-måttet
    pv = bt._results["portfolio_value"]
    ho = pv.iloc[-config.HOLDOUT_WEEKS:] if len(pv) > config.HOLDOUT_WEEKS else pv
    ho_cagr = (ho.iloc[-1] / ho.iloc[0]) ** (52 / max(len(ho) - 1, 1)) - 1
    print("  %-22s  CAGR %6s  Sharpe %5s  alfa %+5.1f%%  beta %.2f  holdout-CAGR %+5.1f%%"
          % (label, s["CAGR"], s["Sharpe"], b["alpha_cagr"] * 100, b["beta"], ho_cagr * 100))


def main():
    tickers, sector_map, _, _ = load_sweden_universe(min_market_cap=["Large Cap", "Mid Cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)

    print("\n===== BASLINJE-JÄMFÖRELSE (samma universum, kostnader, rebalans, filter) =====")
    for col in ("rs_26w", "rs_13w", "rs_4w"):
        show(momentum_signals(feats, col, config.MAX_POSITIONS), data, "Ren momentum %s" % col)

    try:
        ml = pd.read_csv("results/signals.csv", parse_dates=["Date"]).set_index("Date")
        show(ml[["ticker", "pred_signal", "position_size"]], data, "ML (XS-target)")
    except Exception as e:
        print("  [WARN] Kunde inte läsa results/signals.csv för ML-jämförelse: %s" % e)

    print("\n(alfa = CAGR minus likaviktat köp-och-behåll. holdout-CAGR = äkta OOS.)")


if __name__ == "__main__":
    main()
