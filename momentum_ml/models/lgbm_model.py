"""
models/lgbm_model.py – LightGBM LambdaRank-modell med walk-forward korsvalidering.

Baseline v1.0: Låst arkitektur baserad på cross-sectional ranking (lambdarank).
"""
import os
import gc
import json
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from features.feature_engineering import FEATURE_COLS

def walk_forward_splits(
    dates: pd.DatetimeIndex,
    train_weeks: int = config.TRAIN_WINDOW_WEEKS,
    val_weeks:   int = config.VAL_WINDOW_WEEKS,
    step_weeks:  int = config.TEST_STEP_WEEKS,
    embargo_weeks: int = config.EMBARGO_WEEKS,
) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex, pd.DatetimeIndex]]:
    unique_dates = dates.unique().sort_values()
    n = len(unique_dates)
    emb = max(int(embargo_weeks), 0)
    splits = []

    start = 0
    while start + train_weeks + val_weeks + step_weeks <= n:
        train_end = start + train_weeks
        val_end   = train_end + val_weeks
        test_end  = val_end + step_weeks

        train_cut = max(train_end - emb, start + 1)
        val_cut   = max(val_end - emb, train_end + 1)

        train_d = unique_dates[start:train_cut]
        val_d   = unique_dates[train_end:val_cut]
        test_d  = unique_dates[val_end:test_end]

        splits.append((train_d, val_d, test_d))
        start += step_weeks

    return splits


def sanity_check_features(train_df: pd.DataFrame, feature_cols: List[str], split_label: str = "") -> List[str]:
    """
    Varningar-bara sanity-check av ETT träningsfönster (RISK-4,
    EDGE_RISK_SCENARIO_TESTKO.md Tier 3 #22, validerad fristående i
    tune_feature_sanity_checks.py innan detta kopplades in 2026-07-30).
    Skriver INTE ut något själv och ändrar INGET träningsbeteende - bara en
    lista varningssträngar som anroparen väljer att skriva ut eller ej.
    Flaggar: hög NaN-andel (>30%), konstanta (noll varians) kolumner,
    exakta dubblettrader, grova extremvärden (|z|>8). Konstanta/NaN-tunga
    kolumner hanteras redan graciöst av LightGBM (ingen krasch) - det här
    är synlighet, inte ett skydd.
    """
    warnings = []
    X = train_df[feature_cols]

    nan_frac = X.isna().mean()
    for col, frac in nan_frac[nan_frac > 0.30].items():
        warnings.append(f"[NaN]{split_label} {col}: {frac:.0%} saknas i träningsfönstret")

    variance = X.var(numeric_only=True)
    for col in variance[variance.fillna(0) == 0].index:
        warnings.append(f"[KONSTANT]{split_label} {col}: noll varians i träningsfönstret")

    n_dup = int(X.dropna(how="all").duplicated(keep=False).sum())
    if n_dup > 0:
        warnings.append(f"[DUBBLETT]{split_label} {n_dup} rader med exakt identisk featurevektor")

    z = (X - X.mean()) / X.std(ddof=0).replace(0, np.nan)
    extreme = (z.abs() > 8).sum()
    for col, n in extreme[extreme > 0].items():
        warnings.append(f"[EXTREMVÄRDE]{split_label} {col}: {n} rader med |z|>8")

    return warnings


