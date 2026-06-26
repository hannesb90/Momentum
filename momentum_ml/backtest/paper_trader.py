"""
backtest/paper_trader.py – Framåtblickande pappershandel (live track record).

En backtest är historik som modellen delvis sett. Det enda ärliga måttet på
om signalerna fungerar *framåt* är en tidsstämplad track record som byggs upp
i realtid, vecka för vecka, utan efterhandsjusteringar. Den här modulen
persisterar en pappersportfölj och stegar den ETT steg per körning utifrån
de senaste live-signalerna:

  - results/paper_state.json : {cash, holdings, last_date}  (portföljens tillstånd)
  - results/paper_ledger.csv : en rad per registrerad vecka (date, paper_value, ...)

Kostnader (courtage + slippage + likviditetsberoende halv-spread) tas ut vid
ombalansering så att liggaren speglar nettoresultat. Marknadsimpact utelämnas
medvetet – pappersordrarna är hypotetiska och små. Track recorden börjar tom
och växer för varje körning; den blir meningsfull först efter några veckor.
"""

import json
import math
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


class PaperTrader:
    def __init__(
        self,
        results_dir: str = config.RESULTS_DIR,
        initial_capital: float = config.INITIAL_CAPITAL,
    ):
        self.state_path  = Path(results_dir) / "paper_state.json"
        self.ledger_path = Path(results_dir) / "paper_ledger.csv"
        self.initial_capital = initial_capital
        self.cash: float = initial_capital
        self.holdings: Dict[str, float] = {}
        self.last_date: Optional[str] = None
        self._load()

    # ── Persistens ───────────────────────────────────────────────────────────
    def _load(self):
        if self.state_path.exists():
            with open(self.state_path) as f:
                st = json.load(f)
            self.cash      = st.get("cash", self.initial_capital)
            self.holdings  = st.get("holdings", {})
            self.last_date = st.get("last_date")

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({
                "cash": self.cash,
                "holdings": self.holdings,
                "last_date": self.last_date,
                "initial_capital": self.initial_capital,
            }, f, indent=2)

    # ── Hjälpare ─────────────────────────────────────────────────────────────
    @staticmethod
    def _price_at(df: pd.DataFrame, date: pd.Timestamp) -> Optional[float]:
        try:
            idx = df.index.get_indexer([date], method="ffill")[0]
            return float(df.iloc[idx]["Close"]) if idx >= 0 else None
        except Exception:
            return None

    @staticmethod
    def _adv_at(df: pd.DataFrame, date: pd.Timestamp) -> Optional[float]:
        hist = df.loc[:date].iloc[:-1].tail(config.LIQUIDITY_LOOKBACK_WEEKS)
        if hist.empty:
            return None
        adv = (hist["Close"] * hist["Volume"]).mean()
        return float(adv) if adv > 0 else None

    def _cost_rate(self, adv: Optional[float]) -> float:
        """Courtage + slippage + likviditetsberoende halv-spread (utan impact)."""
        if adv is None or adv <= 0:
            spread = config.SPREAD_MAX
        else:
            spread = min(max(config.SPREAD_MIN * math.sqrt(config.SPREAD_ADV_REF / adv),
                             config.SPREAD_MIN), config.SPREAD_MAX)
        return config.COMMISSION + config.SLIPPAGE + spread

    def _market_value(self, prices: Dict[str, pd.DataFrame], date: pd.Timestamp) -> float:
        total = 0.0
        for ticker, sh in self.holdings.items():
            df = prices.get(ticker)
            if df is None:
                continue
            p = self._price_at(df, date)
            if p:
                total += sh * p
        return total

    # ── Ett steg ─────────────────────────────────────────────────────────────
    def step(
        self,
        date: pd.Timestamp,
        target_weights: Dict[str, float],
        prices: Dict[str, pd.DataFrame],
    ) -> Optional[Dict]:
        """
        Stegar pappersportföljen till `date` enligt målvikterna. Returnerar
        radens dict (eller None om datumet redan är registrerat).
        """
        date = pd.Timestamp(date)
        if self.last_date is not None and date <= pd.Timestamp(self.last_date):
            return None   # redan registrerat, undvik dubbletter/lookahead

        portfolio_value = self.cash + self._market_value(prices, date)

        current = set(self.holdings.keys())
        target  = set(target_weights.keys())

        # Sälj det vi inte längre vill ha
        for ticker in current - target:
            df = prices.get(ticker)
            p = self._price_at(df, date) if df is not None else None
            if p is None:
                continue
            sh = self.holdings.pop(ticker)
            self.cash += sh * p * (1 - self._cost_rate(self._adv_at(df, date)))

        # Köp/justera mot målvikt
        for ticker, w in target_weights.items():
            df = prices.get(ticker)
            p = self._price_at(df, date) if df is not None else None
            if p is None or p <= 0:
                continue
            target_value  = portfolio_value * w
            current_value = self.holdings.get(ticker, 0.0) * p
            diff = target_value - current_value
            if abs(diff) < portfolio_value * 0.005:
                continue
            rate = self._cost_rate(self._adv_at(df, date))
            if diff > 0:
                # Köp upp till målet, men aldrig mer än kontanterna räcker till
                # (partiell fyllnad i stället för att hoppa hela ordern – med
                # kostnader kan flera fullviktade köp annars överstiga kapitalet).
                spend = min(diff * (1 + rate), self.cash)
                if spend > 0:
                    bought_value = spend / (1 + rate)
                    self.holdings[ticker] = self.holdings.get(ticker, 0.0) + bought_value / p
                    self.cash -= spend
            elif diff < 0:
                sell_sh = min((-diff) / p, self.holdings.get(ticker, 0.0))
                self.holdings[ticker] = self.holdings.get(ticker, 0.0) - sell_sh
                self.cash += sell_sh * p * (1 - rate)
                if self.holdings[ticker] <= 1e-9:
                    self.holdings.pop(ticker, None)

        paper_value = self.cash + self._market_value(prices, date)
        self.last_date = date.isoformat()
        self._save()

        row = {
            "date":        date.date().isoformat(),
            "paper_value": round(paper_value, 2),
            "cash":        round(self.cash, 2),
            "n_positions": len(self.holdings),
            "return_since_start": round(paper_value / self.initial_capital - 1, 4),
        }
        self._append_ledger(row)
        return row

    def _append_ledger(self, row: Dict):
        df_row = pd.DataFrame([row])
        if self.ledger_path.exists():
            df_row.to_csv(self.ledger_path, mode="a", header=False, index=False)
        else:
            df_row.to_csv(self.ledger_path, index=False)
