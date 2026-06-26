"""
models/ensemble.py – Kombinerar LGBM + LSTM, Kelly-positionssizing.

Output per ticker per vecka:
  - prob_up      : ensemble sannolikhet
  - pred_signal  : Köp(1)/Sälj(0)
  - pred_return  : förväntad avkastning
  - position_size: Kelly-baserad storlek [0..MAX_POSITION]
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from models.ta_filter import ta_confirmation


# ─────────────────────────────────────────────────────────────────────────────
# Ensemble
# ─────────────────────────────────────────────────────────────────────────────

class MomentumEnsemble:
    """
    Dynamisk viktning baserat på rolling Sharpe per modell.
    Startvikter: LGBM=0.6, LSTM=0.4.
    """

    def __init__(
        self,
        lgbm_weight: float = config.ENSEMBLE_LGBM_WEIGHT,
        lstm_weight:  float = config.ENSEMBLE_LSTM_WEIGHT,
    ):
        self.lgbm_w = lgbm_weight
        self.lstm_w  = lstm_weight
        self._history: list = []   # (date, lgbm_ret, lstm_ret, actual_ret)

    # ── Kombinera prediktioner ────────────────────────────────────────────────

    def combine(
        self,
        lgbm_preds: pd.DataFrame,
        lstm_preds: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Slår ihop LGBM och (valfritt) LSTM-prediktioner.
        Gemensamma index (datum) används.
        """
        if lstm_preds is None or lstm_preds.empty:
            return lgbm_preds.copy()

        # Gemensamma datum
        idx = lgbm_preds.index.intersection(lstm_preds.index)
        lg  = lgbm_preds.loc[idx]
        ls  = lstm_preds.loc[idx]

        w_lg = self.lgbm_w / (self.lgbm_w + self.lstm_w)
        w_ls = self.lstm_w  / (self.lgbm_w + self.lstm_w)

        combined = pd.DataFrame(index=idx)
        combined["prob_up"]     = w_lg * lg["prob_up"]    + w_ls * ls["prob_up"]
        combined["pred_return"] = w_lg * lg["pred_return"] + w_ls * ls["pred_return"]
        combined["pred_signal"] = (combined["prob_up"] > 0.5).astype(int)
        return combined

    def update_weights(self, realized_returns: pd.Series):
        """
        Justerar vikterna baserat på rolling Sharpe (senaste ROLLING_SHARPE_WINDOW periods).
        Anropa efter varje backtest-period med faktiska avkastningar.
        """
        # Förenklat: om LGBM historiskt hade bättre Sharpe, öka dess vikt.
        # I produktion: spara per-modell-avkastning och beräkna Sharpe separat.
        pass   # utökas i backtester.py


# ─────────────────────────────────────────────────────────────────────────────
# Positionssizing – Kelly
# ─────────────────────────────────────────────────────────────────────────────

def kelly_position_size(
    prob_up:    float,
    pred_return: float,
    volatility:  float,
    win_loss_ratio: float = 1.5,
) -> float:
    """
    Fractional Kelly:
      f* = (p * b - q) / b  ×  KELLY_FRACTION
    
    Där:
      p = prob_up
      q = 1 - p
      b = win_loss_ratio (förväntad vinst / förlust)
    
    Skalas sedan med volatilitetsinvers för volatilitets-targeting.
    """
    p = np.clip(prob_up, 0.01, 0.99)
    q = 1 - p
    b = max(win_loss_ratio, 0.1)

    kelly = (p * b - q) / b
    kelly = max(kelly, 0.0)                          # aldrig negativt (long-only)
    kelly *= config.KELLY_FRACTION                    # fractional Kelly

    # Volatilitetsskala: target 15% annualiserad vol
    if volatility > 0:
        vol_scale = 0.15 / max(volatility, 0.05)
        kelly *= vol_scale

    return float(np.clip(kelly, 0.0, config.MAX_POSITION))


def _apply_portfolio_constraints(weights: Dict[str, float]) -> Dict[str, float]:
    """
    Gemensam regeltillämpning för portföljvikter:
      - kasta bort vikter under MIN_POSITION
      - begränsa till MAX_POSITIONS (störst vikt vinner)
      - normalisera om total > 1
    """
    weights = {t: w for t, w in weights.items() if w >= config.MIN_POSITION}

    if len(weights) > config.MAX_POSITIONS:
        top = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:config.MAX_POSITIONS]
        weights = dict(top)

    total = sum(weights.values())
    if total > 1.0:
        weights = {t: w / total for t, w in weights.items()}

    return weights


