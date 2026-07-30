"""
tune_qualified_holder_otto_combined.py – [EDGE-12] EN sammanhållen backtest
av lager 3-6 ur docs/CONDITIONAL_MODEL_AUDIT.md:s "Prioriterade kombination"
(EDGE_RISK_SCENARIO_TESTKO.md Tier 2 #12). Lager 1-2 (challenger-modell +
meta-ranking) UTESLUTNA på användarens uttryckliga beslut 2026-07-30 - ingen
källkod kvar för meta-ranking-lagret i den här sandlådan, se
UTVECKLINGSLOGG.

Lager som IST kombineras, ovanpå BEFINTLIGA produktionssignaler
(results/signals.csv, ren LambdaRank-baslinje):
  3. Ordinarie topp-N köps alltid (= MomentumBacktester:s existerande
     beteende, oförändrat - detta ÄR baslinjen i A/B:et).
  4. Qualified holder: en tidigare innehavd aktie som just fallit ur
     topp-N vid en ombalansering får ligga kvar EXTRA (utöver kärnans N
     platser) om trenden är intakt (pris > SMA20 OCH 26v-avkastning slår
     ett likaviktat universumindex) - samma kriterium som
     qualified_holder_portfolio_audit.py, empiriskt validerat där.
  5. Otto-high blockerar EXTRA-platsen: om aktien SAMTIDIGT handlas över
     sin egen historiska Börsvärde/EBIT(DA)-percentil (Otto-metoden, #25,
     redan kausalt implementerad i backtest/integrated_backtest.py::
     _build_otto_panel - återanvänds rakt av, ingen ny kod) nekas den
     extraplatsen trots intakt trend.
  6. Rapportoffset +8-14d: REN LOGGNING i produktionen (påverkar inget
     förrän liveutfall mognat, enligt sin egen postbeskrivning) - bidrar
     därför INGENTING till en backtest per definition, medvetet UTESLUTEN
     ur simuleringen (inte en förbisedd lucka).

VIKTIG SKALJUSTERING (användarens beslut 2026-07-30, efter att en
konceptkrock upptäcktes): den ursprungliga "qualified holder"-revisionen
validerade en TIDSGRÄNS på 4 VECKOR under en VECKOVIS ombalanseringstakt.
Storbolagssegmentets FAKTISKA produktionstakt är REBALANCE_WEEKS=52 (en
ombalansering/år) - "4 veckor" är då nästan meningslöst (bara ETT tillfälle
per år att ens falla ur topp-N). Tolkat om till KONCEPTET snarare än
bokstaven: en kvalificerad avhoppare får ligga kvar till NÄSTA
SCHEMALAGDA OMBALANSERING (inte en fast 4-veckorstimer), då den omprövas
på nytt mot samma kriterier med FÄRSK marknadsdata - naturligt kausalt,
kräver ingen separat utgångsdatum-bokföring.

Extraplatser TAR INTE kapital från kärnans N ordinarie platser - de läggs
till ADDITIVT (portföljen blir marginellt MER investerad de veckor
extraplatser är aktiva, aldrig mindre) - matchar "topp-N köps alltid,
oförändrat" + "extra innehav" i revisionens egen ordalydelse.

    /opt/momentum/venv/bin/python3 tune_qualified_holder_otto_combined.py [large|small]
"""
import sys
sys.path.insert(0, ".")
import config

import numpy as np
import pandas as pd

from backtest.backtester import MomentumBacktester
from backtest.integrated_backtest import IntegratedBacktester