class MomentumLGBM:
    """
    Wrapper kring LightGBM med walk-forward ranking (LambdaRank).
    """

    def __init__(self, params: dict = None):
        # Parametrar anpassade för ranking
        self.params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "ndcg_eval_at": [10, 20],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 30,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "verbose": -1,
            "seed": config.RANDOM_SEED,
            **(params or {})
        }
        self.cls_models: List[lgb.Booster] = []  # För bakåtkompatibilitet (håller rankers)
        self.reg_models: List[lgb.Booster] = []  # Också pekad på rankers
        self.split_starts: List[pd.Timestamp] = []
        self.split_ends: List[pd.Timestamp] = []
        self._stale_warned: bool = False
        self.feature_cols_: List[str] = []
        self.feature_importance_: Optional[pd.DataFrame] = None
        self.feature_importance_history_: Optional[pd.DataFrame] = None
        self.fold_diagnostics_: List[dict] = []
        # Empirisk decil-kalibrering (tune_rank_calibration.py, 2026-07-29):
        # LambdaRank-migreringen tog bort isotonic-kalibreringen (.calibrators)
        # utan ersättning - prob_up blev en ren min-max-normaliserad rankscore
        # ("sorteringsprior"), inte en sannolikhet. decile_win_rates_[i] = empirisk
        # vinstfrekvens (mot target_signal) i decil i (0=lägst score, 9=högst),
        # skattad EN GÅNG på dev-data (ingen holdout-läckage). Används av
        # prob_up_calibrated i predict() - lämnar prob_up självt orört eftersom
        # det redan validerats fungera väl för RANGORDNING (Spearman=0.879 mot
        # empirisk vinstfrekvens), det är bara den absoluta skalan som är fel.
        self.decile_win_rates_: Optional[np.ndarray] = None

    def _checkpoint_path(self) -> Path:
        return Path(config.RESULTS_DIR) / "_lgbm_walkforward_checkpoint.joblib"

    def _checkpoint_key(self, df: pd.DataFrame) -> str:
        import hashlib
        h = hashlib.md5()
        h.update(str(self.params).encode())
        h.update(str(FEATURE_COLS).encode())
        return h.hexdigest()

    def _load_checkpoint(self, key: str) -> Optional[dict]:
        p = self._checkpoint_path()
        if p.exists():
            try:
                cp = joblib.load(p)
                if cp.get("key") == key:
                    return cp
            except Exception:
                pass
        return None

    def _save_checkpoint(self, key: str, next_split: int, cls_imp: list):
        p = self._checkpoint_path()
        try:
            joblib.dump({
                "key": key,
                "next_split": next_split,
                "cls_models": self.cls_models,
                "reg_models": self.reg_models,
                "split_starts": self.split_starts,
                "split_ends": self.split_ends,
                "cls_importances": cls_imp,
                "fold_diagnostics": self.fold_diagnostics_,
            }, p)
        except Exception:
            pass

    def fit_walk_forward(
        self,
        df: pd.DataFrame,
        train_weeks: int = config.TRAIN_WINDOW_WEEKS,
        val_weeks: int = config.VAL_WINDOW_WEEKS,
        step_weeks: int = config.TEST_STEP_WEEKS,
        embargo_weeks: int = config.EMBARGO_WEEKS,
    ) -> "MomentumLGBM":
        splits = walk_forward_splits(df.index, train_weeks=train_weeks, val_weeks=val_weeks,
                                      step_weeks=step_weeks, embargo_weeks=embargo_weeks)
        print(f"[LGBM] Walk-forward LambdaRank: {len(splits)} splits")
        self.feature_cols_ = list(FEATURE_COLS)

        key = self._checkpoint_key(df)
        start_i = 0
        cls_importances = []
        checkpoint = self._load_checkpoint(key)
        if checkpoint is not None:
            self.cls_models = checkpoint["cls_models"]
            self.reg_models = checkpoint["reg_models"]
            self.split_starts = checkpoint["split_starts"]
            self.split_ends = checkpoint.get("split_ends", [])
            cls_importances = checkpoint["cls_importances"]
            self.fold_diagnostics_ = checkpoint.get("fold_diagnostics", [])
            start_i = checkpoint["next_split"]
            print(f"  [checkpoint] Återupptar från split {start_i + 1}/{len(splits)}")

        for i, (train_d, val_d, test_d) in enumerate(splits):
            if i < start_i:
                continue
            
            # Sortera kronologiskt för att gruppera per rebalanseringsvecka
            train_df = df.loc[train_d].sort_index()
            val_df = df.loc[val_d].sort_index()
            test_df = df.loc[test_d].sort_index()

            sanity_warnings = sanity_check_features(train_df, FEATURE_COLS, f" split {i+1}")
            for w in sanity_warnings:
                print(f"  [sanity] {w}")

            print("DEBUG FEATURE_COLS in lgbm_model.py:", list(FEATURE_COLS))
            X_tr = train_df[FEATURE_COLS].values
            X_va = val_df[FEATURE_COLS].values
            X_te = test_df[FEATURE_COLS].values

            train_groups = train_df.groupby(level=0).size().values
            val_groups = val_df.groupby(level=0).size().values

            # Skapa relevanslabels (0-4) per datum
            y_tr_rel = train_df.groupby(level=0)["target_return"].transform(
                lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
            ).values
            y_va_rel = val_df.groupby(level=0)["target_return"].transform(
                lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
            ).values

            if len(X_tr) < 100:
                print(f"  Split {i}: för lite data, hoppar.")
                self._save_checkpoint(key, i + 1, cls_importances)
                continue

            # Tidsutjämning (Equal Date Weighting)
            sizes_tr = train_df.groupby(level=0).size()
            w_tr = (1.0 / sizes_tr.reindex(train_df.index)).values.astype(np.float32)

            ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr)
            ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)

            model = lgb.train(
                self.params,
                ds_tr,
                num_boost_round=500,
                valid_sets=[ds_va],
                callbacks=[lgb.early_stopping(50, verbose=False)]
            )
            print(f"DEBUG: split {i} booster features length: {len(model.feature_name())}, X_tr shape: {X_tr.shape}")

            self.cls_models.append(model)
            self.reg_models.append(model)  # Samma rankingbooster fungerar för båda i gränssnittet
            cls_importances.append(model.feature_importance(importance_type="gain"))

            self.split_starts.append(test_d[0])
            self.split_ends.append(test_d[-1])

            # Enkel fold-utvärdering på NDCG@10
            test_df = test_df.copy()
            test_df["score"] = model.predict(X_te)
            ndcgs = []
            for date, group in test_df.groupby(level=0):
                if len(group) >= 10:
                    sorted_g = group.sort_values(by="score", ascending=False)
                    actual_relevance = sorted_g["target_return"].rank(pct=True).values
                    ndcgs.append(actual_relevance[:10].mean()) # proxy
            
            mean_ndcg = np.mean(ndcgs) if ndcgs else 0.0
            
            self.fold_diagnostics_.append({
                "split": i + 1, "n_splits": len(splits),
                "test_start": test_d[0], "test_end": test_d[-1], "n_test": len(X_te),
                "hit_rate": mean_ndcg, "mean_return_if_bought": float(test_df["target_return"].mean()),
                "pseudo_sharpe": None, "reg_ic": None, "reg_decile_spread": None
            })

            self._save_checkpoint(key, i + 1, cls_importances)
            print(f"  Split {i+1}/{len(splits)}: test {test_d[0].date()}–{test_d[-1].date()} | NDCG Proxy: {mean_ndcg:.4f}")

        if cls_importances:
            self.feature_importance_history_ = pd.DataFrame(
                cls_importances, columns=FEATURE_COLS, index=pd.DatetimeIndex(self.split_starts, name="split_start"),
            )
            self.feature_importance_ = pd.DataFrame({
                "feature": FEATURE_COLS,
                "cls_importance": np.mean(cls_importances, axis=0),
                "reg_importance": np.mean(cls_importances, axis=0),
            }).sort_values("cls_importance", ascending=False)

        self._checkpoint_path().unlink(missing_ok=True)
        return self

    def fit_serving(self, df: pd.DataFrame, val_weeks: int = 26) -> "MomentumLGBM":
        dates = df.index.unique().sort_values()
        self.feature_cols_ = list(FEATURE_COLS)
        train_dates, val_dates = dates[:-val_weeks], dates[-val_weeks:]
        
        train_df = df.loc[train_dates].sort_index()
        val_df = df.loc[val_dates].sort_index()
        
        X_tr = train_df[FEATURE_COLS].values
        X_va = val_df[FEATURE_COLS].values
        
        train_groups = train_df.groupby(level=0).size().values
        val_groups = val_df.groupby(level=0).size().values
        
        y_tr_rel = train_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        ).values
        y_va_rel = val_df.groupby(level=0)["target_return"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else 0
        ).values

        # Tidsutjämning (Equal Date Weighting)
        sizes_tr = train_df.groupby(level=0).size()
        w_tr = (1.0 / sizes_tr.reindex(train_df.index)).values.astype(np.float32)

        ds_tr = lgb.Dataset(X_tr, label=y_tr_rel, group=train_groups, weight=w_tr)
        ds_va = lgb.Dataset(X_va, label=y_va_rel, group=val_groups, reference=ds_tr)

        model = lgb.train(
            self.params,
            ds_tr,
            num_boost_round=500,
            valid_sets=[ds_va],
            callbacks=[lgb.early_stopping(50, verbose=False)]
        )
        self.cls_models = [model]
        self.reg_models = [model]
        self.split_starts = [dates[0]]
        self.split_ends = [dates[-1]]
        return self

    def predict(self, df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
        X = df[FEATURE_COLS].values
        model_idx = self._select_model_idx(df.index)
        self._warn_if_stale(df.index)

        scores = np.empty(len(df))
        for idx in np.unique(model_idx):
            mask = model_idx == idx
            scores[mask] = self.cls_models[idx].predict(X[mask], predict_disable_shape_check=True)

        # För ranking mappar vi scoren till prob_up som en sorteringsprior [0..1]
        # (vi normaliserar tvärsnittellt så att prob_up fungerar oförändrat i ensemble.py/toppN)
        df_out = pd.DataFrame(index=df.index)
        df_out["score"] = scores
        # Normalisera scoren tvärsnittellt till 0-1
        df_out["prob_up"] = df_out.groupby(level=0)["score"].transform(
            lambda x: (x - x.min()) / (x.max() - x.min() + 1e-9) if x.max() > x.min() else 0.5
        )
        df_out["prob_raw"] = scores
        df_out["pred_signal"] = (df_out["prob_up"] > 0.5).astype(int)
        df_out["pred_return"] = scores  # Rankscore agerar som relativ pred_return i sortering

        # prob_up_calibrated: EN RIKTIG sannolikhet (till skillnad från prob_up
        # ovan) för konsumenter som matematiskt kräver det - i praktiken bara
        # Kelly-sizing (models/ensemble.py:s kelly_position_size). Mappar varje
        # akties tvärsnittella percentil till den empiriska decil-vinstfrekvensen
        # via interpolation (robust även för datum med få tickers, till skillnad
        # från en hård qcut-decil). Faller tillbaka till prob_up oförändrat om
        # ingen kalibreringstabell är satt (äldre sparade modeller).
        decile_win_rates = getattr(self, "decile_win_rates_", None)
        if decile_win_rates is not None:
            pct = df_out.groupby(level=0)["score"].rank(pct=True)
            decile_centers = (np.arange(len(decile_win_rates)) + 0.5) / len(decile_win_rates)
            df_out["prob_up_calibrated"] = np.interp(pct.values, decile_centers, decile_win_rates)
        else:
            df_out["prob_up_calibrated"] = df_out["prob_up"]

        return df_out

    def _select_model_idx(self, dates: pd.DatetimeIndex) -> np.ndarray:
        starts = pd.DatetimeIndex(self.split_starts)
        idx = starts.searchsorted(dates, side="right") - 1
        return np.clip(idx, 0, len(self.split_starts) - 1)

    def _warn_if_stale(self, dates: pd.DatetimeIndex, threshold_weeks: int = 4 * config.TEST_STEP_WEEKS) -> None:
        ends = getattr(self, "split_ends", None)
        if not ends or getattr(self, "_stale_warned", False) or len(dates) == 0:
            return
        last_end = pd.DatetimeIndex(ends).max()
        max_date = pd.DatetimeIndex(dates).max()
        staleness_weeks = (max_date - last_end).days / 7.0
        if staleness_weeks > threshold_weeks:
            self._stale_warned = True

    def save(self, path: str = "results/lgbm_model.pkl"):
        Path(path).parent.mkdir(exist_ok=True, parents=True)
        joblib.dump(self, path)
        print(f"[LGBM] LambdaRank-modell sparad: {path}")

    @classmethod
    def load(cls, path: str = "results/lgbm_model.pkl") -> "MomentumLGBM":
        return joblib.load(path)

    def print_feature_importance(self, top_n: int = 20):
        if self.feature_importance_ is None:
            print("Träna modellen först.")
            return
        print(f"\n{'='*50}\nTop-{top_n} feature importance (ranking)\n{'='*50}")
        print(self.feature_importance_.head(top_n).to_string(index=False))

    def print_feature_importance_by_period(self, n_periods: int = 3, top_n: int = 10):
        if self.feature_importance_history_ is None:
            print("Träna modellen först.")
            return
        print(f"\n{'='*50}\nFeature importance per period (top-{top_n})\n{'='*50}")
        # Gruppera eller visa de senaste n perioderna
        df_hist = self.feature_importance_history_.tail(n_periods)
        for date, row in df_hist.iterrows():
            print(f"\nPeriod start: {date.date() if hasattr(date, 'date') else date}")
            top_feats = row.sort_values(ascending=False).head(top_n)
            for feat, val in top_feats.items():
                print(f"  {feat:<30}: {val:.2f}")

    def print_fold_diagnostics(self):
        if not self.fold_diagnostics_:
            print("Träna modellen först.")
            return
        print(f"\n{'='*50}\nPer-fold diagnostik ({len(self.fold_diagnostics_)} folds)\n{'='*50}")
        for diag in self.fold_diagnostics_:
            print(
                f"Split {diag['split']}/{diag['n_splits']}: "
                f"test {diag['test_start'].date() if hasattr(diag['test_start'], 'date') else diag['test_start']} "
                f"till {diag['test_end'].date() if hasattr(diag['test_end'], 'date') else diag['test_end']} | "
                f"NDCG Proxy / HR: {diag['hit_rate']:.4f} | n_test={diag['n_test']}"
            )

