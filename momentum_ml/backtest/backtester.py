"""
backtest/backtester.py – Realistisk walk-forward backtest.

Inkluderar:
  - Transaktionskostnader (courtage + slippage)
  - Veckovis rebalansering
  - Max antal positioner
  - Portföljstatistik: Sharpe, Sortino, Max DD, CAGR, Win rate
"""

import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from typing import Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


# ─────────────────────────────────────────────────────────────────────────────
# Backtester
# ─────────────────────────────────────────────────────────────────────────────

class MomentumBacktester:
    """
    Simulerar portföljhandel vecka för vecka baserat på signals_df.

    signals_df kolumner: Date (index), ticker, pred_signal, position_size
    price_data: {ticker: OHLCV DataFrame}
    """

    def __init__(
        self,
        signals_df: pd.DataFrame,
        price_data: Dict[str, pd.DataFrame],
        initial_capital: float = config.INITIAL_CAPITAL,
        commission:      float = config.COMMISSION,
        slippage:        float = config.SLIPPAGE,
    ):
        self.signals     = signals_df
        self.prices      = price_data
        self.capital     = initial_capital
        self.commission  = commission
        self.slippage    = slippage

        self._portfolio: Dict[str, float] = {}   # {ticker: antal_aktier}
        self._results:   list = []

    # ── Kör backtest ──────────────────────────────────────────────────────────

    def run(self) -> pd.DataFrame:
        """
        Kör hela backtesten. Returnerar daglig portföljvärde-serie.
        """
        dates = self.signals.index.unique().sort_values()
        cash  = self.capital
        peak  = self.capital

        portfolio_values = []

        for date in dates:
            day_signals = self.signals.loc[date]
            if isinstance(day_signals, pd.Series):
                day_signals = day_signals.to_frame().T

            # Beräkna aktuellt portföljvärde
            portfolio_value = cash + self._portfolio_value(date)
            peak = max(peak, portfolio_value)
            drawdown = portfolio_value / peak - 1

            # Önskad allokering
            target_weights = {}
            for _, row in day_signals.iterrows():
                if row["pred_signal"] == 1 and row["position_size"] > 0:
                    target_weights[row["ticker"]] = row["position_size"]

            # Slå ihop kraftigt korrelerade positioner (undvik dold koncentration)
            target_weights = self._correlation_filter(target_weights, date)

            # Begränsa exponering per sektor
            target_weights = self._sector_exposure_filter(target_weights)

            # Normalisera vikter (säkerhet)
            total_w = sum(target_weights.values())
            if total_w > 1.0:
                target_weights = {t: w / total_w for t, w in target_weights.items()}

            # De-leverage vid drawdown
            guard = self._drawdown_guard_factor(drawdown)
            if guard < 1.0:
                target_weights = {t: w * guard for t, w in target_weights.items()}

            # Rebalansera
            cash = self._rebalance(date, target_weights, portfolio_value, cash)

            portfolio_values.append({
                "Date":            date,
                "portfolio_value": cash + self._portfolio_value(date),
                "cash":            cash,
                "n_positions":     len(self._portfolio),
                "drawdown_guard":  guard,
            })

        results = pd.DataFrame(portfolio_values).set_index("Date")
        self._results = results
        return results

    # ── Risk management ──────────────────────────────────────────────────────

    def _drawdown_guard_factor(self, drawdown: float) -> float:
        """
        Skalar ner total exponering linjärt när drawdown (negativt tal,
        t.ex. -0.20 för -20%) passerar DRAWDOWN_GUARD_THRESHOLD, ner till
        DRAWDOWN_GUARD_FLOOR vid 2x tröskeln.
        """
        threshold = config.DRAWDOWN_GUARD_THRESHOLD
        floor     = config.DRAWDOWN_GUARD_FLOOR
        if drawdown >= -threshold:
            return 1.0
        excess = (-drawdown - threshold) / threshold
        return 1.0 - min(excess, 1.0) * (1.0 - floor)

    def _sector_exposure_filter(
        self,
        target_weights: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Skalar ner vikter proportionellt inom en sektor om sektorns
        totalvikt överstiger MAX_SECTOR_EXPOSURE. Tickers som saknas i
        config.SECTOR_MAP grupperas under "Okänd" och begränsas också.
        """
        if not target_weights:
            return target_weights

        sector_totals: Dict[str, float] = {}
        for ticker, w in target_weights.items():
            sector = config.SECTOR_MAP.get(ticker, "Okänd")
            sector_totals[sector] = sector_totals.get(sector, 0.0) + w

        weights = dict(target_weights)
        for sector, total in sector_totals.items():
            if total > config.MAX_SECTOR_EXPOSURE:
                scale = config.MAX_SECTOR_EXPOSURE / total
                for ticker in weights:
                    if config.SECTOR_MAP.get(ticker, "Okänd") == sector:
                        weights[ticker] *= scale

        return weights

    def _correlation_filter(
        self,
        target_weights: Dict[str, float],
        date: pd.Timestamp,
    ) -> Dict[str, float]:
        """
        Om två kandidater har rullande avkastningskorrelation över
        MAX_PAIRWISE_CORRELATION, slå ihop deras vikt på den med störst
        sizing-signal. Förhindrar att Kelly-budgeten i praktiken satsas
        flera gånger på samma underliggande rörelse.
        """
        if len(target_weights) < 2:
            return target_weights

        lookback = config.CORRELATION_LOOKBACK_WEEKS
        returns = {}
        for ticker in target_weights:
            df = self.prices.get(ticker)
            if df is None:
                continue
            hist = df.loc[:date, "Close"].pct_change().dropna().iloc[-lookback:]
            if len(hist) >= lookback // 2:
                returns[ticker] = hist

        if len(returns) < 2:
            return target_weights

        ret_df = pd.DataFrame(returns).dropna()
        if len(ret_df) < lookback // 2:
            return target_weights

        corr = ret_df.corr()
        weights = dict(target_weights)
        dropped = set()

        pairs = [(a, b) for i, a in enumerate(corr.columns)
                 for b in corr.columns[i + 1:]]
        pairs.sort(key=lambda ab: corr.loc[ab[0], ab[1]], reverse=True)

        for a, b in pairs:
            if a in dropped or b in dropped:
                continue
            if corr.loc[a, b] > config.MAX_PAIRWISE_CORRELATION:
                loser  = a if weights.get(a, 0) <= weights.get(b, 0) else b
                winner = b if loser == a else a
                weights[winner] = weights.get(winner, 0) + weights.get(loser, 0)
                weights.pop(loser, None)
                dropped.add(loser)

        return weights

    # ── Likviditet & marknadsimpact ──────────────────────────────────────────

    def _avg_dollar_volume(self, ticker: str, date: pd.Timestamp) -> Optional[float]:
        """Genomsnittlig dollarvolym (Close*Volume) över en historisk lookback,
        strikt före `date` för att undvika lookahead."""
        df = self.prices.get(ticker)
        if df is None:
            return None
        hist = df.loc[:date].iloc[:-1].tail(config.LIQUIDITY_LOOKBACK_WEEKS)
        if hist.empty:
            return None
        dollar_vol = (hist["Close"] * hist["Volume"]).mean()
        return float(dollar_vol) if dollar_vol > 0 else None

    def _liquidity_cap(self, ticker: str, date: pd.Timestamp, trade_value: float) -> float:
        """Begränsar storleken på en enskild orderflöde till en andel av ADV."""
        adv = self._avg_dollar_volume(ticker, date)
        if adv is None:
            return trade_value
        max_trade = adv * config.LIQUIDITY_MAX_ADV_FRACTION
        if abs(trade_value) > max_trade:
            return math.copysign(max_trade, trade_value)
        return trade_value

    def _half_spread(self, adv: Optional[float]) -> float:
        """
        Likviditetsberoende halv-spread (bid/ask). Fast courtage+slippage är
        optimistiskt för tunt handlade bolag; här växer spreaden när ADV ligger
        under SPREAD_ADV_REF (spread ~ sqrt(ref/adv)), klippt till [MIN, MAX].
        Saknad ADV behandlas konservativt som den vidaste spreaden.
        """
        if adv is None or adv <= 0:
            return config.SPREAD_MAX
        spread = config.SPREAD_MIN * math.sqrt(config.SPREAD_ADV_REF / adv)
        return float(min(max(spread, config.SPREAD_MIN), config.SPREAD_MAX))

    def _execution_cost_rate(self, ticker: str, date: pd.Timestamp, trade_value: float) -> float:
        """
        Total exekveringskostnad som andel av trade_value: courtage + slippage
        + likviditetsberoende halv-spread + en sqrt-marknadsimpact-term (impact
        skalar med sqrt(trade/ADV), inte linjärt – större ordrar kostar
        proportionellt mer per krona, men konkavt eftersom orderboken fylls på
        över tid).
        """
        adv = self._avg_dollar_volume(ticker, date)
        base = self.commission + self.slippage + self._half_spread(adv)
        if adv is None or adv <= 0:
            return base
        impact = config.MARKET_IMPACT_COEF * math.sqrt(abs(trade_value) / adv)
        impact = min(impact, config.MARKET_IMPACT_MAX)
        return base + impact

    # ── Rebalansering ─────────────────────────────────────────────────────────

    def _rebalance(
        self,
        date: pd.Timestamp,
        target_weights: Dict[str, float],
        portfolio_value: float,
        cash: float,
    ) -> float:
        """Sälj positioner vi inte längre vill ha, köp nya."""

        current_tickers = set(self._portfolio.keys())
        target_tickers  = set(target_weights.keys())

        # Sälj
        for ticker in current_tickers - target_tickers:
            price = self._get_price(ticker, date)
            if price is None:
                continue
            shares = self._portfolio.pop(ticker)
            trade_value = shares * price
            cost_rate = self._execution_cost_rate(ticker, date, trade_value)
            proceeds = trade_value * (1 - cost_rate)
            cash += proceeds

        # Köp / justera
        for ticker, weight in target_weights.items():
            target_value = portfolio_value * weight
            price = self._get_price(ticker, date)
            if price is None:
                continue

            current_shares = self._portfolio.get(ticker, 0)
            current_value  = current_shares * price
            diff_value     = target_value - current_value

            if abs(diff_value) < portfolio_value * 0.005:
                continue   # under 0.5% – rebalansera ej

            diff_value = self._liquidity_cap(ticker, date, diff_value)
            cost_rate = self._execution_cost_rate(ticker, date, diff_value)

            if diff_value > 0:
                # Köp
                cost = diff_value * (1 + cost_rate)
                if cash >= cost:
                    new_shares = diff_value / price
                    self._portfolio[ticker] = current_shares + new_shares
                    cash -= cost
            else:
                # Sälj delvis
                shares_to_sell = (-diff_value) / price
                shares_to_sell = min(shares_to_sell, current_shares)
                proceeds = shares_to_sell * price * (1 - cost_rate)
                self._portfolio[ticker] = current_shares - shares_to_sell
                cash += proceeds
                if self._portfolio[ticker] <= 0:
                    del self._portfolio[ticker]

        return cash

    # ── Hjälpare ──────────────────────────────────────────────────────────────

    def _get_price(self, ticker: str, date: pd.Timestamp) -> Optional[float]:
        df = self.prices.get(ticker)
        if df is None:
            return None
        try:
            idx = df.index.get_indexer([date], method="ffill")[0]
            return float(df.iloc[idx]["Close"]) if idx >= 0 else None
        except Exception:
            return None

    def _portfolio_value(self, date: pd.Timestamp) -> float:
        total = 0.0
        for ticker, shares in self._portfolio.items():
            price = self._get_price(ticker, date)
            if price:
                total += shares * price
        return total

    # ── Statistik ─────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_stats(pv: pd.Series, start_capital: float) -> Dict:
        rets  = pv.pct_change().dropna()
        weeks = len(rets)
        ann   = 52   # veckodata

        cagr      = (pv.iloc[-1] / pv.iloc[0]) ** (ann / weeks) - 1 if weeks > 0 else 0.0
        sharpe    = (rets.mean() / rets.std()) * np.sqrt(ann) if rets.std() > 0 else 0
        neg_rets  = rets[rets < 0]
        sortino   = (rets.mean() / neg_rets.std()) * np.sqrt(ann) if neg_rets.std() > 0 else 0
        dd        = (pv / pv.cummax() - 1)
        max_dd    = dd.min()
        win_rate  = (rets > 0).mean()
        total_ret = pv.iloc[-1] / pv.iloc[0] - 1

        return {
            "total_return":  f"{total_ret:.1%}",
            "CAGR":          f"{cagr:.1%}",
            "Sharpe":        f"{sharpe:.2f}",
            "Sortino":       f"{sortino:.2f}",
            "Max Drawdown":  f"{max_dd:.1%}",
            "Win Rate":      f"{win_rate:.1%}",
            "Weeks":         weeks,
            "Start Capital": f"{start_capital:,.0f}",
            "End Capital":   f"{pv.iloc[-1]:,.0f}",
        }

    def statistics(self) -> Dict:
        if not len(self._results):
            raise RuntimeError("Kör run() först.")
        return self._compute_stats(self._results["portfolio_value"], self.capital)

    def statistics_for_period(
        self,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
    ) -> Dict:
        """
        Statistik för en delperiod av en redan körd backtest (t.ex. en
        frusen holdout-period). OBS: CAGR/Max Drawdown beräknas på
        portföljvärdet inom fönstret som om det vore en egen path – de
        speglar inte nödvändigtvis hela körningens path-beroende drawdown.
        """
        if not len(self._results):
            raise RuntimeError("Kör run() först.")
        pv = self._results["portfolio_value"]
        if start is not None:
            pv = pv.loc[pv.index >= start]
        if end is not None:
            pv = pv.loc[pv.index <= end]
        if len(pv) < 2:
            raise ValueError("För få datapunkter i den angivna perioden.")
        return self._compute_stats(pv, float(pv.iloc[0]))

    def print_statistics(self, stats: Optional[Dict] = None, title: str = "BACKTEST RESULTAT"):
        stats = stats if stats is not None else self.statistics()
        print("\n" + "="*50)
        print(f"  {title}")
        print("="*50)
        for k, v in stats.items():
            print(f"  {k:<20} {v}")
        print("="*50)

    # ── Plot ─────────────────────────────────────────────────────────────────

    def plot(self, save_path: str = "results/backtest.png"):
        if not len(self._results):
            raise RuntimeError("Kör run() först.")

        Path(save_path).parent.mkdir(exist_ok=True, parents=True)
        pv = self._results["portfolio_value"]
        dd = pv / pv.cummax() - 1

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10),
                                              gridspec_kw={"height_ratios": [3, 1, 1]})
        fig.suptitle("ML Momentum Strategy – Backtest", fontsize=14, fontweight="bold")

        # Portföljvärde
        ax1.plot(pv.index, pv.values / 1e6, color="#2196F3", linewidth=1.5)
        ax1.set_ylabel("Portföljvärde (MSEK)")
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

        # Drawdown
        ax2.fill_between(dd.index, dd.values * 100, 0, color="#f44336", alpha=0.6)
        ax2.set_ylabel("Drawdown (%)")
        ax2.grid(True, alpha=0.3)

        # Antal positioner
        ax3.bar(self._results.index, self._results["n_positions"],
                color="#4CAF50", alpha=0.7, width=5)
        ax3.set_ylabel("Positioner")
        ax3.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"[Backtest] Plot sparad: {save_path}")
        plt.show()