def build_portfolio_weights(
    signals: pd.DataFrame,
    feature_df: pd.DataFrame,   # behövs för volatilitet
    date: pd.Timestamp,
) -> Dict[str, float]:
    """
    Bygger portföljvikter för ett givet datum.

    signals: DataFrame med kolumner [ticker, prob_up, pred_return, pred_signal]
    Returnerar {ticker: weight}
    """
    long_signals = signals[signals["pred_signal"] == 1].copy()

    if long_signals.empty:
        return {}

    weights: Dict[str, float] = {}

    for _, row in long_signals.iterrows():
        ticker = row["ticker"]
        prob   = row["prob_up"]
        ret    = row["pred_return"]

        # Hämta volatilitet om tillgänglig
        try:
            vol = feature_df.loc[feature_df["ticker"] == ticker].loc[:date, "rvol_13w"].iloc[-1]
        except Exception:
            vol = 0.20   # default 20% annualiserad vol

        weights[ticker] = kelly_position_size(prob, ret, vol)

    return _apply_portfolio_constraints(weights)


# ─────────────────────────────────────────────────────────────────────────────
# Full output per datum/ticker
# ─────────────────────────────────────────────────────────────────────────────

def build_full_output(
    lgbm_preds_by_ticker: Dict[str, pd.DataFrame],
    lstm_preds_by_ticker: Optional[Dict[str, pd.DataFrame]],
    feature_dfs: Dict[str, pd.DataFrame],
    ensemble: MomentumEnsemble,
    ta_filter: Optional[str] = None,
    ta_strictness: str = config.TA_FILTER_STRICTNESS,
) -> pd.DataFrame:
    """
    Returnerar ett long-format DataFrame med alla outputs:
      Date, ticker, prob_up, pred_signal, pred_return, ta_score, position_size

    position_size tillämpar MIN_POSITION/MAX_POSITIONS/normalisering per datum
    (samma regler som build_portfolio_weights), så flera tickers med
    samtidiga köpsignaler konkurrerar om portföljutrymmet korrekt.

    ta_filter: None (av), "gate" (hård grind – nollar köpsignaler som TA inte
    bekräftar) eller "score" (mjuk viktning – skalar position_size med andelen
    uppfyllda TA-villkor). ta_strictness väljer villkorsuppsättning, se
    models/ta_filter.py. ta_score sparas alltid (1.0 när filtret är av) för
    transparens.
    """
    if ta_filter not in (None, "gate", "score"):
        raise ValueError(f"Okänt ta_filter: {ta_filter!r}. Välj None, 'gate' eller 'score'.")

    rows = []

    for ticker, lgbm_pred in lgbm_preds_by_ticker.items():
        lstm_pred = (lstm_preds_by_ticker or {}).get(ticker)
        combined  = ensemble.combine(lgbm_pred, lstm_pred)

        feat_df = feature_dfs.get(ticker, pd.DataFrame())

        for date, row in combined.iterrows():
            # Hämta volatilitet
            try:
                vol = feat_df.loc[:date, "rvol_13w"].iloc[-1]
            except Exception:
                vol = 0.20

            raw_kelly  = kelly_position_size(row["prob_up"], row["pred_return"], vol)
            pred_signal = int(row["pred_signal"])

            # ── Valbart TA-bekräftelsefilter ─────────────────────────────────
            ta_score = 1.0
            if ta_filter is not None and pred_signal == 1:
                try:
                    ta_row = feat_df.loc[date]
                    if isinstance(ta_row, pd.DataFrame):   # om datumet är duplicerat
                        ta_row = ta_row.iloc[-1]
                    passed, score = ta_confirmation(ta_row, ta_strictness)
                except Exception:
                    passed, score = False, 0.0   # saknad TA-data = ingen bekräftelse

                if ta_filter == "gate":
                    ta_score = 1.0 if passed else 0.0
                    if not passed:
                        pred_signal = 0          # hård grind: vetar signalen
                        raw_kelly = 0.0
                else:  # score: mjuk viktning av storleken
                    ta_score = score
                    raw_kelly *= score

            rows.append({
                "Date":          date,
                "ticker":        ticker,
                "prob_up":       row["prob_up"],
                "pred_signal":   pred_signal,
                "pred_return":   row["pred_return"],
                "ta_score":      ta_score,
                "raw_kelly":     raw_kelly if pred_signal == 1 else 0.0,
            })

    df = pd.DataFrame(rows).set_index("Date").sort_index()

    def _size_date(group: pd.DataFrame) -> pd.Series:
        candidates = group[group["raw_kelly"] > 0]
        raw_weights = dict(zip(candidates["ticker"], candidates["raw_kelly"]))
        sized = _apply_portfolio_constraints(raw_weights)
        return group["ticker"].map(sized).fillna(0.0)

    df["position_size"] = df.groupby(level="Date", group_keys=False).apply(_size_date)
    df = df.drop(columns="raw_kelly")
    return df
