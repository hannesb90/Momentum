#!/usr/bin/env python3
"""
UNIVERSE TOP-30 DIAGNOSTIC AUDIT (420 TICKERS)

Measures Top-30 frequency, best rank, median rank, number of Top-30 episodes,
total time in Top-30, and volatility for all 420 universe stocks.
Aggregates by K1 Sector, List Segment, Volatility Group, and Terminal Status.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2")
SYS_TOOLS = V2 / "tools"
sys.path.insert(0, str(SYS_TOOLS))

OUT_JSON = V2 / "research_k/universe_top30_audit_results.json"


def load_metadata():
    sec_data = json.loads((V2 / "research_k/sector_classification_v1/validated/sector_classification_intervals.json").read_text(encoding="utf-8"))
    sector_map = {x["instrument_id"]: x["canonical_sector"] for x in sec_data}
    
    qa = json.loads((V2 / "research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json").read_text(encoding="utf-8"))
    list_map = {}
    terminal_map = {}
    for r in qa:
        kod = r["instrument_id"]
        ml = r.get("market_list")
        if ml == "Large Cap Stockholm":
            list_map[kod] = "Large Cap"
        elif ml == "Mid Cap Stockholm":
            list_map[kod] = "Mid Cap"
        elif ml == "Small Cap Stockholm":
            list_map[kod] = "Small Cap"
        elif r.get("terminal") is True:
            list_map[kod] = "Terminal/Avnoterad"
        else:
            list_map[kod] = "Övriga"
        terminal_map[kod] = r.get("terminal", False)
        
    return sector_map, list_map, terminal_map


def main():
    print("=== STARTING UNIVERSE TOP-30 DIAGNOSTIC AUDIT ===")
    sector_map, list_map, terminal_map = load_metadata()
    
    core26 = json.loads((V2 / "panels/core_panel.json").read_text(encoding="utf-8"))
    by_dt_26 = defaultdict(list)
    for r in core26:
        if r.get("mom_52w") is not None:
            by_dt_26[r["panel_date"]].append(r)
            
    ranked_panels_26 = {}
    for dt, rows in by_dt_26.items():
        moms = np.array([r["mom_52w"] for r in rows])
        pct_ranks = stats.rankdata(moms) / len(moms)
        for idx, r in enumerate(rows):
            r_copy = dict(r)
            r_copy["h0_score"] = pct_ranks[idx]
            rows[idx] = r_copy
        rows.sort(key=lambda x: (x["h0_score"], x["kod"]), reverse=True)
        ranked_panels_26[dt] = rows

    import h1419_motor as M
    ranked_panels_1419 = M.RANKNINGAR
    
    ticker_panel_history = defaultdict(list)
    
    for dt, rows in ranked_panels_1419.items():
        for rank_idx, r in enumerate(rows, 1):
            kod = r["kod"]
            vol52 = r.get("vol_52w", 0.25)
            if vol52 is None or not math.isfinite(vol52) or vol52 <= 0:
                vol52 = 0.25
            ticker_panel_history[kod].append({
                "window": "2014-2019",
                "panel_date": dt,
                "rank": rank_idx,
                "is_top30": rank_idx <= 30,
                "vol_52w": vol52
            })
            
    for dt, rows in ranked_panels_26.items():
        for rank_idx, r in enumerate(rows, 1):
            kod = r["kod"]
            vol52 = r.get("vol_52w", 0.25)
            if vol52 is None or not math.isfinite(vol52) or vol52 <= 0:
                vol52 = 0.25
            ticker_panel_history[kod].append({
                "window": "2020-2026",
                "panel_date": dt,
                "rank": rank_idx,
                "is_top30": rank_idx <= 30,
                "vol_52w": vol52
            })
            
    print(f"Total tickers tracked across all panels: {len(ticker_panel_history)}")
    
    ticker_stats = []
    
    for kod, hist in ticker_panel_history.items():
        df_h = pd.DataFrame(hist).sort_values("panel_date")
        n_obs = len(df_h)
        n_top30 = df_h["is_top30"].sum()
        pct_top30 = float(n_top30 / n_obs)
        best_rank = int(df_h["rank"].min())
        median_rank = float(df_h["rank"].median())
        mean_vol = float(df_h["vol_52w"].mean())
        
        top30_blocks = []
        curr_block = 0
        for is_t30 in df_h["is_top30"]:
            if is_t30:
                curr_block += 1
            else:
                if curr_block > 0:
                    top30_blocks.append(curr_block)
                    curr_block = 0
        if curr_block > 0:
            top30_blocks.append(curr_block)
            
        n_episodes = len(top30_blocks)
        total_time_in_top30 = int(n_top30)
        mean_episode_length = float(np.mean(top30_blocks)) if top30_blocks else 0.0
        
        if mean_vol < 0.20:
            vol_group = "Låg Vol (<20%)"
        elif mean_vol <= 0.40:
            vol_group = "Mid Vol (20-40%)"
        else:
            vol_group = "Hög Vol (>40%)"
            
        ticker_stats.append({
            "kod": kod,
            "sector": sector_map.get(kod, "UNKNOWN"),
            "list_segment": list_map.get(kod, "Övriga"),
            "is_terminal": terminal_map.get(kod, False),
            "vol_group": vol_group,
            "mean_vol_52w": mean_vol,
            "n_obs": n_obs,
            "n_top30_panels": n_top30,
            "pct_top30_panels": pct_top30,
            "best_rank": best_rank,
            "median_rank": median_rank,
            "n_episodes": n_episodes,
            "total_tis_panels": total_time_in_top30,
            "mean_episode_length_panels": mean_episode_length
        })
        
    df_ts = pd.DataFrame(ticker_stats)
    
    def aggregate_group(group_col):
        res = {}
        for grp_val, sub in df_ts.groupby(group_col):
            res[str(grp_val)] = {
                "n_tickers": len(sub),
                "n_tickers_ever_top30": int((sub["n_top30_panels"] > 0).sum()),
                "pct_tickers_ever_top30": float((sub["n_top30_panels"] > 0).mean()),
                "mean_top30_panels_per_ticker": float(sub["n_top30_panels"].mean()),
                "mean_pct_top30_panels": float(sub["pct_top30_panels"].mean()),
                "median_best_rank": float(sub["best_rank"].median()),
                "median_overall_rank": float(sub["median_rank"].median()),
                "mean_episodes_per_ticker": float(sub["n_episodes"].mean()),
                "mean_total_tis_panels": float(sub["total_tis_panels"].mean()),
                "mean_vol_52w": float(sub["mean_vol_52w"].mean())
            }
        return res

    by_sector = aggregate_group("sector")
    by_list = aggregate_group("list_segment")
    by_vol = aggregate_group("vol_group")
    by_terminal = aggregate_group("is_terminal")
    
    out_data = {
        "title": "UNIVERSE TOP-30 DIAGNOSTIC AUDIT (420 TICKERS)",
        "date": datetime.now().isoformat(),
        "total_tickers": len(df_ts),
        "by_sector": by_sector,
        "by_list_segment": by_list,
        "by_volatility_group": by_vol,
        "by_terminal_status": by_terminal,
        "ticker_detail_sample": df_ts.sort_values("n_top30_panels", ascending=False).head(20).to_dict(orient="records")
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== AUDIT COMPLETE ===")
    print(f"Results written to: {OUT_JSON}")


if __name__ == "__main__":
    main()
