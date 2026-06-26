"""
features/feature_engineering.py – Bygger ~40 tekniska features per ticker.

Feature-kategorier:
  1. Momentum / ROC
  2. Trend (EMA-kors, ADX)
  3. Volatilitet (ATR, realized vol, vol-ratio)
  4. Volym (OBV, vol-ratio, A/D)
  5. Pris-nivå (52v high/low ratio, BB-position)
  6. Cross-sectional (relativ styrka, percentilrank)
  7. Targets (framåtblickande, läcker ej in i träning)
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


# ─────────────────────────────────────────────────────────────────────────────
# Hjälpfunktioner
# ─────────────────────────────────────────────────────────────────────────────

def _roc(series: pd.Series, n: int) -> pd.Series:
    """Rate of Change: (p_t / p_{t-n}) - 1"""
    return series.pct_change(n)


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    """Returnerar (ADX, +DI, -DI)."""
    up   = high.diff()
    down = -low.diff()
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    atr_n = _atr(high, low, close, n)
    plus_di  = 100 * pd.Series(plus_dm,  index=close.index).rolling(n).mean() / atr_n
    minus_di = 100 * pd.Series(minus_dm, index=close.index).rolling(n).mean() / atr_n

    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    adx = dx.rolling(n).mean()
    return adx, plus_di, minus_di


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def _ad_line(high: pd.Series, low: pd.Series,
             close: pd.Series, volume: pd.Series) -> pd.Series:
    clv = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    return (clv * volume).cumsum()


# ─────────────────────────────────────────────────────────────────────────────
# Huvud-funktion: features per ticker
# ─────────────────────────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input:  DataFrame med kolumner [Open, High, Low, Close, Volume]
    Output: DataFrame med alla features + targets (NaN i början, ej framåtläckage)
    """
    feat = pd.DataFrame(index=df.index)
    o, h, l, c, v = df["Open"], df["High"], df["Low"], df["Close"], df["Volume"]

    # ── 1. Momentum / ROC ────────────────────────────────────────────────────
    for w in config.MOMENTUM_WINDOWS:
        feat[f"roc_{w}w"] = _roc(c, w)

    # Skew och kurtosis av veckoavkastning (13v)
    wr = c.pct_change()
    feat["ret_skew_13w"]  = wr.rolling(13).skew()
    feat["ret_kurt_13w"]  = wr.rolling(13).kurt()

    # ── 2. Trend (EMA-kors, ADX) ─────────────────────────────────────────────
    for fast, slow in config.EMA_PAIRS:
        ema_f = _ema(c, fast)
        ema_s = _ema(c, slow)
        feat[f"ema_cross_{fast}_{slow}"] = (ema_f - ema_s) / c   # normaliserat avstånd
        feat[f"ema_slope_{fast}w"]       = ema_f.pct_change(4)    # lutning

    adx, plus_di, minus_di = _adx(h, l, c, config.ADX_PERIOD)
    feat["adx"]       = adx
    feat["di_diff"]   = (plus_di - minus_di) / 100               # +DI - -DI normaliserat
    feat["adx_trend"] = (plus_di > minus_di).astype(int)         # 1=upptrend

    # ── 3. Volatilitet ────────────────────────────────────────────────────────
    for w in config.VOLATILITY_WINDOWS:
        feat[f"rvol_{w}w"] = wr.rolling(w).std() * np.sqrt(52)   # annualiserad

    feat["atr_norm"] = _atr(h, l, c, 14) / c                     # ATR% av pris
    feat["vol_ratio"] = feat["rvol_4w"] / feat["rvol_26w"]       # kort/lång vol

    # Bollinger Band position
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    feat["bb_position"] = (c - sma20) / (2 * std20)              # -1..+1

    # ── 4. Volym ─────────────────────────────────────────────────────────────
    for w in config.VOLUME_WINDOWS:
        feat[f"vol_ratio_{w}w"] = v / v.rolling(w).mean()        # relativ volym

    obv = _obv(c, v)
    feat["obv_roc_4w"]  = _roc(obv, 4)
    feat["obv_roc_13w"] = _roc(obv, 13)

    ad = _ad_line(h, l, c, v)
    feat["ad_roc_4w"] = _roc(ad, 4)

    # Dollarvolym, absolut nivå – grund för cross-sectional likviditetsrank
    # (add_cross_sectional). Modellen ser idag ingen skillnad mellan en
    # djupt likvid large-cap och en tunn micro-cap förutom via
    # vol_ratio_*w (relativ mot egen historik) – det säger inget om hur
    # likvid aktien är i absoluta termer jämfört med resten av universumet.
    feat["dollar_vol_13w"] = (c * v).rolling(13).mean()

    # ── 5. Pris-nivå ─────────────────────────────────────────────────────────
    feat["high52_ratio"] = c / h.rolling(52).max()               # nära 52v-high?
    feat["low52_ratio"]  = c / l.rolling(52).min()               # över 52v-low?
    feat["price_vs_sma52"] = c / c.rolling(52).mean() - 1

    # ── 6. Targets (LÄCKER EJ – shift bakåt) ─────────────────────────────────
    fwd = config.FORWARD_WEEKS
    fwd_ret = c.shift(-fwd) / c - 1                               # framåtavkastning

    feat["target_return"]   = fwd_ret                             # regression
    feat["target_signal"]   = (fwd_ret > config.RETURN_THRESHOLD).astype(int)  # klassifikation
    feat["target_prob_pos"] = np.nan                              # fylls av modellen

    # Vissa kvoter (volym=0, flat pris -> std=0, OBV/AD-linje som korsar noll)
    # kan ge inf istället för NaN - normalisera så nedströms NaN-hantering
    # (dropna/fillna) täcker även dessa fall.
    feat = feat.replace([np.inf, -np.inf], np.nan)

    # ── Rensa bort rader med för många NaN ───────────────────────────────────
    # (behåll rader som har tillräckligt med historik för alla features)
    min_valid = 0.70
    thresh = int(len(feat.columns) * min_valid)
    feat = feat.dropna(thresh=thresh)

    return feat


