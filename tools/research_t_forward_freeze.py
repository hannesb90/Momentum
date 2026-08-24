"""
RESEARCH T: Forward Challenger Freeze & Journal Setup
First Untouched Forward Decision Panel Date: 2026-09-04

Immutable freeze of 3 models for real forward validation:
1. T0-A: CONTROL H0 (Historical Champion - Forward Unconfirmed)
2. T0-B: INVESTABILITY CHALLENGER (ADV20 >= 1.0 MSEK - Discovery Challenger - Forward Unconfirmed)
3. T0-C: SMA200 ENTRY CHALLENGER (Close >= SMA200 SKIP - Weak-Inconclusive Historical Discovery - Forward Unconfirmed)

Generates SHA256 manifests and initializes append-only forward journals in /home/hannesb/momentum_v2/journals/
"""
from __future__ import annotations
import json, math, hashlib, os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

V2 = Path("/home/hannesb/momentum_v2")
JOURNALS_DIR = V2 / "journals"
MANIFEST_FILE = V2 / "research_k/research_t_freeze_manifest.json"

START_DATE = "2021-07-16"
HISTORICAL_END_DATE = "2026-07-10"
FIRST_FORWARD_DATE = "2026-09-04"
PHASE_ANCHOR_H0 = "2024-01-26"
COST_ONEWAY = 0.002

MODEL_SPECS = {
    "T0_A_CONTROL_H0": {
        "model_id": "T0_A_CONTROL_H0",
        "label": "HISTORICAL CHAMPION — FORWARD UNCONFIRMED",
        "description": "Frozen H0 50/50 12m+18m momentum ranking, Top 30 equal weight, 8w rebalance, V4 execution",
        "selector": "0.5 * rank(mom_12m) + 0.5 * rank(mom_18m)",
        "eligibility_gate": "None (Unconstrained)",
        "entry_rule": "Immediate Top 30 allocation (1/30th per slot)",
        "exit_rule": "None (8w scheduled rebalance)",
        "top_n": 30,
        "weighting": "Equal Weight (1/30th per slot)",
        "rebalance_schedule": "8-week phase anchored on 2024-01-26",
        "execution_standard": "V4 Post-Decision Execution (T+1 Close)",
        "one_way_cost_bp": 20.0,
        "benchmark": "XACT-SVERIGE.ST (Broad Sweden TR ETF)"
    },
    "T0_B_INVESTABILITY": {
        "model_id": "T0_B_INVESTABILITY",
        "label": "HISTORICAL DISCOVERY / INVESTABILITY CHALLENGER — FORWARD UNCONFIRMED",
        "description": "H0 selector with pre-ranking eligibility gate: Trailing 20-day Average Daily Volume (SEK Turnover) >= 1.0 MSEK",
        "selector": "0.5 * rank(mom_12m) + 0.5 * rank(mom_18m) among eligible stocks",
        "eligibility_gate": "ADV20d >= 1,000,000 SEK (Close * Volume 20-day rolling mean)",
        "entry_rule": "Immediate Top 30 eligible allocation (1/30th per slot)",
        "exit_rule": "None (8w scheduled rebalance)",
        "top_n": 30,
        "weighting": "Equal Weight (1/30th per slot)",
        "rebalance_schedule": "8-week phase anchored on 2024-01-26",
        "execution_standard": "V4 Post-Decision Execution (T+1 Close)",
        "one_way_cost_bp": 20.0,
        "benchmark": "XACT-SVERIGE.ST (Broad Sweden TR ETF)"
    },
    "T0_C_SMA200_SKIP": {
        "model_id": "T0_C_SMA200_SKIP",
        "label": "WEAK-INCONCLUSIVE HISTORICAL DISCOVERY — FORWARD UNCONFIRMED",
        "description": "H0 selector Top 30, SKIP entry if Close(T) < SMA200(T). Unbought weight held in Cash (0% return)",
        "selector": "0.5 * rank(mom_12m) + 0.5 * rank(mom_18m)",
        "eligibility_gate": "None at ranking stage",
        "entry_rule": "SKIP entry if Close(T) < SMA200(T). Slot held in Cash. No rank-31 refill. No DELAY.",
        "exit_rule": "None (8w scheduled rebalance)",
        "top_n": 30,
        "weighting": "Equal Weight (1/30th per slot when entry passes, else 0% stock + 1/30th cash)",
        "rebalance_schedule": "8-week phase anchored on 2024-01-26",
        "execution_standard": "V4 Post-Decision Execution (T+1 Close)",
        "one_way_cost_bp": 20.0,
        "benchmark": "XACT-SVERIGE.ST (Broad Sweden TR ETF)"
    }
}

