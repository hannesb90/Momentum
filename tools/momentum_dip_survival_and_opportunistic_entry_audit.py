"""Frozen information/mechanism phase for MOMENTUM_DIP_SURVIVAL_AND_OPPORTUNISTIC_ENTRY_AUDIT.

This script has no portfolio intervention: it observes a first daily DIP_10 event
inside an ordinary H0 interval and measures subsequent H0 rank survival.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/momentum_dip_survival_and_opportunistic_entry_audit"
PLAN = OUT / "PREREGISTRATION.md"
FREEZE = OUT / "PLAN_FREEZE.json"
SEED, DRAWS = 20260821, 2000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_race():
    spec = importlib.util.spec_from_file_location("dip_race", V2 / "tools/rep_model_race_h0v3_kor.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def close_on_or_before(ds, vals, day):
    i = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    return (str(ds[i]), float(vals[i])) if i >= 0 else (None, None)


def first_on_or_after(days, target):
    i = int(np.searchsorted(days, np.datetime64(target), side="left"))
    return str(days[i]) if i < len(days) else None


def annualized_vol(ds, vals, day):
    i = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    if i < 60:
        return None
    r = np.diff(vals[i - 60:i + 1]) / vals[i - 60:i]
    return float(np.std(r, ddof=1) * math.sqrt(252)) if len(r) >= 30 else None


def sma200(ds, vals, day):
    i = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
    if i < 200:
        return None, None
    p, sma = float(vals[i]), float(np.mean(vals[i - 200:i]))
    return bool(p >= sma), p / sma - 1.0


def bootstrap_cluster(events, key, is_proportion=False):
    """Whole ordinary intervals are sampled, preserving event clustering."""
    by = defaultdict(list)
    for e in events:
        if e.get(key) is not None:
            by[e["cluster_id"]].append(float(e[key]))
    clusters = list(by)
    vals = [x for c in clusters for x in by[c]]
    if not vals or not clusters:
        return {"n_events": 0, "n_clusters": 0, "mean": None, "ci95": [None, None], "mde": None}
    rng = np.random.default_rng(SEED)
    boot = []
    for _ in range(DRAWS):
        sampled = rng.choice(clusters, len(clusters), replace=True)
        z = [v for c in sampled for v in by[c]]
        boot.append(float(np.mean(z)))
    sd_cluster = np.std([np.mean(by[c]) for c in clusters], ddof=1) if len(clusters) > 1 else np.nan
    # two-sided alpha=.05, 80% normal-approximation power: (1.96 + .84)*SE(mean)
    mde = float((1.959964 + 0.841621) * sd_cluster / math.sqrt(len(clusters))) if np.isfinite(sd_cluster) else None
    return {"n_events": len(vals), "n_clusters": len(clusters), "mean": float(np.mean(vals)),
            "ci95": [float(x) for x in np.percentile(boot, [2.5, 97.5])], "mde": mde,
            "estimand_type": "proportion" if is_proportion else "mean_return"}


def daily_ranker(R, W):
    """Same H0 12m/18m/PIT/tie semantics as the delayed-detection reconstruction."""
    serie, isin = W["serie"], R.isin_map(W["cfg"]["isin"])
    cache = {}

    def handlas(k, d):
        ds, _ = serie[k]
        i = int(np.searchsorted(ds, d, side="right")) - 1
        return i >= 0 and int((d - ds[i]) / np.timedelta64(1, "D")) <= 30

    def mom(k, d, weeks):
        ds, vals = serie[k]
        target = d - np.timedelta64(7 * weeks, "D")
        i = int(np.searchsorted(ds, d, side="right")) - 1
        j = int(np.searchsorted(ds, target, side="right")) - 1
        if i < 0 or j < 0 or int((target - ds[j]) / np.timedelta64(1, "D")) > 10:
            return None
        return float(vals[i] / vals[j] - 1.0)

    def rank(day):
        d = np.datetime64(day)
        ds = str(d)
        rows = []
        for k in serie:
            ck = (k, ds[:7])
            if ck not in cache:
                cache[ck] = bool(R.PITMEDLEM(k, isin.get(k), ds)[0])
            if handlas(k, d) and cache[ck]:
                rows.append({"kod": k, "m12": mom(k, d, 52), "m18": mom(k, d, 78)})
        for col in ("m12", "m18"):
            valid = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            groups = defaultdict(list)
            for val, k in valid:
                groups[val].append(k)
            ranks, pos = {}, 1
            for val in sorted(groups):
                ks = groups[val]
                pct = (pos + pos + len(ks) - 1) / 2 / max(1, len(valid))
                ranks.update({k: pct for k in ks})
                pos += len(ks)
            for r in rows:
                r[col + "_rank"] = ranks.get(r["kod"])
        raw = [0.5 * (r["m12_rank"] + r["m18_rank"])
               if r["m12_rank"] is not None and r["m18_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raw if x is not None])) if any(x is not None for x in raw) else 0.5
        rows = [{**r, "score": med if x is None else x} for r, x in zip(rows, raw)]
        rows.sort(key=lambda r: (r["score"], r["kod"]), reverse=True)
        return rows
    return rank


def run_window(R, wn):
    print(f"{wn}: loading frozen PIT window", flush=True)
    W = R.load_window(wn)
    P, serie = W["paneler"], W["serie"]
    all_days = np.array(sorted({d for ds, _ in serie.values() for d in ds}))
    rank = daily_ranker(R, W)
    # Exact panel-date reproduction gate, including complete sequence and Top-30.
    repro = {"n_panels": len(P), "universe_exact": 0, "order_exact": 0, "top30_exact": 0, "examples": []}
    for pd in P:
        mine, actual = rank(pd), W["rankings"][pd]
        a, b = [r["kod"] for r in mine], [r["kod"] for r in actual]
        repro["universe_exact"] += int(set(a) == set(b))
        repro["order_exact"] += int(a == b)
        repro["top30_exact"] += int(a[:30] == b[:30])
        if a != b and len(repro["examples"]) < 3:
            repro["examples"].append({"panel": pd, "ours": a[:5], "actual": b[:5]})
    for k in ("universe_exact", "order_exact", "top30_exact"):
        repro[k] = repro[k] / max(1, repro["n_panels"])
    repro["PASS"] = repro["universe_exact"] == repro["order_exact"] == repro["top30_exact"] == 1.0
    print(f"{wn}: shadow reproduction {'PASS' if repro['PASS'] else 'FAIL'}", flush=True)
    if not repro["PASS"]:
        return W, repro, []

    bench = json.loads((V2 / "validated/benchmark_gated/benchmark_xact_sverige_gated.json").read_text()).get("XACT-SVERIGE", [])
    bds = np.array([np.datetime64(x["d"]) for x in bench])
    bvals = np.array([float(x["adj"]) for x in bench])
    events = []
    # Two 4W panels comprise each ordinary decision interval.
    for ix in range(0, len(P) - 2, 2):
        if ix % 10 == 0:
            print(f"{wn}: scanning ordinary interval {ix // 2 + 1}", flush=True)
        ref, next_ord = P[ix], P[ix + 2]
        pre_rows = W["rankings"][ref]
        pre_rank = {r["kod"]: j for j, r in enumerate(pre_rows, 1)}
        top30 = set(k for k, v in pre_rank.items() if v <= 30)
        start = np.datetime64(ref)
        end = np.datetime64(next_ord)
        cluster = f"{wn}:{ref}"
        for k in top30:
            ds, vals = serie[k]
            rd, rp = close_on_or_before(ds, vals, ref)
            if rp is None or rp <= 0:
                continue
            lo = int(np.searchsorted(ds, start, side="right"))
            hi = int(np.searchsorted(ds, end, side="left"))
            crossed = None
            for j in range(lo, hi):
                if vals[j] / rp - 1.0 <= -0.10:
                    crossed = j
                    break
            if crossed is None:
                continue
            t0, p0 = str(ds[crossed]), float(vals[crossed])
            now = rank(t0)
            now_map = {r["kod"]: (j, r) for j, r in enumerate(now, 1)}
            if k not in now_map:  # event-time PIT eligibility is mandatory
                continue
            erank, row = now_map[k]
            event = {"window": wn, "cluster_id": cluster, "ticker": k, "event_date": t0,
                     "reference_rebalance_date": ref, "next_ordinary_rebalance_date": next_ord,
                     "reference_price_date": rd, "reference_price": rp, "p0": p0,
                     "return_since_reference": p0 / rp - 1.0, "pre_dip_rank": pre_rank[k],
                     "event_rank": erank, "rank_change": erank - pre_rank[k],
                     "rank_group": "RANK_1_10" if pre_rank[k] <= 10 else "RANK_11_20" if pre_rank[k] <= 20 else "RANK_21_30",
                     "rank_deterioration_group": "STABLE_RANK" if erank - pre_rank[k] <= 5 else "DETERIORATING_RANK",
                     "m12": row["m12"], "m18": row["m18"], "h0_score": row["score"],
                     "vol60_ann": annualized_vol(ds, vals, t0), "event_information_class": "EVENT_INFORMATION_UNKNOWN",
                     "event_cleanliness_status": "BLOCKED_DATA_REQUIRES_PIT_EVENT_COVERAGE_GATE"}
            ok_sma, dist_sma = sma200(ds, vals, t0)
            event["sma200_ok"], event["distance_to_sma200"] = ok_sma, dist_sma
            # Continuous market diagnostic only.
            _, br = close_on_or_before(bds, bvals, ref); _, bp = close_on_or_before(bds, bvals, t0)
            event["market_drop"] = bp / br - 1.0 if br and bp else None
            event["relative_drop"] = event["return_since_reference"] - event["market_drop"] if event["market_drop"] is not None else None
            for label, target in (("1w", np.datetime64(t0) + np.timedelta64(7, "D")),
                                  ("2w", np.datetime64(t0) + np.timedelta64(14, "D")),
                                  ("4w", np.datetime64(t0) + np.timedelta64(28, "D")),
                                  ("next_8w", np.datetime64(next_ord)),
                                  ("12w", np.datetime64(t0) + np.timedelta64(84, "D"))):
                hd = first_on_or_after(all_days, target)
                if hd is None:
                    event[f"rank_{label}"] = None
                    event[f"return_{label}"] = None
                    continue
                later = rank(hd)
                later_map = {r["kod"]: j for j, r in enumerate(later, 1)}
                event[f"rank_{label}"] = later_map.get(k)
                _, px = close_on_or_before(ds, vals, hd)
                event[f"return_{label}"] = px / p0 - 1.0 if px and p0 else None
            event["momentum_survival_next_8w"] = int(event.get("rank_next_8w") is not None and event["rank_next_8w"] <= 30)
            event["waiting_days_to_next_ordinary"] = int((np.datetime64(next_ord) - np.datetime64(t0)) / np.timedelta64(1, "D"))
            events.append(event)
    return W, repro, events


def main():
    freeze = json.loads(FREEZE.read_text())
    if sha(PLAN) != freeze["sha256"]:
        raise SystemExit("STOP: preregistration hash mismatch")
    R = load_race()
    result = {"study_id": "MOMENTUM_DIP_SURVIVAL_AND_OPPORTUNISTIC_ENTRY_AUDIT",
              "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "preregistration_sha256": sha(PLAN), "phase": "INFORMATION_MECHANISM_ONLY",
              "no_entry_policy_executed": True, "event_cleanliness_gate": "PENDING_SOURCE_AUDIT", "windows": {}}
    all_events = []
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        _, repro, events = run_window(R, wn)
        result["windows"][wn] = {"shadow_ranking_reproduction": repro, "n_events": len(events)}
        if repro["PASS"]:
            result["windows"][wn]["primary_forward_return_next_8w"] = bootstrap_cluster(events, "return_next_8w")
            result["windows"][wn]["momentum_survival_next_8w"] = bootstrap_cluster(events, "momentum_survival_next_8w", True)
        all_events.extend(events)
        print(f"{wn}: {len(events)} DIP_10 events", flush=True)
    fields = sorted({k for e in all_events for k in e})
    with open(OUT / "dip_event_ledger.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(all_events)
    result["overall_reproduction_pass"] = all(v["shadow_ranking_reproduction"]["PASS"] for v in result["windows"].values())
    result["event_cleanliness_gate"] = "BLOCKED_PENDING_PIT_EVENT_SOURCE_AUDIT"
    result["verdict"] = "NO_IDENTIFIABLE_DIP_MECHANISM" if not result["overall_reproduction_pass"] else "MECHANISM_RESULTS_PENDING_EVENT_CLEANLINESS_AND_FULL_REPORT"
    (OUT / "RESULT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
