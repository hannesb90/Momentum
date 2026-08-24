#!/usr/bin/env python3
"""Run preregistered K5 regime and K3 matched fundamental-change diagnostics."""

from __future__ import annotations

import hashlib
import json
import math
import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from decision_portfolio_v2 import V2, annualized, dump, ic_metrics, manifest, target_map
from decision_portfolio_v3_execution import build_portfolio, execution_returns


ROOT = V2
RK = ROOT / "research_k"
G = ROOT / "sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3"
K5_OUT = RK / "results/K5_REGIME_DIAGNOSTIC_V1"
K3_OUT = RK / "results/K3_FUNDAMENTAL_CHANGE_DIAGNOSTIC_V1"
K5_HASH = "f71f91ce53c4ba52d3b58686ad4be20c66de6025b4fd2c759191a05f3c56f70e"
K3_HASH = "44f2be7df469f5dd011f056ebe92cd448c3fe6aaa9fd232e911ee45559c4a1cb"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    try: return math.isfinite(float(value))
    except (TypeError, ValueError): return False


def verify(stage: str) -> dict:
    assert sha(RK / "k5_regime_preregistration.json") == K5_HASH
    assert sha(RK / "k3_fundamental_change_preregistration.json") == K3_HASH
    if stage in ("all", "k5"): assert not K5_OUT.exists(), "immutable K5 output exists"
    if stage in ("all", "k3"): assert not K3_OUT.exists(), "immutable K3 output exists"
    paths = [
        ROOT / "repair_df/FREEZE_MANIFEST.json", ROOT / "panels/core_panel.json",
        ROOT / "panels/core_fundamenta_panel.json", ROOT / "panels/target_table.json",
        ROOT / "spare/macro_v1/macro_panel.json", G / "rankings.json", G / "holdings.json",
        G / "returns.json",
    ]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def load_h0():
    rankings = pd.DataFrame(json.loads((G / "rankings.json").read_text()))
    rankings = rankings[["kod", "panel_date", "score", "rank"]].copy()
    holdings = json.loads((G / "holdings.json").read_text())
    returns = json.loads((G / "returns.json").read_text())
    return rankings, holdings, returns


def target_frame(rankings: pd.DataFrame) -> pd.DataFrame:
    tm = target_map(); z = rankings[["kod", "panel_date"]].copy()
    z["y"] = [tm.get((k, d)) for k, d in zip(z.kod, z.panel_date)]
    return z[z.y.notna()].copy()


def regime_ic(rankings, targets, state_by_date, labels):
    x = rankings.merge(targets, on=["kod", "panel_date"], validate="one_to_one")
    x["state"] = x.panel_date.map(state_by_date)
    per = []
    for dt, g in x.groupby("panel_date", sort=True):
        if pd.isna(g.state.iloc[0]): continue
        top = g.sort_values(["score", "kod"], ascending=[False, False]).head(30)
        per.append({"panel_date": dt, "state": g.state.iloc[0], "n": len(g),
                    "ic52": float(spearmanr(g.score, g.y).statistic),
                    "top30_ic52": float(spearmanr(top.score, top.y).statistic)})
    summaries = {}
    for label in labels:
        rows = [r for r in per if r["state"] == label]; iv = [r["ic52"] for r in rows]; tv = [r["top30_ic52"] for r in rows]
        summaries[label] = {"panel_dates": len(rows), "mean_ic52": float(np.mean(iv)) if iv else None,
                            "median_ic52": float(np.median(iv)) if iv else None,
                            "top30_ic52": float(np.mean(tv)) if tv else None,
                            "positive_ic_share": float(np.mean(np.array(iv) > 0)) if iv else None,
                            "dates": [r["panel_date"] for r in rows]}
    return summaries, per


