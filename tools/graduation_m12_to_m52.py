"""GRADUATION — vilka M12-innhav växer in i M52?

Frågan: av aktierna som M12 plockar upp tidigt (Topp 30/40), vilka dyker
senare upp i M52 Topp 30? Finns det ett mönster vid entry-tidpunkten som
skiljer "graduates" från "washouts"?

Mäter:
  1. Graduationsfrekvens: hur stor andel av M12 Topp-30 hamnar i M52 Topp-30
     inom 1–6 paneler (4–24 veckor)?
  2. Karaktäristik vid entry: vad skiljer graduates från washouts?
     - M52-rank vid entry (hur långt bort var de?)
     - Drawdown resilience vid entry
     - Avkastning under innehavet
  3. Avkastningsskillnad: graduates vs washouts forward return

DIAGNOSTISKT. Rör ingen fryst modell.
Kör: /opt/momentum/venv/bin/python tools/graduation_m12_to_m52.py
"""
from __future__ import annotations
import importlib.util, json, math, statistics
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/graduation_m12_to_m52_results.json"


def ladda():
    s = importlib.util.spec_from_file_location(
        "h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    core, prices, term = m.load_data()
    rmap, alld = m.execution_engine(core, prices, term)
    return m, prices, core, rmap, alld


def momentum_score(prices, kod, dt, weeks):
    if kod not in prices:
        return None
    rs = prices[kod]
    ds = [r["d"] for r in rs]
    adj = [r["adj"] for r in rs]
    i = None
    for j in range(len(ds) - 1, -1, -1):
        if ds[j] <= dt:
            i = j
            break
    if i is None:
        return None
    target = (date.fromisoformat(dt) - timedelta(days=weeks * 7)).isoformat()
    j = None
    for k in range(len(ds) - 1, -1, -1):
        if ds[k] <= target:
            j = k
            break
    if j is None:
        return None
    gap_days = (date.fromisoformat(target) - date.fromisoformat(ds[j])).days
    if abs(gap_days) > 10:
        return None
    if adj[j] <= 0:
        return None
    return adj[i] / adj[j] - 1


def drawdown_resilience(prices, kod, dt):
    if kod not in prices:
        return None
    rs = prices[kod]
    lo = (date.fromisoformat(dt) - timedelta(days=364)).isoformat()
    w = [r for r in rs if lo <= r["d"] <= dt
         and r.get("adj") is not None and r["adj"] > 0]
    if len(w) < 200:
        return None
    peak = w[0]["adj"]
    m = 0.0
    for r in w:
        peak = max(peak, r["adj"])
        m = min(m, r["adj"] / peak - 1)
    return -abs(m)


def build_rankings(core_df, prices):
    dates = sorted(core_df.panel_date.unique())
    dates = [d for d in dates if "2021-07-16" <= d <= "2026-07-10"]

    rankings = {w: {} for w in [12, 26, 52]}

    for dt in dates:
        panel = core_df[core_df.panel_date == dt]
        kods = list(panel.kod)

        for weeks in [12, 26, 52]:
            scores = []
            for kod in kods:
                m = momentum_score(prices, kod, dt, weeks)
                scores.append({"kod": kod, "mom": m})

            valid = [(s["mom"], i) for i, s in enumerate(scores)
                     if s["mom"] is not None]
            valid.sort()
            n_valid = len(valid)
            rank_map = {}
            j = 0
            while j < len(valid):
                k = j + 1
                while k < len(valid) and valid[k][0] == valid[j][0]:
                    k += 1
                for _, idx in valid[j:k]:
                    rank_map[idx] = (j + k + 1) / 2  # 1-indexed avg rank
                j = k

            scored = []
            for i, s in enumerate(scores):
                r = rank_map.get(i)
                scored.append({
                    "kod": s["kod"],
                    "mom": s["mom"],
                    "rank": int(r) if r is not None else None,
                    "n_valid": n_valid,
                })

            scored.sort(key=lambda x: (x["rank"] if x["rank"] is not None
                                       else 9999))
            # Reverse: rank 1 = worst, rank N = best for momentum
            scored.sort(key=lambda x: (-(x["mom"] or -999), x["kod"]))
            # Re-rank after sort
            for i, s in enumerate(scored):
                s["rank"] = i + 1

            rankings[weeks][dt] = scored

    return rankings, dates


def main():
    print("Loading data...")
    m, prices, core, rmap, alld = ladda()

    print("Building rankings...")
    rankings, dates = build_rankings(core, prices)
    print(f"  {len(dates)} paneler")

    # Build rank lookups per date
    rank12 = {}  # (kod, dt) -> rank position (1=best)
    rank52 = {}
    for dt in dates:
        for r in rankings[12][dt]:
            rank12[(r["kod"], dt)] = r["rank"]
        for r in rankings[52][dt]:
            rank52[(r["kod"], dt)] = r["rank"]

    # For each panel, find M12 Top-30 entries that are NOT in M52 Top-30
    # Track whether they graduate to M52 Top-30 within 1-6 panels
    HORIZONS = [1, 2, 3, 4, 6]
    MAX_H = max(HORIZONS)

    events = []  # each event = one stock entering M12 Top-30

    for i, dt in enumerate(dates):
        m12_top30 = set(r["kod"] for r in rankings[12][dt][:30])
        m52_top30 = set(r["kod"] for r in rankings[52][dt][:30])

        for kod in m12_top30:
            r52_now = rank52.get((kod, dt), 999)
            dr = drawdown_resilience(prices, kod, dt)
            m12_val = momentum_score(prices, kod, dt, 12)
            m52_val = momentum_score(prices, kod, dt, 52)

            # Track graduation
            graduated = {}
            fwd_ret = {}
            for h in HORIZONS:
                if i + h < len(dates):
                    future_dt = dates[i + h]
                    future_r52 = rank52.get((kod, future_dt), 999)
                    graduated[h] = future_r52 <= 30
                    fwd_ret[h] = rmap.get((kod, dt), 0.0) if h == 1 else None
                else:
                    graduated[h] = None

            # Cumulative forward return over next 6 panels
            cum_ret = 0.0
            for h in range(min(6, len(dates) - i - 1)):
                cum_ret += rmap.get((kod, dates[i + h]), 0.0)

            already_in_52 = kod in m52_top30

            events.append({
                "kod": kod,
                "panel_date": dt,
                "m12_rank": rank12.get((kod, dt), 999),
                "m52_rank": r52_now,
                "already_in_m52_top30": already_in_52,
                "drawdown_resilience": dr,
                "mom_12w": m12_val,
                "mom_52w": m52_val,
                "graduated": graduated,
                "cum_fwd_return_6p": cum_ret,
            })

    # Analysis
    # Split into: already in M52 Top-30, graduates (enter M52 Top-30 later),
    # washouts (never enter M52 Top-30)
    already = [e for e in events if e["already_in_m52_top30"]]
    new_entries = [e for e in events if not e["already_in_m52_top30"]]

    grad_ever = [e for e in new_entries
                 if any(v is True for v in e["graduated"].values())]
    washouts = [e for e in new_entries
                if all(v is False for v in e["graduated"].values()
                       if v is not None)]

    print(f"\n{'='*80}")
    print(f"GRADUATION ANALYSIS — M12 Top-30 → M52 Top-30")
    print(f"{'='*80}")
    print(f"  Total M12 Top-30 entries: {len(events)}")
    print(f"  Already in M52 Top-30:    {len(already)}"
          f"  ({len(already)/len(events):.0%})")
    print(f"  New (not in M52 Top-30):  {len(new_entries)}"
          f"  ({len(new_entries)/len(events):.0%})")
    print(f"    → Graduate within 6p:   {len(grad_ever)}"
          f"  ({len(grad_ever)/max(len(new_entries),1):.0%} av nya)")
    print(f"    → Washout (aldrig):     {len(washouts)}"
          f"  ({len(washouts)/max(len(new_entries),1):.0%} av nya)")

    # Graduation rate by horizon
    print(f"\n  Graduationsfrekvens per horisont:")
    for h in HORIZONS:
        n_grad = sum(1 for e in new_entries
                     if e["graduated"].get(h) is True)
        n_total = sum(1 for e in new_entries
                      if e["graduated"].get(h) is not None)
        pct = n_grad / max(n_total, 1)
        print(f"    Inom {h} panel(er) ({h*4}v): {n_grad}/{n_total}"
              f"  = {pct:.1%}")

    # Characteristics at entry
    print(f"\n  Karaktäristik vid M12-entry (median):")
    print(f"  {'':30s} {'Graduates':>12s} {'Washouts':>12s} {'Skillnad':>12s}")

    def safe_median(vals):
        v = [x for x in vals if x is not None and math.isfinite(x)]
        return statistics.median(v) if v else None

    def fmt(v):
        return f"{v:.1f}" if v is not None else "N/A"

    def fmtp(v):
        return f"{v:.1%}" if v is not None else "N/A"

    metrics = [
        ("M52-rank vid entry", "m52_rank", fmt),
        ("M12-rank vid entry", "m12_rank", fmt),
        ("Drawdown resilience", "drawdown_resilience", fmtp),
        ("Mom 12w vid entry", "mom_12w", fmtp),
        ("Mom 52w vid entry", "mom_52w", fmtp),
        ("Cum fwd return 6p", "cum_fwd_return_6p", fmtp),
    ]
    result_chars = {}
    for label, key, formatter in metrics:
        g_vals = [e[key] for e in grad_ever]
        w_vals = [e[key] for e in washouts]
        g_med = safe_median(g_vals)
        w_med = safe_median(w_vals)
        diff = (g_med - w_med) if g_med is not None and w_med is not None else None
        print(f"  {label:30s} {formatter(g_med):>12s}"
              f" {formatter(w_med):>12s}"
              f" {formatter(diff):>12s}")
        result_chars[key] = {"graduates": g_med, "washouts": w_med, "diff": diff}

    # M52-rank distribution for graduates vs washouts
    print(f"\n  M52-rank vid entry — fördelning:")
    for bucket_label, lo, hi in [("Topp 50", 1, 50), ("51-100", 51, 100),
                                  ("101-150", 101, 150), ("151-200", 151, 200),
                                  ("200+", 201, 9999)]:
        g_n = sum(1 for e in grad_ever
                  if e["m52_rank"] is not None and lo <= e["m52_rank"] <= hi)
        w_n = sum(1 for e in washouts
                  if e["m52_rank"] is not None and lo <= e["m52_rank"] <= hi)
        g_pct = g_n / max(len(grad_ever), 1)
        w_pct = w_n / max(len(washouts), 1)
        print(f"    M52 {bucket_label:8s}: grad {g_n:4d} ({g_pct:.0%})"
              f"   wash {w_n:4d} ({w_pct:.0%})")

    # Forward return comparison
    print(f"\n  Framtida avkastning (cum 6 paneler):")
    g_ret = safe_median([e["cum_fwd_return_6p"] for e in grad_ever])
    w_ret = safe_median([e["cum_fwd_return_6p"] for e in washouts])
    a_ret = safe_median([e["cum_fwd_return_6p"] for e in already])
    print(f"    Already in M52:  {fmtp(a_ret)}")
    print(f"    Graduates:       {fmtp(g_ret)}")
    print(f"    Washouts:        {fmtp(w_ret)}")

    print(f"\n{'='*80}")

    # Save
    OUT.write_text(json.dumps({
        "version": "GRADUATION_M12_M52_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_paneler": len(dates),
        "total_events": len(events),
        "already_in_m52": len(already),
        "new_entries": len(new_entries),
        "graduates": len(grad_ever),
        "washouts": len(washouts),
        "graduation_rate_by_horizon": {
            f"{h}p": sum(1 for e in new_entries if e["graduated"].get(h) is True)
            / max(sum(1 for e in new_entries if e["graduated"].get(h) is not None), 1)
            for h in HORIZONS
        },
        "characteristics": result_chars,
        "forward_returns": {
            "already_median": a_ret,
            "graduates_median": g_ret,
            "washouts_median": w_ret,
        },
    }, ensure_ascii=False, indent=2))
    print(f"  → {OUT.name}")


if __name__ == "__main__":
    main()
