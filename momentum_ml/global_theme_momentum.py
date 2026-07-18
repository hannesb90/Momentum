"""
global_theme_momentum.py – momentumrankning för GLOBALA teman som saknar
svensk motsvarighet (humanoida robotar, rymd/drönare, uran, ...) – spår 2
i sektorgranularitets-arbetet, vid sidan av backtest/theme_momentum.py
(svenska Avanza-underteman, spår 1).

PRIMÄR KÄLLA (2026-07-18➜): cache/fund_niche_themes.csv, byggd av
altdata/fund_theme_classifier.py – headless Claude (Haiku) läser Avanzas
FULLSTÄNDIGA fondutbud (avanza_fund_categories.csv, 1493 fonder) och taggar
varje fond inom de breda blandkategorierna (teknologi/sjukvård/energi/
industri/strategi/multi-asset) med ett specifikt nischtema. Inom varje
tema väljs den fond med lägst totalavgift bland tillräckligt ägda
(is_primary_pick=True) – VERIFIERAT mot skarp körning 2026-07-18: 230
fonder -> 33 nischteman (Halvledare/AI & Robotik/Rymdteknik/Uran &
Kärnkraft/Bioteknik/Läkemedel/Olja & Gas/Väte/Solenergi/Fintech/...),
0 misslyckade. Matchas på orderbookId, ALDRIG tickerSymbol (en fond kan ha
en icke-uppenbar ticker, t.ex. iShares Digital Security = "L0CK" med
SIFFRAN noll – strängmatchning är onödigt skört när id:t redan är känt).

FALLBACK (om fund_niche_themes.csv saknas – klassificeraren inte körd än):
en liten handplockad lista (GLOBAL_THEMES/GLOBAL_THEMES_BY_ID nedan) med
samma teman som redan var innehav eller tidigt verifierade via probe_etf.

Till skillnad från theme_momentum.py (median över MÅNGA aktier per tema)
är momentumet här EN enskild ETF:s prisrörelse – enklare, men också
känsligare för den enskilda fondens brus (spreads/likviditet i tunna
nischfonder). Använd hellre som en riktningsindikator ("är AI-humanoider
hetare än rymdtemat just nu") än ett precisionsmått.

    python global_theme_momentum.py
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import portfolio as pf  # noqa: E402

# FALLBACK ENDAST (se docstring) – används bara om fund_niche_themes.csv
# inte finns än. ticker -> (temanamn, ETF-namn), redan innehav, matchas via
# sök+exakt tickerSymbol (samma väg som portfolio.py:s fetch_holding_quotes/
# _avanza_weekly_close, redan bevisat pålitlig för dessa).
GLOBAL_THEMES = {
    "VVSM.DE": ("Halvledare", "VanEck Semiconductor"),
    "PAIW.L":  ("AI & Humanoida robotar", "WisdomTree Physical AI"),
    "JEDI.L":  ("Rymd & Drönare", "VanEck Space"),
    "BLCH.L":  ("Blockchain", "Global X Blockchain"),
    "V9N.DE":  ("Datacenter-infrastruktur", "Global X Data Center"),
    "WNUC.L":  ("Uran & Kärnkraft", "WisdomTree Uranium"),
    "ASWC.L":  ("Försvar", "Future of Defence"),
}

# FALLBACK ENDAST (se docstring) – orderBookId -> (temanamn, ETF-namn),
# VERIFIERADE via skarp probe_etf-körning 2026-07-18.
GLOBAL_THEMES_BY_ID = {
    "1064125": ("Robotik & Automation", "iShares Automation & Robotics (2B76)"),
    "1063876": ("Cybersäkerhet", "iShares Digital Security (L0CK)"),
    "2071329": ("Kvantdatorer", "VanEck Quantum Computing (QUTM)"),
}


def _load_niche_theme_entries() -> Optional[List[dict]]:
    """{theme, orderbookId, etf_name, fee} för varje is_primary_pick=True-rad
    i cache/fund_niche_themes.csv (se altdata/fund_theme_classifier.py).
    None om filen saknas (klassificeraren inte körd än) – snapshot()
    faller då tillbaka på GLOBAL_THEMES/GLOBAL_THEMES_BY_ID istället."""
    p = Path(config.anchor("cache")) / "fund_niche_themes.csv"
    if not p.exists():
        return None
    out = []
    try:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            if str(r.get("is_primary_pick")).strip().lower() != "true":
                continue
            oid = (r.get("orderbookId") or "").strip()
            theme = (r.get("theme") or "").strip()
            if not oid or not theme:
                continue
            try:
                fee = float(r.get("managementFee") or 0) + float(r.get("productFee") or 0)
            except (TypeError, ValueError):
                fee = None
            out.append({"theme": theme, "orderbookId": oid,
                        "etf_name": r.get("name") or "", "fee": fee})
    except Exception:  # noqa: BLE001
        return None
    return out or None

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


def _weekly_close_by_id(order_book_id: str):
    """Som portfolio._avanza_weekly_close() men för ett REDAN VERIFIERAT
    orderBookId – hoppar över sök+tickerSymbol-matchningen helt (den är
    till för när vi bara har VÅR ticker, inte när Avanzas eget id redan är
    känt via en skarp probe_etf-körning). Close i instrumentets egen valuta
    (ratio-mått, se _avanza_weekly_close-docstring – ingen FX behövs)."""
    import altdata.avanza as av
    try:
        df = av.fetch_chart_ohlcv(order_book_id, "five_years")
    except Exception:  # noqa: BLE001
        return None
    return None if (df is None or df.empty) else df["Close"]


def snapshot() -> pd.DataFrame:
    windows = config.MOMENTUM_WINDOWS
    rows = []
    niche_entries = _load_niche_theme_entries()

    if niche_entries is not None:
        print(f"[global_theme] {len(niche_entries)} tema(n) ur fund_niche_themes.csv "
              f"(fee-optimerade primärval, se altdata/fund_theme_classifier.py)")
        for e in niche_entries:
            close = pf._safe(lambda i=e["orderbookId"]: _weekly_close_by_id(i), None,
                              f"global-tema id={e['orderbookId']}")
            if close is None or close.dropna().empty:
                print(f"[global_theme] id={e['orderbookId']} ({e['theme']}): ingen prisdata, hoppar")
                continue
            row = {"theme": e["theme"], "ticker": f"id:{e['orderbookId']}",
                   "etf_name": e["etf_name"], "fee": e["fee"], "n_stocks": 1}
            for w in windows:
                row[f"momentum_{w}w"] = _roc(close, w)
            row["_composite_prev"] = float(np.nanmean(
                [_roc(close, w, offset=ROTATION_LOOKBACK_WEEKS) for w in windows]))
            rows.append(row)
    else:
        print("[global_theme] cache/fund_niche_themes.csv saknas – faller tillbaka på "
              "handplockad lista (kör altdata.avanza fund_categories + "
              "altdata/fund_theme_classifier.py classify för det rikare, fee-optimerade urvalet)")
        for ticker, (theme, etf_name) in GLOBAL_THEMES.items():
            close = pf._safe(lambda tk=ticker: pf._avanza_weekly_close(tk), None, f"global-tema {ticker}")
            if close is None or close.dropna().empty:
                print(f"[global_theme] {ticker} ({theme}): ingen prisdata, hoppar")
                continue
            row = {"theme": theme, "ticker": ticker, "etf_name": etf_name, "fee": None, "n_stocks": 1}
            for w in windows:
                row[f"momentum_{w}w"] = _roc(close, w)
            row["_composite_prev"] = float(np.nanmean(
                [_roc(close, w, offset=ROTATION_LOOKBACK_WEEKS) for w in windows]))
            rows.append(row)

        for oid, (theme, etf_name) in GLOBAL_THEMES_BY_ID.items():
            close = pf._safe(lambda i=oid: _weekly_close_by_id(i), None, f"global-tema id={oid}")
            if close is None or close.dropna().empty:
                print(f"[global_theme] id={oid} ({theme}): ingen prisdata, hoppar")
                continue
            row = {"theme": theme, "ticker": f"id:{oid}", "etf_name": etf_name, "fee": None, "n_stocks": 1}
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
    cols = ["rank", "theme", "ticker", "fee", "composite_score", "rank_change", "flow"]
    print(df[cols].to_string(index=False, float_format="{:.3f}".format))
    print(f"\n[global_theme] {len(df)} tema(n) -> {p}")


if __name__ == "__main__":
    build()