CHECKPOINTS = [
    {"checkpoint_id": "CP1_OPERATIONAL", "periods": 3, "approx_months": 6, "purpose": "Technical & operational pipeline QA"},
    {"checkpoint_id": "CP2_EARLY_DIAGNOSTIC", "periods": 6, "approx_months": 12, "purpose": "Early diagnostic forward check"},
    {"checkpoint_id": "CP3_FIRST_COMPARISON", "periods": 12, "approx_months": 24, "purpose": "First meaningful forward comparison"},
    {"checkpoint_id": "CP4_STRONG_ASSESSMENT", "periods": 18, "approx_months": 36, "purpose": "Strong robust forward assessment"}
]

def load_data():
    core = json.loads((V2 / "panels/core_panel.json").read_text())
    target = json.loads((V2 / "panels/target_table.json").read_text())
    prices = json.loads((V2 / "validated/prices/prices_validated.json").read_text())
    terminal = json.loads((V2 / "validated/terminal_events.json").read_text())
    
    tm = {(k, r["panel_date"]): r for k, rs in target.items() for r in rs}
    
    df_core = []
    for r in core:
        t = tm.get((r["kod"], r["panel_date"]))
        y52 = t.get("target_fwd52w") if t else None
        df_core.append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "y52": y52
        })
    df_core = pd.DataFrame(df_core)
    return df_core, prices, terminal

def compute_adv20(prices):
    adv_map = {}
    for kod, rs in prices.items():
        ds = [r["d"] for r in rs]
        c = np.array([r.get("close", r["adj"]) for r in rs], dtype=float)
        v = np.array([r.get("v", 0.0) for r in rs], dtype=float)
        turnover = c * v
        if len(turnover) >= 20:
            roll = pd.Series(turnover).rolling(20).mean().values
            for d, val in zip(ds, roll):
                adv_map[(kod, d)] = float(val) if math.isfinite(val) else 0.0
        else:
            for d in ds:
                adv_map[(kod, d)] = 0.0
    return adv_map

