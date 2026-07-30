"""
tune_feature_multicollinearity.py – Punkt 9 i uppföljningslistan (2026-07-29):
hur korrelerade är de 48 (large-segmentet, efter drop_features) features
modellen tränas på? Ren analys, ingen omträning - kan ablationen ha missat
brus som bara syns som "signal" för att den korrelerar med en riktig
prediktor, snarare än att bära egen information?

Två mått:
  Pearson-korrelationsmatris – hittar PARVIS starkt korrelerade features
                                (|r| > 0.8), lätt att tolka men missar
                                multikollinearitet som uppstår från FLERA
                                features tillsammans.
  VIF (Variance Inflation Factor) – VIF_i = 1/(1-R_i^2) där R_i^2 kommer
                                     från att regrediera feature i mot ALLA
                                     andra features. Fångar den "flera
                                     features tillsammans"-effekten som
                                     parvis korrelation missar. Tumregel:
                                     VIF > 10 = allvarlig multikollinearitet,
                                     5-10 = måttlig, värd att hålla koll på.
                                     statsmodels finns inte i venv, så VIF
                                     räknas manuellt via sklearn LinearRegression
                                     (samma formel, inget statsmodels-beroende).

OBS: LightGBM (trädbaserad) är i sig robust mot multikollinearitet vad gäller
PREDIKTIONSKVALITET (den väljer bara en av två korrelerade features per split
utan att det stör resultatet) - problemet multikollinearitet faktiskt orsakar
här är instabil FEATURE IMPORTANCE (vilken av två korrelerade features som
"får äran" kan variera slumpmässigt mellan walk-forward-splits), vilket gör
feature_importance_history_ svårtolkad och ablationsbeslut osäkra.

Körs på dev-delen (samma HOLDOUT_WEEKS-gräns som huvudpipelinen), återanvänder
feature-cachen.

    /opt/momentum/venv/bin/python3 tune_feature_multicollinearity.py large
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import config

segment = sys.argv[1] if len(sys.argv) > 1 else config.DEFAULT_SEGMENT
seg     = config.SEGMENTS.get(segment) or config.SEGMENTS[config.DEFAULT_SEGMENT]
if "drop_features" in seg:
    config.DROP_FEATURES = seg["drop_features"]

from features.feature_engineering import FEATURE_COLS, build_all_features, attach_categorical_features, attach_fundamentals_features, to_model_df
from data.data_loader import fetch_weekly_data, filter_active_universe, filter_liquid_universe, load_sweden_universe
from sklearn.linear_model import LinearRegression

CORR_THRESHOLD = 0.80
VIF_WARN = 10.0
VIF_WATCH = 5.0


def top_correlated_pairs(corr: pd.DataFrame, threshold: float = CORR_THRESHOLD) -> pd.DataFrame:
    cols = corr.columns
    rows = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if abs(r) >= threshold:
                rows.append({"feature_a": cols[i], "feature_b": cols[j], "pearson_r": r})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.reindex(out["pearson_r"].abs().sort_values(ascending=False).index)
    return out


def compute_vif(X: pd.DataFrame) -> pd.Series:
    vifs = {}
    cols = list(X.columns)
    Xv = X.values
    for i, col in enumerate(cols):
        y = Xv[:, i]
        others = np.delete(Xv, i, axis=1)
        model = LinearRegression().fit(others, y)
        r2 = model.score(others, y)
        vifs[col] = float("inf") if r2 >= 0.999999 else 1.0 / (1.0 - r2)
    return pd.Series(vifs).sort_values(ascending=False)


if __name__ == "__main__":
    print(f"[multicollinearity] Bygger features för segment={segment} ({len(FEATURE_COLS)} features efter drop_features)...")
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=seg["market_cap"])
    config.SECTOR_MAP.update(sector_map)
    data = fetch_weekly_data(tickers, start=config.START_DATE, end=None, use_cache=True)
    data = filter_active_universe(data)
    data = filter_liquid_universe(data, min_avg_turnover=config.UNIVERSE_MIN_AVG_TURNOVER)
    feats = build_all_features(data)
    feats = attach_categorical_features(feats, sector_map=config.SECTOR_MAP, cap_tier_map=cap_tier_map)
    feats = attach_fundamentals_features(feats, segment=segment, prices=data)
    model_df = to_model_df(feats)

    dates = model_df.index.unique().sort_values()
    dev_df = model_df[model_df.index < dates[-config.HOLDOUT_WEEKS]] if len(dates) > config.HOLDOUT_WEEKS else model_df

    X = dev_df[FEATURE_COLS].fillna(0.0)
    # Konstanta/nästan-konstanta kolumner ger division med noll i VIF (R^2->1
    # trivialt eller odefinierat) - uteslut dem explicit, med varning.
    std = X.std()
    zero_var = std[std < 1e-9].index.tolist()
    if zero_var:
        print(f"[multicollinearity] VARNING: {len(zero_var)} feature(s) med ~0 varians, uteslutna ur VIF: {zero_var}")
    X_vif = X.drop(columns=zero_var)

    print(f"[multicollinearity] {len(X)} rader, {len(FEATURE_COLS)} features.")

    corr = X.corr(method="pearson")
    pairs = top_correlated_pairs(corr)

    print(f"\n{'='*90}\nPARVIS Pearson-korrelation |r| >= {CORR_THRESHOLD}\n{'='*90}")
    if pairs.empty:
        print(f"  Inga par över tröskeln {CORR_THRESHOLD}.")
    else:
        for _, r in pairs.iterrows():
            print(f"  {r['feature_a']:<28} {r['feature_b']:<28} r={r['pearson_r']:+.3f}")

    print(f"\n[multicollinearity] Beräknar VIF för {len(X_vif.columns)} features (kan ta en stund)...")
    vif = compute_vif(X_vif)

    print(f"\n{'='*90}\nVIF (Variance Inflation Factor) - topp 15, sorterat fallande\n{'='*90}")
    print(f"  {'feature':<28} {'VIF':>10}  flagga")
    for feat, v in vif.head(15).items():
        flag = "‼️ ALLVARLIG" if v >= VIF_WARN else ("⚠️ måttlig" if v >= VIF_WATCH else "")
        vs = "inf" if not np.isfinite(v) else f"{v:.2f}"
        print(f"  {feat:<28} {vs:>10}  {flag}")

    n_severe = int((vif >= VIF_WARN).sum())
    n_watch = int(((vif >= VIF_WATCH) & (vif < VIF_WARN)).sum())
    print(f"\n  {n_severe} features med VIF >= {VIF_WARN} (allvarlig), {n_watch} med {VIF_WATCH} <= VIF < {VIF_WARN} (måttlig).")

    out_dir = seg["results_dir"]
    corr.to_csv(f"{out_dir}/multicollinearity_corr_matrix.csv")
    pairs.to_csv(f"{out_dir}/multicollinearity_high_corr_pairs.csv", index=False)
    vif.rename("vif").to_csv(f"{out_dir}/multicollinearity_vif.csv")
    print(f"\n  Sparat: {out_dir}/multicollinearity_{{corr_matrix,high_corr_pairs,vif}}.csv")