def regime_portfolio(holdings, returns, state_by_date, labels, pret):
    by_date_hold = defaultdict(list)
    for row in holdings: by_date_hold[row["panel_date"]].append(row)
    summaries = {}
    for label in labels:
        rows = [r for r in returns if state_by_date.get(r["panel_date"]) == label]
        nr = np.array([r["net_return"] for r in rows], float); br = np.array([r["benchmark_return"] for r in rows], float); ex = nr - br
        wealth = np.cumprod(1 + nr) if len(nr) else np.array([]); dd = wealth / np.maximum.accumulate(wealth) - 1 if len(nr) else np.array([])
        contrib = defaultdict(float)
        for r in rows:
            for h in by_date_hold[r["panel_date"]]: contrib[h["kod"]] += h["weight"] * pret.get((h["kod"], r["panel_date"]), 0.0)
        ranked = sorted(contrib.items(), key=lambda z: z[1], reverse=True); total = sum(v for _, v in ranked)
        summaries[label] = {
            "return_periods": len(rows), "conditional_cagr": annualized(nr.tolist()) if len(nr) else None,
            "conditional_benchmark_cagr": annualized(br.tolist()) if len(br) else None,
            "portfolio_excess_cagr": (annualized(nr.tolist()) - annualized(br.tolist())) if len(nr) else None,
            "sharpe_excess": float(ex.mean() / ex.std(ddof=1) * math.sqrt(13)) if len(ex) > 1 and ex.std(ddof=1) > 0 else None,
            "max_drawdown": float(dd.min()) if len(dd) else None,
            "top3_tickers": [k for k, _ in ranked[:3]],
            "top3_arithmetic_contribution_share": sum(v for _, v in ranked[:3]) / total if total else None,
        }
    return summaries


def classify_regime(labels, strong, ic_summary, per):
    weak = next(x for x in labels if x != strong)
    if min(ic_summary[x]["panel_dates"] for x in labels) < 5: return "OTILLRÄCKLIG DATA", {}
    diff = ic_summary[strong]["mean_ic52"] - ic_summary[weak]["mean_ic52"]
    top_diff = ic_summary[strong]["top30_ic52"] - ic_summary[weak]["top30_ic52"]
    dates = sorted({r["panel_date"] for r in per}); half = len(dates) // 2; blocks = [set(dates[:half]), set(dates[half:])]; bd = []
    for block in blocks:
        means = {lab: np.mean([r["ic52"] for r in per if r["state"] == lab and r["panel_date"] in block]) for lab in labels}
        bd.append(float(means[strong] - means[weak]) if all(np.isfinite(list(means.values()))) else None)
    detail = {"expected_strong_minus_other_mean_ic": diff, "top30_difference": top_diff, "chronological_half_differences": bd}
    if diff >= .03 and top_diff >= 0 and all(x is not None and x > 0 for x in bd): return "STABILT DIAGNOSTISKT SAMBAND", detail
    if abs(diff) < .01 and abs(top_diff) < .03: return "INGET SAMBAND", detail
    return "SVAGT/OSÄKERT SAMBAND", detail


def run_k5(rankings, targets, holdings, returns, pret, inputs):
    macro = pd.DataFrame(json.loads((ROOT / "spare/macro_v1/macro_panel.json").read_text())).sort_values("panel_date")
    core = pd.DataFrame(json.loads((ROOT / "panels/core_panel.json").read_text()))[["panel_date", "mom_26w"]]
    breadth = core.groupby("panel_date").mom_26w.apply(lambda s: float((s.dropna() > 0).mean()) if len(s.dropna()) else np.nan)
    macro["market_breadth_6m"] = macro.panel_date.map(breadth)
    macro["market_vol_expanding_median"] = macro.se_market_vol3m.expanding(min_periods=1).median()
    configs = {
        "market_trend_6m": (np.where(macro.se_market_ret6m >= 0, "POSITIVE", "NEGATIVE"), ["POSITIVE", "NEGATIVE"], "POSITIVE"),
        "market_volatility_3m": (np.where(macro.se_market_vol3m > macro.market_vol_expanding_median, "HIGH", "LOW"), ["LOW", "HIGH"], "LOW"),
        "market_breadth_6m": (np.where(macro.market_breadth_6m >= .5, "BROAD", "NARROW"), ["BROAD", "NARROW"], "BROAD"),
        "policy_rate_change_6m": (np.where(macro.policy_rate_d6m > 0, "RISING", "NON_RISING"), ["NON_RISING", "RISING"], "NON_RISING"),
        "yield_curve_10y_2y": (np.where(macro.curve_10y_2y >= 0, "POSITIVE", "INVERTED"), ["POSITIVE", "INVERTED"], "POSITIVE"),
        "risk_vix": (np.where(macro.vix_level >= 25, "STRESS", "NORMAL"), ["NORMAL", "STRESS"], "NORMAL"),
    }
    results = {}
    for name, (states, labels, strong) in configs.items():
        state_by_date = dict(zip(macro.panel_date, states)); ic_sum, per = regime_ic(rankings, targets, state_by_date, labels)
        port = regime_portfolio(holdings, returns, state_by_date, labels, pret); classification, contrast = classify_regime(labels, strong, ic_sum, per)
        seq = [(d, state_by_date.get(d)) for d in sorted(rankings.panel_date.unique())]; transitions = defaultdict(int)
        for (_, a), (_, b) in zip(seq, seq[1:]): transitions[f"{a}->{b}"] += 1
        results[name] = {"classification": classification, "expected_stronger_state": strong,
                         "ic": ic_sum, "portfolio": port, "contrast": contrast,
                         "transitions": dict(transitions), "per_date_ic": per}
    K5_OUT.mkdir(parents=True); dump(K5_OUT / "regime_results.json", results)
    dump(K5_OUT / "run_provenance.json", {"version": "K5_REGIME_DIAGNOSTIC_V1", "preregistration_sha256": K5_HASH,
         "input_hashes": inputs, "h0_holdings_unchanged": True, "gate_or_scaling_created": False,
         "target_used_only_for_evaluation": True, "regime_dates_target_independent": True})
    dump(K5_OUT / "manifest.json", manifest(K5_OUT)); return results


