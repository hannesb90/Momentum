"""
tune_isk_derisk_ranked.py – [SCN-REBAL-1] ISK-skatteuttagets tvångsförsäljning:
proportionell (dagens `_derisk_to_cap`-mekanik) vs rankningsbaserad ("sälj
svagast rankade innehav först"), EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #17.

`config.ISK_TAX_ENABLED=False` som standard - detta test SÄTTER PÅ den
explicit (som `tune_isk_tax.py` redan gör) för att kunna jämföra. Bara
sättet KAPITALET TAS UT skiljer sig mellan varianterna - själva skattebeloppet
(lagstadgad formel) är identiskt.

    proportionell – nuvarande `_derisk_to_cap`: skalar ALLA innehav lika
                    mycket ner mot taket, oavsett rankning.
    rankad        – säljer de SVAGAST rankade innehaven FÖRST (helt, tills
                    taket är nått), lämnar starkare innehav orörda så
                    länge som möjligt.

    /opt/momentum/venv/bin/python3 tune_isk_derisk_ranked.py
"""
import sys
sys.path.insert(0, ".")
import config
config.ISK_TAX_ENABLED = True   # måste sättas FÖRE MomentumBacktester importeras/körs

import pandas as pd

from backtest.backtester import MomentumBacktester
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe


class RankedIskBacktester(MomentumBacktester):
    """Ärver ALLT från basklassen (inkl. _derisk_to_cap för Drawdown Guard,
    OFÖRÄNDRAT) - byter bara ut _isk_pay_tax:s TVÅNGSFÖRSÄLJNINGSSTEG mot en
    rankningsbaserad variant i stället för det ärvda _derisk_to_cap-anropet."""

    def _isk_pay_tax(self, date, cash):
        if not getattr(config, "ISK_TAX_ENABLED", False):
            return cash
        year = date.year
        marks = [v for (y, q), v in self._isk_quarters.items() if y == year]
        if not marks:
            return cash
        kapitalunderlag = sum(marks) / len(marks)

        slr_table = getattr(config, "ISK_SLR_BY_YEAR", {})
        floor = float(getattr(config, "ISK_SCHABLON_FLOOR", 0.0125))
        slr = slr_table.get(year - 1)
        schablon = max(slr / 100.0 + 0.01, floor) if slr is not None else floor
        fribelopp = float(getattr(config, "ISK_FRIBELOPP_BY_YEAR", {}).get(year, 0.0))
        taxable_base = max(0.0, kapitalunderlag - fribelopp)
        tax_rate = float(getattr(config, "ISK_TAX_RATE", 0.30))
        tax_owed = taxable_base * schablon * tax_rate
        if tax_owed <= 0:
            return cash

        if cash < tax_owed and self._portfolio:
            shortfall = tax_owed - cash
            # Sälj HELA innehav, svagast rankade FÖRST, tills bristen är täckt.
            if date in self.signals.index:
                day = self.signals.loc[[date]] if isinstance(self.signals.loc[date], pd.Series) else self.signals.loc[date]
                rank_of = dict(zip(day["ticker"], day.get("selection_rank", pd.Series(dtype=float))))
            else:
                rank_of = {}
            order = sorted(self._portfolio.keys(), key=lambda t: rank_of.get(t, -1e9))
            for t in order:
                if shortfall <= 0:
                    break
                price = self._get_price(t, date)
                if price is None:
                    continue
                shares = self._portfolio.pop(t)
                trade_value = shares * price
                cost_rate = self._execution_cost_rate(t, date, trade_value)
                proceeds = trade_value * (1 - cost_rate)
                cash += proceeds
                shortfall -= proceeds
                self._peak_price.pop(t, None)
        return cash - min(tax_owed, max(cash, 0.0))


def main():
    seg = config.SEGMENTS["large"]
    sig = pd.read_csv(f"{seg['results_dir']}/signals.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    holdout_start = sig.index.unique().sort_values()[-config.HOLDOUT_WEEKS] \
        if len(sig.index.unique()) > config.HOLDOUT_WEEKS else None

    def _pct(stat_dict, key):
        return float(str(stat_dict[key]).rstrip("%")) / 100.0

    print("[isk_ranked] proportionell (baslinje, oförändrad _derisk_to_cap)...")
    bt_prop = MomentumBacktester(sig, data)
    bt_prop.run()

    print("[isk_ranked] rankningsbaserad (svagast rankade säljs helt först)...")
    bt_rank = RankedIskBacktester(sig, data)
    bt_rank.run()

    print("\n" + "=" * 90)
    print("Full backtest (large, ISK_TAX_ENABLED=True) – proportionell vs rankningsbaserad tvångsförsäljning")
    print("=" * 90)
    for name, bt in (("proportionell", bt_prop), ("rankningsbaserad", bt_rank)):
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        print(f"  {name:<18}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%}")

    print("\n[isk_ranked] Klart.")


if __name__ == "__main__":
    main()
