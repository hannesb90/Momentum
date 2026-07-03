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
        self.last_prices: Dict[str, float] = {}   # senast kända pris per ticker (carry-forward)
        self.missing_weeks: Dict[str, int] = {}   # antal steg i rad ett innehav saknat pris
        self._load()

    # ── Persistens ───────────────────────────────────────────────────────────
    def _load(self):
        if self.state_path.exists():
            with open(self.state_path) as f:
                st = json.load(f)
            self.cash      = st.get("cash", self.initial_capital)
            self.holdings  = st.get("holdings", {})
            self.last_date = st.get("last_date")
            self.last_prices = st.get("last_prices", {})
            self.missing_weeks = st.get("missing_weeks", {})

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({
                "cash": self.cash,
                "holdings": self.holdings,
                "last_date": self.last_date,
                "last_prices": self.last_prices,
                "missing_weeks": self.missing_weeks,
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
        """Marknadsvärde av innehaven. Om ett INNEHAV saknar kurs denna körning
        (ticker ej hämtad/utelämnad/data-glapp) värderas det till SENAST KÄNDA pris –
        aldrig till 0. Att nolla en position man fortfarande äger skapade fantom-ras
        (t.ex. −12% på en vecka när ett stort innehav tillfälligt saknade prisdata)."""
        total = 0.0
        for ticker, sh in self.holdings.items():
            df = prices.get(ticker)
            p = self._price_at(df, date) if df is not None else None
            if p and p > 0:
                self.last_prices[ticker] = p          # uppdatera senast kända pris
            else:
                p = self.last_prices.get(ticker)      # bär fram senaste kända pris
            if p and p > 0:
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

        # Spök-bokföring: innehav utan färskt pris räknas per steg. Efter N steg i
        # rad tvångssäljs de på SENAST KÄNDA pris (verklighetens motsvarighet: av-
        # notering/namnbyte hade tvingat en exit). Utan detta fastnar en position
        # vars ticker försvunnit ur datat för evigt – och nollvärderas (fantom-ras).
        limit = int(getattr(config, "PAPER_MISSING_LIQUIDATE_STEPS", 4))
        for ticker in list(self.holdings):
            df = prices.get(ticker)
            fresh = self._price_at(df, date) if df is not None else None
            if fresh and fresh > 0:
                self.missing_weeks.pop(ticker, None)
                continue
            n = self.missing_weeks.get(ticker, 0) + 1
            self.missing_weeks[ticker] = n
            if n >= limit:
                lp = self.last_prices.get(ticker)
                if lp and lp > 0:
                    sh = self.holdings.pop(ticker)
                    self.missing_weeks.pop(ticker, None)
                    self.cash += sh * lp * (1 - self._cost_rate(None))
                    print(f"  [paper] {ticker}: pris saknat {n} steg – tvångssåld "
                          f"på senast kända {lp:.2f}.")
                else:
                    # INGET känt pris: stryk INTE till 0 (det cementerar fantom-
                    # förlusten). Behåll och varna – kör 'diagnose' och laga tickern.
                    print(f"  [paper] {ticker}: pris saknat {n} steg och INGET känt pris – "
                          f"kör 'python backtest/paper_trader.py diagnose' och laga tickern.")

        current = set(self.holdings.keys())
        target  = set(target_weights.keys())

        # Sälj det vi inte längre vill ha (på färskt pris, annars senast kända –
        # tidigare fastnade positionen om priset saknades just säljveckan)
        for ticker in current - target:
            df = prices.get(ticker)
            p = self._price_at(df, date) if df is not None else None
            if p is None:
                p = self.last_prices.get(ticker)
            if p is None or p <= 0:
                continue   # okänt pris – spök-bokföringen ovan tar den till slut
            sh = self.holdings.pop(ticker)
            self.cash += sh * p * (1 - self._cost_rate(self._adv_at(df, date) if df is not None else None))

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
                    self.last_prices[ticker] = p   # känt pris från köpet (carry-forward-frö)
            elif diff < 0:
                sell_sh = min((-diff) / p, self.holdings.get(ticker, 0.0))
                self.holdings[ticker] = self.holdings.get(ticker, 0.0) - sell_sh
                self.cash += sell_sh * p * (1 - rate)
                self.last_prices[ticker] = p
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


# ── Diagnos: vilken position orsakar ett fantom-ras? ─────────────────────────
def diagnose(segment: str = "large") -> None:
    """Visar pappersportföljens innehav och vilka som SAKNAR pris i cachen –
    dvs. exakt vad som nollvärderats och skapat t.ex. '−12% på en vecka'.

        python backtest/paper_trader.py diagnose         # storbolag
        python backtest/paper_trader.py diagnose small   # småbolag
    """
    seg = config.SEGMENTS.get(segment) or {}
    rd = seg.get("results_dir", config.RESULTS_DIR)
    pt = PaperTrader(results_dir=rd)
    if not pt.holdings:
        print(f"[diagnose] {segment}: inga innehav i {pt.state_path} – inget att diagnosticera.")
        return
    from data.data_loader import fetch_weekly_data
    data = fetch_weekly_data(list(pt.holdings), use_cache=True)
    now = pd.Timestamp.now().normalize()
    print(f"\n  PAPPERSPORTFÖLJ ({segment}) – {len(pt.holdings)} innehav, kassa {pt.cash:,.0f} kr".replace(",", " "))
    print(f"  {'ticker':<14}{'andelar':>10}{'pris':>9}{'prisdatum':>12}{'värde':>12}   status")
    valued, ghost_value = 0.0, 0.0
    for t, sh in sorted(pt.holdings.items()):
        df = data.get(t)
        p = PaperTrader._price_at(df, now) if df is not None and not df.empty else None
        pdate = str(df.index.max().date()) if df is not None and not df.empty else "–"
        lp = pt.last_prices.get(t)
        if p and p > 0:
            v = sh * p
            valued += v
            stale = (now - df.index.max()).days > 14
            status = "OK" if not stale else f"GAMMALT PRIS ({pdate})"
            print(f"  {t:<14}{sh:>10.2f}{p:>9.2f}{pdate:>12}{v:>12,.0f}   {status}".replace(",", " "))
        else:
            v = sh * lp if lp else 0.0
            ghost_value += v
            status = (f"SPÖKE – inget pris i datat (senast kända {lp:.2f} → {v:,.0f} kr)".replace(",", " ")
                      if lp else "SPÖKE – inget pris ALLS (nollvärderad!)")
            print(f"  {t:<14}{sh:>10.2f}{'–':>9}{pdate:>12}{'?':>12}   {status}")
    total_cf = pt.cash + valued + ghost_value
    print(f"\n  Kassa + prissatta innehav          : {pt.cash + valued:>12,.0f} kr".replace(",", " "))
    print(f"  + spöken till senast kända pris    : {ghost_value:>12,.0f} kr".replace(",", " "))
    print(f"  = korrekt portföljvärde            : {total_cf:>12,.0f} kr "
          f"({total_cf / pt.initial_capital - 1:+.1%} sedan start)".replace(",", " "))
    if pt.ledger_path.exists():
        led = pd.read_csv(pt.ledger_path)
        if len(led):
            last = led.iloc[-1]
            print(f"  Liggarens senaste rad ({last['date']})  : {last['paper_value']:>12,.0f} kr "
                  f"({last['return_since_start']:+.1%})".replace(",", " "))
            diff = total_cf - float(last["paper_value"])
            if abs(diff) > 0.005 * pt.initial_capital:
                print(f"  → LIGGAREN AVVIKER {diff:+,.0f} kr – fantomvärdering bekräftad. "
                      f"Nästa körning skriver rätt rad (carry-forward-fixen).".replace(",", " "))


if __name__ == "__main__":
    _args = [a for a in sys.argv[1:] if a != "diagnose"]
    diagnose(_args[0] if _args else "large")
