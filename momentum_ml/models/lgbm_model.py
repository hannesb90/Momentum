"""
models/lgbm_model.py – LightGBM bas-modell med walk-forward korsvalidering.

Output per sample:
  - prob_up      : P(avkastning > threshold)   [0..1]
  - pred_signal  : Köp(1) / Sälj(0)
  - pred_return  : förväntad avkastning (regression)
"""

import numpy as np
import pandas as pd
import lightgbm as lgb
import joblib
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from sklearn.isotonic import IsotonicRegression

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from features.feature_engineering import FEATURE_COLS


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward splitter
# ─────────────────────────────────────────────────────────────────────────────

def walk_forward_splits(
    dates: pd.DatetimeIndex,
    train_weeks: int = config.TRAIN_WINDOW_WEEKS,
    val_weeks:   int = config.VAL_WINDOW_WEEKS,
    step_weeks:  int = config.TEST_STEP_WEEKS,
    embargo_weeks: int = config.EMBARGO_WEEKS,
) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex, pd.DatetimeIndex]]:
    """
    Returnerar lista av (train_idx, val_idx, test_idx) som DatetimeIndex.
    Ingen framåtläckage – train slutar alltid innan val, val innan test.

    Purge/embargo: targets är FORWARD_WEEKS framåtavkastning, så en observation
    vid tid t bär ett label som beror på pris vid t+FORWARD_WEEKS. Utan gap
    skulle de sista observationerna i train ha labels som sträcker sig in i
    val-fönstret (och val in i test) – ett subtilt läckage som blåser upp
    out-of-sample-måtten. Vi rensar (purgar) därför de sista `embargo_weeks`
    observationerna ur train- respektive val-segmentet. Se López de Prado,
    Advances in Financial Machine Learning (purged k-fold).
    """
    unique_dates = dates.unique().sort_values()
    n = len(unique_dates)
    emb = max(int(embargo_weeks), 0)
    splits = []

    start = 0
    while start + train_weeks + val_weeks + step_weeks <= n:
        train_end = start + train_weeks
        val_end   = train_end + val_weeks
        test_end  = val_end + step_weeks

        # Purga slutet av train (labels läcker in i val) och slutet av val
        # (labels läcker in i test). Behåll minst en observation i varje.
        train_cut = max(train_end - emb, start + 1)
        val_cut   = max(val_end - emb, train_end + 1)

        train_d = unique_dates[start:train_cut]
        val_d   = unique_dates[train_end:val_cut]
        test_d  = unique_dates[val_end:test_end]

        splits.append((train_d, val_d, test_d))
        start += step_weeks   # rulla ett steg framåt

    return splits


# ─────────────────────────────────────────────────────────────────────────────
# LightGBM modell
# ─────────────────────────────────────────────────────────────────────────────

