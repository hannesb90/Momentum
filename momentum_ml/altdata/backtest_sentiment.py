"""
altdata/backtest_sentiment.py – Har PM-sentiment en ärlig OOS-edge?

Validate-first: INNAN sentiment byggs in i modellen mäter vi om signalen
rangordnar framåtavkastning rätt på rent OOS-data (2016+, samma fönster som
era_analysis.py). Måttet är capture-spread (mirror av capture_analysis.py):
ger högre PM-ton i snitt högre faktisk framtida avkastning?

Två test:
  1) EVENT-STUDIE: framåtavkastning efter starkt positiva vs starkt negativa PM
     (PEAD – driver tonen kursen veckorna efter?).
  2) TVÄRSNITT: varje vecka, aggregera varje bolags PM-ton i ett bakåtfönster,
     rangordna, mät spreaden topp- vs botten-tercil.

Point-in-time: ett PM räknas först från NÄSTA veckostängning efter publicering
(ingen look-ahead). Körs på Pi:n efter fetch + score:

    /opt/momentum/venv/bin/python altdata/backtest_sentiment.py large
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import pandas as pd
import numpy as np
import config
from data.data_loader import (
    fetch_weekly_data, filter_liquid_universe, filter_active_universe, load_sweden_universe,
)


def _load_scored(segment) -> pd.DataFrame:
    """Slår ihop MFN-cachen med sentiment-cachen → en rad per poängsatt PM."""
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    mfn_dir, sent_dir = Path(config.MFN_CACHE_DIR), Path(config.SENTIMENT_CACHE_DIR)
    rows = []
    for t in tickers:
        p = mfn_dir / f"{t}.json"
        if not p.exists():
            continue
        for it in json.loads(p.read_text()).get("items", []):
            sp = sent_dir / ("".join(c if c.isalnum() else "_" for c in it["id"])[:80] + ".json")
            if not sp.exists():
                continue
            s = json.loads(sp.read_text())
            rows.append({
                "ticker": t,
                "published": pd.to_datetime(it["published"], errors="coerce", utc=True),
                "sentiment": s.get("sentiment", 0),
                "materiality": s.get("materiality", 0),
                "category": s.get("category", "other"),
            })
    df = pd.DataFrame(rows).dropna(subset=["published"])
    df["published"] = df["published"].dt.tz_localize(None)
    # vikta tonen med materialitet (rutin-PM ska väga lätt)
    df["tone"] = df["sentiment"] * (df["materiality"] + 1)
    return df


def main():
    segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
    seg = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
    print(f"[Segment] {segment} ({seg['label']})")

    scored = _load_scored(segment)
    if scored.empty:
        print("[FEL] Inga poängsatta PM. Kör mfn_fetch.py fetch + sentiment.py score först.")
        return
    print(f"[data] {len(scored)} poängsatta PM, {scored['ticker'].nunique()} bolag, "
          f"{scored['published'].min().date()}–{scored['published'].max().date()}")

    tickers, sector_map, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)

    fwd = config.FORWARD_WEEKS
    oos = config.SENTIMENT_OOS_START

    # Veckopanel: close + framåtavkastning per ticker
    panels = []
    for t, d in data.items():
        c = d["Close"].copy()
        p = pd.DataFrame({"Date": c.index, "ticker": t, "close": c.values})
        p["fwd_ret"] = c.shift(-fwd).values / c.values - 1
        panels.append(p)
    px = pd.concat(panels, ignore_index=True)
    week_index = {t: d["Close"].index for t, d in data.items()}

    # Point-in-time: knyt varje PM till FÖRSTA veckostängning STRIKT efter
    # publicering. side="right" ger idx[pos] > ts, så det close vi "agerar på"
    # garanterat ligger efter PM:et oavsett om veckoindexet etiketteras med
    # veckans start eller slut (bulletproof mot date-only-tidsstämplar = ingen
    # look-ahead; i värsta fall en veckas extra fördröjning, vilket är konservativt).
    def next_week(t, ts):
        idx = week_index.get(t)
        if idx is None:
            return pd.NaT
        pos = idx.searchsorted(ts, side="right")
        return idx[pos] if pos < len(idx) else pd.NaT

    scored["eff_date"] = [next_week(r.ticker, r.published) for r in scored.itertuples()]
    scored = scored.dropna(subset=["eff_date"])

    # ── 1. EVENT-STUDIE ───────────────────────────────────────────────────────
    ev = scored.merge(px, left_on=["ticker", "eff_date"], right_on=["ticker", "Date"], how="inner")
    ev = ev[ev["Date"] >= oos].dropna(subset=["fwd_ret"])
    print("\n" + "=" * 72)
    print(f"  EVENT-STUDIE (OOS {oos}+) – {fwd}v framåtavkastning efter PM, per ton")
    print("=" * 72)
    if len(ev) < 30:
        print(f"  För få PM-event i OOS-fönstret ({len(ev)}) för slutsats.")
    else:
        pos = ev[ev["sentiment"] >= 1]["fwd_ret"]
        neg = ev[ev["sentiment"] <= -1]["fwd_ret"]
        neu = ev[ev["sentiment"] == 0]["fwd_ret"]
        for lbl, s in [("positiva PM (≥+1)", pos), ("neutrala  PM ( 0)", neu),
                       ("negativa PM (≤−1)", neg)]:
            if len(s):
                print(f"  {lbl}:  snitt fwd {s.mean():+6.1%}   median {s.median():+6.1%}  (n={len(s):,})")
        if len(pos) and len(neg):
            spread = pos.mean() - neg.mean()
            print("-" * 72)
            print(f"  SPREAD (pos − neg):  {spread:+.1%}-enheter  "
                  f"{'(positiv = PM-ton förutsäger drift = EDGE)' if spread > 0 else '(NEGATIV = ingen/omvänd edge)'}")
            # materiella PM bör ge starkare drift om signalen är äkta
            big = ev[ev["materiality"] >= 2]
            if len(big) > 30:
                bp = big[big["sentiment"] >= 1]["fwd_ret"].mean()
                bn = big[big["sentiment"] <= -1]["fwd_ret"].mean()
                print(f"  Endast VÄSENTLIGA PM (materiality≥2):  spread {bp - bn:+.1%}-enheter  (n={len(big):,})")

    # ── 2. TVÄRSNITT (veckovis aggregerad ton) ────────────────────────────────
    print("\n" + "=" * 72)
    print(f"  TVÄRSNITT (OOS {oos}+) – veckovis ton-rank vs {fwd}v framåtavkastning")
    print("=" * 72)
    # Aggregera per (ticker, eff_date): alla PM som mappar till SAMMA veckostängning
    # summeras (eff_date bucketar redan in PM:en veckovis ≈ SENTIMENT_LOOKBACK_DAYS).
    # OBS metod: terciler tas på den POOLADE ton-fördelningen (inte rank inom varje
    # vecka). Ton är dessutom diskret (sentiment×materialitet) → grova terciler. Det
    # är ett rimligt v1-mått; en striktare per-vecka-tvärsnittsrank kan läggas till
    # om signalen visar sig bära edge.
    agg = (scored.groupby(["ticker", "eff_date"])["tone"].sum().reset_index()
           .rename(columns={"eff_date": "Date"}))
    m = px.merge(agg, on=["ticker", "Date"], how="left")
    m["tone"] = m["tone"].fillna(0.0)
    m = m[(m["Date"] >= oos)].dropna(subset=["fwd_ret"])
    news = m[m["tone"] != 0]
    if len(news) < 50:
        print(f"  För få bolag-veckor med PM-ton i OOS ({len(news)}) för tvärsnittsspread.")
    else:
        hi = news["tone"].quantile(0.67)
        lo = news["tone"].quantile(0.33)
        top = news[news["tone"] >= hi]["fwd_ret"].mean()
        bot = news[news["tone"] <= lo]["fwd_ret"].mean()
        nonews = m[m["tone"] == 0]["fwd_ret"].mean()
        print(f"  Hög ton  (topp-tercil):  snitt fwd {top:+.1%}  (n={len(news[news['tone']>=hi]):,})")
        print(f"  Låg ton  (botten-tercil):snitt fwd {bot:+.1%}  (n={len(news[news['tone']<=lo]):,})")
        print(f"  Ingen PM denna vecka:    snitt fwd {nonews:+.1%}  (n={len(m[m['tone']==0]):,})")
        print("-" * 72)
        print(f"  SPREAD (hög − låg):  {top - bot:+.1%}-enheter  "
              f"{'(positiv = ton rangordnar rätt → värt att bygga in)' if top > bot else '(NEGATIV = ingen edge)'}")

    print("\n  Tolkning: är BÅDA spreadarna tydligt positiva (och störst för "
          "materiella PM) finns en ärlig edge att bygga in som modell-feature.\n"
          "  Är de nära noll/negativa har pris-only-modellen redan allt – spara pengarna.")


if __name__ == "__main__":
    main()
