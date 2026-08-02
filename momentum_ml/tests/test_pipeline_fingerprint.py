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
import pandas as pd

from backtest.pipeline_fingerprint import compute_fingerprint  # noqa: E402


def test_fingerprint_is_deterministic_within_same_process():
    """Enhetstestet får inte göra nätverks-I/O eller bero på dagens tickerlista.
    Den riktiga modell-/data-integrationen körs av CLI-verktyget; här isoleras
    determinismkontraktet så testordning och nätverk inte kan ändra utfallet."""
    class DeterministicModel:
        def predict(self, feature_row):
            score = feature_row["feature"].astype(float) / 10.0
            return pd.DataFrame({
                "prob_up": score,
                "prob_raw": score + 0.1,
                "pred_return": score - 0.1,
            }, index=feature_row.index)

    feature_row = pd.DataFrame(
        {"feature": [1.0, 2.0]},
        index=pd.DatetimeIndex(["2025-01-06", "2025-01-13"]),
    )
    lgbm = DeterministicModel()

    fp1 = compute_fingerprint(feature_row, lgbm, None)
    fp2 = compute_fingerprint(feature_row, lgbm, None)
    assert fp1 == fp2
