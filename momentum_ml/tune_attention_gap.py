"""
tune_attention_gap.py – "Limited attention" (DellaVigna & Pollet 2009):
är PEAD-drivet starkare när rapportveckans HANDELSVOLYM var ovanligt låg
(marknaden ägnade rapporten mindre uppmärksamhet), oavsett hur mycket
priset rörde sig?

Skiljer sig från tune_report_crowding.py (som redan testats och förkastats):
den mätte hur många ANDRA bolag som rapporterade samma vecka. Här mäts i
stället bolagets EGEN omsättning rapportveckan mot dess normala nivå – ett
annat "limited attention"-fenomen: rapporter som drunknar i lågt handlat
värde (t.ex. fredags-PM, illikvida perioder) får mindre granskning oavsett
konkurrerande rapporter.

Samma token-fria PEAD-reaktion (rapportveckans abnormala avkastning) som
altdata/pead.py redan mäter, men här delas rapporthändelserna upp på
LÅG vs HÖG omsättning rapportveckan (relativt bolagets egna trailing 13v-
snitt FÖRE rapporten, för att undvika att rapportveckans egen volymspik
läcker in i normalnivån) och jämförs mot framåtavkastning.

Hypotesen: reaktionens prediktiva kraft (IC mot framåtavkastning) ska vara
TYDLIGT starkare i låg-volym-händelser än hög-volym-händelser.

Kör (från /opt/momentum/src/momentum_ml eller motsvarande deploy-katalog):
    /opt/momentum/venv/bin/python tune_attention_gap.py [large|small]
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe
from altdata.pead import load_report_dates

HORIZONS = [8, 26]
VOL_LOOKBACK_WEEKS = 13


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]
    tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])

    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    dvol = pd.DataFrame({t: (d["Close"] * d["Volume"]) for t, d in data.items()
                          if "Close" in d and "Volume" in d}).sort_index()
    rets = px.pct_change()
    market = rets.mean(axis=1)
    abn = rets.sub(market, axis=0)
    weeks = px.index

    # Trailing 13v-snitt omsättning FÖRE rapportveckan (shift(1) = exkluderar
    # veckan själv - annars läcker rapportveckans egen volymspik in i "normal").
    dvol_normal = dvol.rolling(VOL_LOOKBACK_WEEKS).mean().shift(1)

    report_dates = load_report_dates(config.MFN_CACHE_DIR)
    if not report_dates:
        print(f"Ingen MFN-cache i {config.MFN_CACHE_DIR}. Kör fetch_universe först.")
        return

    def _week_of(ts):
        pos = weeks.searchsorted(ts, side="left")
        return weeks[pos] if pos < len(weeks) else None

    rows = []
    for t, dates in report_dates.items():
        if t not in px.columns:
            continue
        for d in dates:
            wk = _week_of(pd.Timestamp(d))
            if wk is None or wk not in abn.index:
                continue
            reaction = abn.at[wk, t] if t in abn.columns else np.nan
            vol_wk = dvol.at[wk, t] if t in dvol.columns else np.nan
            vol_norm = dvol_normal.at[wk, t] if t in dvol_normal.columns else np.nan
            if pd.isna(reaction) or pd.isna(vol_wk) or pd.isna(vol_norm) or vol_norm == 0:
                continue
            rows.append({"ticker": t, "published": pd.Timestamp(d), "report_week": wk,
                          "reaction": reaction, "vol_ratio": vol_wk / vol_norm})
    events = pd.DataFrame(rows)
    if events.empty:
        print("Inga rapporthändelser med både reaktion och volymdata matchade.")
        return
    print(f"{len(events)} rapporthändelser, {events['ticker'].nunique()} bolag, "
          f"vol_ratio median={events['vol_ratio'].median():.2f}")

    for h in HORIZONS:
        vals = []
        for wk, t in zip(events["report_week"], events["ticker"]):
            s = px[t]
            pos = px.index.get_loc(wk)
            if pos + h < len(px.index) and pd.notna(s.iloc[pos]) and s.iloc[pos] != 0:
                vals.append(s.iloc[pos + h] / s.iloc[pos] - 1)
            else:
                vals.append(np.nan)
        events[f"fwd_{h}"] = vals

    events["year"] = events["published"].dt.year
    for h in HORIZONS:
        col = f"fwd_{h}"
        events[f"x_{h}"] = events[col] - events.groupby("year")[col].transform("mean")

    holdout_start = weeks[-1] - pd.DateOffset(weeks=config.HOLDOUT_WEEKS)
    low_vol = events["vol_ratio"] <= events["vol_ratio"].median()

    def ic_and_spread(df, x_col):
        sub = df.dropna(subset=["reaction", x_col])
        if len(sub) < 20:
            return float("nan"), float("nan"), len(sub)
        ic = sub["reaction"].rank().corr(sub[x_col].rank())
        q5 = sub[sub["reaction"] >= sub["reaction"].quantile(0.8)][x_col].mean()
        q1 = sub[sub["reaction"] <= sub["reaction"].quantile(0.2)][x_col].mean()
        return ic, (q5 - q1), len(sub)

    print("\n" + "=" * 78)
    print(f"  UPPMÄRKSAMHETS-GAP · PEAD-edge (reaktion → framåtavkastning) låg vs hög volym · {seg}")
    print("=" * 78)
    for label, mask in (("LÅG omsättning rapportveckan (<= median)", low_vol),
                         ("HÖG omsättning rapportveckan (> median)", ~low_vol)):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n':>8}")
        print("  " + "-" * 48)
        sub_all = events[mask]
        for h in HORIZONS:
            full = ic_and_spread(sub_all, f"x_{h}")
            ho = ic_and_spread(sub_all[sub_all["published"] >= holdout_start], f"x_{h}")
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>8}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>8}")

    print("""
  Dom: PEAD-IC/Q5-Q1 bör vara TYDLIGT starkare vid låg omsättning rapport-
  veckan än hög för att "limited attention"-hypotesen ska hålla. Ingen
  skillnad (eller omvänd) → idén tillför inget utöver PEAD:et som redan
  finns.""")


if __name__ == "__main__":
    main()
