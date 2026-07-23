import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from ablation_components import variant_inputs, format_result_row, _VARIANTS  # noqa: E402


_LGBM = {"AZA.ST": "lgbm-preds"}
_LSTM = {"AZA.ST": "lstm-preds"}


def test_variant_inputs_lgbm_only_uses_only_lgbm_predictions():
    first, second, market_filter = variant_inputs("lgbm_only", _LGBM, _LSTM)
    assert first is _LGBM
    assert second is None
    assert market_filter is False


def test_variant_inputs_lstm_only_uses_only_lstm_predictions():
    """Kärnmekaniken: build_full_output/combine() bryr sig bara om
    prob_up/pred_return-kolumnerna finns, inte om dictionaryn kom från
    LGBM eller LSTM – att skicka LSTM-prediktionerna som FÖRSTA argument
    (med lstm_preds=None) ger en giltig 'LSTM-only'-körning."""
    first, second, market_filter = variant_inputs("lstm_only", _LGBM, _LSTM)
    assert first is _LSTM
    assert second is None
    assert market_filter is False


def test_variant_inputs_ensemble_combines_both_no_regime_filter():
    first, second, market_filter = variant_inputs("ensemble", _LGBM, _LSTM)
    assert first is _LGBM
    assert second is _LSTM
    assert market_filter is False


def test_variant_inputs_regime_combines_both_with_regime_filter():
    first, second, market_filter = variant_inputs("regime", _LGBM, _LSTM)
    assert first is _LGBM
    assert second is _LSTM
    assert market_filter is True


def test_variant_inputs_unknown_variant_raises():
    with pytest.raises(ValueError, match="Okänd variant"):
        variant_inputs("something_else", _LGBM, _LSTM)


def test_all_declared_variants_are_handled():
    """Regressionsskydd: en ny variant i _VARIANTS utan motsvarande gren i
    variant_inputs ska fela HÄR i ett test, inte tyst i en natt-körning på Pi:n."""
    for v in _VARIANTS:
        variant_inputs(v, _LGBM, _LSTM)   # kastar inte -> ok


def test_format_result_row_includes_variant_and_metrics():
    stats = {"CAGR": "12.3%", "Sharpe": "1.05", "Max Drawdown": "-18.2%"}
    row = format_result_row("ensemble", stats, alpha_cagr=0.034)
    assert "ensemble" in row
    assert "12.3%" in row
    assert "1.05" in row
    assert "+3.4%" in row


def test_format_result_row_handles_missing_alpha():
    stats = {"CAGR": "5.0%", "Sharpe": "0.5", "Max Drawdown": "-10%"}
    row = format_result_row("lgbm_only", stats, alpha_cagr=None)
    assert "n/a" in row
