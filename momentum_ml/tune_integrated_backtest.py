"""
tune_integrated_backtest.py – "baka ihop kaksmulorna" (se konversationen
2026-07-24): kör backtest/integrated_backtest.py::IntegratedBacktester mot
SAMMA indata som den redan tränade produktionsmodellen (results/<segment>/
signals.csv + fetch_weekly_data), jämför mot en oförändrad
MomentumBacktester på EXAKT samma period – det här är det FAKTISKA
kombinerade utfallet (docs/UTVECKLINGSLOGG.md #26), inte bara kärnmodellens
isolerade Sharpe/CAGR som hittills citerats.

Tre körningar:
  1. MomentumBacktester (baseline, kärnmodellen ensam, oförändrad).
  2. IntegratedBacktester, alla tre lager PÅ (härdighet+insynsköp vid
     entry, säljvakt nivå 2 tvingad 50%-delförsäljning / nivå 3 full exit).
  3. Sanity-check: IntegratedBacktester med alla tre lager AV ska ge
     BIT-FÖR-BIT samma portföljvärde-serie som (1) – bevisar att
     integrationen inte läcker lookahead eller ändrar basbeteendet av
     misstag när den är avstängd.

Kör (Pi:n. Nät krävs bara för otto-band/FI-insyn-cache som ännu saknas för
enskilda bolag – #24/#25/#23 byggde redan huvuddelen av cachen, annars
helt lokalt):
    /opt/momentum/venv/bin/python tune_integrated_backtest.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe
from backtest.backtester import MomentumBacktester
from backtest.integrated_backtest import IntegratedBacktester


def _load_signals(seg_name: str) -> pd.DataFrame:
    seg = config.SEGMENTS[seg_name]
    p = f"{config.anchor(seg['results_dir'])}/signals.csv"
    return pd.read_csv(p, parse_dates=["Date"]).set_index("Date")


def main():
    seg_name = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg = config.SEGMENTS[seg_name]

    print(f"[tune_integrated_backtest] segment={seg_name}: läser signals.csv + prisdata...")
    signals_df = _load_signals(seg_name)

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    all_dates = signals_df.index.unique().sort_values()
    holdout_start = all_dates[-config.HOLDOUT_WEEKS] if len(all_dates) > config.HOLDOUT_WEEKS else None

    print(f"  {len(signals_df)} signalrader, {len(data)} bolag med prisdata, "
          f"{len(all_dates)} veckor ({all_dates[0].date()} -> {all_dates[-1].date()}).")

    # ── 1. Baseline ──────────────────────────────────────────────────────
    print("\n[1/3] MomentumBacktester (baseline, kärnmodellen ensam)...")
    base_bt = MomentumBacktester(signals_df, data)
    base_results = base_bt.run()
    base_bt.print_statistics(title="BASELINE - HELA PERIODEN")
    if holdout_start is not None:
        base_bt.print_statistics(base_bt.statistics_for_period(start=holdout_start),
                                 title="BASELINE - HOLDOUT (frusen)")

    # ── 2. Integrerad ────────────────────────────────────────────────────
    print("\n[2/3] IntegratedBacktester (härdighet + insynsköp + säljvakt PÅ)...")
    int_bt = IntegratedBacktester(signals_df, data)
    int_bt.run()
    int_bt.print_statistics(title="INTEGRERAD - HELA PERIODEN")
    if holdout_start is not None:
        int_bt.print_statistics(int_bt.statistics_for_period(start=holdout_start),
                                title="INTEGRERAD - HOLDOUT (frusen)")

    # ── 3. Sanity-check: alla lager AV == baseline, bit för bit ─────────
    print("\n[3/3] Sanity-check: alla tre lager AV ska matcha baseline exakt...")
    off_bt = IntegratedBacktester(signals_df, data, hold_fund_enabled=False,
                                  insider_enabled=False, sellwatch_enabled=False)
    off_results = off_bt.run()
    identical = base_results["portfolio_value"].equals(off_results["portfolio_value"])
    print(f"  Identisk med baseline: {'JA' if identical else 'NEJ - se koden, lookahead/sidoeffekt misstänkt'}")
    if not identical:
        diff = (base_results["portfolio_value"] - off_results["portfolio_value"]).abs()
        print(f"  Max avvikelse: {diff.max():,.2f} kr vid {diff.idxmax()}")

    print("\n" + "=" * 70)
    print("  SAMMANFATTNING - lägg in i docs/UTVECKLINGSLOGG.md #26")
    print("=" * 70)
    if holdout_start is not None:
        b = base_bt.statistics_for_period(start=holdout_start)
        i = int_bt.statistics_for_period(start=holdout_start)
        for k in ("CAGR", "Sharpe", "Sortino", "Max Drawdown", "Win Rate"):
            print(f"  {k:<14} baseline {b.get(k, '-'):>10}   integrerad {i.get(k, '-'):>10}")


if __name__ == "__main__":
    main()
