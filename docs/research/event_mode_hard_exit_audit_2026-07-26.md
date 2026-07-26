# Event mode hard-exit audit

Date: 2026-07-26

## Scope

The production Large/Mid signal history was run through the existing
`REBALANCE_MODE="event"` implementation without modifying its decision logic.
For every held position and weekly event cycle, the audit recorded:

- trend break (`close < EXIT_SMA_WEEKS`)
- ATR trailing-stop trigger
- whether the ticker was still held after the same event rebalance

## Result before fix

| Measure | Count |
|---|---:|
| Hard-exit events | 2,525 |
| Trend-break events | 2,367 |
| ATR-stop events | 158 |
| Same-cycle hard-exit violations | 1,568 |
| Trend-break violations | 1,452 |
| ATR-stop violations | 116 |

## Root cause

1. A trend-broken holding is excluded from `survivors`, but remains in the
   ranked eligible list and can immediately be added back to `entries`.
2. Event mode calls `_event_rebalance()` directly and never calls
   `_atr_stop_exit()`, so ATR is not a hard exit in this mode.
3. There is no per-cycle hard-exit blocklist shared by exits and entry
   selection.

This means the old event-mode backtests do not implement their documented
hard-exit semantics. They must not be used to authorize production promotion.

## Required correction

- Resolve hard exits before voluntary rotation.
- Exclude every hard-exited ticker from entries for the entire decision cycle.
- Apply ATR, trend, ineligibility and stale/delisting checks consistently.
- Add regression tests for same-cycle re-entry.
- Preserve hard exits outside any voluntary replacement budget.

The raw local audit artefacts are:

- `/home/hannesb/event_hard_exit_audit.json`
- `/home/hannesb/event_hard_exit_audit.csv`
