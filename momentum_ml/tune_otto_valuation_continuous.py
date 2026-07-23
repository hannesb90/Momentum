"""
tune_otto_valuation_continuous.py – uppföljning på #25 (tune_otto_valuation_
band.py). Användarens invändning: Ottos "köpvärd" är byggt på en KONSERVATIV
FRAMTIDA EBIT(DA)-nivå x den låga multipeln - för förhoppningsbolag når
kursen sällan/aldrig ner dit. Det gör #25:s regel A (diskret händelse "kurs
NÅDDE egen-historisk-lägsta multipel") till fel test - den fångar genuina
nödlägen (resultatet har kollapsat), inte Ottos avsedda "attraktivt
risk/reward"-tröskel, som mest är en referenslinje, inte en tröskel som
förväntas nås ofta.

Två saker testas här i stället, återanvänder cache/otto_band/*.pkl (ingen
ny nätåtkomst):

  1. EMPIRISK KOLL på användarens påstående: hur OFTA når ett bolags
     multipel faktiskt ner till dess egen 10:e percentil (per konstruktion
     ~10% av åren för VILKET bolag som helst - percentiler är alltid
     "sällsynta" i sin egen definition)? Mer relevant: hur ofta är
     multipeln under HALVA sin egen mediannivå (en grövre, mer intuitiv
     "handlas till rabatt"-tröskel)?
  2. KONTINUERLIGT mått i stället för diskret händelse: bolagets ÅRLIGA
     multipel-PERCENTILRANK inom sin egen historik (0 = billigast någonsin,
     1 = dyrast någonsin) - IC mot framåtavkastning. Om "närmare sin egen
     botten = bättre framåtavkastning" håller ens svagt, ska IC vara
     negativ (låg percentilrank -> hög framtida excess) utan att kräva att
     ett diskret tröskelvärde faktiskt nås.

Kör (ingen nätåtkomst - läser bara cache/otto_band/*.pkl från #25):
    /opt/momentum/venv/bin/python tune_otto_valuation_continuous.py
"""
import pickle
import sys
from pathlib import Path

sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

HORIZONS_WEEKS = [13, 26, 52, 104]
CACHE_DIR = Path(__file__).parent / "cache" / "otto_band"


def main():
    cache_files = list(CACHE_DIR.glob("*.pkl"))
    print(f"[tune_otto_valuation_continuous] {len(cache_files)} cachade bolag hittade i {CACHE_DIR}")

    per_ticker = {}
    for cp in cache_files:
        # cache-nyckeln är ticker.replace('.', '_') - återskapa .ST/.DE-suffixet
        ticker = cp.stem.replace("_ST", ".ST").replace("_DE", ".DE")
        try:
            df = pickle.loads(cp.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        if not df.empty:
            per_ticker[ticker] = df

    # ── DEL 1: empirisk koll - hur ofta nås egen-historisk botten? ──
    below_10pct_count, below_half_median_count, total_obs = 0, 0, 0
    for t, df in per_ticker.items():
        for col in ("mult_ebit", "mult_ebitda"):
            vals = df[col].dropna()
            if len(vals) < 3:
                continue
            median = vals.median()
            p10 = vals.quantile(0.10)
            total_obs += len(vals)
            below_10pct_count += (vals <= p10).sum()
            below_half_median_count += (vals <= median * 0.5).sum()
            break
    print(f"\n[DEL 1] Empirisk koll ({total_obs} bolag/år-observationer):")
    print(f"  Andel år under egen 10:e percentilen: {below_10pct_count/total_obs:.1%} "
          f"(per konstruktion ~10% - kontrollerar bara att inget är trasigt)")
    print(f"  Andel år under HALVA egen medianmultipel: {below_half_median_count/total_obs:.1%} "
          f"- {'sällsynt, stödjer användarens poäng' if below_half_median_count/total_obs < 0.15 else 'inte särskilt sällsynt'}")

    # ── DEL 2: kontinuerlig percentilrank -> IC mot framåtavkastning ──
    tickers, sector_map, cap_map, name_map = load_sweden_universe(min_market_cap=None)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx_level = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    weeks = px.index

    def _fwd_excess(ticker, date, h):
        pos = weeks.searchsorted(date, side="left")
        p1i = pos + h
        if ticker not in px.columns or pos >= len(weeks) or p1i >= len(weeks):
            return None
        p0, p1 = px[ticker].iloc[pos], px[ticker].iloc[p1i]
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            return None
        r = p1 / p0 - 1
        b = idx_level.iloc[p1i] / idx_level.iloc[pos] - 1
        return r - b

    rows = []
    for t, df in per_ticker.items():
        for col in ("mult_ebit", "mult_ebitda"):
            vals = df[col].dropna()
            if len(vals) < 3:
                continue
            pct_rank = vals.rank(pct=True)   # 0=billigast NÅGONSIN, 1=dyrast NÅGONSIN
            for yr in vals.index:
                rows.append({"ticker": t, "year": yr, "date": df.loc[yr, "date"],
                            "pct_rank": pct_rank[yr]})
            break

    ev = pd.DataFrame(rows)
    print(f"\n[DEL 2] {len(ev)} bolag/år med giltig percentilrank.")

    for h in HORIZONS_WEEKS:
        ev[f"x_{h}"] = [_fwd_excess(r["ticker"], r["date"], h) for _, r in ev.iterrows()]

    print(f"\n  {'horisont':>10}{'IC':>10}{'Q1(billigast)':>16}{'Q5(dyrast)':>14}{'Q1-Q5':>10}{'n':>8}")
    print("  " + "-" * 68)
    for h in HORIZONS_WEEKS:
        sub = ev.dropna(subset=[f"x_{h}"])
        if len(sub) < 20:
            print(f"  {h:>9}v{'(för få)':>10}")
            continue
        ic = sub["pct_rank"].rank().corr(sub[f"x_{h}"].rank())
        q1 = sub[sub["pct_rank"] <= sub["pct_rank"].quantile(0.2)][f"x_{h}"].median()
        q5 = sub[sub["pct_rank"] >= sub["pct_rank"].quantile(0.8)][f"x_{h}"].median()
        print(f"  {h:>9}v{ic:>10.3f}{q1:>+15.1%}{q5:>+13.1%}{q1-q5:>+9.1%}{len(sub):>8}")

    print("\n  Läsning: NEGATIV IC stödjer 'billigare mot egen historik -> bättre framåtavkastning'")
    print("  (Q1 = billigaste femtedelen mot egen historik ska då slå Q5 = dyraste femtedelen).")
    print("  Det här är en KONTINUERLIG version av #25:s regel A - inget diskret tröskelvärde")
    print("  krävs, så den fångar det svagare, gradvisa sambandet #25:s alla-eller-inget-test missade.")


if __name__ == "__main__":
    main()
