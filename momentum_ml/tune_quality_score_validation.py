"""
tune_quality_score_validation.py – har LLM/mjuk-kvalitetsbetyget (0-5,
quality_screener.py/soft_signals.py) NÅGON framåtavkastnings-edge, och är
ett lågt/obefintligt betyg i sig en varningssignal?

Samma fråga som #19 (tune_hold_forever_fundamentals.py) ställde för
fundamenta-kompositen (ROE+tillväxt+skuld) - men för en ANNAN signal
(LLM:ens kvalitativa 0-5-betyg). Ingen riktig point-in-time-historik finns
för det betyget (bara dagens ögonblicksbild, se portfolio.py:s kommentar om
varför modellval-backtest är omöjligt av samma skäl) - GROV APPROXIMATION
här: cache/quality/<ticker>.json:s filmodifieringstid används som
"ungefär när betyget först sattes" (LLM-anropet skrivs bara en gång per
ticker, cachas sedan för alltid - se quality_screener.score_company()).

VIKTIGA BEGRÄNSNINGAR (ärliga, innan resultatet läses):
  · mtime är INTE ett riktigt köpbeslutsdatum - bara "när screenern råkade
    köras för det bolaget", ofta batch-körd i klumpar över några dagar
    (se filernas faktiska datumspridning nedan). Svagare point-in-time-
    disciplin än #19:s riktiga modell-köpsignaler.
  · Ingen omvärdering: ett betyg satt i juli 2026 antas oförändrat även om
    det jämförs mot en händelse i juni - eftersom scoren FAKTISKT var
    statisk (cachad) fram tills screenern kördes om, är detta ändå en
    rättvis "vad hade jag sett just då"-approximation, bara grövre än #19.
  · "Opoängsatt"-gruppen (bolag helt utanför cache/quality/) får ett
    SLUMPMÄSSIGT jämförelsedatum draget ur samma fördelning som de
    poängsattas mtime - kontrollerar för att kalenderperioden i sig
    (marknadsläge) inte snedvrider jämförelsen.

Kör (Pi:n, ingen nätåtkomst behövs - allt redan cachat):
    /opt/momentum/venv/bin/python tune_quality_score_validation.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, '.')
import numpy as np
import pandas as pd

import config
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

HORIZONS_WEEKS = [13, 26, 52, 104]


def _load_scored() -> pd.DataFrame:
    qdir = Path(config.anchor(config.QUALITY_CACHE_DIR))
    rows = []
    for f in qdir.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        composite = d.get("composite")
        if composite is None:
            continue
        rows.append({
            "ticker": f.stem,
            "composite": float(composite),
            "known_date": pd.Timestamp(f.stat().st_mtime, unit="s").normalize(),
        })
    return pd.DataFrame(rows)


def main():
    scored = _load_scored()
    print(f"[tune_quality_score_validation] {len(scored)} bolag med LLM-kompositbetyg "
          f"(cache/quality/*.json), datumspridning {scored['known_date'].min().date()} -> "
          f"{scored['known_date'].max().date()}")

    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=None)
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    px = pd.DataFrame({t: d["Close"] for t, d in data.items() if "Close" in d}).sort_index()
    idx_level = (1 + px.pct_change().mean(axis=1).fillna(0)).cumprod()
    weeks = px.index

    scored = scored[scored["ticker"].isin(px.columns)].copy()
    scored["week_pos"] = weeks.searchsorted(scored["known_date"], side="left")
    scored = scored[scored["week_pos"] < len(weeks)]
    scored["tercil"] = pd.qcut(scored["composite"], 3, labels=["T1 (lågt)", "T2", "T3 (högt)"], duplicates="drop")

    # Opoängsatta: resten av universumet, slumpmässigt datum draget ur samma
    # fördelning som de poängsattas mtime - kontrollerar för kalenderperiod.
    rng = np.random.default_rng(42)
    unscored_tickers = [t for t in px.columns if t not in set(scored["ticker"])]
    sampled_dates = scored["known_date"].sample(n=len(unscored_tickers), replace=True, random_state=42).values
    unscored = pd.DataFrame({"ticker": unscored_tickers, "known_date": sampled_dates})
    unscored["week_pos"] = weeks.searchsorted(unscored["known_date"], side="left")
    unscored = unscored[unscored["week_pos"] < len(weeks)]

    def _stats(sub, h):
        excs = []
        for _, row in sub.iterrows():
            p0i, p1i = int(row["week_pos"]), int(row["week_pos"]) + h
            if p1i >= len(weeks) or row["ticker"] not in px.columns:
                continue
            p0, p1 = px[row["ticker"]].iloc[p0i], px[row["ticker"]].iloc[p1i]
            if pd.isna(p0) or pd.isna(p1) or p0 == 0:
                continue
            r = p1 / p0 - 1
            b = idx_level.iloc[p1i] / idx_level.iloc[p0i] - 1
            excs.append(r - b)
        if not excs:
            return None
        return (float(np.median(excs)), float(np.mean([e > 0 for e in excs])), len(excs))

    header = (f"  {'grupp':<12}{'n':>6}"
              + "".join(f"{f'{h}v exc':>10}{f'{h}v win%':>9}{f'{h}v n':>7}" for h in HORIZONS_WEEKS))
    print("\n" + "=" * len(header))
    print("  LLM-kvalitetsbetyg (0-5) vid ungefärligt känt-datum - median-excess & win% vs likaviktat index")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    groups = [(str(t), scored[scored["tercil"] == t]) for t in scored["tercil"].cat.categories]
    groups.append(("opoängsatt", unscored))
    for label, sub in groups:
        cells = f"  {label:<12}{len(sub):>6}"
        for h in HORIZONS_WEEKS:
            st = _stats(sub, h)
            if st is None:
                cells += f"{'–':>10}{'–':>9}{'–':>7}"
            else:
                e, w, n = st
                cells += f"{e:>+10.1%}{w:>8.0%} {n:>7}"
        print(cells)
    print("-" * len(header))
    print("  Läsning: håller tesen ska T3 (högt betyg) slå T1 (lågt) OCH opoängsatt-raden -")
    print("  annars ger LLM-betyget ingen mätbar edge här, eller (om opoängsatt slår alla) är")
    print("  ett obetygsatt bolag inte i sig ett varningstecken. OBS: grov mtime-approximation,")
    print("  se docstring - svagare point-in-time-disciplin än #19:s riktiga köpsignal-datum.")


if __name__ == "__main__":
    main()
