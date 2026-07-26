# Fixed event mode – KEEP band matrix

Date: 2026-07-26

This is the first KEEP-band matrix run after correcting same-cycle hard-exit
re-entry and protecting incumbents in risk filters. Earlier event-mode results
are not promotion evidence because their hard-exit semantics were invalid.

## Full-period results

| Variant | CAGR | Sharpe | MaxDD | Turnover/year | Mean hold | Median hold | Rebuys 1–4w |
|---|---:|---:|---:|---:|---:|---:|---:|
| Production calendar | 12.13% | 1.06 | -21.41% | 4.64× | 15.61w | 13w | 12 |
| Event KEEP 1.0 | -2.70% | -0.43 | -44.32% | 14.81× | 1.97w | 1w | 2,313 |
| Event KEEP 1.5 | -2.20% | -0.25 | -38.93% | 15.85× | 2.30w | 1w | 1,842 |
| Event KEEP 2.0 | -0.77% | -0.03 | -36.78% | 17.64× | 2.65w | 1w | 1,518 |
| Event KEEP 2.5 | 0.83% | 0.13 | -34.68% | 16.42× | 2.93w | 1w | 1,364 |

## Modern and frozen holdout

- Modern CAGR: KEEP 1.0 -2.16%, 1.5 -2.34%, 2.0 -8.10%, 2.5 -8.57%.
- Frozen holdout CAGR: KEEP 1.0 -3.18%, 1.5 -4.60%, 2.0 -9.34%,
  2.5 -9.03%.
- No event variant beats the production calendar baseline.

## Replacement ledger

Mean forward 13-week replacement alpha:

| Variant | Hard exits | Voluntary exits |
|---|---:|---:|
| KEEP 1.0 | -0.29pp | +0.70pp |
| KEEP 1.5 | -0.47pp | +1.13pp |
| KEEP 2.0 | -0.34pp | +1.36pp |
| KEEP 2.5 | +0.08pp | +0.85pp |

Voluntary rotation has weak positive replacement alpha, but nowhere near enough
to offset weekly churn and execution costs. Hard exits generally move into a
slightly worse subsequent 13-week return.

## Decision

All raw KEEP-band variants are rejected. The one-week median holding period and
thousands of rapid rebuys show that a stateless `selection_eligible` decision
is functioning as a hard weekly exit. The next isolated test must separate the
strict buy momentum gate from a relaxed incumbent hold gate before replacement
thresholds or rotation budgets are evaluated.

Local artefacts:

- `/home/hannesb/fixed_event_keep_band_results.csv`
- `/home/hannesb/fixed_event_replacement_ledger.csv`
- `/home/hannesb/fixed_event_keep_band_results.json`
