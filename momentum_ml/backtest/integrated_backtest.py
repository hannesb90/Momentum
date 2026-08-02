"""
backtest/integrated_backtest.py – IntegratedBacktester: bakar ihop de
tidigare separat validerade "kaksmulorna" (härdighets-bonus, modellens
riktkurs/Otto-metoden #25, insynsklustring #23, säljvaktens
eskaleringsstege) i EN walk-forward-backtest, i stället för att bara mäta
kärnmodellens rena pris→signal-steg (MomentumBacktester).

BAKGRUND (docs/UTVECKLINGSLOGG.md #26): portfolio.py:s köp-/säljvakt
(_hold_fund_pctl, _takeprofit m.fl.) körs bara mot SENASTE ögonblicksbild
av CSV:er (ingen historik sparas) – de har alltså ALDRIG körts genom en
riktig backtest. Den här modulen rekonstruerar de signaler som GÅR att
göra point-in-time (utan lookahead) och lägger dem ovanpå
MomentumBacktester, oförändrad i övrigt.

VAD SOM ÄR MED (och hur, allt causalt – bara data känd <= datumet används):
  · Härdighets-bonus (ROE/tillväxt/skuld) vid ENTRY – merge_asof mot de tre
    fundamenta-CSV:erna, samma mönster som validerade kompositen
    (tune_hold_forever_fundamentals.py, 2026-07-22).
  · Modellens riktkurs (Otto-metoden, #25) – expanderande eget band (bara
    år FÖRE innevarande år), cache/otto_band/*.pkl (ingen ny nätåtkomst
    för redan täckta bolag).
  · Insynsköp/-sälj-nettoklustring – FI:s fulla, evigt cachade register
    (samma källa som #23) – regulatorisk historik ändras aldrig i
    efterhand, så inget lookahead-problem här.
  · Säljvaktens pris-härledda bekräftelser (melt-up, gap-vs-index,
    SMA20-trendbrott, modellen har släppt bolaget) – rent ur OHLCV/
    signals som backtestern redan har.

VAD SOM INTE ÄR MED (och varför) – förblir live-only, se #26:
  · Offentlig riktkurs (analytiker-medel) – Yahoo ger bara DAGENS värde.
  · LLM/mjukt kvalitetsbetyg – kräver en läsning VID DEN TIDPUNKTEN.
  · MFN-textflaggor (röda flaggor, uppdragsanalys) – samma skäl.
De append-only-CSV:er som startats 2026-07-23 (public_target_price.csv,
quality_shortlist.csv) ger om ~3 månader nog historik för en riktig
framåt-validering av dessa två.

Tre lager, var för sig av-/påslagbara (default alla PÅ). Med alla tre AV
ska resultatet vara BIT-FÖR-BIT identiskt med MomentumBacktester – se
tune_integrated_backtest.py:s sanity-check.

    from backtest.integrated_backtest import IntegratedBacktester
    bt = IntegratedBacktester(signals_df, price_data)
    bt.run()
"""
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import numpy as np
import pandas as pd

import config
from backtest.backtester import MomentumBacktester
from tune_otto_valuation_band import annual_multiples, MIN_PROFITABLE_YEARS, HIGH_PCT
from altdata.fi_insynsregistret import fetch_issuer_transactions, BUY_CHARACTERS, SELL_CHARACTERS
from tune_insider_gap_fi import _clean_name

INSIDER_CLUSTER_DAYS = 90
FUND_MERGE_TOLERANCE_DAYS = 400   # årsrapporter, samma tolerans som tune_hold_forever_fundamentals.py


