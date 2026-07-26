"""
models/lgbm_model.py – LightGBM bas-modell med walk-forward korsvalidering.

Output per sample:
  - prob_up      : P(avkastning > threshold)   [0..1]
  - pred_signal  : Köp(1) / Sälj(0)
  - pred_return  : förväntad avkastning (regression)
"""

import hashlib
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

# Extern kodgranskning 2026-07-25, Fas 1 punkt 4: early stopping och isotonic-
# kalibrering använde tidigare EXAKT samma valideringsfönster - kalibratorn
# var därmed inte helt oberoende av modellvalet (early stopping har redan
# "sett" och optimerat mot just detta fönster). Delar nu valideringsfönstret
# KRONOLOGISKT i två delar i stället: den tidigare delen för early stopping,
# den SENARE (närmast test-fönstret, mest representativ för regimen modellen
# faktiskt ska användas i) för kalibrering. Ingen ändring av
# walk_forward_splits egna train/val/test-datum krävs - bara hur
# valideringsfönstret ANVÄNDS internt i fit_walk_forward.
CALIBRATION_VAL_FRACTION = 0.4


def _code_hash() -> str:
    """Hash av lgbm_model.py + config.py:s källkod - samma paranoida
    invalideringsprincip som _checkpoint_key (varje kodändring, t.ex. nya
    hyperparametrar, ska synas i hashen). Utdragen till en modulfunktion
    (2026-07-26, pipeline-hälsogranskning) så både _checkpoint_key och
    reproducerbarhetsmetadata i pipeline_diagnostics.py delar EN
    implementation i stället för att riskera att de driver isär."""
    code = Path(__file__).read_text() + Path(config.__file__).read_text()
    return hashlib.sha1(code.encode()).hexdigest()[:16]


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
        # test-fönstrets start-/slutdatum per modell, samma ordning/index som
        # cls_models/reg_models – används för datum-medveten prediktion.
        # split_ends (tillagd 2026-07-25, extern kodgranskning punkt 5):
        # _select_model_idx väljer redan rätt modell för datum INOM ett
        # testfönster via split_starts, men kunde inte skilja "en riktig
        # split täcker det här datumet" från "vi extrapolerar långt bortom
        # sista kända testfönster" (live/serving-fallet) - split_ends gör
        # den skillnaden mätbar (se predict()).
        self.split_starts: List[pd.Timestamp] = []
        self.split_ends: List[pd.Timestamp] = []
        self._stale_warned: bool = False   # se _warn_if_stale - en varning per instans, inte per rad
        # Extern kodgranskning 2026-07-25, Fas 1 punkt 8: featurelistan
        # (namn OCH ORDNING) VID TRÄNINGSTILLFÄLLET - FEATURE_COLS är en
        # modulnivå-lista i feature_engineering.py, inte sparad på modellen
        # tidigare. Ändras FEATURE_COLS (ny/borttagen/omordnad feature)
        # efter att en modell tränats, skulle df[FEATURE_COLS].values i
        # predict() tyst mata fel kolumn till fel plats i trädet - inga
        # NaN/krascher, bara felaktiga prediktioner. Valideras i predict().
        self.feature_cols_: List[str] = []
        self.feature_importance_: Optional[pd.DataFrame] = None
        # Per-split diagnostik (kodgranskning 2026-07-23): feature_importance_
        # ovan är BARA medelvärdet över alla splits – om viktiga features
        # faktiskt skiftar mellan perioder (2015-2018 vs 2023-2025) syns det
        # aldrig i ett medelvärde. De rådata som skulle behövas fanns redan
        # (cls_importances/reg_importances-listorna i fit_walk_forward) men
        # kastades bort efter medelvärdesbildningen. Sparas nu istället här.
        self.feature_importance_history_: Optional[pd.DataFrame] = None
        # Per-fold (per walk-forward-split) prediktionsdiagnostik på
        # TEST-fönstret. OBS: det här är INTE en portfölj-Sharpe (ingen
        # positionsstorlek/kostnad/multi-ticker-aggregering, bara enkel
        # avkastning/std på de rader modellen skulle köpt i just den
        # splitten) - ett lättviktigt stabilitetsmått, inte en ersättning
        # för backtester.run(). Se print_fold_diagnostics().
        self.fold_diagnostics_: List[dict] = []

    # ── Träning ──────────────────────────────────────────────────────────────

    def _checkpoint_path(self) -> Path:
        # config.RESULTS_DIR är redan anchor():ad (segment-uppdelad, se
        # config.SEGMENTS) - samma direkta användning som main.py:s
        # _feature_cache_path, ingen extra anchor()-inpackning här.
        return Path(config.RESULTS_DIR) / "_lgbm_walkforward_checkpoint.joblib"

    def _checkpoint_key(self, df: pd.DataFrame) -> str:
        """Samma paranoida invalideringsprincip som features-cachen
        (feature_engineering.py, se dess kommentar): hashar HELA denna fil +
        config.py:s källkod, inte en manuellt underhållen versionssträng -
        varje kodändring (nya hyperparametrar, ändrad splitlogik) river
        automatiskt en gammal checkpoint i stället för att riskera att tyst
        återuppta träning med gammal logik. Datahash (hash_pandas_object)
        fångar om df (features/labels) ändrats sedan checkpointen skrevs."""
        code_hash = _code_hash()
        data_hash = hashlib.sha1(
            pd.util.hash_pandas_object(df, index=True).values.tobytes()
        ).hexdigest()[:16]
        return f"{code_hash}_{data_hash}"

    def _save_checkpoint(self, key: str, next_i: int, cls_imp: list, reg_imp: list) -> None:
        """Atomär skrivning (temp-fil + os.replace) - run_watched.sh kan
        SIGKILLa processen när som helst, en halvskriven checkpoint-fil får
        aldrig kunna läsas som giltig av nästa försök."""
        path = self._checkpoint_path()
        tmp = path.with_suffix(".tmp")
        try:
            joblib.dump({
                "key": key, "next_split": next_i,
                "cls_models": self.cls_models, "reg_models": self.reg_models,
                "calibrators": self.calibrators, "split_starts": self.split_starts,
                "split_ends": self.split_ends,
                "cls_importances": cls_imp, "reg_importances": reg_imp,
                "fold_diagnostics": self.fold_diagnostics_,
            }, tmp)
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001 - checkpointen är en optimering, aldrig kritisk
            print(f"  [WARN] Kunde inte skriva walk-forward-checkpoint (icke-kritiskt): {e}")

    def _load_checkpoint(self, key: str):
        path = self._checkpoint_path()
        if not path.exists():
            return None
        try:
            saved = joblib.load(path)
            if saved.get("key") != key:
                return None
            return saved
        except Exception:  # noqa: BLE001 - korrupt/ofullständig checkpoint, börja om
            return None

    def _preserve_rejected_split(
        self, split_i: int, train_d, val_d, val_d_stop,
        X_tr: np.ndarray, y_cls_tr: np.ndarray, X_va_stop: np.ndarray, y_cls_va_stop: np.ndarray,
        cls_model: lgb.Booster,
    ) -> None:
        """
        Sparar EXAKT träningsindata + reproducerbarhetsmetadata för en
        underkänd split (num_trees<=1) till results/rejected_splits/.

        BAKGRUND (session 2026-07-26): en granskning av rank-gap/bytesfrekvens
        i pipeline_health.json ledde till att ~en tredjedel av walk-forward-
        splittarna visade sig ha bara ETT träd (num_trees==best_iteration==
        current_iteration==1) - LightGBM:s EGEN interna "no further splits
        with positive gain"-terminering, inte den konfigurerade 50-rundors
        tålamods-regeln (den senare hade krävt >=51 körda rundor). Ett försök
        att i efterhand reproducera en av dessa splits gav ETT ANNAT resultat
        (13 träd, en äkta om än svag modell) på en tillgänglig men INTE
        bit-identisk feature-cache - main.py:s _feature_cache_path.unlink()
        raderar feature-cachen efter varje orkestrerad körning, så den
        EXAKTA datan som faktiskt orsakade en given natts 1-träds-resultat
        gick inte att återskapa. Det här stänger den luckan: nästa gång en
        split underkänns bevaras dess exakta (X, y) + fullständig
        reproducerbarhetsmetadata, så framtida forskning slipper gissa.

        Filnamnet nyckelas på split-startdatumet (inte körningstillfället) -
        walk-forward-splittarnas datum är deterministiska givet samma
        historik+config, så en förnyad natts körning skriver helt enkelt över
        en tidigare bevarad, fortsatt underkänd splits fil i stället för att
        ackumulera obegränsat.
        """
        out_dir = Path(config.RESULTS_DIR) / "rejected_splits"
        out_dir.mkdir(parents=True, exist_ok=True)
        split_start_str = pd.Timestamp(pd.DatetimeIndex(val_d).min()).date().isoformat()
        path = out_dir / f"rejected_split_{split_start_str}.pkl"
        tmp = path.with_suffix(".tmp")

        payload = {
            "saved_at": pd.Timestamp.now("UTC").isoformat(),
            "split_index": split_i,
            "train_date_range": (
                pd.Timestamp(pd.DatetimeIndex(train_d).min()).isoformat(),
                pd.Timestamp(pd.DatetimeIndex(train_d).max()).isoformat()),
            "val_date_range": (
                pd.Timestamp(pd.DatetimeIndex(val_d).min()).isoformat(),
                pd.Timestamp(pd.DatetimeIndex(val_d).max()).isoformat()),
            "val_stop_date_range": (
                (pd.Timestamp(pd.DatetimeIndex(val_d_stop).min()).isoformat(),
                 pd.Timestamp(pd.DatetimeIndex(val_d_stop).max()).isoformat())
                if len(val_d_stop) else None),
            "num_trees": cls_model.num_trees(),
            "best_iteration": cls_model.best_iteration,
            "reproducibility": {
                "code_hash": _code_hash(),
                "random_seed": config.RANDOM_SEED,
                "cls_params": dict(self.cls_params),
                "feature_cols": list(FEATURE_COLS),
            },
            # EXAKT indata - inte bara en hash - så en framtida undersökning
            # kan återköra lgb.train direkt utan att bygga om features/priser.
            "X_tr": X_tr, "y_cls_tr": y_cls_tr,
            "X_va_stop": X_va_stop, "y_cls_va_stop": y_cls_va_stop,
        }
        try:
            joblib.dump(payload, tmp, compress=3)
            os.replace(tmp, path)
            print(f"  [KRITISKT] Split {split_i+1}: underkänd (num_trees="
                  f"{cls_model.num_trees()}) - exakt indata bevarad: {path}")
        except Exception as e:  # noqa: BLE001 - bevarandet är diagnostik, aldrig kritiskt för träningen
            print(f"  [WARN] Kunde inte bevara underkänd split {split_i+1} (icke-kritiskt): {e}")

    @staticmethod
    def _sanity_check(df: pd.DataFrame) -> None:
        """
        Extern kodgranskning 2026-07-25 (hygienlistan): automatiska
        kontroller FÖRE träning - varnar (kraschar inte, en degenererad
        indata ska inte tysta stoppa en hel nattkörning) om:
          - NaN i target_signal/target_return (borde redan vara droppat av
            to_model_df, men en framtida ändring där kunde tyst läcka in det)
          - oändliga värden i FEATURE_COLS
          - konstanta features (noll varians - ingen information, bara brus
            för trädsplittarna)
          - dubblettrader (samma (datum, alla features) mer än en gång)
          - för få positiva ELLER negativa target_signal-labels (en nästan
            ren klass gör klassificeringen meningslös)
        """
        n = len(df)
        if n == 0:
            print("  [sanity] VARNING: tom träningsdata.")
            return

        for col in ("target_signal", "target_return"):
            if col in df.columns:
                n_nan = int(df[col].isna().sum())
                if n_nan:
                    print(f"  [sanity] VARNING: {n_nan}/{n} NaN i '{col}' - borde redan vara droppat.")

        X = df[FEATURE_COLS]
        n_inf = int(np.isinf(X.select_dtypes(include=[np.number])).sum().sum())
        if n_inf:
            print(f"  [sanity] VARNING: {n_inf} oändliga värden i FEATURE_COLS.")

        const_cols = [c for c in FEATURE_COLS if c in X.columns and X[c].nunique(dropna=True) <= 1]
        if const_cols:
            print(f"  [sanity] VARNING: {len(const_cols)} konstanta features (ingen information): {const_cols[:10]}"
                  + (" ..." if len(const_cols) > 10 else ""))

        n_dup = int(df.duplicated(subset=["target_signal", "target_return"] + FEATURE_COLS).sum())
        if n_dup:
            print(f"  [sanity] VARNING: {n_dup}/{n} exakta dubblettrader (datum+alla features+target).")

        if "target_signal" in df.columns:
            pos = int((df["target_signal"] == 1).sum())
            neg = n - pos
            pos_frac = pos / n if n else 0.0
            if pos_frac < 0.05 or pos_frac > 0.95:
                print(f"  [sanity] VARNING: kraftigt obalanserade klasser - {pos} positiva/{neg} negativa "
                      f"({pos_frac:.1%} positiva).")

    def fit_walk_forward(
        self,
        df: pd.DataFrame,
        train_weeks: int = config.TRAIN_WINDOW_WEEKS,
        val_weeks: int = config.VAL_WINDOW_WEEKS,
        step_weeks: int = config.TEST_STEP_WEEKS,
        embargo_weeks: int = config.EMBARGO_WEEKS,
    ) -> "MomentumLGBM":
        """
        Tränar walk-forward. df måste ha DatetimeIndex och kolumner i FEATURE_COLS
        samt 'target_signal' och 'target_return'.

        train_weeks/val_weeks/step_weeks/embargo_weeks: överstyr config-
        defaulten för fönsterstorlekarna (t.ex. ett litet test som vill
        trigga en split på syntetisk data utan 260v historik). Skickas
        oförändrade vidare till walk_forward_splits – live-träningen (main.py)
        anropar utan dessa och får exakt tidigare beteende.

        CHECKPOINT/RESUME (2026-07-22, verkligt fall: minnesvakten avbröt
        walk-forward-träningen mitt i split 1/31 flera kvällar i rad - hela
        körningen fick börja om från noll varje gång). Sparar tillståndet
        till disk efter VARJE split (modeller + kalibratorer + importances),
        så ett avbrott bara kostar den senaste, ännu ej klara splitten - inte
        alla föregående. Checkpointen är knuten till en hash av data+kod (se
        _checkpoint_key) och ren läge-återupptagning av OBEROENDE splits
        (varje split tränar sin egen modell, ingen delad tillstånd mellan
        dem) - inte en partiell/inkrementell omträning av en enda modell,
        så en återupptagen körning ger giltigt tränade modeller för varje
        split, på samma sätt som en ostörd körning skulle gjort. KORRIGERAT
        2026-07-25 (den äldre versionen av denna kommentar hävdade felaktigt
        att LightGBM var osådd/icke-deterministisk - config.LGBM_PARAMS har
        redan seed/bagging_seed/feature_fraction_seed/data_random_seed +
        deterministic=True/force_row_wise=True, verifierat i koden. En
        återupptagen körning ska alltså ge BIT-FÖR-BIT identiska modeller
        som en ostörd körning, inte bara "giltiga" - avvikelser vore ett
        reproducerbarhetsfel värt att undersöka, inte förväntat brus).
        """
        self._sanity_check(df)
        splits = walk_forward_splits(df.index, train_weeks=train_weeks, val_weeks=val_weeks,
                                      step_weeks=step_weeks, embargo_weeks=embargo_weeks)
        print(f"[LGBM] Walk-forward: {len(splits)} splits")
        self.feature_cols_ = list(FEATURE_COLS)

        key = self._checkpoint_key(df)
        start_i = 0
        cls_importances, reg_importances = [], []
        checkpoint = self._load_checkpoint(key)
        if checkpoint is not None:
            self.cls_models = checkpoint["cls_models"]
            self.reg_models = checkpoint["reg_models"]
            self.calibrators = checkpoint["calibrators"]
            self.split_starts = checkpoint["split_starts"]
            self.split_ends = checkpoint.get("split_ends", [])
            cls_importances = checkpoint["cls_importances"]
            reg_importances = checkpoint["reg_importances"]
            self.fold_diagnostics_ = checkpoint.get("fold_diagnostics", [])
            start_i = checkpoint["next_split"]
            print(f"  [checkpoint] Återupptar från split {start_i + 1}/{len(splits)} "
                  f"({len(self.cls_models)} redan tränade modeller från tidigare försök).")

        for i, (train_d, val_d, test_d) in enumerate(splits):
            if i < start_i:
                continue
            X_tr, y_cls_tr, y_reg_tr = self._slice(df, train_d)
            X_va, y_cls_va, y_reg_va = self._slice(df, val_d)

            if len(X_tr) < 100:
                print(f"  Split {i}: för lite data ({len(X_tr)} rader), hoppar.")
                self._save_checkpoint(key, i + 1, cls_importances, reg_importances)
                continue

            # Dela valideringsfönstret kronologiskt: tidigare del -> early
            # stopping, senare del -> kalibrering (se CALIBRATION_VAL_FRACTION
            # ovan). Faller tillbaka på HELA val_d för båda om den senare
            # delen skulle bli för liten (litet valideringsfönster/få rader
            # per datum) - hellre än att krascha eller kalibrera på nästan
            # ingen data.
            val_dates_sorted = pd.DatetimeIndex(val_d).sort_values().unique()
            split_i_val = int(len(val_dates_sorted) * (1 - CALIBRATION_VAL_FRACTION))
            val_d_stop = val_dates_sorted[:split_i_val]
            val_d_calib = val_dates_sorted[split_i_val:]
            X_va_calib, y_cls_va_calib, _ = self._slice(df, val_d_calib)
            if len(val_d_stop) == 0 or len(val_d_calib) == 0 or len(X_va_calib) < 30:
                X_va_stop, y_cls_va_stop = X_va, y_cls_va
                X_va_calib, y_cls_va_calib = X_va, y_cls_va
            else:
                X_va_stop, y_cls_va_stop, _ = self._slice(df, val_d_stop)

            # Klassifikation
            cls_model = self._fit_cls(X_tr, y_cls_tr, X_va_stop, y_cls_va_stop)
            if cls_model.num_trees() <= 1:
                # Underkänd split (pipeline-hälsogranskning 2026-07-26): LightGBM
                # hittade ingen split med positiv vinst efter runda 1 och avbröt
                # HELT (inte den vanliga 50-rundors-tålamodsregeln - se
                # _preserve_rejected_split-docstringen). Bevara den EXAKTA
                # indatan nu - main.py raderar feature-cachen efter varje
                # orkestrerad körning, så det här är enda chansen att kunna
                # undersöka/reproducera varför i efterhand.
                self._preserve_rejected_split(
                    i, train_d, val_d, val_d_stop, X_tr, y_cls_tr, X_va_stop, y_cls_va_stop, cls_model)
            self.cls_models.append(cls_model)
            cls_importances.append(cls_model.feature_importance(importance_type="gain"))
            calibrator = self._fit_calibrator(cls_model, X_va_calib, y_cls_va_calib)
            self.calibrators.append(calibrator)

            # Regression
            reg_model = self._fit_reg(X_tr, y_reg_tr, X_va, y_reg_va)
            self.reg_models.append(reg_model)
            reg_importances.append(reg_model.feature_importance(importance_type="gain"))

            self.split_starts.append(test_d[0])
            self.split_ends.append(test_d[-1])

            # Per-fold diagnostik på TEST-fönstret (aldrig sett av vare sig
            # träning eller kalibrering) - se attributets docstring i __init__
            # för vad det INTE är (ingen portfölj-Sharpe).
            self.fold_diagnostics_.append(
                self._fold_diagnostics(df, test_d, cls_model, calibrator, i, len(splits),
                                        reg_model=reg_model)
            )

            self._save_checkpoint(key, i + 1, cls_importances, reg_importances)

            print(f"  Split {i+1}/{len(splits)}: "
                  f"träning t.o.m {train_d[-1].date()}, "
                  f"test {test_d[0].date()}–{test_d[-1].date()}")

        # Feature importance PER SPLIT (kodgranskning 2026-07-23) - de rådata
        # som redan beräknades ovan (cls_importances) men tidigare kastades
        # bort efter medelvärdesbildningen. En rad per split, en kolumn per
        # feature, indexerad på splittens test-startdatum - gör det möjligt
        # att se om viktiga features skiftar mellan perioder (se
        # print_feature_importance_by_period nedan), inte bara det
        # tidsoberoende medelvärdet i feature_importance_.
        if cls_importances:
            self.feature_importance_history_ = pd.DataFrame(
                cls_importances, columns=FEATURE_COLS, index=pd.DatetimeIndex(self.split_starts, name="split_start"),
            )

        # Feature importance (genomsnitt över splits)
        self.feature_importance_ = pd.DataFrame({
            "feature": FEATURE_COLS,
            "cls_importance": np.mean(cls_importances, axis=0),
            "reg_importance": np.mean(reg_importances, axis=0),
        }).sort_values("cls_importance", ascending=False)

        # Klart - checkpointen behövs inte längre. Nästa körning (annan dag,
        # annan data) ska inte kunna råka läsa en gammal, avslutad checkpoint.
        self._checkpoint_path().unlink(missing_ok=True)

        return self

    def fit_serving(self, df: pd.DataFrame, val_weeks: int = 26) -> "MomentumLGBM":
        """
        SERVERINGSMODELL (UTVECKLINGSLOGG #29): EN modell tränad på ALL
        labelad data (t.o.m. nu − FORWARD_WEEKS), för appens LIVE-
        rekommendationer. Bakgrund: den frusna holdouten (104v) + val-
        fönstret (52v) + embargot gör att fit_walk_forward:s SISTA modell
        är tränad på data som slutar ~3-4 år bakåt – och det är den som
        gjort appens "dagens" prediktioner. Staleness-testet (#29) visade
        att färska folds ger blandat-positivt utfall 2024-2026 där den
        gamla modellen rankade konsekvent FEL håll (IC −0,056).

        FÅR ALDRIG användas för holdout-/backtest-mätning – den är tränad
        på holdout-perioden. Mätningen ägs helt av fit_walk_forward
        (lgbm_model.pkl / signals.csv), som lämnas orörd.

        Sista `val_weeks` veckorna används för early stopping + isotonisk
        kalibrering (inget embargo: syftet är färskhet, inte mätning).
        """
        dates = df.index.unique().sort_values()
        if len(dates) <= val_weeks + 20:
            raise ValueError("För lite data för en serveringsmodell.")
        self.feature_cols_ = list(FEATURE_COLS)
        train_dates, val_dates = dates[:-val_weeks], dates[-val_weeks:]
        X_tr, y_cls_tr, y_reg_tr = self._slice(df, train_dates)
        X_va, y_cls_va, y_reg_va = self._slice(df, val_dates)

        cls_model = self._fit_cls(X_tr, y_cls_tr, X_va, y_cls_va)
        self.cls_models = [cls_model]
        self.calibrators = [self._fit_calibrator(cls_model, X_va, y_cls_va)]
        self.reg_models = [self._fit_reg(X_tr, y_reg_tr, X_va, y_reg_va)]
        self.split_starts = [dates[0]]
        self.split_ends = [dates[-1]]
        print(f"[LGBM] Serveringsmodell: träning {train_dates[0].date()} -> "
              f"{train_dates[-1].date()}, val/kalibrering {val_dates[0].date()} -> "
              f"{val_dates[-1].date()} ({len(X_tr):,} rader)")
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

    def _fold_diagnostics(
        self, df: pd.DataFrame, test_d: pd.DatetimeIndex,
        cls_model: lgb.Booster, calibrator: IsotonicRegression,
        split_i: int, n_splits: int,
        reg_model: Optional[lgb.Booster] = None,
    ) -> dict:
        """
        Enkel, per-fold prediktionsdiagnostik på TEST-fönstret (aldrig sett av
        träning eller kalibrering i den här splitten).

        VIKTIGT vad det INTE är: ingen portfölj-Sharpe. Ingen positions-
        storlek, inga kostnader, ingen aggregering över tickers per datum
        (bara raden-för-raden-avkastning på de rader modellen skulle köpt).
        Det är ett lättviktigt STABILITETSMÅTT - syftet är att se om
        prestandan svänger vilt mellan fönster (t.ex. 2.4/2.3/2.1/-0.4/2.2,
        instabilt) eller ligger jämnt (1.1/1.0/1.2/0.9/1.1, robust), inte att
        ersätta backtester.run() som redan gör den riktiga, kostnadsjusterade
        portföljsimuleringen på FULL ensemble-output.

        reg_model (tillagd 2026-07-25, extern kodgranskning punkt 3): mäter
        REGRESSIONENS ekonomiska värde separat från klassificeringen -
        IC (Spearman-rankkorrelation mellan pred_return och faktisk
        target_return) och decilspread (medel-avkastning topp- minus
        bottendecil av pred_return), på SAMMA aldrig-sedda testfönster.
        Valfri parameter (default None) - gamla anrop utan reg_model funkar
        oförändrat, bara IC/decilspread blir None.
        """
        X_te, y_cls_te, y_reg_te = self._slice(df, test_d)
        out = {
            "split": split_i + 1, "n_splits": n_splits,
            "test_start": test_d[0], "test_end": test_d[-1], "n_test": len(X_te),
            "hit_rate": None, "mean_return_if_bought": None, "pseudo_sharpe": None,
            "reg_ic": None, "reg_decile_spread": None, "n_bought": None,
            "cls_best_iteration": getattr(cls_model, "best_iteration", None),
            "reg_best_iteration": getattr(reg_model, "best_iteration", None),
            # Pipeline-hälsogranskning 2026-07-26: num_trees (INTE bara
            # best_iteration) avslöjar en LightGBM-intern "no further splits
            # with positive gain"-terminering - se _preserve_rejected_split.
            # De två är samma tal i praktiken (current_iteration stannar där
            # boostingen faktiskt avbröts), men lagras separat/explicit så
            # ett framtida LightGBM-beteende (save_best etc.) inte tyst gör
            # dem olika utan att någon märker det.
            "cls_num_trees": cls_model.num_trees(),
        }
        if len(X_te) == 0:
            return out

        raw = cls_model.predict(X_te)
        prob = calibrator.transform(raw)
        bought = prob > 0.5
        out["n_bought"] = int(bought.sum())   # extern kodgranskning: upptäck degenererat "köp allt/inget"

        out["hit_rate"] = float(np.mean((bought.astype(int)) == y_cls_te))
        if bought.any():
            rets = y_reg_te[bought]
            out["mean_return_if_bought"] = float(np.mean(rets))
            std = float(np.std(rets))
            # "pseudo": avkastning/std på EN splits testfönster, inte en
            # annualiserad portfölj-Sharpe - jämförbar mellan folds, inte
            # med backtesterns riktiga Sharpe-tal.
            out["pseudo_sharpe"] = float(np.mean(rets) / std) if std > 0 else None

        if reg_model is not None and len(X_te) >= 10:
            reg_pred = reg_model.predict(X_te)
            s_pred = pd.Series(reg_pred)
            s_actual = pd.Series(y_reg_te)
            ic = s_pred.corr(s_actual, method="spearman")
            out["reg_ic"] = float(ic) if pd.notna(ic) else None
            try:
                deciles = pd.qcut(s_pred, 10, labels=False, duplicates="drop")
                by_decile = s_actual.groupby(deciles).mean()
                if len(by_decile) >= 2:
                    out["reg_decile_spread"] = float(by_decile.iloc[-1] - by_decile.iloc[0])
            except ValueError:
                pass   # för få unika pred_return-värden för 10 deciler i det här fönstret
        return out

    # ── Prediktion ────────────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
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

        strict (extern kodgranskning 2026-07-25, Fas 1 punkt 6): False
        (default, ALLA befintliga anrop opåverkade) = ovanstående live/
        serving-fallback tillåts tyst. True = kastar ValueError om NÅGOT
        datum ligger utanför [första split_start, sista split_end] - dvs.
        inget verkligt walk-forward-testfönster täcker det, bara
        extrapolering med senaste modellen. Använd strict=True i backtest-/
        forskningskod där ett datum SKA ha en äkta historisk modell (aldrig
        av misstag blanda in live-extrapolering i ett historiskt resultat);
        lämna av (default) för faktisk live/serving-prediktion, där
        fallbacken är avsedd, inte ett fel.
        """
        # Featurevalidering (Fas 1 punkt 8): kör ALLTID, inte bara i strict-
        # läge - en tyst kolumn-/ordningsmiss ger felaktiga prediktioner,
        # inte extrapolering (det senare kan vara avsett, se strict ovan).
        # Bakåtkompatibelt: äldre sparade modeller saknar feature_cols_
        # (tom lista, attributet fanns inte innan denna kodändring) - då
        # görs ingen kontroll i stället för en falsk krasch.
        trained_cols = getattr(self, "feature_cols_", None)
        if trained_cols and list(FEATURE_COLS) != trained_cols:
            missing = set(trained_cols) - set(FEATURE_COLS)
            added = set(FEATURE_COLS) - set(trained_cols)
            raise ValueError(
                f"predict(): FEATURE_COLS har ändrats sedan modellen tränades - "
                f"saknas nu: {sorted(missing) or '–'}, nya: {sorted(added) or '–'}"
                + (", ELLER ordningen har ändrats (samma mängd, annan sekvens)."
                   if not missing and not added else ".")
                + " Träna om modellen mot aktuell FEATURE_COLS."
            )

        X = df[FEATURE_COLS].fillna(0).values
        model_idx = self._select_model_idx(df.index)
        self._warn_if_stale(df.index)

        split_ends = getattr(self, "split_ends", [])
        if strict and self.split_starts and split_ends:
            lo, hi = pd.Timestamp(min(self.split_starts)), pd.Timestamp(max(split_ends))
            dates = pd.DatetimeIndex(df.index)
            out_of_range = dates[(dates < lo) | (dates > hi)]
            if len(out_of_range):
                raise ValueError(
                    f"predict(strict=True): {len(out_of_range)} datum ligger utanför "
                    f"tränade testfönster [{lo.date()}, {hi.date()}] - t.ex. "
                    f"{out_of_range[0].date()}. Inget verkligt walk-forward-testfönster "
                    f"täcker dem, bara extrapolering med senaste modellen. Använd "
                    f"strict=False om detta är avsedd live/serving-prediktion."
                )

        cls_preds = np.empty(len(df))
        raw_preds = np.empty(len(df))
        reg_preds = np.empty(len(df))
        for idx in np.unique(model_idx):
            mask = model_idx == idx
            raw = self.cls_models[idx].predict(X[mask])
            raw_preds[mask] = raw
            # Bakåtkompatibelt: äldre sparade modeller (innan kalibrering
            # infördes) har en tom calibrators-lista – kör då okalibrerat
            # istället för att krascha vid laddning av en gammal pkl.
            if idx < len(self.calibrators):
                cls_preds[mask] = self.calibrators[idx].transform(raw)
            else:
                cls_preds[mask] = raw
            reg_preds[mask] = self.reg_models[idx].predict(X[mask])

        # prob_raw: isotonic är en TRAPPSTEGSFUNKTION – vid svag signal kollapsar
        # den till en bred platå på basfrekvensen (~34%), där nästan alla bolag
        # står exakt lika i prob_up i åratal och topp-N-urvalet blir godtyckliga
        # tie-breaks. Den råa poängen är kontinuerlig och bevarar modellens
        # finordning; den följer med till signals.csv som tie-break i urvalet
        # och som underlag för prob_rank (tvärsnitts-percentil) i appen.
        return pd.DataFrame({
            "prob_up":     cls_preds,
            "prob_raw":    raw_preds,
            "pred_signal": (cls_preds > 0.5).astype(int),
            "pred_return": reg_preds,
        }, index=df.index)

    def _select_model_idx(self, dates: pd.DatetimeIndex) -> np.ndarray:
        starts = pd.DatetimeIndex(self.split_starts)
        idx = starts.searchsorted(dates, side="right") - 1
        return np.clip(idx, 0, len(self.split_starts) - 1)

    def _warn_if_stale(self, dates: pd.DatetimeIndex, threshold_weeks: int = 4 * config.TEST_STEP_WEEKS) -> None:
        """
        Extern kodgranskning 2026-07-25, punkt 5/hygienlistan: varna EN
        gång per modellinstans (inte per rad) om vi predikterar långt bortom
        sista kända testfönster - dvs. vi extrapolerar med senaste modellen
        i stället för att en riktig walk-forward-split faktiskt täcker
        datumet (samma "senaste modellen"-fallback som _select_model_idx
        redan använder avsiktligt för live/serving-datum, se predict():s
        docstring - varningen ändrar inget beteende, gör bara det synligt).
        Bakåtkompatibelt: äldre sparade modeller saknar split_ends helt
        (attributet fanns inte innan denna kodändring) - tyst no-op då,
        inte en krasch.
        """
        ends = getattr(self, "split_ends", None)
        if not ends or getattr(self, "_stale_warned", False) or len(dates) == 0:
            return
        last_end = pd.DatetimeIndex(ends).max()
        max_date = pd.DatetimeIndex(dates).max()
        staleness_weeks = (max_date - last_end).days / 7.0
        if staleness_weeks > threshold_weeks:
            print(f"  [VARNING] MomentumLGBM.predict(): predikterar för {max_date.date()}, "
                  f"{staleness_weeks:.0f}v efter sista tränade testfönstrets slut "
                  f"({last_end.date()}) - senaste modellen återanvänds som extrapolering, "
                  f"ingen split täcker faktiskt detta datum. Förväntat för live/serving-"
                  f"signaler, men flaggar om det gäller ett HISTORISKT backtest-datum.")
            self._stale_warned = True

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

    def print_feature_importance_by_period(self, n_periods: int = 3, top_n: int = 10):
        """
        Delar feature_importance_history_ (en rad per walk-forward-split) i
        n_periods ungefär lika stora KRONOLOGISKA hinkar och visar topp-features
        per hink. Svarar på: bygger modellen hela tiden på samma signaler, eller
        skiftar de viktigaste features mellan perioder (ett möjligt instabilitets-
        tecken, se docs/UTVECKLINGSLOGG.md)?
        """
        if self.feature_importance_history_ is None or self.feature_importance_history_.empty:
            print("Ingen per-split feature-importance-historik – träna modellen först.")
            return
        hist = self.feature_importance_history_
        bucket = pd.qcut(np.arange(len(hist)), q=min(n_periods, len(hist)), duplicates="drop")
        print(f"\n{'='*60}\nFeature importance per period ({n_periods} hinkar)\n{'='*60}")
        for label, idx in hist.groupby(bucket).groups.items():
            rows = hist.loc[idx]
            start, end = rows.index.min().date(), rows.index.max().date()
            top = rows.mean(axis=0).sort_values(ascending=False).head(top_n)
            print(f"\n  {start} → {end}  ({len(rows)} splits)")
            for feat, val in top.items():
                print(f"    {feat:<28} {val:,.1f}")

    def print_fold_diagnostics(self):
        """
        Skriver ut per-fold (per walk-forward-split) hit rate/avkastning/
        pseudo-Sharpe, INTE bara ett aggregat – en modell som växlar mellan
        starka och katastrofala fold är mindre robust än en som ligger jämnt,
        vilket ett enda medelvärde döljer helt. Se _fold_diagnostics för vad
        pseudo_sharpe är (och INTE är – ingen portfölj-Sharpe).
        """
        if not self.fold_diagnostics_:
            print("Ingen fold-diagnostik – träna modellen först.")
            return
        print(f"\n{'='*70}\nPer-fold diagnostik ({len(self.fold_diagnostics_)} splits)\n{'='*70}")
        print(f"  {'split':>7} {'test-start':>12} {'n':>6} {'hit-rate':>9} "
              f"{'avk|köpt':>10} {'pseudo-Sharpe':>14} {'reg-IC':>8} {'decilspr':>10}")
        for d in self.fold_diagnostics_:
            hr = f"{d['hit_rate']:.1%}" if d["hit_rate"] is not None else "–"
            ret = f"{d['mean_return_if_bought']:+.1%}" if d["mean_return_if_bought"] is not None else "–"
            ps = f"{d['pseudo_sharpe']:.2f}" if d["pseudo_sharpe"] is not None else "–"
            ic = f"{d.get('reg_ic'):+.3f}" if d.get("reg_ic") is not None else "–"
            ds = f"{d.get('reg_decile_spread'):+.1%}" if d.get("reg_decile_spread") is not None else "–"
            print(f"  {d['split']:>4}/{d['n_splits']:<3} {str(d['test_start'].date()):>12} "
                  f"{d['n_test']:>6} {hr:>9} {ret:>10} {ps:>14} {ic:>8} {ds:>10}")
