"""
Verifierar #10 i pipeline-granskningslistan (se backtest/pipeline_fingerprint.py):
samma featurevektor genom samma sparade modell ska ge IDENTISKT resultat två
gånger i samma process. Kräver en redan tränad+sparad LGBM-modell – samma
förutsättning som backtest/calibration_check.py:s CLI – hoppas över annars
(t.ex. en färsk checkout utan en nattlig träningskörning bakom sig).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
from data.data_loader import fetch_weekly_data, load_sweden_universe  # noqa: E402
from features.feature_engineering import (  # noqa: E402
    build_all_features, attach_categorical_features, attach_fundamentals_features, FEATURE_COLS,
)
from models.lgbm_model import MomentumLGBM  # noqa: E402
from backtest.pipeline_fingerprint import compute_fingerprint  # noqa: E402

_SEG = config.SEGMENTS[config.DEFAULT_SEGMENT]
_MODEL_PATH = Path(_SEG["results_dir"]) / "lgbm_model.pkl"


@pytest.mark.skipif(
    not _MODEL_PATH.exists(),
    reason="Kräver en redan tränad+sparad LGBM-modell (samma villkor som calibration_check.py:s CLI)",
)
def test_fingerprint_is_deterministic_within_same_process():
    lgbm = MomentumLGBM.load(str(_MODEL_PATH))
    tickers, sector_map, cap_tier_map, _ = load_sweden_universe(min_market_cap=_SEG["market_cap"])
    ticker = tickers[0]

    data = fetch_weekly_data([ticker], start=config.START_DATE, end=None, use_cache=True)
    feat_dict = build_all_features(data)
    feat_dict = attach_categorical_features(feat_dict, sector_map=sector_map, cap_tier_map=cap_tier_map)
    feat_dict = attach_fundamentals_features(feat_dict, segment=config.DEFAULT_SEGMENT, prices=data)
    feature_row = feat_dict[ticker].dropna(subset=FEATURE_COLS[:5])

    fp1 = compute_fingerprint(feature_row, lgbm, None)
    fp2 = compute_fingerprint(feature_row, lgbm, None)
    assert fp1 == fp2
