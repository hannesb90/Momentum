"""N3-30 / SR8: DEV-only screen of conditional risk-adjusted momentum."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

from backtest.regime import classify_regimes
from niva3_stage_control import freeze_stage, verify_manifest
from tune_publication_missingness_niva3_stage17 import reconstructed_state
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/niva3_stages/29_newly_qualified_sleeve_gate.json"
SIGNALS = ROOT / "results/niva3_reconstructed_price_signals_corrected.csv"
OUT = ROOT / "results/niva3_conditional_riskadj_screen.json"
DATES = ROOT / "results/niva3_conditional_riskadj_date_metrics.csv"
SUMMARY = ROOT / "results/niva3_conditional_riskadj_summary.csv"
DOCS = (ROOT / "docs/UTVECKLINGSLOGG.md", ROOT / "docs/niva3_status_handoff.md")


def zscore(x: pd.Series) -> pd.Series:
    sd = x.std(ddof=0)
    return (x - x.mean()) / sd if pd.notna(sd) and sd > 0 else x * 0.0


def holm(pvalues: np.ndarray) -> np.ndarray:
    order = np.argsort(pvalues); passed = np.zeros(len(pvalues), dtype=bool); active = True
    for rank, idx in enumerate(order):
        ok = active and pvalues[idx] <= .05 / (len(pvalues) - rank)
        passed[idx] = ok; active = bool(ok)
    return passed


def main() -> None:
    parent = verify_manifest(PARENT)
    features, prices, _ = reconstructed_state()
    panel = panel_from(features, prices)
    oof = pd.DatetimeIndex(pd.read_csv(SIGNALS, parse_dates=["Date"]).Date.drop_duplicates().sort_values())
    panel = panel[panel.index.isin(oof)].copy()
    regimes = classify_regimes(prices).reindex(oof).ffill()
    rows = []
    pairs = (("mom12", "mom_12_1", "rvol_26w"), ("roc13", "roc_13w", "rvol_13w"))
    for date, g0 in panel.groupby(level=0):
        regime = regimes.get(date)
        for family, raw_col, vol_col in pairs:
            g = g0[[raw_col, vol_col, "ret13"]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(g) < 20: continue
            raw = zscore(g[raw_col])
            riskadj = zscore(g[raw_col] / g[vol_col].clip(lower=.02))
            high_vol = g[vol_col].rank(pct=True).ge(.75)
            variants = {
                "high_vol_q4": raw.where(~high_vol, riskadj),
                "bear_regime": riskadj if regime == "bear" else raw,
            }
            raw_ic = raw.rank().corr(g.ret13.rank())
            raw_down = g.loc[raw.nlargest(max(1, len(g)//10)).index, "ret13"].clip(upper=0).mean()
            for conditional, score in variants.items():
                top = score.nlargest(max(1, len(g)//10)).index
                rows.append({"date": date, "family": family, "conditional": conditional,
                             "regime": regime, "raw_ic": raw_ic,
                             "conditional_ic": score.rank().corr(g.ret13.rank()),
                             "raw_top_decile_downside": raw_down,
                             "conditional_top_decile_downside": g.loc[top, "ret13"].clip(upper=0).mean()})
    d = pd.DataFrame(rows)
    d["ic_delta"] = d.conditional_ic - d.raw_ic
    d["downside_delta"] = d.conditional_top_decile_downside - d.raw_top_decile_downside
    d.to_csv(DATES, index=False)
    summary = []
    for (family, conditional), g in d.groupby(["family", "conditional"]):
        x = g.ic_delta.dropna()
        p = float(stats.ttest_1samp(x, 0, alternative="greater").pvalue) if len(x) > 2 else 1.0
        yearly = g.assign(year=pd.to_datetime(g.date).dt.year).groupby("year").ic_delta.mean()
        summary.append({"family": family, "conditional": conditional, "weeks": len(x),
                        "raw_mean_ic": g.raw_ic.mean(), "conditional_mean_ic": g.conditional_ic.mean(),
                        "mean_ic_delta": x.mean(), "positive_year_share": float((yearly > 0).mean()),
                        "mean_downside_delta": g.downside_delta.mean(), "pvalue": p})
    s = pd.DataFrame(summary)
    s["holm_pass"] = holm(s.pvalue.to_numpy())
    s["screen_pass"] = (s.holm_pass & s.mean_ic_delta.ge(.01) &
                        s.positive_year_share.ge(.60) & s.mean_downside_delta.ge(0))
    s.to_csv(SUMMARY, index=False)
    passed = [f"{row.family}/{row.conditional}"
              for row in s.loc[s.screen_pass].itertuples(index=False)]
    report = {"status": "PASS", "parent_stage": parent["manifest_sha256"],
              "test": "N3-SR8-conditional-risk-adjusted-momentum-screen",
              "variants": ["mom12/high_vol_q4", "mom12/bear_regime",
                           "roc13/high_vol_q4", "roc13/bear_regime"],
              "passed_variants": passed, "screen_gate": "PASS" if passed else "FAIL",
              "decision_rule": "Holm one-sided p<.05, mean IC delta >=.01, positive in >=60% years, top-decile downside not worse",
              "full_model_retrain_authorized": bool(passed), "selection_allowed": False,
              "holdout_used": False, "production": False}
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    best = s.sort_values("mean_ic_delta", ascending=False).iloc[0]
    section = ("\n## 2026-08-01 – N3-30: SR8 villkorat riskjusterat momentum\n\n"
               f"Fyra förregistrerade DEV-varianter screenades med Holm-korrigering. "
               f"Bäst IC-delta var `{best.family}/{best.conditional}` {best.mean_ic_delta:+.4f}; "
               f"godkända varianter: {passed or 'inga'}. `screen_gate={report['screen_gate']}`. "
               "Endast en godkänd screen får utlösa full LambdaRank-omträning. Ingen holdout "
               "eller produktion användes.\n")
    for doc in DOCS:
        with doc.open("a", encoding="utf-8") as f: f.write(section)
    stage = freeze_stage("30_conditional_riskadj_screen",
                         [OUT, DATES, SUMMARY, Path(__file__).resolve(), SIGNALS],
                         {"test": "N3-SR8", "screen_gate": report["screen_gate"],
                          "passed_variants": passed, "production": False}, parent=PARENT)
    print(s.to_string(index=False)); print(json.dumps(report, indent=2, ensure_ascii=False)); print(stage)


if __name__ == "__main__": main()
