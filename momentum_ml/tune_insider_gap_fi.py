"""
tune_insider_gap_fi.py – samma fråga som tune_insider_gap.py ("insynsköp-
kluster UTAN prisreaktion → fördröjd uppvärdering?"), men mot Finansinspek-
tionens FULLA öppna insynsregister (altdata/fi_insynsregistret.py) i stället
för MFN-cachens tunna delmängd.

Bakgrund: tune_insider_gap.py landade OAVGJORT (2026-07-19) - bara 30 PDMR-
poster totalt i MFN-cachen, för tunt för en slutsats åt något håll. FI:s
EGET register (lagstadgad rapportering av ALL insynshandel) är den
fullständiga källan MFN bara speglar en bråkdel av - det här skriptet kör
EXAKT samma nedströms-analys (gap_score vs. buy_only_score, IC/Q5-Q1 per
horisont) på den rikare datan, för en direkt jämförbar, förhoppningsvis
avgörande, körning.

Skiljer sig ENDAST i datakällan/laddningsfunktionen - allt nedströms
(reaktionsproxy, gap_score, IC/Q5-Q1, holdout-uppdelning) är kopierat rakt
av från tune_insider_gap.py för att vara en ärlig, jämförbar omkörning.

Kör (nät krävs FÖRSTA gången per bolag - evigt cachat sedan i cache/fi_insyn/):
    /opt/momentum/venv/bin/python tune_insider_gap_fi.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import re

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe
from altdata.fi_insynsregistret import fetch_issuer_transactions, BUY_CHARACTERS, SELL_CHARACTERS

HORIZONS = [8, 26]
CLUSTER_WINDOW_DAYS = 90


def _clean_name(name: str) -> str:
    """BUGG (fixad, 2026-07-23): sweden_universe.csv:s namn ("AB Electrolux
    (publ)") matchar sällan FI:s exakta registrerade juridiska form
    ("Aktiebolaget Electrolux") - 128 av 181 bolag gav noll träffar innan
    denna fix. FI:s Utgivare-sökning gör DELSTRÄNGS-matchning - att söka på
    bara kärnnamnet ("Electrolux", "SKF", "Sagax") träffar oavsett om den
    fulla juridiska formen är "AB X", "Aktiebolaget X" eller "X (publ)"."""
    n = re.sub(r"\(publ\.?\)", "", name, flags=re.I).strip()
    n = re.sub(r"\s+Class\s+[A-Z]$", "", n, flags=re.I).strip()
    n = re.sub(r"^(AB|Aktiebolaget)\s+", "", n, flags=re.I).strip()
    n = re.sub(r"\s+AB$", "", n, flags=re.I).strip()
    return n or name


def _load_buy_events_with_net_fi(name_to_ticker: dict) -> pd.DataFrame:
    """Samma utdata-form som tune_insider_gap.py:s _load_buy_events_with_net()
    (ticker, published, net_buys_90d) - men källan är FI:s fulla register,
    hämtat per unikt bolagsnamn (flera aktieslag/tickers kan dela namn)."""
    all_events = []
    names = sorted(name_to_ticker.keys())
    for i, name in enumerate(names):
        rows = fetch_issuer_transactions(name)
        if (i + 1) % 25 == 0:
            print(f"  ... {i + 1}/{len(names)} bolag hämtade (FI), {len(all_events)} köp/sälj hittills")
        for r in rows:
            char = r.get("character")
            if char not in BUY_CHARACTERS and char not in SELL_CHARACTERS:
                continue
            if r.get("instrument_type") != "Aktie":
                continue   # bara underliggande aktien - inte optioner/warrants/BTU
            side = "buy" if char in BUY_CHARACTERS else "sell"
            pub = pd.to_datetime(r["publish_date"], errors="coerce")
            if pd.isna(pub):
                continue
            for ticker in name_to_ticker[name]:
                all_events.append({"ticker": ticker, "published": pub, "side": side})

    if not all_events:
        return pd.DataFrame()
    df = pd.DataFrame(all_events)
    out = []
    for t, g in df.groupby("ticker"):
        g = g.sort_values("published").reset_index(drop=True)
        dates = g["published"].values
        sides = g["side"].values
        for i, row in g.iterrows():
            if row["side"] != "buy":
                continue
            win_start = row["published"] - pd.Timedelta(days=CLUSTER_WINDOW_DAYS)
            mask = (dates > np.datetime64(win_start)) & (dates <= np.datetime64(row["published"]))
            net = int((sides[mask] == "buy").sum() - (sides[mask] == "sell").sum())
            out.append({"ticker": t, "published": row["published"], "net_buys_90d": net})
    return pd.DataFrame(out)


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
    uni = pd.read_csv(config.anchor("data/sweden_universe.csv"))
    uni = uni[uni["ticker"].isin(tickers)]
    name_to_ticker: dict = {}
    for _, row in uni.iterrows():
        name_to_ticker.setdefault(_clean_name(row["name"]), []).append(row["ticker"])

    print(f"[tune_insider_gap_fi] hämtar FI-insynsdata för {len(name_to_ticker)} unika bolagsnamn "
          f"({len(tickers)} tickers, segment {seg})...")
    events = _load_buy_events_with_net_fi(name_to_ticker)
    if events.empty:
        print("Inga insynsköp hittade via FI - avbryter.")
        return
    print(f"\n{len(events)} köp-PM med nettoköp-kontext, {events['ticker'].nunique()} bolag "
          f"(jmf tune_insider_gap.py/MFN: 30 poster totalt).")

    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    px.index = pd.to_datetime(px.index)
    rets = px.pct_change()
    market = rets.mean(axis=1)
    abn = rets.sub(market, axis=0)

    events = events[events["ticker"].isin(px.columns)].copy()
    weeks = px.index

    def _week_of(ts):
        pos = weeks.searchsorted(ts, side="left")
        return weeks[pos] if pos < len(weeks) else None

    events["event_week"] = events["published"].apply(_week_of)
    events = events.dropna(subset=["event_week"])

    events["reaction"] = [
        abn.at[wk, tk] if (wk in abn.index and tk in abn.columns) else np.nan
        for wk, tk in zip(events["event_week"], events["ticker"])
    ]
    for h in HORIZONS:
        vals = []
        for wk, tk in zip(events["event_week"], events["ticker"]):
            s = px[tk] if tk in px.columns else None
            if s is None or wk not in px.index:
                vals.append(np.nan)
                continue
            pos = px.index.get_loc(wk)
            if pos + h < len(px.index) and pd.notna(s.iloc[pos]) and s.iloc[pos] != 0:
                vals.append(s.iloc[pos + h] / s.iloc[pos] - 1)
            else:
                vals.append(np.nan)
        events[f"fwd_{h}"] = vals

    events = events.dropna(subset=["reaction"])
    events["year"] = events["published"].dt.year
    for h in HORIZONS:
        col = f"fwd_{h}"
        events[f"x_{h}"] = events[col] - events.groupby("year")[col].transform("mean")

    events["buy_rank"] = events["net_buys_90d"].rank(pct=True)
    events["reaction_mag_rank"] = events["reaction"].abs().rank(pct=True)
    events["gap_score"] = events["buy_rank"] - events["reaction_mag_rank"]
    events["buy_only_score"] = events["buy_rank"]

    holdout_start = pd.Timestamp.now() - pd.DateOffset(weeks=config.HOLDOUT_WEEKS)

    def ic_and_spread(df, score_col, x_col):
        sub = df.dropna(subset=[score_col, x_col])
        if len(sub) < 20:
            return float("nan"), float("nan"), len(sub)
        ic = sub[score_col].rank().corr(sub[x_col].rank())
        q5 = sub[sub[score_col] >= sub[score_col].quantile(0.8)][x_col].mean()
        q1 = sub[sub[score_col] <= sub[score_col].quantile(0.2)][x_col].mean()
        return ic, (q5 - q1), len(sub)

    print("\n" + "=" * 78)
    print(f"  INSYNSKÖP-GAP (FI-registret, fullständigt) · segment {seg}")
    print("=" * 78)
    for label, score_col in (("gap_score (nettoköp − |reaktion|)", "gap_score"),
                              ("buy_only (rått nettoköp, ingen reaktionsfilter)", "buy_only_score")):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n':>8}")
        print("  " + "-" * 48)
        for h in HORIZONS:
            full = ic_and_spread(events, score_col, f"x_{h}")
            ho = ic_and_spread(events[events["published"] >= holdout_start], score_col, f"x_{h}")
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>8}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>8}")

    print("""
  Dom (samma tröskel som tune_insider_gap.py): gap_score bör slå buy_only_score
  OCH ha |IC| >= 0.03-0.05 med positiv Q5-Q1 på 8v/26v-horisonten för att vara
  värd att bygga in.""")


if __name__ == "__main__":
    main()
