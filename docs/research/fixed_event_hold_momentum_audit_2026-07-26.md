# Fixed event mode – separate buy/hold momentum

Date: 2026-07-26

New entries always required 12-1 momentum above +0.10. Only already-held,
base-eligible positions inside KEEP 2.0 received the alternative hold
thresholds. Trend, ATR, stale/ineligible and other hard exits remained
mandatory.

## Full-period results

| Hold momentum | CAGR | Sharpe | MaxDD | Turnover/year | Mean hold | Rebuys 1–4w |
|---|---:|---:|---:|---:|---:|---:|
| +0.10 | -0.77% | -0.03 | -36.78% | 17.64× | 2.65w | 1,518 |
| +0.05 | **0.42%** | **0.09** | -36.92% | 17.18× | 2.76w | 1,442 |
| 0.00 | 0.02% | 0.05 | -36.71% | 16.60× | 2.82w | 1,394 |
| -0.05 | 0.27% | 0.08 | **-36.52%** | 17.01× | 2.85w | 1,382 |

All variants retained a one-week median holding period.

## Modern / holdout

- Modern CAGR: +0.10 -8.10%, +0.05 -6.82%, 0.00 -8.29%, -0.05 -7.50%.
- Holdout CAGR: +0.10 -9.34%, +0.05 -7.42%, 0.00 -7.91%, -0.05 -10.66%.
- The +0.05 incumbent threshold is the least bad balanced variant, but it is
  still far below the production calendar baseline.

## Replacement ledger

Voluntary replacement alpha remained positive (+1.36pp to +1.73pp over the
subsequent 13 weeks). Hard-exit replacement alpha remained negative
(-0.32pp to -0.58pp).

## Decision

The +0.05 hold threshold improves the strict +0.10 event variant, but the
effect is too small to rescue event mode. It is retained only as the best
research setting for the next isolated replacement tests, not as a production
candidate.

The remaining one-week median and 1,382–1,518 rapid rebuys show that mandatory
trend/data exits, rather than the momentum gate alone, dominate turnover.

Local artefacts:

- `/home/hannesb/fixed_event_hold_momentum_results.csv`
- `/home/hannesb/fixed_event_hold_momentum_ledger.csv`
- `/home/hannesb/fixed_event_hold_momentum_results.json`
