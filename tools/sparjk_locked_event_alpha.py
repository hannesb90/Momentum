#!/usr/bin/env python3
"""Run the locked report/PEAD and insider-conditional-H0 tests, one stage at a time."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from decision_portfolio_v2 import V2, dump, manifest, target_map


ROOT = V2
RK = ROOT / "research_k"
G = ROOT / "sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3"
REPORT_PRE = RK / "REPORT_PEAD_PREREGISTRATION_BEFORE_ALPHA.json"
INSIDER_PRE = RK / "INSIDER_CONDITIONAL_H0_PREREGISTRATION_BEFORE_ALPHA.json"
OP_LOCK = RK / "EVENT_ALPHA_OPERATIONAL_LOCK_BEFORE_RESULTS.json"
REPORT_OUT = RK / "results/REPORT_PEAD_LOCKED_V1"
INSIDER_OUT = RK / "results/INSIDER_CONDITIONAL_H0_LOCKED_V1"
REPORT_PRE_SHA = "ac92a3b3cb7cc13d34029a3a8356e042e73fcbb68929e5928048ae8efaa087c6"
INSIDER_PRE_SHA = "f5a3af5afa170cbdc137626cd242a3c666463dc64a95a8e3e742e83aadd4caf7"
MFN_MANIFEST_SHA = "5d74ff7188767ec125ddbc5dbc6f317f087f911d4f08e654e1a0046bd7724db5"
FI_MANIFEST_SHA = "80fd640c968f6324135ff806673ac92072df074499eb486024272df87e26fbb0"
STOCKHOLM = ZoneInfo("Europe/Stockholm")
UTC = ZoneInfo("UTC")
MIN_GROUP = 3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(x):
    try:
        return float(x) if math.isfinite(float(x)) else None
    except (TypeError, ValueError):
        return None


def verify(stage: str) -> dict:
    assert sha(REPORT_PRE) == REPORT_PRE_SHA
    assert sha(INSIDER_PRE) == INSIDER_PRE_SHA
    assert sha(ROOT / "trackj/validated_mfn_report_events_v1/manifest.json") == MFN_MANIFEST_SHA
    assert sha(ROOT / "trackj/validated_fi_insider_v4/FINAL_FREEZE_MANIFEST.json") == FI_MANIFEST_SHA
    if stage == "report":
        assert not REPORT_OUT.exists(), "immutable report result already exists"
        assert not INSIDER_OUT.exists(), "insider result already exists before report stage"
    elif stage == "insider":
        assert REPORT_OUT.exists(), "report must be frozen first"
        verify_result(REPORT_OUT)
        assert not INSIDER_OUT.exists(), "immutable insider result already exists"
    return {
        "report_preregistration": REPORT_PRE_SHA,
        "insider_preregistration": INSIDER_PRE_SHA,
        "operational_lock": sha(OP_LOCK),
        "mfn_manifest": MFN_MANIFEST_SHA,
        "fi_manifest": FI_MANIFEST_SHA,
        "h0_rankings": sha(G / "rankings.json"),
        "target_table": sha(ROOT / "panels/target_table.json"),
        "validated_prices": sha(ROOT / "validated/prices/prices_validated.json"),
        "terminal_events": sha(ROOT / "validated/terminal_events.json"),
    }


def verify_result(out: Path) -> None:
    mf = json.loads((out / "manifest.json").read_text())
    for row in mf["files"]:
        path = out / row["path"]
        if not path.is_file() or sha(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise RuntimeError(f"frozen result mismatch: {path}")


def load_h0() -> pd.DataFrame:
    rows = json.loads((G / "rankings.json").read_text())
    return pd.DataFrame(rows)[["kod", "panel_date", "score", "rank"]].copy()


def targets_for(rows: pd.DataFrame) -> pd.DataFrame:
    tm = target_map()
    out = rows[["kod", "panel_date"]].drop_duplicates().copy()
    out["y"] = [tm.get((k, d)) for k, d in zip(out.kod, out.panel_date)]
    return out[out.y.notna()].copy()


def safe_spearman(a, b):
    if len(a) < MIN_GROUP or pd.Series(a).nunique() < 2 or pd.Series(b).nunique() < 2:
        return None
    return finite(spearmanr(a, b).statistic)


def score_metrics(scores: pd.DataFrame, targets: pd.DataFrame) -> dict:
    x = scores.merge(targets, on=["kod", "panel_date"], how="inner", validate="one_to_one")
    per = []
    for dt, g in x.groupby("panel_date", sort=True):
        ic = safe_spearman(g.score, g.y)
        top = g.sort_values(["score", "kod"], ascending=[False, True]).head(30)
        top_ic = safe_spearman(top.score, top.y)
        per.append({"panel_date": dt, "n": len(g), "ic52": ic, "top30_ic52": top_ic,
                    "distinct_scores": int(g.score.nunique())})
    iv = [r["ic52"] for r in per if r["ic52"] is not None]
    tv = [r["top30_ic52"] for r in per if r["top30_ic52"] is not None]
    return {
        "observations": len(x), "panel_dates": len(per), "evaluable_ic_dates": len(iv),
        "mean_ic52": finite(np.mean(iv)) if iv else None,
        "median_ic52": finite(np.median(iv)) if iv else None,
        "top30_ic52": finite(np.mean(tv)) if tv else None,
        "positive_ic_share": finite(np.mean(np.array(iv) > 0)) if iv else None,
        "per_date": per,
    }


def delta_metrics(base: pd.DataFrame, blend: pd.DataFrame, targets: pd.DataFrame) -> dict:
    b = score_metrics(base, targets); c = score_metrics(blend, targets)
    delta = {key: c[key] - b[key] if c[key] is not None and b[key] is not None else None
             for key in ("mean_ic52", "median_ic52", "top30_ic52", "positive_ic_share")}
    dates = sorted(set(r["panel_date"] for r in c["per_date"] if r["ic52"] is not None))
    halves = [set(dates[:len(dates)//2]), set(dates[len(dates)//2:])]
    blocks = []
    for i, ds in enumerate(halves, 1):
        bt = targets[targets.panel_date.isin(ds)]
        bm = score_metrics(base[base.panel_date.isin(ds)], bt)
        cm = score_metrics(blend[blend.panel_date.isin(ds)], bt)
        blocks.append({"half": i, "dates": len(ds),
                       "delta_mean_ic52": (cm["mean_ic52"] - bm["mean_ic52"]
                                           if cm["mean_ic52"] is not None and bm["mean_ic52"] is not None else None)})
    return {"h0_matched": b, "challenger": c, "delta": delta, "chronological_halves": blocks}


def classify_delta(result: dict, require_terminal=False, terminal_delta=None) -> str:
    c = result["challenger"]; d = result["delta"]; halves = result["chronological_halves"]
    if c["evaluable_ic_dates"] < 10 or any(x["dates"] < 3 for x in halves):
        return "OTILLRÄCKLIG DATA"
    support = (d["mean_ic52"] is not None and d["mean_ic52"] >= .01
               and d["median_ic52"] is not None and d["median_ic52"] >= 0
               and d["top30_ic52"] is not None and d["top30_ic52"] >= 0
               and d["positive_ic_share"] is not None and d["positive_ic_share"] >= 0
               and all(x["delta_mean_ic52"] is not None and x["delta_mean_ic52"] > 0 for x in halves))
    if require_terminal:
        support = support and terminal_delta is not None and terminal_delta >= 0
    if support:
        return "STÖD"
    return "SVAGT STÖD" if d["mean_ic52"] is not None and d["mean_ic52"] > 0 else "INGET STÖD"


def price_data():
    raw = json.loads((ROOT / "validated/prices/prices_validated.json").read_text())
    return {k: sorted(rs, key=lambda r: r["d"]) for k, rs in raw.items()}


def close_timestamp(day: str) -> datetime:
    return datetime.combine(date.fromisoformat(day), time(17, 30), tzinfo=STOCKHOLM).astimezone(UTC)


def report_measurements() -> list[dict]:
    prices = price_data(); terminal = json.loads((ROOT / "validated/terminal_events.json").read_text())
    events = []
    path = ROOT / "trackj/validated_mfn_report_events_v1/validated_mfn_report_events.jsonl"
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if not (row["primary_event_for_instrument_day"] and row["provider_report_tag"]
                and row["event_type"] in {"Q1", "Q2", "Q3", "Q4", "YEAR_END"}):
            continue
        code = row["instrument_id"]; rs = prices.get(code, [])
        pub = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
        before = [r for r in rs if close_timestamp(r["d"]) < pub]
        after = [r for r in rs if close_timestamp(r["d"]) > pub]
        if not before or not after:
            continue
        pre, post = before[-1], after[0]
        horizon_date = (date.fromisoformat(post["d"]) + timedelta(days=91)).isoformat()
        horizon = next((r for r in rs if r["d"] >= horizon_date), None)
        terminal_used = False
        if horizon is None:
            ev = terminal.get(code)
            if ev and post["d"] <= ev["event_date"] <= horizon_date:
                candidates = [r for r in rs if post["d"] <= r["d"] <= ev["event_date"]]
                horizon = candidates[-1] if candidates else None
                terminal_used = horizon is not None
        initial = post["adj"] / pre["adj"] - 1 if pre["adj"] else None
        drift = horizon["adj"] / post["adj"] - 1 if horizon and post["adj"] else None
        events.append({
            "event_id": row["event_id"], "kod": code, "isin": row["isin"],
            "event_type": row["event_type"], "published_at": row["published_at"],
            "pre_close_date": pre["d"], "post_close_date": post["d"],
            "horizon_close_date": horizon["d"] if horizon else None,
            "initial_return": finite(initial), "drift_13w": finite(drift),
            "is_terminal_instrument": code in terminal, "terminal_endpoint_used": terminal_used,
            "source_reference": row["source_reference"]
        })
    return events


def pead_metrics(events: pd.DataFrame, exclude_terminal=False) -> dict:
    z = events[events.drift_13w.notna() & events.initial_return.notna()].copy()
    if exclude_terminal:
        z = z[~z.is_terminal_instrument].copy()
    z["initial_rank"] = z.groupby("post_close_date").initial_return.rank(pct=True, method="average")
    per = []
    for dt, g in z.groupby("post_close_date", sort=True):
        ic = safe_spearman(g.initial_rank, g.drift_13w)
        if ic is not None:
            per.append({"post_close_date": dt, "events": len(g), "ic13w": ic})
    vals = [r["ic13w"] for r in per]
    dates = [r["post_close_date"] for r in per]
    halves = [set(dates[:len(dates)//2]), set(dates[len(dates)//2:])]
    return {
        "events": len(z), "instruments": int(z.kod.nunique()), "terminal_events": int(z.is_terminal_instrument.sum()),
        "evaluable_dates": len(per), "mean_ic13w": finite(np.mean(vals)) if vals else None,
        "median_ic13w": finite(np.median(vals)) if vals else None,
        "positive_ic_share": finite(np.mean(np.array(vals) > 0)) if vals else None,
        "pooled_spearman": safe_spearman(z.initial_rank, z.drift_13w),
        "chronological_halves": [{"half": i + 1, "dates": len(ds),
                                   "mean_ic13w": finite(np.mean([r["ic13w"] for r in per if r["post_close_date"] in ds])) if ds else None}
                                  for i, ds in enumerate(halves)],
        "per_date": per
    }


def classify_pead(primary: dict, terminal_sensitivity: dict) -> str:
    halves = primary["chronological_halves"]
    if primary["evaluable_dates"] < 10 or any(x["dates"] < 3 for x in halves):
        return "OTILLRÄCKLIG DATA"
    support = (primary["mean_ic13w"] > 0 and primary["median_ic13w"] > 0
               and all(x["mean_ic13w"] is not None and x["mean_ic13w"] > 0 for x in halves)
               and terminal_sensitivity["mean_ic13w"] is not None and terminal_sensitivity["mean_ic13w"] >= 0)
    if support:
        return "STÖD"
    return "SVAGT STÖD" if primary["mean_ic13w"] is not None and primary["mean_ic13w"] > 0 else "INGET STÖD"


def concentration_diagnostics(rows: pd.DataFrame, base, blend, targets) -> dict:
    counts = rows.kod.value_counts(); top = list(counts.index[:10])
    out = {"rows": len(rows), "tickers": int(rows.kod.nunique()),
           "top_ticker": top[0] if top else None,
           "top1_row_share": finite(counts.iloc[0] / len(rows)) if len(rows) else None,
           "top3_row_share": finite(counts.iloc[:3].sum() / len(rows)) if len(rows) else None,
           "top5_row_share": finite(counts.iloc[:5].sum() / len(rows)) if len(rows) else None,
           "top10_tickers": top}
    for n in (3, 5):
        keep = ~base.kod.isin(set(top[:n])); bk = base[keep]
        ck = blend[~blend.kod.isin(set(top[:n]))]
        tk = targets[~targets.kod.isin(set(top[:n]))]
        out[f"leave_top{n}_count_tickers"] = delta_metrics(bk, ck, tk)
    return out


def run_report(inputs: dict) -> dict:
    events = report_measurements(); edf = pd.DataFrame(events)
    pead = pead_metrics(edf); pead_no_terminal = pead_metrics(edf, exclude_terminal=True)
    pead_class = classify_pead(pead, pead_no_terminal)
    reaction = {
        "events": len(edf), "with_initial_return": int(edf.initial_return.notna().sum()),
        "mean_initial_return": finite(edf.initial_return.mean()), "median_initial_return": finite(edf.initial_return.median()),
        "by_event_type": {k: {"events": len(g), "mean_initial_return": finite(g.initial_return.mean()),
                               "median_initial_return": finite(g.initial_return.median())}
                          for k, g in edf.groupby("event_type")},
        "by_publication_year": {k: int(v) for k, v in edf.published_at.str[:4].value_counts().sort_index().items()}
    }

    h0 = load_h0(); terminal = set(json.loads((ROOT / "validated/terminal_events.json").read_text()))
    by_code = defaultdict(list)
    for row in events:
        if row["initial_return"] is not None:
            by_code[row["kod"]].append(row)
    matched = []
    for row in h0.itertuples(index=False):
        decision = datetime.combine(date.fromisoformat(row.panel_date), time(17, 30), tzinfo=STOCKHOLM).astimezone(UTC)
        lower = decision - timedelta(days=28)
        candidates = [e for e in by_code[row.kod]
                      if lower < datetime.fromisoformat(e["published_at"].replace("Z", "+00:00")) <= decision
                      and close_timestamp(e["post_close_date"]) <= decision]
        if not candidates:
            continue
        e = max(candidates, key=lambda x: x["published_at"])
        matched.append({"kod": row.kod, "panel_date": row.panel_date, "h0_score": row.score,
                        "event_id": e["event_id"], "event_published_at": e["published_at"],
                        "initial_return": e["initial_return"], "is_terminal_instrument": row.kod in terminal})
    z = pd.DataFrame(matched)
    z["h0_rank"] = z.groupby("panel_date").h0_score.rank(pct=True, method="average")
    z["event_rank"] = z.groupby("panel_date").initial_return.rank(pct=True, method="average")
    z["blend_score"] = .5 * z.h0_rank + .5 * z.event_rank
    base = z[["kod", "panel_date", "h0_score"]].rename(columns={"h0_score": "score"})
    blend = z[["kod", "panel_date", "blend_score"]].rename(columns={"blend_score": "score"})
    targets = targets_for(z)
    confirmation = delta_metrics(base, blend, targets)
    nonterminal = ~z.kod.isin(terminal)
    terminal_sensitivity = delta_metrics(base[nonterminal], blend[nonterminal], targets[~targets.kod.isin(terminal)])
    confirmation_class = classify_delta(confirmation)
    confirmation["terminal_sensitivity"] = terminal_sensitivity
    confirmation["classification"] = confirmation_class
    confirmation["coverage"] = {
        "matched_decision_rows": len(z), "target_evaluation_rows": len(targets),
        "instruments": int(z.kod.nunique()), "terminal_instruments": int(z[z.is_terminal_instrument].kod.nunique()),
        "panel_dates": int(z.panel_date.nunique()),
        "per_panel": {str(k): int(v) for k, v in z.panel_date.value_counts().sort_index().items()}
    }
    confirmation["ticker_concentration"] = concentration_diagnostics(z, base, blend, targets)
    if confirmation_class == "STÖD":
        overall = "STÖD"
    elif confirmation_class == "SVAGT STÖD" or pead_class == "STÖD":
        overall = "SVAGT STÖD"
    elif confirmation_class == "OTILLRÄCKLIG DATA":
        overall = "OTILLRÄCKLIG DATA"
    else:
        overall = "INGET STÖD"
    result = {"version": "REPORT_PEAD_LOCKED_V1", "classification": overall,
              "report_reaction": reaction,
              "pead": {"classification": pead_class, "primary": pead, "without_terminal_instruments": pead_no_terminal},
              "report_confirmation_conditional_h0": confirmation,
              "attention_gap": {"classification": "OTILLRÄCKLIG DATA", "reason": "preregistered data block: event-volume QA absent"}}
    REPORT_OUT.mkdir(parents=True)
    dump(REPORT_OUT / "event_measurements.json", events)
    dump(REPORT_OUT / "conditional_scores.json", matched)
    dump(REPORT_OUT / "results.json", result)
    dump(REPORT_OUT / "run_provenance.json", {"version": result["version"], "input_hashes": inputs,
         "target_used_only_after_event_and_score_construction": True, "H0_changed": False,
         "parameters_searched": 0, "report_insider_combined": False})
    dump(REPORT_OUT / "manifest.json", manifest(REPORT_OUT))
    verify_result(REPORT_OUT)
    return result


def build_insider_scores(rows: list[dict], h0: pd.DataFrame, clean_only=False) -> pd.DataFrame:
    eligible = [r for r in rows if r["transaction_character"] in {"Förvärv", "Avyttring"}]
    if clean_only:
        keys = ["instrument_id", "transaction_date", "transaction_character", "quantity", "price", "currency"]
        contaminated = set()
        for r in eligible:
            key = tuple(r.get(k) for k in keys)
            if r["source_status"] != "Aktuell" or r["correction_flag"]:
                contaminated.add(key)
        eligible = [r for r in eligible if tuple(r.get(k) for k in keys) not in contaminated]
    by_code = defaultdict(list)
    for r in eligible:
        by_code[r["instrument_id"]].append(r)
    out = []
    for row in h0.itertuples(index=False):
        decision = datetime.combine(date.fromisoformat(row.panel_date), time(17, 30), tzinfo=STOCKHOLM).astimezone(UTC)
        lower = decision - timedelta(days=28)
        events = [r for r in by_code[row.kod] if lower < datetime.fromisoformat(r["market_known_time"]) <= decision]
        if not events:
            continue
        buys = any(r["transaction_character"] == "Förvärv" for r in events)
        sells = any(r["transaction_character"] == "Avyttring" for r in events)
        out.append({"kod": row.kod, "panel_date": row.panel_date, "h0_score": row.score,
                    "insider_signal": int(buys) - int(sells), "has_purchase": buys, "has_sale": sells,
                    "publications": len(events), "clean_group_sensitivity": clean_only})
    return pd.DataFrame(out)


def evaluate_insider(z: pd.DataFrame, terminal: set[str]) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    z = z.copy()
    z["h0_rank"] = z.groupby("panel_date").h0_score.rank(pct=True, method="average")
    z["feature_rank"] = z.groupby("panel_date").insider_signal.rank(pct=True, method="average")
    z["blend_score"] = .5 * z.h0_rank + .5 * z.feature_rank
    base = z[["kod", "panel_date", "h0_score"]].rename(columns={"h0_score": "score"})
    blend = z[["kod", "panel_date", "blend_score"]].rename(columns={"blend_score": "score"})
    targets = targets_for(z)
    result = delta_metrics(base, blend, targets)
    keep = ~z.kod.isin(terminal)
    sensitivity = delta_metrics(base[keep], blend[keep], targets[~targets.kod.isin(terminal)])
    terminal_delta = sensitivity["delta"]["mean_ic52"]
    result["terminal_sensitivity"] = sensitivity
    result["classification"] = classify_delta(result, require_terminal=True, terminal_delta=terminal_delta)
    result["ticker_concentration"] = concentration_diagnostics(z, base, blend, targets)
    result["strata"] = {}
    merged = z.merge(targets, on=["kod", "panel_date"], how="inner")
    for name, mask in {"purchase_present": merged.has_purchase, "sale_present": merged.has_sale,
                       "purchase_only": merged.has_purchase & ~merged.has_sale,
                       "sale_only": merged.has_sale & ~merged.has_purchase,
                       "both": merged.has_sale & merged.has_purchase}.items():
        g = merged[mask]
        result["strata"][name] = {"rows": len(g), "instruments": int(g.kod.nunique()),
                                   "mean_target_fwd52w": finite(g.y.mean()) if len(g) else None,
                                   "median_target_fwd52w": finite(g.y.median()) if len(g) else None}
    return result, z, base, blend


def run_insider(inputs: dict) -> dict:
    rows = [json.loads(x) for x in (ROOT / "trackj/validated_fi_insider_v4/validated_fi_insider.jsonl").read_text().splitlines()]
    h0 = load_h0(); terminal = set(json.loads((ROOT / "validated/terminal_events.json").read_text()))
    primary_z = build_insider_scores(rows, h0, clean_only=False)
    primary, scored, _, _ = evaluate_insider(primary_z, terminal)
    clean_z = build_insider_scores(rows, h0, clean_only=True)
    clean, _, _, _ = evaluate_insider(clean_z, terminal)
    fi_summary = json.loads((ROOT / "trackj/validated_fi_insider_v4/qa_extended.json").read_text())
    target_rows = targets_for(primary_z)
    primary["coverage"] = {
        "foundation": fi_summary["coverage"],
        "h0_rows_total": len(h0), "h0_rows_with_insider_information": len(primary_z),
        "h0_information_share": finite(len(primary_z) / len(h0)),
        "target_evaluation_rows": len(target_rows), "panel_dates": int(primary_z.panel_date.nunique()),
        "instruments": int(primary_z.kod.nunique()),
        "terminal_instruments_with_h0_information": sorted(set(primary_z.kod) & terminal),
        "terminal_information_count": len(set(primary_z.kod) & terminal),
        "missing_terminal_foundation": ["AGRO", "AM1S", "ENDO", "MIC-SDB", "SMF"],
        "per_panel_information_rows": {str(k): int(v) for k, v in primary_z.panel_date.value_counts().sort_index().items()}
    }
    result = {"version": "INSIDER_CONDITIONAL_H0_LOCKED_V1", "classification": primary["classification"],
              "primary_all_publications_status_ignored": primary,
              "diagnostic_clean_groups_only": clean,
              "correction_governance": "primary never filters on retrieval-time current status; clean-groups result is mandatory diagnostic only"}
    INSIDER_OUT.mkdir(parents=True)
    dump(INSIDER_OUT / "information_scores.json", scored.to_dict("records"))
    dump(INSIDER_OUT / "results.json", result)
    dump(INSIDER_OUT / "run_provenance.json", {"version": result["version"], "input_hashes": inputs,
         "report_result_manifest_sha256": sha(REPORT_OUT / "manifest.json"),
         "target_used_only_after_information_score_construction": True, "current_status_used_for_primary": False,
         "H0_changed": False, "parameters_searched": 0, "report_insider_combined": False})
    dump(INSIDER_OUT / "manifest.json", manifest(INSIDER_OUT))
    verify_result(INSIDER_OUT)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("report", "insider", "verify"), required=True)
    args = ap.parse_args()
    if args.stage == "verify":
        verify_result(REPORT_OUT); verify_result(INSIDER_OUT)
        print(json.dumps({"status": "PASS", "report_manifest": sha(REPORT_OUT / "manifest.json"),
                          "insider_manifest": sha(INSIDER_OUT / "manifest.json")}, indent=2))
        return
    inputs = verify(args.stage)
    result = run_report(inputs) if args.stage == "report" else run_insider(inputs)
    print(json.dumps({"stage": args.stage, "classification": result["classification"],
                      "manifest_sha256": sha((REPORT_OUT if args.stage == "report" else INSIDER_OUT) / "manifest.json")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
