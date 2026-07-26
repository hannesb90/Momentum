"""
Verifierar de nya diagnostik-attributen i MomentumLGBM.fit_walk_forward
(kodgranskning 2026-07-23): feature_importance_history_ (per-split, inte
bara medelvärdet) och fold_diagnostics_ (per-fold hit rate/pseudo-Sharpe).

Kör en RIKTIG (men liten) LightGBM-träning på syntetisk data – snabbt
tack vare fit_walk_forward:s nya train_weeks/val_weeks/step_weeks/
embargo_weeks-överstyrning och en liten n_estimators/early_stopping-
konfiguration, inte en mockad modell. Detta är den enda pålitliga
verifieringen att attributen faktiskt fylls med rätt form under en
skarp träningsloop, inte bara att koden kompilerar.
"""
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
from features.feature_engineering import FEATURE_COLS  # noqa: E402
from models.lgbm_model import MomentumLGBM  # noqa: E402

_SMALL_PARAMS = {
    "objective": "binary",
    "metric": ["binary_logloss"],
    "learning_rate": 0.2,
    "num_leaves": 7,
    "min_child_samples": 5,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "reg_alpha": 0.0,
    "reg_lambda": 0.0,
    "n_estimators": 15,
    "early_stopping_rounds": 5,
    "verbose": -1,
    "num_threads": 1,
    "seed": 42,
    "bagging_seed": 42,
    "feature_fraction_seed": 42,
    "data_random_seed": 42,
    "deterministic": True,
    "force_row_wise": True,
}


