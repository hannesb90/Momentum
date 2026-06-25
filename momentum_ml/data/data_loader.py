"""
data/data_loader.py – Hämtar och cachar veckodata via yfinance.

OBS: yfinance ger bara historik för tickers som finns/går att slå upp
idag. Aktier som avnoterats, gått i konkurs eller blivit uppköpta
saknas helt, vilket ger survivorship bias i backtester – CAGR/Sharpe
tenderar att överskattas eftersom universumet implicit bara innehåller
"vinnare". För kapital i den storleksordning som motiverar den här
strategin bör en datakälla med korrekt point-in-time-universum (t.ex.
Polygon.io eller Norgate Data, båda betaltjänster) användas innan
resultat tas på allvar. Att byta källa innebär att skriva en ny
funktion med samma retur-kontrakt som fetch_weekly_data (Dict[ticker,
DataFrame] med kolumnerna Open/High/Low/Close/Volume).
"""

import os
import pickle
import hashlib
import pandas as pd
import yfinance as yf
from pathlib import Path
from typing import Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def _cache_path(key: str) -> Path:
    Path(config.CACHE_DIR).mkdir(exist_ok=True)
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return Path(config.CACHE_DIR) / f"{h}.pkl"


def fetch_weekly_data(
    tickers: List[str],
    start: str = config.START_DATE,
    end: Optional[str] = config.END_DATE,
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Hämtar OHLCV-veckodata för en lista tickers.
    Returnerar dict {ticker: DataFrame med kolumner Open/High/Low/Close/Volume}.
    """
    cache_key = f"{','.join(sorted(tickers))}_{start}_{end}"
    cp = _cache_path(cache_key)

    if use_cache and cp.exists():
        print(f"[DataLoader] Laddar cache: {cp}")
        with open(cp, "rb") as f:
            return pickle.load(f)

    print(f"[DataLoader] Hämtar {len(tickers)} tickers från Yahoo Finance...")
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        interval="1wk",
        auto_adjust=True,
        progress=True,
        threads=True,
    )

    result: Dict[str, pd.DataFrame] = {}

    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in tickers:
            try:
                df = raw.xs(ticker, axis=1, level=1).copy()
                df = _clean(df, ticker)
                if df is not None:
                    result[ticker] = df
            except KeyError:
                print(f"  [WARN] {ticker}: ingen data, hoppar över.")
    else:
        # Enstaka ticker
        df = _clean(raw, tickers[0])
        if df is not None:
            result[tickers[0]] = df

    if not result:
        raise RuntimeError(
            "Ingen ticker gav tillräcklig data. Kontrollera nätverksåtkomst "
            "till Yahoo Finance och att tickrarna/perioden är giltiga."
        )

    print(f"[DataLoader] Laddade {len(result)} tickers, "
          f"{min(len(v) for v in result.values())}–"
          f"{max(len(v) for v in result.values())} veckor vardera.")

    with open(cp, "wb") as f:
        pickle.dump(result, f)

    return result


def _check_suspicious_jumps(df: pd.DataFrame, ticker: str) -> None:
    """
    Flaggar (men korrigerar inte) veckoavkastningar över
    SUSPICIOUS_JUMP_THRESHOLD i magnitud. Sådana hopp kan vara legitima
    (vinstvarningar, biotech-resultat) eller artefakter av ojusterade
    corporate actions (splits/utdelningar som yfinance missat). Att
    auto-korrigera riskerar att introducera nya fel, så det här är bara
    en varning för manuell granskning.
    """
    weekly_ret = df["Close"].pct_change().dropna()
    jumps = weekly_ret[weekly_ret.abs() > config.SUSPICIOUS_JUMP_THRESHOLD]
    for date, ret in jumps.items():
        print(f"  [WARN] {ticker} {date.date()}: misstänkt hopp {ret:+.1%} "
              f"– kontrollera ev. ojusterad corporate action.")


def _clean(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """Droppar NaN-rader, kontrollerar minimilängd."""
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  [WARN] {ticker}: saknar kolumner {missing}.")
        return None

    df = df[required].copy()
    df.dropna(subset=["Close"], inplace=True)
    df["Volume"] = df["Volume"].fillna(0)
    df.sort_index(inplace=True)

    min_rows = config.TRAIN_WINDOW_WEEKS + config.LSTM_SEQUENCE_LEN + config.FORWARD_WEEKS
    if len(df) < min_rows:
        print(f"  [WARN] {ticker}: för kort historik ({len(df)} veckor), "
              f"behöver minst {min_rows}.")
        return None

    _check_suspicious_jumps(df, ticker)

    return df


def build_universe_df(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Sätter ihop alla tickers till ett long-format DataFrame.
    Kolumner: ticker, Open, High, Low, Close, Volume  (index = Date)
    """
    frames = []
    for ticker, df in data.items():
        tmp = df.copy()
        tmp["ticker"] = ticker
        frames.append(tmp)
    universe = pd.concat(frames).sort_index()
    universe.index.name = "Date"
    return universe
