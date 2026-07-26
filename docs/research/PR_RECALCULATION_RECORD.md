# PR recalculation record (2026-07-26)

The event backtest code was rerun from commit `915f34e` (the PR containing
pipeline diagnostics, feature-order validation, calibration split and seeded
LSTM changes). The source feature cache was the complete saved Large cache at
`/opt/momentum/momentum_ml/results/challenger/features_latest.pkl`.

The deterministic pipeline fingerprint passed twice on the same AAK.ST feature
history: 813 rows, last date 2026-07-20, identical LGBM output on both runs
(`prob_up=0.34444444444444444`, `prob_raw=0.35952906309066135`,
`pred_return=0.04728788657932945`). No LSTM checkpoint was present, so this is
an LGBM-only fingerprint.

Yahoo/EODHD was unavailable while attempting a fresh feature rebuild. The
feature cache therefore was not regenerated from raw prices; this record is a
valid test of the PR inference/ensemble path on the saved feature vectors, but
not a claim that raw-data feature engineering was recalculated. Production
signals were not overwritten.

The event hard-exit and KEEP-band scripts were prepared to consume an isolated
signal path. Their previously recorded corrected-engine results remain the
reference until a fresh raw-data rebuild is possible.
