"""
backtest/theme_momentum.py – FIN sektormomentum, ovanpå sector_momentum.py.

sector_momentum.py rankar GICS-hinkar (Information Technology, Health Care,
...) – för breda för att skilja t.ex. "Medicinsk utrustning" (mätteknik,
implantat) från "Bioteknik" (läkemedelsutveckling, helt annan riskprofil)
eller "Halvledare" från "Hårdvaruutrustning", trots att de delar
GICS-hink. Det här modulet rankar istället Avanzas EGNA, betydligt
finkornigare sektortaggar (cache/avanza_sectors.csv, byggd av
altdata.avanza.sectors_extract() – VERIFIERAT 2026-07-18 mot skarpa
körningar: 742 bolag, 92 unika underteman).

GICS/sector_momentum.py RÖRS INTE av detta – sektor-relativa
screening-barrar (ROE/skuld, config.SECTOR_RANK_MIN_PEERS) kräver breda,
stabila jämförelsegrupper och fortsätter läsa GICS oförändrat. Det här är
ett ADDITIVT lager för visning/rotation (Sektorer-sidan, förvaltarbrevet).

Tunna teman (< min_peers bolag) faller tillbaka på Avanzas BREDA
toppsektor (sector_broad, t.ex. "Teknologi") istället för att exkluderas
helt eller ranka på ett för litet/brusigt underlag.
"""

import csv
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from backtest.sector_momentum import _composite_for_offset, ROTATION_LOOKBACK_WEEKS, ROTATION_FLAG_THRESHOLD

MIN_PEERS = 5   # under detta: fall tillbaka på sector_broad (samma tröskel som SECTOR_RANK_MIN_PEERS)


def load_avanza_theme_map() -> Dict[str, dict]:
    """{ticker: {"fine": ..., "broad": ...}} ur cache/avanza_sectors.csv.
    Tom dict om filen saknas (kör inte 'python -m altdata.avanza sectors'
    ännu) – ingen krasch, bara att temamomentum då blir tomt."""
    p = Path(config.anchor("cache")) / "avanza_sectors.csv"
    out = {}
    if not p.exists():
        return out
    try:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            tk = (r.get("ticker") or "").upper()
            if tk:
                out[tk] = {"fine": r.get("sector_fine") or "", "broad": r.get("sector_broad") or ""}
    except Exception:  # noqa: BLE001
        return {}
    return out


def theme_momentum_snapshot(
    all_features: Dict[str, pd.DataFrame],
    theme_map: Optional[Dict[str, dict]] = None,
    cap_tier_map: Optional[Dict[str, str]] = None,
    min_peers: int = MIN_PEERS,
    rotation_lookback_weeks: int = ROTATION_LOOKBACK_WEEKS,
) -> pd.DataFrame:
    """Samma beräkning som sector_momentum_snapshot() (median roc_Nw per
    grupp, composite_score, rank_change/flow) men grupperat på Avanzas fina
    undertema. Ett tema med FÄRRE än min_peers bolag i universumet rullas
    upp till sin BREDA toppsektor istället för att stå ensamt (för brusigt/
    litet underlag annars) – dessa rader har level='broad (fallback)',
    riktiga fina teman har level='fine'."""
    theme_map = theme_map if theme_map is not None else load_avanza_theme_map()
    cap_tier_map = cap_tier_map or {}
    windows = config.MOMENTUM_WINDOWS

    if not theme_map:
        return pd.DataFrame()

    # Steg 1: räkna peers per fint tema BLAND TICKERS SOM FAKTISKT HAR FEATURES
    # (inte hela avanza_sectors.csv – ett tema kan ha fler taggade bolag än
    # vad som faktiskt är kvar i dagens universum efter likviditets-/
    # delisting-filter).
    fine_counts: Dict[str, int] = {}
    for ticker in all_features:
        if cap_tier_map.get(ticker) == "Fond":
            continue
        info = theme_map.get(ticker)
        if info and info["fine"]:
            fine_counts[info["fine"]] = fine_counts.get(info["fine"], 0) + 1

    by_theme: Dict[str, list] = {}
    level_of: Dict[str, str] = {}
    for ticker, feat in all_features.items():
        if cap_tier_map.get(ticker) == "Fond":
            continue
        info = theme_map.get(ticker)
        if not info or not info["fine"]:
            continue
        fine, broad = info["fine"], info["broad"]
        if fine_counts.get(fine, 0) >= min_peers:
            key, level = fine, "fine"
        elif broad:
            key, level = broad, "broad (fallback)"
        else:
            continue
        by_theme.setdefault(key, []).append(feat)
        level_of[key] = level

    rows = []
    for theme, feats in by_theme.items():
        row = {"theme": theme, "level": level_of[theme], "n_stocks": len(feats)}
        for w in windows:
            col = f"roc_{w}w"
            vals = [f[col].iloc[-1] for f in feats
                    if not f.empty and col in f.columns and pd.notna(f[col].iloc[-1])]
            row[f"momentum_{w}w"] = float(np.median(vals)) if vals else np.nan
        row["_composite_prev"] = _composite_for_offset(feats, windows, rotation_lookback_weeks)
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

    def _flow(change: float) -> str:
        if pd.isna(change):
            return "Okänd"
        if change >= ROTATION_FLAG_THRESHOLD:
            return "Kapital in"
        if change <= -ROTATION_FLAG_THRESHOLD:
            return "Kapital ut"
        return "Stabil"

    df["flow"] = df["rank_change"].apply(_flow)
    df = df.drop(columns="_composite_prev")
    return df


def print_theme_momentum(df: pd.DataFrame) -> None:
    if df.empty:
        print("  [Tema-momentum] Inget att ranka (cache/avanza_sectors.csv saknas/tom "
              "– kör 'python -m altdata.avanza sectors' + 'sectors quality').")
        return
    print("\n  === TEMA-MOMENTUM (Avanzas fina underteman, rankat) ===")
    cols = ["rank", "theme", "level", "n_stocks", "composite_score", "rank_change", "flow"]
    print(df[cols].to_string(index=False, float_format="{:.3f}".format))
