"""SR-43: structural feature/label isolation plus deterministic placebo controls."""
from __future__ import annotations
import numpy as np
import pandas as pd
from features.feature_engineering import FEATURE_COLS
from research_gates_common import ROOT, write_report

FORBIDDEN_TOKENS = ("target", "forward", "future", "realized", "label")


def _mean_date_ic(score: pd.Series, target: pd.Series, dates: pd.Series) -> float:
    frame = pd.DataFrame({"s": score, "y": target, "d": dates}).dropna()
    vals = frame.groupby("d").apply(lambda x: x.s.corr(x.y, method="spearman"), include_groups=False)
    return float(vals.mean())


def main() -> int:
    forbidden = [c for c in FEATURE_COLS if any(t in c.lower() for t in FORBIDDEN_TOKENS)]
    sig = pd.read_csv(ROOT / "results/signals.csv", parse_dates=["Date"])
    px = pd.read_csv(ROOT / "results/prices.csv", parse_dates=["date"])
    panel = px.pivot(index="date", columns="ticker", values="close").sort_index()
    fwd = panel.shift(-52) / panel - 1
    long = fwd.stack().rename("target").reset_index().rename(columns={"date": "Date"})
    sample = sig[["Date", "ticker", "selection_rank"]].merge(long, on=["Date", "ticker"]).dropna().tail(30000)
    rng = np.random.default_rng(20260801)
    placebo = sample.groupby("Date")["selection_rank"].transform(lambda x: rng.permutation(x.to_numpy()))
    placebo_ic = _mean_date_ic(placebo, sample.target, sample.Date)
    positive_ic = _mean_date_ic(sample.groupby("Date")["target"].rank(pct=True), sample.target, sample.Date)
    placebo_ok = abs(placebo_ic) < 0.03
    positive_ok = positive_ic > 0.95
    pass_gate = not forbidden and placebo_ok and positive_ok
    report = {"gate": "SR-43", "status": "PASS" if pass_gate else "FAIL",
              "forbidden_feature_names": forbidden, "n_observations": len(sample),
              "placebo_mean_date_ic": placebo_ic, "placebo_abs_limit": 0.03,
              "positive_control_mean_date_ic": positive_ic,
              "note": "Structural gate; each new source still requires timestamp-specific lag tests."}
    path = write_report("sr43_placebo_leakage", report)
    print(report); print(path)
    return 0 if pass_gate else 1


if __name__ == "__main__": raise SystemExit(main())