def derive_h0_scores(core_df, prices):
    series = {
        k: (np.array([np.datetime64(r["d"]) for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }

    def momentum(k, dt, weeks):
        if k not in series: return None
        ds, values = series[k]
        now = np.datetime64(dt)
        target_dt = now - np.timedelta64(7 * weeks, "D")
        i = np.searchsorted(ds, now, side="right") - 1
        j = np.searchsorted(ds, target_dt, side="right") - 1
        if i < 0 or j < 0 or int((target_dt - ds[j]) / np.timedelta64(1, "D")) > 10:
            return None
        return float(values[i] / values[j] - 1)

    by_date = defaultdict(list)
    for _, r in core_df.iterrows():
        if r["panel_date"] < START_DATE or r["panel_date"] > HISTORICAL_END_DATE:
            continue
        m12 = momentum(r["kod"], r["panel_date"], 52)
        m18 = momentum(r["kod"], r["panel_date"], 78)
        by_date[r["panel_date"]].append({
            "kod": r["kod"], "panel_date": r["panel_date"], "price_date": r["price_date"],
            "mom_12m": m12, "mom_18m": m18, "y52": r["y52"]
        })

    rankings = {}
    for dt, rows in sorted(by_date.items()):
        for col in ("mom_12m", "mom_18m"):
            valid = sorted((r[col], r["kod"]) for r in rows if r[col] is not None)
            grouped = defaultdict(list)
            for val, kod in valid: grouped[val].append(kod)
            ranks = {}
            pos = 1
            for val in sorted(grouped):
                ks = grouped[val]
                avg = (pos + pos + len(ks) - 1) / 2 / len(valid)
                for kod in ks: ranks[kod] = avg
                pos += len(ks)
            for r in rows: r[col + "_rank"] = ranks.get(r["kod"])
        raw = [0.5 * (r["mom_12m_rank"] + r["mom_18m_rank"]) if r["mom_12m_rank"] is not None and r["mom_18m_rank"] is not None else None for r in rows]
        med = float(np.median([x for x in raw if x is not None])) if any(x is not None for x in raw) else 0.5
        scored = []
        for r, value in zip(rows, raw):
            scored.append({**r, "score": med if value is None else value})
        scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        rankings[dt] = scored
    return rankings

def generate_model_manifests():
    manifests = {}
    for m_id, spec in MODEL_SPECS.items():
        raw_json = json.dumps(spec, sort_keys=True)
        sha256_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        manifests[m_id] = {
            "spec": spec,
            "sha256": sha256_hash
        }
    return manifests

def setup_journals(rankings, prices, adv_map):
    JOURNALS_DIR.mkdir(parents=True, exist_ok=True)
    
    price_series = {
        k: (np.array([r["d"] for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }

    journal_files = {
        "T0_A_CONTROL_H0": JOURNALS_DIR / "H0_CONTROL_FORWARD.jsonl",
        "T0_B_INVESTABILITY": JOURNALS_DIR / "ADV20_1M_FORWARD.jsonl",
        "T0_C_SMA200_SKIP": JOURNALS_DIR / "SMA200_SKIP_FORWARD.jsonl"
    }

    eval_dates = sorted(rankings.keys())
    
    for m_id, path in journal_files.items():
        entries = []
        for dt in eval_dates:
            universe = rankings[dt]
            
            if m_id == "T0_A_CONTROL_H0":
                selected = [r["kod"] for r in universe[:30]]
                blocked = []
                cash_weight = 0.0
            elif m_id == "T0_B_INVESTABILITY":
                eligible = [r for r in universe if adv_map.get((r["kod"], r.get("price_date", dt)), 0.0) >= 1000000.0]
                selected = [r["kod"] for r in eligible[:30]]
                blocked = [r["kod"] for r in universe[:30] if r["kod"] not in selected]
                cash_weight = 0.0
            elif m_id == "T0_C_SMA200_SKIP":
                top30_kods = [r["kod"] for r in universe[:30]]
                selected = []
                blocked = []
                for k in top30_kods:
                    if k in price_series:
                        ds, adj = price_series[k]
                        idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                        if idx is not None and idx >= 200:
                            sma200 = float(np.mean(adj[idx-200:idx]))
                            if adj[idx] >= sma200:
                                selected.append(k)
                            else:
                                blocked.append(k)
                        else:
                            selected.append(k)
                    else:
                        selected.append(k)
                cash_weight = (30 - len(selected)) / 30.0

            ranking_hash = hashlib.sha256(json.dumps([r["kod"] for r in universe]).encode("utf-8")).hexdigest()
            
            rec = {
                "panel_date": dt,
                "model_id": m_id,
                "data_as_of": dt,
                "eligible_universe_count": len(universe),
                "selected_top30": selected,
                "blocked_names": blocked,
                "cash_weight": cash_weight,
                "target_weights": {k: 1/30.0 for k in selected},
                "intended_execution_standard": "V4 Post-Decision Execution (T+1 Close)",
                "one_way_cost_bp": 20.0,
                "ranking_hash": ranking_hash
            }
            entries.append(rec)
            
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, sort_keys=True) + "\n")

    return journal_files

def main():
    print("=" * 80)
    print("RESEARCH T: FORWARD CHALLENGER FREEZE & JOURNAL SETUP")
    print(f"First Untouched Forward Decision Date: {FIRST_FORWARD_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    adv_map = compute_adv20(prices)
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("\n1. Generating SHA256 Freeze Manifests...")
    manifests = generate_model_manifests()
    
    freeze_payload = {
        "freeze_timestamp": "2026-08-10T09:50:00+02:00",
        "first_untouched_forward_panel_date": FIRST_FORWARD_DATE,
        "phase_anchor_date": PHASE_ANCHOR_H0,
        "models": manifests,
        "checkpoints": CHECKPOINTS,
        "governance_audit": {
            "T0_A_CONTROL_H0": "HISTORICAL CHAMPION — FORWARD UNCONFIRMED",
            "T0_B_INVESTABILITY": "DISCOVERY CHALLENGER — FORWARD ONLY (ADV20 >= 1.0 MSEK pre-ranking gate)",
            "T0_C_SMA200_SKIP": "WEAK-INCONCLUSIVE HISTORICAL DISCOVERY — FORWARD ONLY (Close >= SMA200 SKIP gate)"
        }
    }
    
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(freeze_payload, indent=2, sort_keys=True), encoding="utf-8")
    
    print("2. Initializing Append-Only Forward Journals...")
    journal_files = setup_journals(h0_rankings, prices, adv_map)
    
    print("\n" + "=" * 80)
    print("RESEARCH T IMMUTABLE FREEZE COMPLETE")
    print("=" * 80)
    print(f"Manifest File: {MANIFEST_FILE}")
    for m_id, path in journal_files.items():
        print(f" - {m_id:22s} -> {path} (SHA256: {manifests[m_id]['sha256'][:16]}...)")
    print("=" * 80)

if __name__ == "__main__":
    main()