class IntegratedBacktester(MomentumBacktester):
    """Se modulens docstring. Ärver hela kostnads-/likviditets-/regim-
    motorn oförändrad – lägger bara till entry-rerank + en säljvakt."""

    def __init__(
        self,
        signals_df: pd.DataFrame,
        price_data: Dict[str, pd.DataFrame],
        *,
        hold_fund_enabled: bool = True,
        insider_enabled: bool = True,
        sellwatch_enabled: bool = True,
        sellwatch_partial_frac: float = 0.5,
        **kwargs,
    ):
        super().__init__(signals_df, price_data, **kwargs)
        self.hold_fund_enabled = hold_fund_enabled
        self.insider_enabled = insider_enabled
        self.sellwatch_enabled = sellwatch_enabled
        self.sellwatch_partial_frac = sellwatch_partial_frac

        # Positions-bokföring säljvakten behöver men basklassen inte har:
        # snittinköpspris (för att avgöra ORELISERAD VINST, säljvaktens
        # armeringsvillkor) och vilka innehav som redan fått sin
        # ENGÅNGS-nivå2-delförsäljning (annars skulle den halvera
        # positionen varje vecka villkoren håller, inte en gång per
        # innehavsperiod).
        self._cost_basis: Dict[str, float] = {}
        self._level2_done: set = set()
        self._sellwatch_last_date = None

        # Lazy: byggs EN gång i _build_close_panel (körs först i run()),
        # så self._close_panel/self._get_price finns tillgängliga.
        self._hardiness_panel: Optional[pd.DataFrame] = None
        self._otto_high_panel: Optional[pd.DataFrame] = None
        self._insider_panel: Optional[pd.DataFrame] = None
        self._idx_level = None
        self._pred_signal_panel: Optional[pd.DataFrame] = None

    # ── Hook: körs först i run(), lägger till panelbygge + entry-rerank ────

    def _build_close_panel(self, dates) -> None:
        super()._build_close_panel(dates)
        tickers = list(self.prices.keys())

        if self.sellwatch_enabled:
            if self._below_sma is None:
                # Basklassen bygger bara detta om ASYMMETRIC_EXIT/event-läge
                # är på (se _build_close_panel:s docstring) – säljvakten
                # behöver trendbrotts-panelen oavsett den configen.
                w = int(getattr(config, "EXIT_SMA_WEEKS", 20))
                sma = self._close_panel.rolling(w, min_periods=max(w // 2, 5)).mean()
                self._below_sma = (self._close_panel < sma)
            self._idx_level = (1 + self._close_panel.pct_change().mean(axis=1).fillna(0)).cumprod()
            ps = self.signals.reset_index()
            idx_name = ps.columns[0]
            self._pred_signal_panel = ps.pivot_table(
                index=idx_name, columns="ticker", values="pred_signal", aggfunc="last")

        if self.hold_fund_enabled:
            self._hardiness_panel = self._build_hardiness_panel(dates, tickers)

        if self.sellwatch_enabled or self.insider_enabled:
            self._insider_panel = self._build_insider_panel(dates, tickers)

        if self.sellwatch_enabled:
            self._otto_high_panel = self._build_otto_panel(dates, tickers)

        if self.hold_fund_enabled or self.insider_enabled:
            self.signals = self._apply_entry_adjustments(self.signals)

    # ── Entry-rerank (härdighet + insynsköp) ────────────────────────────────

    def _lookup(self, panel: Optional[pd.DataFrame], sig: pd.DataFrame) -> pd.Series:
        """Slår upp panel[date, ticker] för varje rad i `sig` (Date-index +
        ticker-kolumn) – panel.stack() + MultiIndex-reindex, snabbare än en
        rad-för-rad-loop över hela signals_df."""
        if panel is None:
            return pd.Series(np.nan, index=sig.index)
        # pandas >= 2.1: stack() bevarar NaN-rader per default (ingen
        # dropna-parameter längre - äldre dropna=False motsvarar nu default).
        long = panel.stack()
        long.index.names = ["_d", "_t"]
        mi = pd.MultiIndex.from_arrays([sig.index, sig["ticker"]], names=["_d", "_t"])
        return pd.Series(long.reindex(mi).values, index=sig.index)

    def _apply_entry_adjustments(self, signals: pd.DataFrame) -> pd.DataFrame:
        """
        Härdighets- och insynsköp-bonus vid ENTRY – samma tröskellogik som
        portfolio.py::_unified_rank/_hold_fund_pctl/_composite_score (terciler
        ≥2/3 resp. <1/3 för härdighet, netto ≥2 90d för insynsköp). Additiv
        justering av position_size (kalender-läget bygger target_weights
        direkt av den) OCH prob_up (event-lägets _event_rebalance rankar på
        prob_up/prob_raw i stället, se backtester.py) – nedskalad på prob_up
        så den bara nudgar rankningen, aldrig utanför [0,1]. Ren
        rankningsjustering, ingen ny handelsmekanik.
        """
        sig = signals.copy()
        hold_bonus = float(getattr(config, "PORTFOLIO_HOLD_FUND_BONUS", 0.08))
        ins_bonus = float(getattr(config, "PORTFOLIO_INSIDER_BONUS", 0.05))
        max_pos = float(getattr(config, "MAX_POSITION", 0.20))
        bump = pd.Series(0.0, index=sig.index)

        if self.hold_fund_enabled and self._hardiness_panel is not None:
            hp = self._lookup(self._hardiness_panel, sig)
            bump = bump + np.where(hp >= 2 / 3, hold_bonus, np.where(hp < 1 / 3, -hold_bonus, 0.0))

        if self.insider_enabled and self._insider_panel is not None:
            ins = self._lookup(self._insider_panel, sig)
            bump = bump + np.where(ins >= 2, ins_bonus, 0.0)

        if "position_size" in sig.columns:
            sig["position_size"] = (sig["position_size"] + bump).clip(lower=0.0, upper=max_pos)
        if "prob_up" in sig.columns:
            sig["prob_up"] = (sig["prob_up"] + bump * 0.5).clip(lower=0.0, upper=1.0)
        return sig

    # ── Point-in-time-rekonstruktion ─────────────────────────────────────

    def _load_fundamentals_all_segments(self) -> pd.DataFrame:
        """Samma tre fundamenta-CSV:er/kolumnlogik som
        tune_hold_forever_fundamentals.py::_load_fundamentals – generaliserad
        till ALLA segment (large+small), inte bara "large"."""
        frames = []
        for seg in config.SEGMENTS.values():
            rd = config.anchor(seg.get("results_dir", ""))
            for fname in ("fundamentals_from_mfn.csv", "fundamentals_from_pdf.csv",
                          "fundamentals_from_avanza.csv"):
                p = Path(rd) / fname
                if not p.exists():
                    continue
                try:
                    frames.append(pd.read_csv(p))
                except Exception:  # noqa: BLE001
                    pass
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        df["published"] = pd.to_datetime(df["published"], errors="coerce", utc=True).dt.tz_localize(None)
        df = df.dropna(subset=["ticker", "published"])

        def col(name):
            return pd.to_numeric(df[name], errors="coerce") if name in df.columns else pd.Series(np.nan, index=df.index)

        roe = col("roe_avanza").where(lambda s: s.notna(), col("roe_pct"))
        rev, rev_prior = col("revenue"), col("revenue_prior")
        growth = (rev - rev_prior) / rev_prior.abs()
        growth[(rev_prior == 0) | rev_prior.isna() | rev.isna()] = np.nan
        liab, eq = col("liabilities"), col("equity")
        de_fallback = (liab / eq).where((eq > 0) & liab.notna())
        debt_eq = col("debt_equity_avanza").where(lambda s: s.notna(), de_fallback)

        out = pd.DataFrame({"ticker": df["ticker"], "published": df["published"],
                            "roe": roe, "growth": growth, "debt_eq": debt_eq})
        out = out.dropna(subset=["roe", "growth", "debt_eq"], how="all")
        return out.sort_values("published")

    def _build_hardiness_panel(self, dates, tickers) -> pd.DataFrame:
        """
        Härdighets-komposit point-in-time: EGET metrikvärde per bolag känt
        <= datumet (merge_asof backward, ingen lookahead på bolagsnivå).
        Tvärsnitts-percentilen räknas PER DATUM över bara de bolag som redan
        har ett känt värde det datumet – kausal även i tvärsnittet.
        """
        fund = self._load_fundamentals_all_segments()
        if fund.empty:
            return pd.DataFrame(index=dates, columns=tickers, dtype=float)

        date_df = pd.DataFrame({"asof": pd.DatetimeIndex(dates)})
        frames = []
        for t, g in fund.groupby("ticker"):
            g = g.sort_values("published")
            m = pd.merge_asof(date_df, g, left_on="asof", right_on="published",
                               direction="backward",
                               tolerance=pd.Timedelta(days=FUND_MERGE_TOLERANCE_DAYS))
            m["ticker"] = t
            frames.append(m[["asof", "ticker", "roe", "growth", "debt_eq"]])
        panel = pd.concat(frames, ignore_index=True)

        def _score(g: pd.DataFrame) -> pd.Series:
            r = pd.DataFrame(index=g.index)
            r["roe"] = g["roe"].rank(pct=True)
            r["growth"] = g["growth"].rank(pct=True)
            r["debt"] = (-g["debt_eq"]).rank(pct=True)
            n_avail = r.notna().sum(axis=1)
            return r.mean(axis=1).where(n_avail >= 2)

        panel["score"] = panel.groupby("asof", group_keys=False).apply(_score)
        wide = panel.pivot(index="asof", columns="ticker", values="score")
        return wide.reindex(index=dates, columns=tickers)

    def _build_otto_panel(self, dates, tickers) -> pd.DataFrame:
        """
        Modellens riktkurs (Otto-metoden, #25) point-in-time: EXPANDERANDE
        eget band – bara år FÖRE innevarande år räknas in i percentilerna,
        aldrig årets egna resultat. "Dagens multipel" approximeras som
        senaste kända helårs-multipel skalad med kursrörelsen sedan det
        årsskiftet (mult_now ≈ mult_vid_årsskifte × pris_nu/pris_vid_
        årsskifte) – samma princip som model_target_price.py (dagens pris
        mot ett historiskt resultatmått), fast på Otto-forskningens ÅRLIGA
        granularitet så cache/otto_band/*.pkl (#25) kan återanvändas rakt
        av i stället för en ny TTM-hämtning per vecka.
        """
        dates = pd.DatetimeIndex(dates)
        years = sorted(dates.year.unique())
        panels = {}
        for t in tickers:
            df = annual_multiples(t)
            if df.empty:
                continue
            df = df.sort_index()

            per_year = {}
            for yr in years:
                prior = df[df.index < yr]
                col = None
                for c in ("mult_ebit", "mult_ebitda"):
                    if prior[c].dropna().shape[0] >= MIN_PROFITABLE_YEARS:
                        col = c
                        break
                if col is None:
                    continue
                vals = prior[col].dropna()
                last_yr = prior.index.max()
                base_mult, base_date = prior.loc[last_yr, col], prior.loc[last_yr, "date"]
                if pd.isna(base_mult) or pd.isna(base_date):
                    continue
                px_base = self._get_price(t, base_date)
                if not px_base:
                    continue
                per_year[yr] = (float(vals.quantile(HIGH_PCT)), float(base_mult), float(px_base))
            if not per_year:
                continue

            flags = pd.Series(False, index=dates)
            for asof in dates:
                yr_data = per_year.get(asof.year)
                if yr_data is None:
                    continue
                high_mult, base_mult, px_base = yr_data
                px_now = self._get_price(t, asof)
                if not px_now:
                    continue
                mult_now = base_mult * (px_now / px_base)
                flags[asof] = bool(mult_now >= high_mult)
            panels[t] = flags
        if not panels:
            return pd.DataFrame(index=dates, columns=tickers, dtype=bool)
        return pd.DataFrame(panels).reindex(index=dates, columns=tickers).fillna(False)

    def _build_insider_panel(self, dates, tickers) -> pd.DataFrame:
        """
        Insynsköp/-sälj-nettoklustring point-in-time: FI:s fulla register
        (samma källa som #23, evigt cachat i cache/fi_insyn/). Regulatorisk
        historik ändras aldrig i efterhand – en transaktion publicerad FÖRE
        asof-datumet är per definition redan känd då, inget lookahead-
        problem här till skillnad från fundamenta/pris.
        """
        from data.data_loader import load_sweden_universe
        name_to_ticker: Dict[str, list] = {}
        for seg in config.SEGMENTS.values():
            tks, _, _, name_map = load_sweden_universe(min_market_cap=seg.get("market_cap"))
            for tk in tks:
                if tk not in tickers:
                    continue
                name = _clean_name(name_map.get(tk, tk))
                name_to_ticker.setdefault(name, []).append(tk)

        events = []
        for name, tks in name_to_ticker.items():
            rows = fetch_issuer_transactions(name)
            for r in rows:
                char = r.get("character")
                if char not in BUY_CHARACTERS and char not in SELL_CHARACTERS:
                    continue
                if r.get("instrument_type") != "Aktie":
                    continue
                side = 1 if char in BUY_CHARACTERS else -1
                pub = pd.to_datetime(r.get("publish_date"), errors="coerce")
                if pd.isna(pub):
                    continue
                for tk in tks:
                    events.append({"ticker": tk, "published": pub, "side": side})

        dates = pd.DatetimeIndex(dates)
        panel = pd.DataFrame(0, index=dates, columns=tickers, dtype=int)
        if not events:
            return panel
        ev = pd.DataFrame(events)
        for t, g in ev.groupby("ticker"):
            if t not in panel.columns:
                continue
            g = g.sort_values("published")
            pub_vals = g["published"].values
            side_vals = g["side"].values
            for asof in dates:
                win_start = np.datetime64(asof - pd.Timedelta(days=INSIDER_CLUSTER_DAYS))
                mask = (pub_vals > win_start) & (pub_vals <= np.datetime64(asof))
                panel.at[asof, t] = int(side_vals[mask].sum())
        return panel

    # ── Säljvakt (nivå 2 = tvingad delförsäljning, nivå 3 = full exit) ─────

    def _trailing_return(self, ticker: str, date, weeks: int) -> Optional[float]:
        panel = self._close_panel
        if ticker not in panel.columns:
            return None
        pos = panel.index.searchsorted(date, side="left")
        if pos - weeks < 0 or pos >= len(panel):
            return None
        p0, p1 = panel[ticker].iloc[pos - weeks], panel[ticker].iloc[pos]
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            return None
        return float(p1 / p0 - 1)

    def _index_trailing_return(self, date, weeks: int) -> Optional[float]:
        idx = self._idx_level
        pos = idx.index.searchsorted(date, side="left")
        if pos - weeks < 0 or pos >= len(idx):
            return None
        return float(idx.iloc[pos] / idx.iloc[pos - weeks] - 1)

    def _pred_signal_dropped(self, ticker: str, date) -> bool:
        panel = self._pred_signal_panel
        if panel is None or ticker not in panel.columns:
            return False
        try:
            v = panel.at[date, ticker]
            return bool(pd.notna(v) and float(v) == 0.0)
        except Exception:
            return False

    def _apply_sellwatch(self, date, cash: float) -> float:
        """
        SÄLJVAKTEN, backtest-version av portfolio.py::_takeprofit (bara de
        point-in-time-rekonstruerbara bekräftelserna, se modulens docstring):
          armering  – orealiserad gain (pris/snittinköpspris − 1) >=
                      TAKEPROFIT_GAIN i SIMULERINGEN (kräver att köpet
                      faktiskt skedde i denna backtest – _update_cost_basis).
          nivå 2    – armerad + minst en bekräftelse (melt-up/gap-vs-index/
                      modellen släppt bolaget/modellens riktkurs/
                      insynsförsäljningar) → TVINGAD delförsäljning
                      (sellwatch_partial_frac, default 50%) – ENGÅNGS per
                      innehavsperiod (_level2_done), inte varje vecka
                      villkoren håller.
          nivå 3    – armerad + SMA20-trendbrott → full exit.
        """
        if not self.sellwatch_enabled or self._sellwatch_last_date == date:
            return cash
        self._sellwatch_last_date = date

        gain_min = float(getattr(config, "TAKEPROFIT_GAIN", 0.50))
        gap_min = float(getattr(config, "TAKEPROFIT_GAP_PP", 0.50))
        weeks = int(getattr(config, "TAKEPROFIT_WEEKS", 26))
        accel_share = float(getattr(config, "TAKEPROFIT_ACCEL_SHARE", 0.5))

        for ticker in list(self._portfolio.keys()):
            price = self._get_price(ticker, date)
            cost = self._cost_basis.get(ticker)
            if price is None or not cost or cost <= 0:
                continue
            gain = price / cost - 1
            if gain < gain_min:
                continue

            confirms = []
            h_ret = self._trailing_return(ticker, date, weeks)
            if h_ret is not None and h_ret > 0.10:
                r4 = self._trailing_return(ticker, date, 4)
                if r4 is not None and (r4 / h_ret) >= accel_share:
                    confirms.append("melt-up")
            if h_ret is not None:
                idx_ret = self._index_trailing_return(date, weeks)
                if idx_ret is not None and (h_ret - idx_ret) >= gap_min:
                    confirms.append("gap-vs-index")
            if self._pred_signal_dropped(ticker, date):
                confirms.append("modellen släppt bolaget")
            if self._otto_high_panel is not None and ticker in self._otto_high_panel.columns:
                try:
                    if bool(self._otto_high_panel.at[date, ticker]):
                        confirms.append("modellens riktkurs")
                except Exception:
                    pass
            if self._insider_panel is not None and ticker in self._insider_panel.columns:
                try:
                    if int(self._insider_panel.at[date, ticker]) <= -2:
                        confirms.append("insynsförsäljningar")
                except Exception:
                    pass

            broken = self._is_broken(ticker, date)
            level = 2 if confirms else 1
            if broken:
                level = 3

            if level == 3:
                shares = self._portfolio.pop(ticker)
                trade_value = shares * price
                cost_rate = self._execution_cost_rate(ticker, date, trade_value)
                cash += trade_value * (1 - cost_rate)
                self._peak_price.pop(ticker, None)
                self._cost_basis.pop(ticker, None)
                self._level2_done.discard(ticker)
            elif level == 2 and ticker not in self._level2_done:
                shares = self._portfolio[ticker]
                sell_shares = shares * self.sellwatch_partial_frac
                trade_value = sell_shares * price
                cost_rate = self._execution_cost_rate(ticker, date, trade_value)
                cash += trade_value * (1 - cost_rate)
                self._portfolio[ticker] = shares - sell_shares
                self._level2_done.add(ticker)
        return cash

    # ── Positions-bokföring (kostnadsbas) ────────────────────────────────

    def _update_cost_basis(self, date, before: Dict[str, float]) -> None:
        """Viktat snittinköpspris – jämför _portfolio före/efter en normal
        _rebalance-affär (samma diff-mot-tidigare-tillstånd-princip som
        basklassens _peak_price)."""
        for ticker, shares in self._portfolio.items():
            prev_shares = before.get(ticker, 0.0)
            if shares > prev_shares + 1e-9:
                price = self._get_price(ticker, date)
                if price is None:
                    continue
                bought = shares - prev_shares
                prev_cost = self._cost_basis.get(ticker, price)
                self._cost_basis[ticker] = (prev_cost * prev_shares + price * bought) / shares
        self._cleanup_position_state()

    def _cleanup_position_state(self) -> None:
        for ticker in list(self._cost_basis):
            if ticker not in self._portfolio:
                self._cost_basis.pop(ticker, None)
                self._level2_done.discard(ticker)

    # ── Hooks in i basklassens handelsflöde ─────────────────────────────

    def _rebalance(self, date, target_weights, portfolio_value, cash):
        cash = self._apply_sellwatch(date, cash)
        before = dict(self._portfolio)
        cash = super()._rebalance(date, target_weights, portfolio_value, cash)
        self._update_cost_basis(date, before)
        return cash

    def _trend_exit(self, date, cash):
        cash = self._apply_sellwatch(date, cash)
        cash = super()._trend_exit(date, cash)
        self._cleanup_position_state()
        return cash

    def _atr_stop_exit(self, date, cash):
        cash = super()._atr_stop_exit(date, cash)
        self._cleanup_position_state()
        return cash
