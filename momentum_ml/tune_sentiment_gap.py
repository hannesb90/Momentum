"""
tune_sentiment_gap.py – LLM-sentiment UTAN prisreaktion: har marknaden missat
att ett PM var genuint positivt?

Samma gap-mönster som tune_earnings_reaction_gap.py/tune_insider_gap.py, men
med LLM-sentimentscoren (altdata/sentiment.py, cache/sentiment/<pm_id>.json,
{"sentiment": -2..2, "materiality": 0/1, ...}) som trigger i stället för
hårda siffror/insynsköp:
  · "Surprise" = LLM-sentimentet för PM:et (aktieägar-ton, -2..2), oberoende
    av hur kursen rörde sig.
  · "Reaktion" = samma token-fria abnormal-avkastning-proxy som PEAD/
    earnings-gapet/insynsköp-gapet använder, veckan PM:et publicerades.
Hypotesen: PM med genuint positivt sentiment men DÄMPAD prisreaktion
(marknaden har inte hunnit reagera på vad texten faktiskt sa) borde ge en
fördröjd uppvärdering.

Datakällor (redan cachade på Pi:n, inget nätverksanrop, inga nya LLM-anrop):
  · cache/mfn/<ticker>.json – MFN-poster, strömmande (en fil i taget, samma
    minnesskäl som altdata/pead.load_report_dates/mfn_events.load_insider_events).
  · cache/sentiment/<pm_id>.json – redan scorade PM (8799 st i cachen just
    nu), nyckel = PM:ets 'id'-fält med "".join(alnum-or-underscore) precis
    som altdata/sentiment._cache_path.
  · data/data_loader.fetch_weekly_data – veckopris, cachad.

Kör (från /opt/momentum/src/momentum_ml eller motsvarande deploy-katalog):
    /opt/momentum/venv/bin/python tune_sentiment_gap.py [large|small]
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, load_sweden_universe

HORIZONS = [8, 26]


def _safe_id(pid: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(pid))[:80]


def _load_sentiment_events() -> pd.DataFrame:
    """cache/mfn/<ticker>.json (strömmande) join:ad mot cache/sentiment/<id>.json
    → [{ticker, published, sentiment, materiality}] för PM där båda finns."""
    mfn_dir = Path(config.MFN_CACHE_DIR)
    sent_dir = Path(config.SENTIMENT_CACHE_DIR)
    if not mfn_dir.exists() or not sent_dir.exists():
        return pd.DataFrame()
    rows = []
    for f in mfn_dir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for it in items:
            pid = it.get("id")
            published = it.get("published")
            if not pid or not published:
                continue
            sp = sent_dir / f"{_safe_id(pid)}.json"
            if not sp.exists():
                continue
            try:
                sd = json.loads(sp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            sentiment = sd.get("sentiment")
            if not isinstance(sentiment, (int, float)):
                continue
            rows.append({"ticker": f.stem, "published": published,
                          "sentiment": float(sentiment),
                          "materiality": sd.get("materiality", 0)})
    return pd.DataFrame(rows)


def main():
    seg = sys.argv[1] if len(sys.argv) > 1 else "large"
    seg_cfg = config.SEGMENTS[seg]

    events = _load_sentiment_events()
    if events.empty:
        print(f"Ingen sentiment-cache hittad i {config.SENTIMENT_CACHE_DIR} som matchar "
              f"MFN-cachen i {config.MFN_CACHE_DIR}. Kör altdata/sentiment.py score_segment(...) först.")
        return
    events["published"] = pd.to_datetime(events["published"], errors="coerce", utc=True).dt.tz_localize(None)
    events = events.dropna(subset=["published"])
    print(f"{len(events)} PM med sentiment-score, {events['ticker'].nunique()} bolag "
          f"(sentiment-fördelning: {events['sentiment'].value_counts().sort_index().to_dict()})")

    tickers, *_ = load_sweden_universe(min_market_cap=seg_cfg["market_cap"])
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

    # ── Poolade percentilrankningar: sentiment + reaktionens magnitud ──
    events["sent_rank"] = events["sentiment"].rank(pct=True)
    events["reaction_mag_rank"] = events["reaction"].abs().rank(pct=True)
    events["gap_score"] = events["sent_rank"] - events["reaction_mag_rank"]
    events["sent_only_score"] = events["sent_rank"]

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
    print(f"  SENTIMENT-GAP (LLM-ton UTAN prisreaktion) · segment {seg}")
    print("=" * 78)
    for label, score_col in (("gap_score (sentiment − |reaktion|)", "gap_score"),
                              ("sent_only (rått sentiment, ingen reaktionsfilter)", "sent_only_score")):
        print(f"\n  {label}")
        print(f"  {'period':<10}{'horisont':>10}{'IC':>10}{'Q5-Q1':>10}{'n':>8}")
        print("  " + "-" * 48)
        for h in HORIZONS:
            full = ic_and_spread(events, score_col, f"x_{h}")
            ho = ic_and_spread(events[events["published"] >= holdout_start], score_col, f"x_{h}")
            print(f"  {'hela':<10}{h:>9}v{full[0]:>10.3f}{full[1]:>10.2%}{full[2]:>8}")
            print(f"  {'holdout':<10}{h:>9}v{ho[0]:>10.3f}{ho[1]:>10.2%}{ho[2]:>8}")

    print("""
  Dom: gap_score bör slå sent_only_score (visar att reaktionsfiltret TILLFÖR
  något utöver "sentimentet var positivt") OCH ha |IC| ≥ 0.03-0.05 med
  positiv Q5-Q1 på 8v/26v-horisonten för att vara värd att bygga in. Slår
  gap_score inte sent_only_score → idén om "marknaden missade sentimentet"
  håller inte, bara sentimentet självt gör jobbet.""")


if __name__ == "__main__":
    main()