class MomentumLGBM:
    """
    Wrapper kring LightGBM med walk-forward träning.
    Tränar ett klassifikationsmodell (prob_up) och ett regressionsmodell (pred_return).
    """

    def __init__(self, params: dict = None):
        self.cls_params = {**(params or config.LGBM_PARAMS), "objective": "binary"}
        self.reg_params = {**(params or config.LGBM_PARAMS), "objective": "regression",
                           "metric": ["rmse", "mae"]}
        self.cls_models: List[lgb.Booster] = []
        self.reg_models: List[lgb.Booster] = []
        # Kalibrerar rå LGBM-sannolikheter mot faktisk frekvens (isotonic
        # regression, anpassad på valideringsfönstret – aldrig på
        # träningsdata, annars kalibrerar man bort modellens egen
        # overfitting istället för att korrigera den). Utan detta var
        # prob_up okalibrerad och matades direkt in i Kelly-sizing
        # (ensemble.py), vilket gör positionsstorlekarna otillförlitliga
        # om t.ex. 0.65 i praktiken bara träffar 55% av tiden.
        self.calibrators: List[IsotonicRegression] = []
        # test-fönstrets startdatum per modell, samma ordning/index som
        # cls_models/reg_models – används för datum-medveten prediktion.
        self.split_starts: List[pd.Timestamp] = []
        self.feature_importance_: Optional[pd.DataFrame] = None

    # ── Träning ──────────────────────────────────────────────────────────────

    def fit_walk_forward(self, df: pd.DataFrame) -> "MomentumLGBM":
        """
        Tränar walk-forward. df måste ha DatetimeIndex och kolumner i FEATURE_COLS
        samt 'target_signal' och 'target_return'.
        """
        splits = walk_forward_splits(df.index)
        print(f"[LGBM] Walk-forward: {len(splits)} splits")

        cls_importances, reg_importances = [], []

        for i, (train_d, val_d, test_d) in enumerate(splits):
            X_tr, y_cls_tr, y_reg_tr = self._slice(df, train_d)
            X_va, y_cls_va, y_reg_va = self._slice(df, val_d)

            if len(X_tr) < 100:
                print(f"  Split {i}: för lite data ({len(X_tr)} rader), hoppar.")
                continue

            # Klassifikation
            cls_model = self._fit_cls(X_tr, y_cls_tr, X_va, y_cls_va)
            self.cls_models.append(cls_model)
            cls_importances.append(cls_model.feature_importance(importance_type="gain"))
            self.calibrators.append(self._fit_calibrator(cls_model, X_va, y_cls_va))

            # Regression
            reg_model = self._fit_reg(X_tr, y_reg_tr, X_va, y_reg_va)
            self.reg_models.append(reg_model)
            reg_importances.append(reg_model.feature_importance(importance_type="gain"))

            self.split_starts.append(test_d[0])

            print(f"  Split {i+1}/{len(splits)}: "
                  f"träning t.o.m {train_d[-1].date()}, "
                  f"test {test_d[0].date()}–{test_d[-1].date()}")

        # Feature importance (genomsnitt över splits)
        self.feature_importance_ = pd.DataFrame({
            "feature": FEATURE_COLS,
            "cls_importance": np.mean(cls_importances, axis=0),
            "reg_importance": np.mean(reg_importances, axis=0),
        }).sort_values("cls_importance", ascending=False)

        return self

    def _fit_cls(self, X_tr, y_tr, X_va, y_va) -> lgb.Booster:
        ds_tr = lgb.Dataset(X_tr, label=y_tr)
        ds_va = lgb.Dataset(X_va, label=y_va, reference=ds_tr)
        p = {k: v for k, v in self.cls_params.items()
             if k not in ("n_estimators", "early_stopping_rounds")}
        return lgb.train(
            p,
            ds_tr,
            num_boost_round=self.cls_params["n_estimators"],
            valid_sets=[ds_va],
            callbacks=[
                lgb.early_stopping(self.cls_params["early_stopping_rounds"], verbose=False),
                lgb.log_evaluation(period=-1),
            ],
        )

    def _fit_reg(self, X_tr, y_tr, X_va, y_va) -> lgb.Booster:
        ds_tr = lgb.Dataset(X_tr, label=y_tr)
        ds_va = lgb.Dataset(X_va, label=y_va, reference=ds_tr)
        p = {k: v for k, v in self.reg_params.items()
             if k not in ("n_estimators", "early_stopping_rounds")}
        return lgb.train(
            p,
            ds_tr,
            num_boost_round=self.reg_params["n_estimators"],
            valid_sets=[ds_va],
            callbacks=[
                lgb.early_stopping(self.reg_params["early_stopping_rounds"], verbose=False),
                lgb.log_evaluation(period=-1),
            ],
        )

    @staticmethod
    def _fit_calibrator(cls_model: lgb.Booster, X_va, y_va) -> IsotonicRegression:
        """
        Isotonic regression: monoton mappning rå_sannolikhet -> kalibrerad
        sannolikhet, anpassad på (rå prediktion, faktiskt utfall) i
        valideringsfönstret. Fångar systematisk över-/undersäkerhet utan
        att anta en specifik form (till skillnad från Platt-skalning).
        Fungerar även om valideringsfönstret bara har en klass eller är
        litet – degenererar då till en konstant/grov mappning, men kraschar
        inte.
        """
        raw_va = cls_model.predict(X_va)
        calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrator.fit(raw_va, y_va)
        return calibrator

    # ── Prediktion ────────────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returnerar DataFrame med kolumner:
          prob_up, pred_signal, pred_return

        Väljer, per datum, den modell vars test-fönster faktiskt täcker det
        datumet (äkta walk-forward-attribuering) istället för att medel-
        värdesbilda alla splits – ett medelvärde över 95 modeller tränade på
        helt olika regimer/perioder späder ut signalen så mycket att
        sannolikheten nästan aldrig passerar 0.5, oavsett hur stark
        momentum-uppgången faktiskt var. Datum efter sista test-fönstret
        (dagens/levande signaler) får senaste modellen – den enda som
        faktiskt vore tillgänglig i produktion vid den tidpunkten. Datum
        före första test-fönstret (sällan förekommande) får äldsta modellen.
        """
        X = df[FEATURE_COLS].fillna(0).values
        model_idx = self._select_model_idx(df.index)

        cls_preds = np.empty(len(df))
        reg_preds = np.empty(len(df))
        for idx in np.unique(model_idx):
            mask = model_idx == idx
            raw = self.cls_models[idx].predict(X[mask])
            # Bakåtkompatibelt: äldre sparade modeller (innan kalibrering
            # infördes) har en tom calibrators-lista – kör då okalibrerat
            # istället för att krascha vid laddning av en gammal pkl.
            if idx < len(self.calibrators):
                cls_preds[mask] = self.calibrators[idx].transform(raw)
            else:
                cls_preds[mask] = raw
            reg_preds[mask] = self.reg_models[idx].predict(X[mask])

        return pd.DataFrame({
            "prob_up":     cls_preds,
            "pred_signal": (cls_preds > 0.5).astype(int),
            "pred_return": reg_preds,
        }, index=df.index)

    def _select_model_idx(self, dates: pd.DatetimeIndex) -> np.ndarray:
        starts = pd.DatetimeIndex(self.split_starts)
        idx = starts.searchsorted(dates, side="right") - 1
        return np.clip(idx, 0, len(self.split_starts) - 1)

    # ── Hjälpare ──────────────────────────────────────────────────────────────

    @staticmethod
    def _slice(df, dates):
        mask = df.index.isin(dates)
        sub  = df[mask]
        X    = sub[FEATURE_COLS].fillna(0).values
        y_cls= sub["target_signal"].values
        y_reg= sub["target_return"].values
        return X, y_cls, y_reg

    # ── Spara/ladda ───────────────────────────────────────────────────────────

    def save(self, path: str = "results/lgbm_model.pkl"):
        Path(path).parent.mkdir(exist_ok=True, parents=True)
        joblib.dump(self, path)
        print(f"[LGBM] Modell sparad: {path}")

    @classmethod
    def load(cls, path: str = "results/lgbm_model.pkl") -> "MomentumLGBM":
        return joblib.load(path)

    def print_feature_importance(self, top_n: int = 20):
        if self.feature_importance_ is None:
            print("Träna modellen först.")
            return
        print(f"\n{'='*50}")
        print(f"Top-{top_n} feature importance (klassifikation)")
        print(f"{'='*50}")
        print(self.feature_importance_.head(top_n).to_string(index=False))