# ─────────────────────────────────────────────────────────────────────────────
# Cross-sectional features (kräver hela universum)
# ─────────────────────────────────────────────────────────────────────────────

def add_cross_sectional(all_features: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Lägger till cross-sectional features:
      - rs_4w, rs_13w, rs_26w : relativ styrka vs universum (mean)
      - rank_4w, rank_26w     : percentilrank i universum
    """
    # Samla ROC per datum
    roc_4  = pd.DataFrame({t: f["roc_4w"]  for t, f in all_features.items()})
    roc_13 = pd.DataFrame({t: f["roc_13w"] for t, f in all_features.items()})
    roc_26 = pd.DataFrame({t: f["roc_26w"] for t, f in all_features.items()})
    dvol   = pd.DataFrame({t: f["dollar_vol_13w"] for t, f in all_features.items()})

    universe_mean_4  = roc_4.mean(axis=1)
    universe_mean_26 = roc_26.mean(axis=1)
    dvol_rank = dvol.rank(axis=1, pct=True)   # 0=tunnast, 1=mest likvid i universumet just det datumet

    for ticker, feat in all_features.items():
        feat["rs_4w"]   = feat["roc_4w"]  - universe_mean_4
        feat["rs_13w"]  = feat["roc_13w"] - roc_13.mean(axis=1)
        feat["rs_26w"]  = feat["roc_26w"] - universe_mean_26
        feat["rank_4w"] = roc_4.rank(axis=1, pct=True)[ticker]
        feat["rank_26w"]= roc_26.rank(axis=1, pct=True)[ticker]
        feat["liquidity_rank"] = dvol_rank[ticker]

    return all_features


def build_all_features(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Kör feature engineering för alla tickers + cross-sectional.
    """
    print("[Features] Bygger features...")
    all_feat = {}
    for ticker, df in data.items():
        try:
            all_feat[ticker] = build_features(df)
        except Exception as e:
            print(f"  [WARN] {ticker}: feature error: {e}")

    all_feat = add_cross_sectional(all_feat)
    print(f"[Features] Klar. {len(all_feat)} tickers, "
          f"{next(iter(all_feat.values())).shape[1]} features.")
    return all_feat


def _category_code(value: Optional[str], categories: list) -> int:
    """
    Ordinal kod för en kategori utifrån en fast lista (se config.py
    SECTOR_CATEGORIES/CAP_TIER_CATEGORIES). Fast lista krävs eftersom
    träning och prediktion körs i separata processer (main.py) – koderna
    måste vara identiska mellan körningarna. Okänt/saknat värde får sista
    kategorins kod ("Okänd").
    """
    if value in categories:
        return categories.index(value)
    return len(categories) - 1


def attach_categorical_features(
    all_features: Dict[str, pd.DataFrame],
    sector_map: Optional[Dict[str, str]] = None,
    cap_tier_map: Optional[Dict[str, str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Lägger till sector_code/cap_tier_code (ordinal-kodade, fast lista i
    config.py) på varje tickers feature-DataFrame, INNAN to_model_df
    respektive prediktion – main.py använder samma all_features-dict för
    både träning (via to_model_df) och live-prediktion (direkt iteration),
    så kolumnerna måste finnas här för att båda vägarna ska se samma
    FEATURE_COLS. Saknas mappningarna sätts allt till "Okänd"-koden
    (bakåtkompatibelt, t.ex. för ad-hoc --tickers-körningar).
    """
    for ticker, feat in all_features.items():
        sector = (sector_map or {}).get(ticker)
        cap_tier = (cap_tier_map or {}).get(ticker)
        feat["sector_code"]   = _category_code(sector, config.SECTOR_CATEGORIES)
        feat["cap_tier_code"] = _category_code(cap_tier, config.CAP_TIER_CATEGORIES)
    return all_features


def to_model_df(all_features: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Slår ihop alla tickers till ett long-format df med 'ticker'-kolumn.
    Droppar rader där target är NaN (sista FORWARD_WEEKS veckorna).
    """
    frames = []
    for ticker, feat in all_features.items():
        tmp = feat.copy()
        tmp["ticker"] = ticker
        frames.append(tmp)
    df = pd.concat(frames).sort_index()
    df = df.dropna(subset=["target_return", "target_signal"])
    return df


FEATURE_COLS = [
    # Momentum
    *[f"roc_{w}w" for w in config.MOMENTUM_WINDOWS],
    "ret_skew_13w", "ret_kurt_13w",
    # Trend
    *[f"ema_cross_{f}_{s}" for f, s in config.EMA_PAIRS],
    *[f"ema_slope_{f}w" for f, _ in config.EMA_PAIRS],
    "adx", "di_diff", "adx_trend",
    # Volatilitet
    *[f"rvol_{w}w" for w in config.VOLATILITY_WINDOWS],
    "atr_norm", "vol_ratio", "bb_position",
    # Volym
    *[f"vol_ratio_{w}w" for w in config.VOLUME_WINDOWS],
    "obv_roc_4w", "obv_roc_13w", "ad_roc_4w",
    # Pris-nivå
    "high52_ratio", "low52_ratio", "price_vs_sma52",
    # Cross-sectional
    "rs_4w", "rs_13w", "rs_26w", "rank_4w", "rank_26w", "liquidity_rank",
    # Klassificering (ordinal-kodad, fast lista i config.py)
    "sector_code", "cap_tier_code",
]
