"""
backtest/sector_momentum.py – Sektor-momentum.

Aggregerar per-aktie-momentum (roc_Nw från feature_engineering) per sektor
(config.SECTOR_MAP) för att ranka sektorer och peka mot en motsvarande
handelsbar fond/ETF. Komplement till per-aktie-signalerna: identifierar
vilken sektor-ETF/fond som är mest momentum-attraktiv just nu, snarare än
vilken enskild aktie.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# Sverige saknar egna GICS-sektor-ETF:er (se data/sweden_funds.csv) - mappar
# istället mot iShares STOXX Europe 600-sektorserien (Xetra), som är
# handelsbar via svenska nätmäklare (Avanza/Montrose m.fl.). US SPDR-listan
# i data/sector_etfs.csv finns kvar som referens/fallback.
SECTOR_ETF_MAP = {
    "Technology":             "EXV3",
    "Information Technology": "EXV3",
    "Financials":             "EXH2",
    "Health Care":            "EXV4",
    "Consumer Discretionary": "EXH8",
    "Consumer Staples":       "EXH3",
    "Energy":                 "EXH1",
    "Industrials":            "EXH4",
    "Materials":              "EXV6",
    "Utilities":              "EXH9",
    "Real Estate":            "EXI5",
    "Communication Services": "EXV2",
}


def sector_momentum_snapshot(
    all_features: Dict[str, pd.DataFrame],
    sector_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Returnerar en DataFrame (en rad per sektor) med senaste roc_Nw-median
    per sektor (median = robust mot enskilda extremrörelser), antal aktier
    bakom signalen, en sammanvägd composite_score och föreslagen ETF-ticker.
    """
    sector_map = sector_map or config.SECTOR_MAP
    windows = config.MOMENTUM_WINDOWS

    by_sector: Dict[str, list] = {}
    for ticker, feat in all_features.items():
        sector = sector_map.get(ticker, "Okänd")
        if sector == "Fond":
            continue  # fonder/ETF:er ska inte räknas in i sin egen sektor-signal
        by_sector.setdefault(sector, []).append(feat)

    rows = []
    for sector, feats in by_sector.items():
        row = {"sector": sector, "n_stocks": len(feats)}
        for w in windows:
            col = f"roc_{w}w"
            vals = [f[col].iloc[-1] for f in feats
                    if not f.empty and col in f.columns and pd.notna(f[col].iloc[-1])]
            row[f"momentum_{w}w"] = float(np.median(vals)) if vals else np.nan
        row["etf_ticker"] = SECTOR_ETF_MAP.get(sector)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    score_cols = [f"momentum_{w}w" for w in windows]
    df["composite_score"] = df[score_cols].mean(axis=1, skipna=True)
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df


def print_sector_momentum(df: pd.DataFrame) -> None:
    if df.empty:
        print("  [Sektor-momentum] Inga sektorer att ranka.")
        return
    print("\n  === SEKTOR-MOMENTUM (rankat, senaste data) ===")
    cols = ["rank", "sector", "n_stocks", "composite_score", "etf_ticker"]
    print(df[cols].to_string(index=False, float_format="{:.3f}".format))
