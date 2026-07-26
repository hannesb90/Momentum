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

## Follow-up: scoped raw-data verification (2026-07-26, later same day)

The previous session ended before the raw-data rebuild above could be
attempted again. This session picked it up: Yahoo responded normally this
time (a single-ticker fetch test succeeded), but the Pi had tight memory at
the time (933MB available, 887MB already in swap, load ~2 - the same
conditions that have caused OOM crashes before). A full ~650-ticker
universe rebuild was therefore deliberately skipped in favor of a scoped
12-ticker Large-cap basket (AAK.ST, ATCO-A.ST, ERIC-B.ST, HM-B.ST,
INVE-B.ST, SAND.ST, SEB-A.ST, SKF-B.ST, SWED-A.ST, TELIA.ST, VOLV-B.ST,
ASSA-B.ST), run under `run_watched.sh` for memory safety.

Results:

- Fresh fetch (`use_cache=False`) succeeded for all 12/12 tickers.
- Full feature build (`build_all_features` + categorical + fundamentals,
  i.e. real cross-sectional features, not a degenerate single-ticker
  fingerprint) completed without error.
- The pipeline fingerprint was run twice against the **live production**
  `lgbm_model.pkl` (`/opt/momentum/momentum_ml/results/lgbm_model.pkl`,
  trained 2026-07-26 - not the stale local checkout artifact used
  elsewhere in this repo's tests) on freshly rebuilt AAK.ST features:
  identical result both times (`prob_up=0.4782608695652174`,
  `prob_raw=0.3870618222416631`, `pred_return=0.09789030613034388`). No
  LSTM checkpoint exists in the deploy tree, so this remains LGBM-only.
- The corrected event-mode backtester (post hard-exit fix) was run over
  this basket's full history: 2,268 recorded event decisions, **0**
  same-cycle hard-exit -> entry violations - confirming the fix holds
  against freshly recalculated raw data, not only the cached feature
  snapshot used earlier the same day.

This closes the specific gap flagged above (raw-data feature engineering
was not previously recalculated) at a reduced, memory-safe scope. It is
still not a full-universe raw-data validation - that remains a fair-weather
follow-up for a moment when the Pi has more headroom, or can simply rely on
the ordinary nightly `momentum-train.timer` run, which does rebuild the
full universe from raw data as a matter of course.
