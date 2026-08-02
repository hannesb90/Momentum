"""
tune_kelly_win_loss_ratio.py – [EDGE-7] Empirisk skattning av Kelly
win_loss_ratio (idag fast 1,5 i models/ensemble.py::kelly_position_size).
IRRELEVANT för dagens live-sizing (config.SIZING_MODE="inverse_vol" gör att
Kelly/raw_kelly styr ingenting, se Test 8/#132) - men relevant om
conviction-läget någonsin återaktiveras (EDGE_RISK_SCENARIO_TESTKO.md
Tier 3 #19). Ren mätning mot results/signals.csv, samma hållperiods-
rekonstruktion som #141 (SCN-HÅLL-4).

    /opt/momentum/venv/bin/python3 tune_kelly_win_loss_ratio.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from backtest.backtester import MomentumBacktester
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe


class EventTrackingBacktester(MomentumBacktester):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []

    def _rebalance(self, date, target_weights, portfolio_value, cash):
        before = set(self._portfolio.keys())
        cash = super()._rebalance(date, target_weights, portfolio_value, cash)
        after = set(self._portfolio.keys())
        for t in after - before:
            self.events.append((date, t, "buy"))
        for t in before - after:
            self.events.append((date, t, "sell"))
        return cash


def main():
    seg = config.SEGMENTS["large"]
    config.RESULTS_DIR = seg["results_dir"]
    if "max_positions" in seg:
        config.MAX_POSITIONS = seg["max_positions"]
    if "forward_weeks" in seg:
        config.FORWARD_WEEKS = seg["forward_weeks"]
        config.REBALANCE_WEEKS = seg["rebalance_weeks"]
    if "atr_stop_enabled" in seg:
        config.ATR_STOP_ENABLED = seg["atr_stop_enabled"]
    if "market_filter_exposure" in seg:
        config.MARKET_FILTER_EXPOSURE = seg["market_filter_exposure"]
    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    tickers, sector_map, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    print("[kelly_wl] Kör backtest med köp/sälj-loggning...")
    bt = EventTrackingBacktester(sig, data)
    bt.run()
    px = bt._close_panel

    open_buy = {}
    holdings = []
    for date, t, action in bt.events:
        if action == "buy" and t not in open_buy:
            open_buy[t] = date
        elif action == "sell" and t in open_buy:
            holdings.append((t, open_buy.pop(t), date))
    for t, buy_date in open_buy.items():
        holdings.append((t, buy_date, px.index[-1]))

    holdout_start = sig.index.unique().sort_values()[-config.HOLDOUT_WEEKS] \
        if len(sig.index.unique()) > config.HOLDOUT_WEEKS else None

    rows = []
    for t, d0, d1 in holdings:
        if t not in px.columns:
            continue
        p0, p1 = px.at[d0, t] if d0 in px.index else np.nan, px.at[d1, t] if d1 in px.index else np.nan
        if pd.isna(p0) or pd.isna(p1) or not p0:
            continue
        rows.append({"ticker": t, "buy": d0, "sell": d1, "ret": p1 / p0 - 1,
                     "period": "holdout" if holdout_start is not None and d0 >= holdout_start else "dev"})

    out = pd.DataFrame(rows)
    print(f"[kelly_wl] {len(out)} hållperioder med mätbar avkastning.\n")

    print("=" * 80)
    print("Empirisk win/loss-ratio (medel-vinst / |medel-förlust|) – mot fast antagande 1,5")
    print("=" * 80)
    for label, sub in (("Hela perioden", out), ("Dev", out[out["period"] == "dev"]),
                        ("Holdout", out[out["period"] == "holdout"])):
        if sub.empty:
            continue
        wins = sub[sub["ret"] > 0]["ret"]
        losses = sub[sub["ret"] <= 0]["ret"]
        if len(wins) == 0 or len(losses) == 0:
            print(f"\n  {label}: saknar vinster eller förluster, kan inte beräkna ratio.")
            continue
        avg_win, avg_loss = wins.mean(), losses.mean()
        wl_ratio = avg_win / abs(avg_loss)
        win_rate = len(wins) / len(sub)
        print(f"\n  {label} (n={len(sub)}, vinstandel={win_rate:.1%}):")
        print(f"    medel-vinst={avg_win:+.1%} (n={len(wins)})  medel-förlust={avg_loss:+.1%} (n={len(losses)})")
        print(f"    empirisk win/loss-ratio = {wl_ratio:.2f}  (fast antagande i koden: 1.50)")
        median_win, median_loss = wins.median(), losses.median()
        print(f"    (median-baserad ratio = {median_win/abs(median_loss):.2f}, mindre känslig för extremutfall)")

    print("\n[kelly_wl] Klart.")


if __name__ == "__main__":
    main()
