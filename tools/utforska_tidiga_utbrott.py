"""TIDIGA UTBROTT — Vad skiljer äkta utbrott från falska pumps?

Isolerar aktier vid paneldatum som har:
  - M12-momentum i Topp 30 (stark kortsiktig rörelse)
  - M52-momentum OUTSIDE Topp 100 (låg/mogen historik = genuint TIDIG)

Mäter vad vid entry-tidpunkten som bäst förutsäger framtida 6-månaders avkastning:
  1. Avstånd till 52-veckors högsta (price / max_52w_price)
  2. 12-veckors trend-stabilitet (t-stat för log-pris över 12v)
  3. SMA50 / SMA200 ratio (är korta trenden över den långa?)
  4. Volatilitet (60d vol)
  5. Drawdown resilience (12v max dd)

DIAGNOSTISKT.
Kör: /opt/momentum/venv/bin/python tools/utforska_tidiga_utbrott.py
"""
from __future__ import annotations
import importlib.util, json, math, statistics
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/utforska_tidiga_utbrott_results.json"


def ladda():
    s = importlib.util.spec_from_file_location(
        "h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    core, prices, term = m.load_data()
    rmap, alld = m.execution_engine(core, prices, term)
    return m, prices, core, rmap, alld


def get_price_window(rs, panel_dt, days):
    lo = (date.fromisoformat(panel_dt) - timedelta(days=days)).isoformat()
    return [r for r in rs if lo <= r["d"] <= panel_dt
            and r.get("adj") is not None and r["adj"] > 0]


def compute_factors(rs, dt):
    """Compute candidate early-breakout filters at panel date `dt`."""
    w52 = get_price_window(rs, dt, 364)
    w12 = get_price_window(rs, dt, 84)

    if len(w52) < 200 or len(w12) < 40:
        return None

    adj52 = np.array([r["adj"] for r in w52], float)
    adj12 = np.array([r["adj"] for r in w12], float)

    curr_p = adj12[-1]

    # 1. Price relative to 52w high (1.0 = at 52w high)
    max_52w = float(np.max(adj52))
    p_to_52w_high = curr_p / max_52w if max_52w > 0 else None

    # 2. Price relative to 52w low
    min_52w = float(np.min(adj52))
    p_to_52w_low = curr_p / min_52w if min_52w > 0 else None

    # 3. 12w trend consistency (t-stat over last 12 weeks)
    y12 = np.log(adj12)
    x12 = np.arange(len(y12), dtype=float)
    X12 = np.column_stack([np.ones(len(x12)), x12])
    beta12 = np.linalg.lstsq(X12, y12, rcond=None)[0]
    res12 = y12 - X12 @ beta12
    s2_12 = float(res12 @ res12) / max(len(x12) - 2, 1)
    se12 = math.sqrt(s2_12 * np.linalg.inv(X12.T @ X12)[1, 1]) if s2_12 > 0 else 0
    tstat_12w = float(beta12[1] / se12) if se12 > 0 else 0.0

    # 4. SMA50 vs SMA200
    sma50 = float(np.mean(adj52[-50:])) if len(adj52) >= 50 else None
    sma200 = float(np.mean(adj52[-200:])) if len(adj52) >= 200 else None
    sma50_200_ratio = (sma50 / sma200) if (sma50 and sma200 and sma200 > 0) else None

    # 5. 12w max drawdown
    peak12 = adj12[0]
    m12_dd = 0.0
    for p in adj12:
        peak12 = max(peak12, p)
        m12_dd = min(m12_dd, p / peak12 - 1)

    return {
        "p_to_52w_high": p_to_52w_high,
        "p_to_52w_low": p_to_52w_low,
        "tstat_12w": tstat_12w,
        "sma50_200_ratio": sma50_200_ratio,
        "m12_dd": m12_dd,
    }


def main():
    print("Loading data...")
    m, prices, core, rmap, alld = ladda()

    # Build price lists
    price_lists = {k: sorted(rs, key=lambda r: r["d"])
                   for k, rs in prices.items()}

    # Compute 12w and 52w momentum rankings per date
    dates = sorted(core.panel_date.unique())
    dates = [d for d in dates if "2021-07-16" <= d <= "2026-07-10"]

    events = []

    for i, dt in enumerate(dates):
        panel = core[core.panel_date == dt]
        kods = list(panel.kod)

        # 12w and 52w scores
        m12_list = []
        m52_list = []
        for k in kods:
            rs = price_lists.get(k, [])
            w12 = get_price_window(rs, dt, 84)
            w52 = get_price_window(rs, dt, 364)
            r12 = (w12[-1]["adj"] / w12[0]["adj"] - 1) if len(w12) >= 40 and w12[0]["adj"] > 0 else -999
            r52 = (w52[-1]["adj"] / w52[0]["adj"] - 1) if len(w52) >= 200 and w52[0]["adj"] > 0 else -999
            m12_list.append((r12, k))
            m52_list.append((r52, k))

        m12_list.sort(reverse=True)
        m52_list.sort(reverse=True)

        rank12 = {k: r + 1 for r, (_, k) in enumerate(m12_list)}
        rank52 = {k: r + 1 for r, (_, k) in enumerate(m52_list)}

        # Find early breakout candidates: M12 Top-30 AND M52 rank > 100
        for k in kods:
            r12_val = rank12.get(k, 999)
            r52_val = rank52.get(k, 999)

            if r12_val <= 30 and r52_val > 100:
                rs = price_lists.get(k, [])
                factors = compute_factors(rs, dt)
                if factors is None:
                    continue

                # Forward return over next 6 panels (24 weeks)
                cum_ret_6p = 0.0
                for h in range(min(6, len(dates) - i - 1)):
                    cum_ret_6p += rmap.get((k, dates[i + h]), 0.0)

                events.append({
                    "kod": k,
                    "panel_date": dt,
                    "m12_rank": r12_val,
                    "m52_rank": r52_val,
                    "fwd_ret_6p": cum_ret_6p,
                    "is_big_winner": cum_ret_6p >= 0.30,  # +30% or more
                    "is_big_loser": cum_ret_6p <= -0.15,  # -15% or worse
                    **factors
                })

    print(f"\n{'='*85}")
    print(f"EARLY BREAKOUT ANALYSIS (M12 Top-30 AND M52 Rank > 100)")
    print(f"{'='*85}")
    print(f"  Totalt antal tidiga utbrottsobservationer: {len(events)}")

    big_winners = [e for e in events if e["is_big_winner"]]
    big_losers = [e for e in events if e["is_big_loser"]]
    others = [e for e in events if not e["is_big_winner"] and not e["is_big_loser"]]

    print(f"  Stora vinnare (≥ +30% på 24v): {len(big_winners)} ({len(big_winners)/len(events):.1%})")
    print(f"  Stora förlorare (≤ -15% på 24v): {len(big_losers)} ({len(big_losers)/len(events):.1%})")
    print(f"  Neutrala:                     {len(others)} ({len(others)/len(events):.1%})")

    def med(vals):
        v = [x for x in vals if x is not None and math.isfinite(x)]
        return statistics.median(v) if v else None

    def fmtp(v): return f"{v:.1%}" if v is not None else "N/A"
    def fmtf(v): return f"{v:.2f}" if v is not None else "N/A"

    print(f"\n  Jämförelse vid entry (medianer):")
    print(f"  {'Faktor':32s} {'Vinnare (≥+30%)':>18s} {'Förlorare (≤-15%)':>18s} {'Diff':>12s}")

    metrics = [
        ("Pris / 52w High (1.0 = nära topp)", "p_to_52w_high", fmtp),
        ("Pris / 52w Low (högre = längre från botten)", "p_to_52w_low", fmtf),
        ("12v Trend Stabilitet (t-stat)", "tstat_12w", fmtf),
        ("SMA50 / SMA200 Ratio (>1.0 = gyllene kors)", "sma50_200_ratio", fmtf),
        ("12v Max Drawdown (mindre = jämnare uppgång)", "m12_dd", fmtp),
    ]

    result_data = {}
    for label, key, fmt in metrics:
        w_m = med([e[key] for e in big_winners])
        l_m = med([e[key] for e in big_losers])
        diff = (w_m - l_m) if w_m is not None and l_m is not None else None
        print(f"  {label:32s} {fmt(w_m):>18s} {fmt(l_m):>18s} {fmt(diff):>12s}")
        result_data[key] = {"winner_median": w_m, "loser_median": l_m}

    # Test filtering rules on early breakouts!
    print(f"\n{'='*85}")
    print("TEST AV REGLER FÖR ATT FILTERA TIDIGA UTBROTT")
    print(f"{'='*85}")

    rules = [
        ("Ingen filter (alla M12 Top30 & M52 > 100)", lambda e: True),
        ("Pris ≥ 80% av 52w High (Nära 52w topp)", lambda e: e["p_to_52w_high"] is not None and e["p_to_52w_high"] >= 0.80),
        ("Pris ≥ 90% av 52w High (Mycket nära topp)", lambda e: e["p_to_52w_high"] is not None and e["p_to_52w_high"] >= 0.90),
        ("SMA50 > SMA200 (Gyllene kors)", lambda e: e["sma50_200_ratio"] is not None and e["sma50_200_ratio"] >= 1.0),
        ("12v t-stat ≥ 2.0 (Stabil 12v trend)", lambda e: e["tstat_12w"] is not None and e["tstat_12w"] >= 2.0),
        ("Kombination: Pris≥85% 52wHigh OCH t-stat≥1.5", lambda e: e["p_to_52w_high"] is not None and e["p_to_52w_high"] >= 0.85 and e["tstat_12w"] >= 1.5),
    ]

    for r_label, r_fn in rules:
        sub = [e for e in events if r_fn(e)]
        if not sub:
            continue
        n_sub = len(sub)
        w_sub = sum(1 for e in sub if e["is_big_winner"])
        l_sub = sum(1 for e in sub if e["is_big_loser"])
        med_ret = med([e["fwd_ret_6p"] for e in sub])
        print(f"  {r_label:48s}: N={n_sub:4d} | Vinnare: {w_sub/n_sub:.1%} | Förlorare: {l_sub/n_sub:.1%} | MedRet: {fmtp(med_ret)}")

    OUT.write_text(json.dumps({
        "version": "EARLY_BREAKOUT_EXPLORATION_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_events": len(events),
        "metrics": result_data,
    }, ensure_ascii=False, indent=2))
    print(f"\n  → {OUT.name}")


if __name__ == "__main__":
    main()