def rank_pct(series, higher=True):
    return series.rank(pct=True, ascending=higher)


def feature_ic(scores, targets):
    return ic_metrics(scores, targets, n=30)


def block_delta(blend, base, targets):
    dates = sorted(targets.panel_date.unique()); blocks = [set(dates[:len(dates)//2]), set(dates[len(dates)//2:])]; out=[]
    for i, ds in enumerate(blocks, 1):
        b = feature_ic(base[base.panel_date.isin(ds)], targets[targets.panel_date.isin(ds)])
        c = feature_ic(blend[blend.panel_date.isin(ds)], targets[targets.panel_date.isin(ds)])
        out.append({"block": i, "dates": len(ds), "delta_mean_ic52": c["mean_ic52"] - b["mean_ic52"]})
    return out


def run_k3(rankings, targets, inputs, pret, emeta):
    fund = pd.DataFrame(json.loads((ROOT / "panels/core_fundamenta_panel.json").read_text()))
    cols = ["kod", "panel_date", "has_fundamenta", "revenue_growth_yoy", "operating_margin_ttm", "ebitda_margin_ttm", "fcf_margin_ttm", "shares_growth_yoy"]
    fund = fund[cols].sort_values(["kod", "panel_date"])
    for source, out in [("operating_margin_ttm", "operating_margin_change_yoy"), ("ebitda_margin_ttm", "ebitda_margin_change_yoy"), ("fcf_margin_ttm", "fcf_margin_change_yoy")]:
        prior = fund[["kod", "panel_date", source]].copy(); prior["panel_date"] = (pd.to_datetime(prior.panel_date) + pd.Timedelta(days=364)).dt.strftime("%Y-%m-%d")
        prior = prior.rename(columns={source: source + "_prior"}); fund = fund.merge(prior, on=["kod", "panel_date"], how="left", validate="one_to_one")
        fund[out] = fund[source] - fund[source + "_prior"]
    specs = {"revenue_growth_yoy": True, "operating_margin_change_yoy": True, "ebitda_margin_change_yoy": True,
             "fcf_margin_change_yoy": True, "share_count_dilution_yoy": False}
    fund["share_count_dilution_yoy"] = fund.shares_growth_yoy
    terminal = set(json.loads((ROOT / "validated/terminal_events.json").read_text()))
    results = {}; artifacts = {k: [] for k in ("rankings", "holdings", "trades", "returns")}
    for feature, higher in specs.items():
        z = rankings.merge(fund[["kod", "panel_date", "has_fundamenta", feature]], on=["kod", "panel_date"], how="left", validate="one_to_one")
        z = z[z[feature].map(finite)].copy(); z["feature_rank"] = z.groupby("panel_date")[feature].rank(pct=True, ascending=higher)
        z["h0_rank_matched"] = z.groupby("panel_date").score.rank(pct=True); z["blend_score"] = .5*z.h0_rank_matched + .5*z.feature_rank
        base = z[["kod", "panel_date", "score"]].copy(); blend = z[["kod", "panel_date", "blend_score"]].rename(columns={"blend_score": "score"})
        mt = targets.merge(z[["kod", "panel_date"]], on=["kod", "panel_date"], how="inner", validate="one_to_one")
        bi = feature_ic(base, mt); ci = feature_ic(blend, mt); blocks = block_delta(blend, base, mt)
        delta = {"mean_ic52": ci["mean_ic52"]-bi["mean_ic52"], "median_ic52": ci["median_ic52"]-bi["median_ic52"],
                 "top30_ic52": ci["mean_topN_ic52"]-bi["mean_topN_ic52"], "positive_ic_share": ci["positive_ic_share"]-bi["positive_ic_share"]}
        if delta["mean_ic52"] >= .01 and delta["median_ic52"] > 0 and delta["top30_ic52"] >= 0 and delta["positive_ic_share"] >= 0 and all(x["delta_mean_ic52"] > 0 for x in blocks): cls="INKREMENTELLT INFORMATIONSSTÖD"
        elif delta["mean_ic52"] > 0: cls="SVAGT STÖD"
        else: cls="INGET STÖD"
        # Portfolio selection is coverage-matched at rebalance, while existing
        # holdings persist on intervening 4w panels even if a new fundamental
        # value is absent.  Full-universe sentinel rows are rank-last only and
        # never encode an economic value.
        available = z[["kod", "panel_date", "blend_score"]]
        port = rankings.merge(available, on=["kod", "panel_date"], how="left", validate="one_to_one")
        port["h0_matched_port_score"] = np.where(port.blend_score.notna(), port.score, -1e12)
        port["blend_port_score"] = port.blend_score.fillna(-1e12)
        base_port = port[["kod", "panel_date", "h0_matched_port_score"]].rename(columns={"h0_matched_port_score":"score"})
        blend_port = port[["kod", "panel_date", "blend_port_score"]].rename(columns={"blend_port_score":"score"})
        bm, ba = build_portfolio(base_port, n=30, every=2, cost=.002, model=feature+"_matched_h0", returns_map=pret, execution_meta=emeta)
        cm, ca = build_portfolio(blend_port, n=30, every=2, cost=.002, model=feature+"_blend", returns_map=pret, execution_meta=emeta)
        for art in (ba, ca):
            for key in artifacts: artifacts[key] += art[key]
        covered_codes=set(z.kod); term=sorted(covered_codes & terminal)
        results[feature] = {"classification": cls, "warning": "NOT SURVIVORSHIP SAFE", "coverage": {"decision_rows": len(z),
            "target_evaluation_rows": len(mt), "instruments": len(covered_codes), "terminal_instruments": len(term), "terminal_codes": term,
            "panel_dates": z.panel_date.nunique()}, "matched_h0_ic": bi, "blend_ic": ci, "delta": delta, "chronological_blocks": blocks,
            "secondary_matched_portfolio": {"h0": bm, "blend": cm}}
    K3_OUT.mkdir(parents=True); dump(K3_OUT / "fundamental_change_results.json", results)
    for key, rows in artifacts.items(): dump(K3_OUT / f"{key}.json", rows)
    dump(K3_OUT / "run_provenance.json", {"version": "K3_FUNDAMENTAL_CHANGE_DIAGNOSTIC_V1", "preregistration_sha256": K3_HASH,
         "input_hashes": inputs, "warning": "NOT SURVIVORSHIP SAFE", "challenger_created": False,
         "target_used_only_for_evaluation": True, "matched_population_rule": True})
    dump(K3_OUT / "manifest.json", manifest(K3_OUT)); return results


def main():
    global K5_OUT, K3_OUT
    ap=argparse.ArgumentParser();ap.add_argument("--stage",choices=("all","k5","k3"),default="all");ap.add_argument("--output-root");args=ap.parse_args()
    if args.output_root:
        base=Path(args.output_root);K5_OUT=base/"K5_REGIME_DIAGNOSTIC_V1";K3_OUT=base/"K3_FUNDAMENTAL_CHANGE_DIAGNOSTIC_V1"
    inputs = verify(args.stage); rankings, holdings, returns = load_h0(); targets = target_frame(rankings); pret, emeta = execution_returns(); answer={}
    if args.stage in ("all","k5"):
        k5 = run_k5(rankings, targets, holdings, returns, pret, inputs); answer["K5"]={k:v["classification"] for k,v in k5.items()}
    if args.stage in ("all","k3"):
        k3 = run_k3(rankings, targets, inputs, pret, emeta); answer["K3"]={k:v["classification"] for k,v in k3.items()}
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
