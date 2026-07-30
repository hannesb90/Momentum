"""
tune_feature_sanity_checks.py – [RISK-4] Automatiska sanity-checks före
träning (EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #22, FKO-diagnostiklista,
skärper LCA-39). Engångsbygge: en fristående, återanvändbar kontrollfunktion
som körs mot den redan cachade feature-panelen (results/abstention_features.pkl)
för att se om den FAKTISKT hittar något - inte bara ett teoretiskt verktyg.

Kontrollerar per walk-forward-split (samma splits träningen använder):
  1. NaN-andel per feature i träningsfönstret (hög andel = riskabel kolumn).
  2. Konstanta features (noll varians i just DET fönstret - kan vara
     legitimt för en enskild split även om featuren varierar globalt).
  3. Exakta dubblettrader (identisk hel featurevektor för två olika
     ticker/datum-par - kan indikera en pipeline-bugg, t.ex. att samma rad
     råkat kopieras).
  4. Extremvärden (|z-score| > 8 mot fönstrets egen medel/std - grova
     outliers som kan vara datafel snarare än äkta signal).

INTE inbakat i models/lgbm_model.py::fit_walk_forward ännu - kräver
uttryckligt godkännande innan produktionskod (models/*.py) ändras, per
projektets stående regel. Detta skript demonstrerar/validerar funktionen
fristående, körd en gång mot verklig data, innan ett sådant beslut tas.

    /opt/momentum/venv/bin/python3 tune_feature_sanity_checks.py
"""
import sys
sys.path.insert(0, ".")
import config
import numpy as np
import pandas as pd

from features.feature_engineering import to_model_df, FEATURE_COLS
from models.lgbm_model import walk_forward_splits


def sanity_check_split(train_df: pd.DataFrame, feature_cols: list, split_label: str) -> list:
    """Returnerar en lista varningssträngar (tom = allt rent) för EN splits träningsfönster."""
    warnings = []
    X = train_df[feature_cols]

    nan_frac = X.isna().mean()
    bad_nan = nan_frac[nan_frac > 0.30]
    for col, frac in bad_nan.items():
        warnings.append(f"[NaN] {col}: {frac:.0%} saknas i träningsfönstret")

    variance = X.var(numeric_only=True)
    constant = variance[variance.fillna(0) == 0]
    for col in constant.index:
        warnings.append(f"[KONSTANT] {col}: noll varians i träningsfönstret")

    dup_mask = X.dropna(how="all").duplicated(keep=False)
    n_dup = int(dup_mask.sum())
    if n_dup > 0:
        warnings.append(f"[DUBBLETT] {n_dup} rader med exakt identisk featurevektor")

    z = (X - X.mean()) / X.std(ddof=0).replace(0, np.nan)
    extreme = (z.abs() > 8).sum()
    extreme = extreme[extreme > 0]
    for col, n in extreme.items():
        warnings.append(f"[EXTREMVÄRDE] {col}: {n} rader med |z|>8")

    return warnings


def main():
    model_features = pd.read_pickle("results/abstention_features.pkl")
    model_df = to_model_df(model_features)
    all_dates = model_df.index.unique().sort_values()
    purge_start = all_dates[-(config.HOLDOUT_WEEKS + config.FORWARD_WEEKS)]
    dev_df = model_df[model_df.index < purge_start]
    splits = walk_forward_splits(dev_df.index)
    print(f"[sanity] Kontrollerar {len(splits)} splits × {len(FEATURE_COLS)} features "
          f"({dev_df.shape[0]:,} rader totalt i dev-perioden).\n")

    total_warnings = 0
    for i, (train_d, val_d, test_d) in enumerate(splits):
        train_sub = dev_df[dev_df.index.isin(train_d)]
        warns = sanity_check_split(train_sub, FEATURE_COLS, f"split {i+1}")
        if warns:
            print(f"  Split {i+1}/{len(splits)} ({train_d.min().date()}–{train_d.max().date()}, "
                  f"n={len(train_sub)}):")
            for w in warns:
                print(f"    {w}")
            total_warnings += len(warns)

    if total_warnings == 0:
        print("[sanity] INGA varningar över hela svepet – feature-panelen är ren "
              "(inga NaN>30%, konstanta kolumner, dubblettrader, eller |z|>8-extremvärden).")
    else:
        print(f"\n[sanity] {total_warnings} varningar totalt över {len(splits)} splits.")
    print("[sanity] Klart.")


if __name__ == "__main__":
    main()
