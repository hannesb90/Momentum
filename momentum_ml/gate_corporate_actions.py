"""SR-10: identify extreme weekly returns not explained by PIT corporate actions."""
from __future__ import annotations
import pandas as pd
from research_gates_common import ROOT, write_report

JUMP = 0.50
WINDOW_DAYS = 10
EVIDENCE = ROOT / "data" / "extreme_jump_evidence.csv"


def main() -> int:
    px = pd.read_csv(ROOT / "results/prices.csv", parse_dates=["date"]).sort_values(["ticker", "date"])
    px["return"] = px.groupby("ticker")["close"].pct_change()
    jumps = px[px["return"].abs() >= JUMP].copy()
    actions = pd.read_csv(ROOT / "results/point_in_time/corporate_actions.csv", parse_dates=["event_date"])
    actions = actions[actions.event_date.notna()].copy()
    evidence = pd.read_csv(EVIDENCE, parse_dates=["event_date"]) if EVIDENCE.exists() else pd.DataFrame()
    explained = []
    nearest = []
    for row in jumps.itertuples():
        cand = actions[actions.ticker.eq(row.ticker)]
        days = (cand.event_date - row.date).abs().dt.days if len(cand) else pd.Series(dtype=float)
        d = int(days.min()) if len(days) else None
        nearest.append(d)
        reviewed = False
        if len(evidence):
            ev = evidence[evidence.ticker.eq(row.ticker)]
            reviewed = bool(((ev.event_date - row.date).abs().dt.days <= WINDOW_DAYS).any())
        explained.append((d is not None and d <= WINDOW_DAYS) or reviewed)
    jumps["nearest_action_days"] = nearest
    jumps["explained"] = explained
    unresolved = jumps[~jumps.explained]
    out_csv = ROOT / "results/research_gates/sr10_jump_audit.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    jumps.to_csv(out_csv, index=False)
    report = {"gate": "SR-10", "status": "PASS" if len(unresolved) == 0 else "FAIL",
              "jump_threshold": JUMP, "action_window_days": WINDOW_DAYS,
              "n_extreme_jumps": len(jumps), "n_explained": int(jumps.explained.sum()),
              "n_unresolved": len(unresolved),
              "reviewed_evidence_file": str(EVIDENCE.relative_to(ROOT)),
              "unresolved_sample": unresolved[["date", "ticker", "return", "nearest_action_days"]].head(25).to_dict("records")}
    path = write_report("sr10_corporate_actions", report)
    print(report); print(path); print(out_csv)
    return 0 if not len(unresolved) else 1


if __name__ == "__main__": raise SystemExit(main())
