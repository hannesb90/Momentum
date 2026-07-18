"""
global_theme_momentum.py – momentumrankning för GLOBALA teman som saknar
svensk motsvarighet (humanoida robotar, rymd/drönare, uran, ...) – spår 2
i sektorgranularitets-arbetet, vid sidan av backtest/theme_momentum.py
(svenska Avanza-underteman, spår 1).

Varje tema representeras av EN tematisk UCITS-ETF (handelsbar via Avanza/
Montrose) – redan verifierade tickers, samma som portfolio.py:s _CURATED-
karta (dessa 7 är redan innehav i portföljen, se sync_montrose_holdings.py):

    VVSM.DE  Halvledare              VanEck Semiconductor
    PAIW.L   AI & Humanoida robotar  WisdomTree Physical AI
    JEDI.L   Rymd & Drönare          VanEck Space
    BLCH.L   Blockchain              Global X Blockchain
    V9N.DE   Datacenter-infra        Global X Data Center
    WNUC.L   Uran & Kärnkraft        WisdomTree Uranium
    ASWC.L   Försvar                 Future of Defence

Till skillnad från theme_momentum.py (median över MÅNGA aktier per tema)
är momentumet här EN enskild ETF:s prisrörelse – enklare, men också
känsligare för den enskilda fondens brus (spreads/likviditet i tunna
nischfonder). Använd hellre som en riktningsindikator ("är AI-humanoider
hetare än rymdtemat just nu") än ett precisionsmått.

UTÖKNING: fler teman (t.ex. cybersäkerhet, kvantdatorer, robotik brett)
kräver en NY verifierad ETF-ticker per tema (samma probe_etf-disciplin
som de befintliga 7 gick igenom) – gissa aldrig en ticker rakt av.

    python global_theme_momentum.py
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402

# ticker -> (temanamn, ETF-namn för loggutskrift)
GLOBAL_THEMES = {
    "VVSM.DE": ("Halvledare", "VanEck Semiconductor"),
    "PAIW.L":  ("AI & Humanoida robotar", "WisdomTree Physical AI"),
    "JEDI.L":  ("Rymd & Drönare", "VanEck Space"),
    "BLCH.L":  ("Blockchain", "Global X Blockchain"),
    "V9N.DE":  ("Datacenter-infrastruktur", "Global X Data Center"),
    "WNUC.L":  ("Uran & Kärnkraft", "WisdomTree Uranium"),
    "ASWC.L":  ("Försvar", "Future of Defence"),
}

ROTATION_LOOKBACK_WEEKS = 4
ROTATION_FLAG_THRESHOLD = 2


def _roc(series: pd.Series, weeks: int, offset: int = 0) -> float:
    """Avkastning `weeks` veckor tillbaka från punkten `offset` veckor
    tillbaka (offset=0 -> senaste). NaN om serien är för kort."""
    s = series.dropna()
    idx = len(s) - 1 - offset
    if idx - weeks < 0 or idx >= len(s):
        return float("nan")
    now, then = s.iloc[idx], s.iloc[idx - weeks]
    return float(now / then - 1.0) if then else float("nan")


def snapshot() -> pd.DataFrame:
    windows = config.MOMENTUM_WINDOWS
    rows = []
    for ticker, (theme, etf_name) in GLOBAL_THEMES.items():
        close = pf._safe(lambda tk=ticker: pf._avanza_weekly_close(tk), None, f"global-tema {ticker}")
        if close is None or close.dropna().empty:
            print(f"[global_theme] {ticker} ({theme}): ingen prisdata, hoppar")
            continue
        row = {"theme": theme, "ticker": ticker, "etf_name": etf_name, "n_stocks": 1}
        for w in windows:
            row[f"momentum_{w}w"] = _roc(close, w)
        row["_composite_prev"] = float(np.nanmean(
            [_roc(close, w, offset=ROTATION_LOOKBACK_WEEKS) for w in windows]))
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    score_cols = [f"momentum_{w}w" for w in windows]
    df["composite_score"] = df[score_cols].mean(axis=1, skipna=True)
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)

    prev = df[["theme", "_composite_prev"]].sort_values("_composite_prev", ascending=False)
    prev_rank = {theme: i + 1 for i, theme in enumerate(prev["theme"])}
    df["rank_change"] = df["theme"].map(prev_rank) - df["rank"]

    def _flow(change):
        if pd.isna(change):
            return "Okänd"
        if change >= ROTATION_FLAG_THRESHOLD:
            return "Kapital in"
        if change <= -ROTATION_FLAG_THRESHOLD:
            return "Kapital ut"
        return "Stabil"

    df["flow"] = df["rank_change"].apply(_flow)
    return df.drop(columns="_composite_prev")


def build():
    df = snapshot()
    if df.empty:
        print("[global_theme] ingen prisdata för något tema – avbryter.")
        return
    p = pf._results_dir() / "global_theme_momentum.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    print(f"\n  === GLOBALA TEMAN (rankat, senaste data) ===")
    cols = ["rank", "theme", "ticker", "composite_score", "rank_change", "flow"]
    print(df[cols].to_string(index=False, float_format="{:.3f}".format))
    print(f"\n[global_theme] {len(df)} tema(n) -> {p}")


if __name__ == "__main__":
    build()
