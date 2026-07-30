"""
tune_triple_barrier.py – [EDGE-5] Triple-barrier-target (López de Prado),
billig PILOT mot cachead prisdata (EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #15).
INTE en omträning/produktionsbeslut - en förutsättningskontroll: ger
triple-barrier-etiketten en rimligare/mer informativ målvariabel än
dagens XS_TARGET (kvantil av fast FORWARD_WEEKS-avkastning), innan man
investerar i en full omträning med ny targetdefinition (stor ändring,
skilt från `tune_metalabel.py`:s redan köade sekundära filter)?

Metod: för varje (ticker, startdatum) i det redan hämtade large-universumet,
sätt tre barriärer FRAMÅT från startdatumet:
  - övre (vinsthemtagning): +UPPER_PCT
  - undre (stop-loss):      -LOWER_PCT
  - vertikal (tidsgräns):   VERTICAL_WEEKS veckor (matchar produktionens
                            FORWARD_WEEKS=52 för large)
Etikett = vilken barriär som nås FÖRST (upper/lower/vertical), samt hur
många veckor det tog. Jämför sedan etikettens fördelning + hålltid mot
dagens fasta 52-veckors horisont, och en billig sanity-check: korrelerar
redan existerande momentum (`mom_12_1`, kausalt känt vid startdatumet) med
vilken barriär som nås, i den riktning man skulle förvänta (starkare
momentum -> oftare upper-hit, snabbare)?

Asymmetriska barriärer (+25%/-15%) reflekterar momentum-strategins egen
typiska risk/reward-profil, inte en optimerad parameter - en riktig
targetbyte skulle kräva ett eget kalibreringssteg.

    /opt/momentum/venv/bin/python3 tune_triple_barrier.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe

UPPER_PCT = 0.25
LOWER_PCT = 0.15
VERTICAL_WEEKS = 52
SAMPLE_STEP_WEEKS = 4   # sampla vart 4:e datum per ticker (billigare, färre överlappande fönster)


def triple_barrier_label(prices: pd.Series, start_idx: int, horizon: int, upper: float, lower: float):
    p0 = prices.iloc[start_idx]
    if pd.isna(p0) or p0 <= 0:
        return None
    end_idx = min(start_idx + horizon, len(prices) - 1)
    if end_idx <= start_idx:
        return None
    window = prices.iloc[start_idx + 1: end_idx + 1]
    rel = window / p0 - 1.0
    upper_hits = rel[rel >= upper]
    lower_hits = rel[rel <= -lower]
    upper_t = upper_hits.index[0] if len(upper_hits) else None
    lower_t = lower_hits.index[0] if len(lower_hits) else None
    if upper_t is not None and (lower_t is None or upper_t <= lower_t):
        weeks = window.index.get_loc(upper_t) + 1
        return {"label": "upper", "weeks": weeks, "ret": float(rel.loc[upper_t])}
    if lower_t is not None:
        weeks = window.index.get_loc(lower_t) + 1
        return {"label": "lower", "weeks": weeks, "ret": float(rel.loc[lower_t])}
    final_ret = float(rel.iloc[-1]) if len(rel) else 0.0
    return {"label": "vertical", "weeks": len(window), "ret": final_ret}


def main():
    seg = config.SEGMENTS["large"]
    tickers, _, _, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    data = fetch_weekly_data(tickers, start="2010-01-01", end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    print(f"[triple_barrier] {len(data)} tickers, barriärer +{UPPER_PCT:.0%}/-{LOWER_PCT:.0%}, "
          f"vertikal={VERTICAL_WEEKS}v, sampling var {SAMPLE_STEP_WEEKS}:e vecka.")

    rows = []
    for t, df in data.items():
        closes = df["Close"].dropna()
        if len(closes) < VERTICAL_WEEKS + 5:
            continue
        mom_12_1 = (closes / closes.shift(52 - 4) - 1).shift(4)   # grov 12-1-momentumapproximation, kausal
        for i in range(0, len(closes) - VERTICAL_WEEKS - 1, SAMPLE_STEP_WEEKS):
            r = triple_barrier_label(closes, i, VERTICAL_WEEKS, UPPER_PCT, LOWER_PCT)
            if r is None:
                continue
            m = mom_12_1.iloc[i] if i < len(mom_12_1) else np.nan
            rows.append({"ticker": t, "date": closes.index[i], "mom_12_1": m, **r})

    out = pd.DataFrame(rows)
    print(f"\n[triple_barrier] {len(out)} observationer.\n")

    print("=" * 80)
    print("Etikettfördelning (vilken barriär nås först)")
    print("=" * 80)
    dist = out["label"].value_counts(normalize=True)
    for label, frac in dist.items():
        sub = out[out["label"] == label]
        print(f"  {label:<10}: {frac:.1%}  (n={len(sub)}, medel hålltid={sub['weeks'].mean():.1f}v, "
              f"median={sub['weeks'].median():.0f}v)")
    print(f"\n  Jämför: dagens fasta horisont är ALLTID {VERTICAL_WEEKS}v, oavsett utfall.")
    hit_frac = 1 - dist.get("vertical", 0.0)
    print(f"  {hit_frac:.1%} av observationerna hade nått EN av barriärerna INNAN {VERTICAL_WEEKS}v "
          f"(triple-barrier hade gett en TIDIGARE, mer informativ etikett för dessa).")

    print("\n" + "=" * 80)
    print("Sanity-check: korrelerar mom_12_1 (kausalt känt vid start) med barriär-utfallet?")
    print("=" * 80)
    valid = out.dropna(subset=["mom_12_1"])
    for label in ["upper", "lower", "vertical"]:
        sub = valid[valid["label"] == label]
        if len(sub):
            print(f"  {label:<10}: medel mom_12_1={sub['mom_12_1'].mean():+.3f} (n={len(sub)})")
    ic = valid["mom_12_1"].rank().corr((valid["label"] == "upper").astype(int).rank())
    print(f"\n  Spearman(mom_12_1, upper-hit) = {ic:+.3f} (förväntat POSITIVT om momentum predicerar vinsthemtagning)")

    print("\n[triple_barrier] Klart.")


if __name__ == "__main__":
    main()