def _synthetic_df(n_weeks=60, n_tickers=8, seed=7):
    """Syntetisk multi-ticker df i samma form fit_walk_forward förväntar:
    DatetimeIndex + FEATURE_COLS + target_signal/target_return. Värdena är
    slumpmässiga (inget riktigt momentum-mönster) – testet bryr sig bara om
    att pipelinen KÖR och lagrar rätt saker, inte om modellen tränar bra."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-04", periods=n_weeks, freq="W")
    rows = []
    for d in dates:
        for t in range(n_tickers):
            row = {c: rng.normal() for c in FEATURE_COLS}
            row["target_signal"] = int(rng.random() > 0.5)
            row["target_return"] = float(rng.normal(0, 0.05))
            rows.append(row)
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(np.repeat(dates, n_tickers)))
    return df


@pytest.fixture(scope="module")
def trained_model(tmp_path_factory):
    # RESULTS_DIR omdirigeras till en tmp-katalog under träningen (inte bara
    # monkeypatch, som är funktions- inte modul-scopad): fit_walk_forward
    # kan nu skriva results/rejected_splits/-artefakter för underkända
    # splits (se _preserve_rejected_split) - den riktiga projekt-resultat-
    # mappen ska aldrig smutsas ner av testkörningar.
    original_results_dir = config.RESULTS_DIR
    config.RESULTS_DIR = str(tmp_path_factory.mktemp("lgbm_results"))
    try:
        df = _synthetic_df()
        model = MomentumLGBM(params=_SMALL_PARAMS)
        model.fit_walk_forward(df, train_weeks=20, val_weeks=6, step_weeks=6, embargo_weeks=2)
        return model
    finally:
        config.RESULTS_DIR = original_results_dir


def test_fit_walk_forward_runs_multiple_splits(trained_model):
    assert len(trained_model.cls_models) >= 2
    assert len(trained_model.split_starts) == len(trained_model.cls_models)


# ── feature_importance_history_ ─────────────────────────────────────────────

def test_feature_importance_history_has_one_row_per_split(trained_model):
    hist = trained_model.feature_importance_history_
    assert hist is not None
    assert len(hist) == len(trained_model.cls_models)


def test_feature_importance_history_columns_match_feature_cols(trained_model):
    hist = trained_model.feature_importance_history_
    assert list(hist.columns) == FEATURE_COLS


def test_feature_importance_history_indexed_by_split_start_dates(trained_model):
    hist = trained_model.feature_importance_history_
    assert list(hist.index) == trained_model.split_starts


def test_feature_importance_history_values_are_finite_and_nonnegative(trained_model):
    """LightGBM gain-importance är alltid >= 0."""
    hist = trained_model.feature_importance_history_
    assert np.isfinite(hist.values).all()
    assert (hist.values >= 0).all()


def test_feature_importance_mean_matches_history_mean(trained_model):
    """Det gamla, aggregerade feature_importance_ ska fortfarande vara
    EXAKT medelvärdet av den nya per-split-historiken – historiken lägger
    till detaljinformation, den ersätter inte/motsäger inte det gamla
    kontraktet andra anropare (main.py: print_feature_importance) litar på."""
    hist = trained_model.feature_importance_history_
    agg = trained_model.feature_importance_
    recomputed_mean = hist.mean(axis=0)
    for _, row in agg.iterrows():
        assert row["cls_importance"] == pytest.approx(recomputed_mean[row["feature"]], abs=1e-6)


def test_print_feature_importance_by_period_does_not_crash(trained_model, capsys):
    trained_model.print_feature_importance_by_period(n_periods=2, top_n=5)
    out = capsys.readouterr().out
    assert "Feature importance per period" in out


# ── fold_diagnostics_ ────────────────────────────────────────────────────────

def test_fold_diagnostics_has_one_entry_per_split(trained_model):
    assert len(trained_model.fold_diagnostics_) == len(trained_model.cls_models)


def test_fold_diagnostics_hit_rate_in_valid_range(trained_model):
    for d in trained_model.fold_diagnostics_:
        assert d["hit_rate"] is None or 0.0 <= d["hit_rate"] <= 1.0


def test_fold_diagnostics_split_numbers_are_sequential(trained_model):
    splits = [d["split"] for d in trained_model.fold_diagnostics_]
    assert splits == list(range(1, len(splits) + 1))
    assert all(d["n_splits"] == len(splits) for d in trained_model.fold_diagnostics_)


def test_fold_diagnostics_test_window_is_chronological(trained_model):
    for d in trained_model.fold_diagnostics_:
        assert d["test_start"] <= d["test_end"]


def test_print_fold_diagnostics_does_not_crash(trained_model, capsys):
    trained_model.print_fold_diagnostics()
    out = capsys.readouterr().out
    assert "Per-fold diagnostik" in out
    assert str(len(trained_model.fold_diagnostics_)) in out


def test_fold_diagnostics_empty_before_training():
    model = MomentumLGBM(params=_SMALL_PARAMS)
    assert model.fold_diagnostics_ == []
    assert model.feature_importance_history_ is None


# ── Featureordnings-guard (#6 i pipeline-granskningslistan) ──────────────────
# predict() jämför redan self.feature_cols_ (satt vid träning) mot den LIVE
# FEATURE_COLS och kastar ValueError vid avvikelse (models/lgbm_model.py,
# se docstringen för strict=). Detta var den enda av de 10 granskade
# kontrollerna som redan var löst i produktionskoden - men aldrig testad.

def test_predict_raises_when_feature_cols_changed_since_training(trained_model):
    df = _synthetic_df(n_weeks=10, n_tickers=4, seed=99)
    original = trained_model.feature_cols_
    try:
        trained_model.feature_cols_ = original[:-1] + ["some_other_feature"]
        with pytest.raises(ValueError, match="FEATURE_COLS har ändrats"):
            trained_model.predict(df)
    finally:
        trained_model.feature_cols_ = original


def test_predict_succeeds_when_feature_cols_unchanged(trained_model):
    df = _synthetic_df(n_weeks=10, n_tickers=4, seed=99)
    result = trained_model.predict(df)
    assert len(result) == len(df)


# ── Trädhälsa / bevarande av underkända splits (pipeline-granskning 2026-07-26)
# Uppföljning på rank-gap-fyndet: identiska rå LGBM-poäng mellan olika bolag
# spårades till splits med num_trees()<=1 (LightGBM:s egen "no further splits
# with positive gain"-terminering). trained_model tränas på ren slumpdata
# (inget verkligt momentum-mönster) - på den datan degenererar MERPARTEN av
# splittarna till exakt 1 träd, vilket gör den till ett bekvämt, redan
# existerande sätt att testa mekanismen utan att konstruera ett särskilt
# scenario.

def test_fold_diagnostics_records_num_trees_matching_actual_model(trained_model):
    for i, d in enumerate(trained_model.fold_diagnostics_):
        assert d["cls_num_trees"] == trained_model.cls_models[i].num_trees()


def test_degenerate_splits_exist_on_pure_noise_data(trained_model):
    """Sanity-check av testdatan självt: om INGEN split degenererar på ren
    slumpdata (inget momentum-mönster) täcker resten av testerna nedan noll
    verkligt scenario - trained_model MÅSTE innehålla minst en degenererad
    split för att vara meningsfull som fixture här."""
    num_trees = [d["cls_num_trees"] for d in trained_model.fold_diagnostics_]
    assert any(n <= 1 for n in num_trees)


def test_rejected_split_artifact_written_for_each_degenerate_split(trained_model, tmp_path):
    # trained_model-fixturen pekade om config.RESULTS_DIR under sin egen
    # körning (och återställde den efteråt) - kör en EGEN liten träning här,
    # riktad mot tmp_path, för att kunna inspektera de skrivna filerna direkt.
    original = config.RESULTS_DIR
    config.RESULTS_DIR = str(tmp_path)
    try:
        df = _synthetic_df(seed=7)
        model = MomentumLGBM(params=_SMALL_PARAMS)
        model.fit_walk_forward(df, train_weeks=20, val_weeks=6, step_weeks=6, embargo_weeks=2)
    finally:
        config.RESULTS_DIR = original

    degenerate_splits = [d for d in model.fold_diagnostics_ if d["cls_num_trees"] <= 1]
    assert degenerate_splits, "testdatan gav ingen degenererad split - se test ovan"

    rejected_dir = tmp_path / "rejected_splits"
    assert rejected_dir.exists()
    files = list(rejected_dir.glob("rejected_split_*.pkl"))
    assert len(files) == len(degenerate_splits)

    payload = joblib.load(files[0])
    assert payload["num_trees"] <= 1
    assert payload["status"] == "FAILED"
    assert payload["current_iteration"] == payload["num_trees"]
    assert set(payload["reproducibility"]) == {"code_hash", "random_seed", "cls_params", "feature_cols"}
    assert payload["reproducibility"]["random_seed"] == config.RANDOM_SEED
    assert payload["reproducibility"]["feature_cols"] == FEATURE_COLS
    assert payload["sample_weights"] is None
    assert isinstance(payload["X_tr"], np.ndarray)
    assert isinstance(payload["y_cls_tr"], np.ndarray)
    assert isinstance(payload["y_reg_tr"], np.ndarray)
    assert payload["X_tr"].shape[1] == len(FEATURE_COLS)
    assert payload["train_date_range"][0] < payload["train_date_range"][1]

    # Träningsindex: Date+ticker per rad, en rad per rad i X_tr/X_va.
    assert list(payload["train_index"].columns) == ["Date", "ticker"]
    assert len(payload["train_index"]) == len(payload["X_tr"])
    assert len(payload["val_index"]) == len(payload["X_va"])

    # eval_history: en lista per mätt metrik, en post per FÖRSÖKT boosting-
    # runda - inte bara de som blev kvar i den slutliga (early-stopping-
    # trunkerade) modellen. num_trees()==1 betyder att runda 1 var bäst och
    # ALDRIG slogs - det kan mycket väl betyda att ytterligare
    # early_stopping_rounds därefter faktiskt kördes (och finns i
    # eval_history) utan att förbättra, INTE att bara en enda runda någonsin
    # försöktes (se test_lgbm_diagnostics.py:s upptäckt 2026-07-26 - en
    # tidigare hypotes om "ingen ytterligare runda kördes alls" visade sig
    # motsägas av just denna logg).
    assert payload["eval_history"]
    for metric_values in payload["eval_history"].values():
        assert len(metric_values) >= payload["current_iteration"]

    # Datahashar: en per bevarad array, deterministiska (samma array -> samma hash).
    expected_hash_keys = {"X_tr", "y_cls_tr", "y_reg_tr", "X_va", "y_cls_va", "y_reg_va"}
    assert set(payload["data_hashes"]) == expected_hash_keys
    import hashlib
    assert payload["data_hashes"]["X_tr"] == hashlib.sha1(
        np.ascontiguousarray(payload["X_tr"]).tobytes()).hexdigest()[:16]


def test_fold_diagnostics_records_val_auc_current_iteration_and_score_resolution(trained_model):
    for d in trained_model.fold_diagnostics_:
        assert d["cls_current_iteration"] == d["cls_num_trees"]
        # AUC kan vara None om valideringsfönstret degenererat till en enda
        # klass (sällsynt men möjligt på ren slumpdata) - annars 0..1.
        if d["cls_val_auc"] is not None:
            assert 0.0 <= d["cls_val_auc"] <= 1.0
        assert d["cls_val_score_n_unique"] >= 1
        assert 0.0 <= d["cls_val_score_largest_plateau_frac"] <= 1.0


def test_rejected_split_reruns_overwrite_instead_of_accumulating(tmp_path):
    # Filnamnet nyckelas på val-startdatumet (deterministiskt givet samma
    # historik+config), inte t.ex. en körningstidsstämpel - en förnyad natts
    # körning ska skriva ÖVER en fortsatt underkänd splits fil, inte
    # ackumulera en ny fil per natt i all evighet.
    original = config.RESULTS_DIR
    config.RESULTS_DIR = str(tmp_path)
    try:
        df = _synthetic_df(seed=7)
        for _ in range(2):
            model = MomentumLGBM(params=_SMALL_PARAMS)
            model.fit_walk_forward(df, train_weeks=20, val_weeks=6, step_weeks=6, embargo_weeks=2)
    finally:
        config.RESULTS_DIR = original

    degenerate_splits = [d for d in model.fold_diagnostics_ if d["cls_num_trees"] <= 1]
    files = list((tmp_path / "rejected_splits").glob("rejected_split_*.pkl"))
    assert len(files) == len(degenerate_splits)   # inte dubbelt så många efter två körningar
