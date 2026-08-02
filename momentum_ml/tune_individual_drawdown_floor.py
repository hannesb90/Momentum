"""
tune_individual_drawdown_floor.py – [SCN-HÅLL-4] Individ-drawdown-golv:
Drawdown Guard reagerar bara på PORTFÖLJNIVÅ – kan en enskild position rasa
-40/-50% medan portföljen som helhet inte är i drawdown, obemärkt av något
skyddsmekanism? (EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #25.)

Ren mätning (steg 1, 🟢): kör en OFÖRÄNDRAD backtest (results/signals.csv,
ingen omträning), spåra varje innehavsperiods egen peak-till-trough-drawdown
(veckovis, från köpvecka till säljvecka) och jämför med PORTFÖLJENS egen
drawdown (från toppnivå) under exakt samma veckor. Flaggar fall där en
enskild position föll <= INDIVID_DD_TRÖSKEL medan portföljen låg grundare
än PORTFÖLJ_DD_TAK vid samma tidpunkt - "obemärkt" i den mening att
Drawdown Guard (som bara ser portföljnivån) aldrig skulle reagerat.

    /opt/momentum/venv/bin/python3 tune_individual_drawdown_floor.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from backtest.backtester import MomentumBacktester
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

INDIVID_DD_THRESHOLD = -0.40
PORTFOLIO_DD_CEILING = -0.10   # "grund" portföljdrawdown = grundare än detta


class EventTrackingBacktester(MomentumBacktester):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []   # (date, ticker, "buy"/"sell")

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

    print("[dd_floor] Kör backtest med köp/sälj-loggning...")
    bt = EventTrackingBacktester(sig, data)
    bt.run()

    pv = bt._results["portfolio_value"]
    port_dd = pv / pv.cummax() - 1
    px = bt._close_panel

    # Bygg hållperioder ur buy/sell-loggen (FIFO per ticker - enkla köp/sälj-par,
    # position_size-ombalansering ignoreras här: vi mäter PRISETS drawdown
    # under tiden tickern är innehavd, inte den exakta viktade avkastningen).
    open_buy = {}
    holdings = []
    for date, t, action in bt.events:
        if action == "buy" and t not in open_buy:
            open_buy[t] = date
        elif action == "sell" and t in open_buy:
            holdings.append((t, open_buy.pop(t), date))
    for t, buy_date in open_buy.items():
        holdings.append((t, buy_date, pv.index[-1]))

    print(f"[dd_floor] {len(holdings)} hållperioder rekonstruerade.\n")

    rows = []
    for t, d0, d1 in holdings:
        if t not in px.columns:
            continue
        window = px.loc[d0:d1, t].dropna()
        if len(window) < 2:
            continue
        running_dd = window / window.cummax() - 1
        worst_dd = running_dd.min()
        worst_date = running_dd.idxmin()
        port_dd_then = port_dd.reindex([worst_date], method="nearest").iloc[0]
        rows.append({
            "ticker": t, "buy": d0, "sell": d1, "weeks_held": len(window),
            "worst_individual_dd": worst_dd, "worst_date": worst_date,
            "portfolio_dd_then": port_dd_then,
        })

    out = pd.DataFrame(rows)
    flagged = out[(out["worst_individual_dd"] <= INDIVID_DD_THRESHOLD)
                  & (out["portfolio_dd_then"] > PORTFOLIO_DD_CEILING)]
    severe_all = out[out["worst_individual_dd"] <= INDIVID_DD_THRESHOLD]

    print(f"[dd_floor] {len(out)} hållperioder med mätbar drawdown.")
    print(f"[dd_floor] {len(severe_all)} ({100*len(severe_all)/max(len(out),1):.1f}%) hade en individuell "
          f"drawdown <= {INDIVID_DD_THRESHOLD:.0%} NÅGON GÅNG under hållperioden.")
    print(f"[dd_floor] Av dessa: {len(flagged)} ({100*len(flagged)/max(len(severe_all),1):.1f}% av de svåra) "
          f"inträffade medan portföljen var grundare än {PORTFOLIO_DD_CEILING:.0%} DD "
          f"(Drawdown Guard skulle ALDRIG reagerat).\n")

    if len(flagged):
        print("=" * 90)
        print(f"Flaggade fall (individ <= {INDIVID_DD_THRESHOLD:.0%}, portfölj > {PORTFOLIO_DD_CEILING:.0%})")
        print("=" * 90)
        for _, r in flagged.sort_values("worst_individual_dd").head(25).iterrows():
            print(f"  {r['ticker']:<14} köpt {r['buy'].date()} sålt {r['sell'].date()} "
                  f"({r['weeks_held']}v): individ-DD={r['worst_individual_dd']:+.1%} "
                  f"@ {r['worst_date'].date()} (portfölj-DD då={r['portfolio_dd_then']:+.1%})")
        if len(flagged) > 25:
            print(f"  ... och {len(flagged) - 25} till.")

    print("\n[dd_floor] Klart.")


if __name__ == "__main__":
    main()
