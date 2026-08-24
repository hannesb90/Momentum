"""
RESEARCH W: Forward Freeze & Live Validation Protocol
First Untouched Forward Decision Panel Date: 2026-09-04

Immutable freeze of 3 models for live shadow validation:
1. CONTROL C: H0 + SMA200 SKIP Equal Weight (Forward Control)
2. V-A CHALLENGER: H0 + SMA200 SKIP + Inverse Vol Weighting (Return-Leaning Challenger)
3. V-B CHALLENGER: H0 + SMA200 SKIP + Inverse Vol Weighting + Target Vol 15% (Capital-Preservation Challenger)

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
MANIFEST_FILE = V2 / "research_k/research_w_freeze_manifest.json"

START_DATE = "2021-07-16"
HISTORICAL_END_DATE = "2026-07-10"
FIRST_FORWARD_DATE = "2026-09-04"
PHASE_ANCHOR_H0 = "2024-01-26"
COST_ONEWAY = 0.002

MODEL_SPECS = {
    "CONTROL_C_SMA200": {
        "model_id": "CONTROL_C_SMA200",
        "label": "FROZEN FOR FORWARD — CONTROL",
        "status": "FORWARD CONTROL",
        "description": "Frozen H0 Top 30, SKIP entry if Close(T) < SMA200(T). Unbought weight held in Cash. Equal weight 1/30th per slot.",
        "selector": "0.5 * rank(mom_12m) + 0.5 * rank(mom_18m)",
        "eligibility_gate": "None at ranking stage",
        "entry_rule": "SKIP entry if Close(T) < SMA200(T). Slot held in Cash. No rank-31 refill. No DELAY.",
        "exit_rule": "None (8w scheduled rebalance)",
        "top_n": 30,
        "weighting": "Equal Weight (1/30th per slot when entry passes, else 0% stock + 1/30th cash)",
        "target_vol_rule": "None (100% active allocation of passed slots)",
        "rebalance_schedule": "8-week phase anchored on 2024-01-26",
        "execution_standard": "V4 Post-Decision Execution (T+1 Close)",
        "one_way_cost_bp": 20.0,
        "benchmark": "XACT-SVERIGE.ST (Broad Sweden TR ETF)",
        "historical_cagr": 0.11622172155678867,
        "historical_vol": 0.19571489008573634,
        "historical_max_dd": -0.2874748900330324,
        "historical_sharpe": 0.245615728117383
    },
    "VA_RETURN_CHALLENGER": {
        "model_id": "VA_RETURN_CHALLENGER",
        "label": "FROZEN FOR FORWARD — V-A CHALLENGER",
        "status": "VALID ROBUST HISTORICAL DISCOVERY — FORWARD CHALLENGER",
        "description": "H0 Top 30, SMA200 SKIP entry, weighted by Inverse Volatility (60d trailing realized vol, 1.0% <= w_i <= 6.0%).",
        "selector": "0.5 * rank(mom_12m) + 0.5 * rank(mom_18m)",
        "eligibility_gate": "None at ranking stage",
        "entry_rule": "SKIP entry if Close(T) < SMA200(T). Slot held in Cash. No rank-31 refill.",
        "exit_rule": "None (8w scheduled rebalance)",
        "top_n": 30,
        "weighting": "Inverse Volatility (w_i proportional to 1/sigma_i,60d), capped [1.0%, 6.0%], normalized to active stock allocation.",
        "caps_floors": {"min_weight": 0.01, "max_weight": 0.06},
        "target_vol_rule": "None",
        "rebalance_schedule": "8-week phase anchored on 2024-01-26",
        "execution_standard": "V4 Post-Decision Execution (T+1 Close)",
        "one_way_cost_bp": 20.0,
        "benchmark": "XACT-SVERIGE.ST (Broad Sweden TR ETF)",
        "historical_cagr": 0.13089354493540872,
        "historical_vol": 0.1839486346584717,
        "historical_max_dd": -0.24802628909569358,
        "historical_sharpe": 0.3324169943685729
    },
    "VB_CAPITAL_PRESERVATION_CHALLENGER": {
        "model_id": "VB_CAPITAL_PRESERVATION_CHALLENGER",
        "label": "FROZEN FOR FORWARD — V-B CHALLENGER",
        "status": "VALID ROBUST HISTORICAL DISCOVERY — FORWARD CHALLENGER",
        "description": "V-A Return Challenger + Portfolio Target Volatility Scaling at 15.0% (S(T) = min(1.0, 0.15 / sigma_p,60d)).",
        "selector": "0.5 * rank(mom_12m) + 0.5 * rank(mom_18m)",
        "eligibility_gate": "None at ranking stage",
        "entry_rule": "SKIP entry if Close(T) < SMA200(T). Slot held in Cash.",
        "exit_rule": "None (8w scheduled rebalance)",
        "top_n": 30,
        "weighting": "Inverse Volatility [1.0%, 6.0%] + Portfolio Target Vol 15.0% scaling factor S(T) <= 1.0.",
        "caps_floors": {"min_weight": 0.01, "max_weight": 0.06},
        "target_vol_rule": "Target Vol = 15.0% (0.150 annual), max leverage = 1.0. Uninvested scaling held in Cash.",
        "rebalance_schedule": "8-week phase anchored on 2024-01-26",
        "execution_standard": "V4 Post-Decision Execution (T+1 Close)",
        "one_way_cost_bp": 20.0,
        "benchmark": "XACT-SVERIGE.ST (Broad Sweden TR ETF)",
        "historical_cagr": 0.12469164636320573,
        "historical_vol": 0.1518066603270119,
        "historical_max_dd": -0.17141199460092627,
        "historical_sharpe": 0.2796306927033954
    }
}

SUCCESS_CRITERIA = {
    "V_A_RETURN_CHALLENGER": {
        "primary_goal": "Deliver higher risk-adjusted return (Sharpe / Sortino) than Control C without losing momentum alpha",
        "volatility_target": "<= 18.5%",
        "max_dd_target": "<= 25.0%",
        "sharpe_target": "> Control C Sharpe"
    },
    "V_B_CAPITAL_PRESERVATION_CHALLENGER": {
        "primary_goal": "Deliver superior drawdown protection and capital preservation while maintaining CAGR >= 10.0%",
        "cagr_target": ">= 10.0%",
        "volatility_target": "<= 16.0%",
        "max_dd_target": "<= 20.0% (historical -17.14%)",
        "downside_capture_target": "< Control C downside capture"
    }
}

VALIDATION_HORIZON = {
    "minimum_months": 24,
    "minimum_decision_panels": 13,
    "evaluation_checkpoints": [
        {"period_count": 3, "months": 6, "stage": "Operational & Pipeline QA"},
        {"period_count": 6, "months": 12, "stage": "Early Forward Diagnostic"},
        {"period_count": 13, "months": 24, "stage": "Formal Primary Validation Checkpoint"},
        {"period_count": 26, "months": 48, "stage": "Long-Term Regimes Robustness Assessment"}
    ]
}

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

def compute_trailing_vols_and_cov(prices, window=60):
    vol_map = {}
    price_series = {
        k: (np.array([r["d"] for r in rs]), np.array([r["adj"] for r in rs], dtype=float))
        for k, rs in prices.items()
    }
    for kod, (ds, adj) in price_series.items():
        if len(adj) >= 2:
            rets = np.diff(adj) / adj[:-1]
            ds_rets = ds[1:]
            if len(rets) >= window:
                roll_std = pd.Series(rets).rolling(window).std().values * math.sqrt(252)
                for d, val in zip(ds_rets, roll_std):
                    if math.isfinite(val) and val > 1e-4:
                        vol_map[(kod, d)] = float(val)
    return vol_map, price_series

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

def generate_manifests():
    manifests = {}
    for m_id, spec in MODEL_SPECS.items():
        raw_json = json.dumps(spec, sort_keys=True)
        sha256_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        manifests[m_id] = {
            "spec": spec,
            "sha256": sha256_hash
        }
    return manifests

def setup_journals(rankings, prices, vol_map, price_series):
    JOURNALS_DIR.mkdir(parents=True, exist_ok=True)
    
    journal_files = {
        "CONTROL_C_SMA200": JOURNALS_DIR / "CONTROL_C_SMA200_FORWARD.jsonl",
        "VA_RETURN_CHALLENGER": JOURNALS_DIR / "VA_INVVOL_FORWARD.jsonl",
        "VB_CAPITAL_PRESERVATION_CHALLENGER": JOURNALS_DIR / "VB_INVVOL_TV15_FORWARD.jsonl"
    }

    eval_dates = sorted(rankings.keys())
    
    for m_id, path in journal_files.items():
        entries = []
        for dt in eval_dates:
            universe = rankings[dt]
            top30 = universe[:30]
            top30_kods = [r["kod"] for r in top30]
            
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
                    
            n_held = len(selected)
            
            if m_id == "CONTROL_C_SMA200":
                weights = {k: 1/30.0 for k in selected}
                cash_weight = (30 - n_held) / 30.0
                scaling_factor = 1.0
            elif m_id in ("VA_RETURN_CHALLENGER", "VB_CAPITAL_PRESERVATION_CHALLENGER"):
                vols = np.array([vol_map.get((k, dt), 0.25) for k in selected], dtype=float)
                inv_vols = 1.0 / np.maximum(vols, 0.05)
                w_raw = inv_vols / np.sum(inv_vols) * (n_held / 30.0)
                w_capped = np.clip(w_raw, 0.01, 0.06)
                w_norm = w_capped / np.sum(w_capped) * (n_held / 30.0)
                
                scaling_factor = 1.0
                if m_id == "VB_CAPITAL_PRESERVATION_CHALLENGER" and n_held > 1:
                    mat = []
                    for k in selected:
                        if k in price_series:
                            ds, adj = price_series[k]
                            idx = next((i for i in range(len(ds)-1, -1, -1) if ds[i] <= dt), None)
                            if idx is not None and idx >= 60:
                                rets = np.diff(adj[idx-60:idx+1]) / adj[idx-60:idx]
                                mat.append(rets)
                    if len(mat) == n_held:
                        cov = np.cov(np.array(mat)) * 252.0
                        port_var = float(w_norm.T @ cov @ w_norm)
                        est_port_vol = math.sqrt(max(port_var, 1e-4))
                        scaling_factor = min(1.0, 0.150 / est_port_vol)
                        w_norm = w_norm * scaling_factor

                weights = {k: float(w_norm[i]) for i, k in enumerate(selected)}
                cash_weight = float(1.0 - sum(weights.values()))

            ranking_hash = hashlib.sha256(json.dumps([r["kod"] for r in universe]).encode("utf-8")).hexdigest()
            
            rec = {
                "panel_date": dt,
                "model_id": m_id,
                "data_as_of": dt,
                "eligible_universe_count": len(universe),
                "selected_top30": top30_kods,
                "passed_entries": selected,
                "blocked_names": blocked,
                "cash_weight": cash_weight,
                "scaling_factor": scaling_factor,
                "target_weights": weights,
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
    print("RESEARCH W: FORWARD FREEZE & LIVE VALIDATION PROTOCOL")
    print(f"First Untouched Forward Decision Date: {FIRST_FORWARD_DATE}")
    print("=" * 80)
    
    core_df, prices, terminal = load_data()
    vol_map, price_series = compute_trailing_vols_and_cov(prices, window=60)
    h0_rankings = derive_h0_scores(core_df, prices)
    
    print("\n1. Generating SHA256 Model Manifests...")
    manifests = generate_manifests()
    
    freeze_payload = {
        "freeze_timestamp": "2026-08-10T10:37:00+02:00",
        "first_untouched_forward_panel_date": FIRST_FORWARD_DATE,
        "phase_anchor_date": PHASE_ANCHOR_H0,
        "models": manifests,
        "success_criteria": SUCCESS_CRITERIA,
        "validation_horizon": VALIDATION_HORIZON,
        "governance_status": {
            "CONTROL_C_SMA200": "FROZEN FOR FORWARD — CONTROL",
            "VA_RETURN_CHALLENGER": "FROZEN FOR FORWARD — V-A CHALLENGER",
            "VB_CAPITAL_PRESERVATION_CHALLENGER": "FROZEN FOR FORWARD — V-B CHALLENGER"
        }
    }
    
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(json.dumps(freeze_payload, indent=2, sort_keys=True), encoding="utf-8")
    
    print("2. Initializing Append-Only Forward Journals...")
    journal_files = setup_journals(h0_rankings, prices, vol_map, price_series)
    
    print("\n" + "=" * 80)
    print("RESEARCH W IMMUTABLE FREEZE COMPLETE")
    print("=" * 80)
    print(f"Manifest File: {MANIFEST_FILE}")
    for m_id, path in journal_files.items():
        print(f" - {m_id:36s} -> {path} (SHA256: {manifests[m_id]['sha256'][:16]}...)")
    print("=" * 80)

if __name__ == "__main__":
    main()