class QualifiedHolderOttoBacktester(IntegratedBacktester):
    """Lager 4+5: qualified-holder-förlängning (till nästa ombalansering),
    blockerad av Otto-high. Lager 1-3/6 av (se moduldocstring)."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, hold_fund_enabled=False, insider_enabled=False,
            sellwatch_enabled=False, **kwargs,
        )
        self.n_extra_slots_used = 0   # diagnostik
        self.n_otto_blocked = 0       # diagnostik: hade annars kvalificerat

    def _build_close_panel(self, dates) -> None:
        # Basklassen (IntegratedBacktester) bygger bara _below_sma/_idx_level/
        # _otto_high_panel om sellwatch_enabled - vi vill ha dem ändå, så
        # hoppar förbi den och replikerar exakt samma byggsteg.
        MomentumBacktester._build_close_panel(self, dates)
        tickers = list(self.prices.keys())
        w = int(getattr(config, "EXIT_SMA_WEEKS", 20))
        self._below_sma = (self._close_panel < self._close_panel.rolling(
            w, min_periods=max(w // 2, 5)).mean())
        self._idx_level = (1 + self._close_panel.pct_change().mean(axis=1).fillna(0)).cumprod()
        self._otto_high_panel = self._build_otto_panel(dates, tickers)

    def _trend_intact(self, ticker: str, date) -> bool:
        if ticker not in self._below_sma.columns:
            return False
        try:
            below = bool(self._below_sma.at[date, ticker])
        except Exception:
            return False
        if below:
            return False
        h_ret = self._trailing_return(ticker, date, 26)
        idx_ret = self._index_trailing_return(date, 26)
        if h_ret is None or idx_ret is None:
            return False
        return (h_ret - idx_ret) > 0

    def _otto_high(self, ticker: str, date) -> bool:
        panel = self._otto_high_panel
        if panel is None or ticker not in panel.columns:
            return False
        try:
            return bool(panel.at[date, ticker])
        except Exception:
            return False

    def _rebalance(self, date, target_weights, portfolio_value, cash):
        core = set(target_weights.keys())
        dropped = set(self._portfolio.keys()) - core
        extended = dict(target_weights)
        eq_weight = (sum(target_weights.values()) / len(target_weights)) if target_weights else 0.0
        for ticker in dropped:
            if not self._trend_intact(ticker, date):
                continue
            if self._otto_high(ticker, date):
                self.n_otto_blocked += 1
                continue
            extended[ticker] = eq_weight   # additiv extraplats, samma vikt som en kärnposition
            self.n_extra_slots_used += 1
        return super()._rebalance(date, extended, portfolio_value, cash)


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg = config.SEGMENTS[segment]
    rd = config.anchor(seg["results_dir"])
    sig_path = f"{rd}/signals.csv"
    print(f"[combined] Läser {sig_path} (befintlig produktionsmodell, ingen omträning)...")
    sig = pd.read_csv(sig_path, parse_dates=["Date"]).set_index("Date").sort_index()

    from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    holdout_start = sig.index.unique().sort_values()[-config.HOLDOUT_WEEKS] \
        if len(sig.index.unique()) > config.HOLDOUT_WEEKS else None

    print("[combined] Baseline (MomentumBacktester, lager 3 = oförändrat)...")
    bt_base = MomentumBacktester(sig, data)
    bt_base.run()

    print("[combined] Kombinerad variant (lager 4+5: qualified holder + Otto-blockering)...")
    bt_combo = QualifiedHolderOttoBacktester(sig, data)
    bt_combo.run()

    def _pct(stat_dict, key):
        return float(str(stat_dict[key]).rstrip("%")) / 100.0

    print("\n" + "=" * 90)
    print(f"Full backtest ({segment}-segmentet) – baseline vs qualified-holder+Otto-block")
    print("=" * 90)
    for name, bt in (("baseline (lager 3)", bt_base), ("kombinerad (lager 3+4+5)", bt_combo)):
        overall = bt.statistics()
        dev = bt.statistics_for_period(end=holdout_start) if holdout_start is not None else overall
        holdout = bt.statistics_for_period(start=holdout_start) if holdout_start is not None else None
        print(f"  {name:<28}: dev CAGR={_pct(dev,'CAGR'):+.2%} Sharpe={float(dev['Sharpe']):.2f} "
              f"MaxDD={_pct(dev,'Max Drawdown'):.1%} | "
              f"holdout CAGR={_pct(holdout,'CAGR'):+.2%} Sharpe={float(holdout['Sharpe']) if holdout else 0.0:.2f} "
              f"MaxDD={_pct(holdout,'Max Drawdown'):.1%}" if holdout else "")

    print(f"\n[combined] Diagnostik: {bt_combo.n_extra_slots_used} extraplats-tillfällen använda, "
          f"{bt_combo.n_otto_blocked} tillfällen där Otto-high blockerade en annars kvalificerad avhoppare.")
    print("[combined] Klart.")


if __name__ == "__main__":
    main()
