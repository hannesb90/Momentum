"""Exploratory-only H0 exit-pattern screen on historical 2014--2019 data.

It deliberately does not read 2021--2026. Any candidate must be separately
preregistered before the later period is opened for its independent test.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import h0_reentry_score_improvement as H
import h1419_motor as M

OUT = V2 / "research_k/h0_exit_pattern_explorer_2014_2019.json"
N = 30


def fwd8(returns, dates, i, kod):
    if i + 1 >= len(dates):
        return None
    return (1 + returns.get((kod, dates[i]), 0.0)) * (1 + returns.get((kod, dates[i + 1]), 0.0)) - 1


def summary(rows):
    x = np.asarray([r["target"] for r in rows], float)
    return {"n": len(rows), "mean_target": None if not len(x) else round(float(x.mean()), 4),
            "positive_share": None if not len(x) else round(float((x > 0).mean()), 4)}


def rows():
    rankings, dates, returns, _, schedule = H.early_loader()
    prior, entry = [], {}
    out = []
    for i, day in enumerate(dates):
        ranked = rankings[day]
        by_code = {r["kod"]: r for r in ranked}
        rank = {r["kod"]: j + 1 for j, r in enumerate(ranked)}
        if not prior or schedule(i, day):
            current = [r["kod"] for r in ranked[:N]]
            sold, bought = set(prior) - set(current), set(current) - set(prior)
            basket = [fwd8(returns, dates, i, k) for k in bought]
            basket = [v for v in basket if v is not None]
            # State is constructed from prices known on the decision date only.
            market_26w = []
            for item in ranked:
                ds, px = M.SERIE.get(item["kod"], (np.array([]), np.array([])))
                j = int(np.searchsorted(ds, np.datetime64(day), side="right")) - 1
                k = int(np.searchsorted(ds, np.datetime64(day) - np.timedelta64(182, "D"), side="right")) - 1
                if j >= 0 and k >= 0 and px[k] > 0:
                    market_26w.append(float(px[j] / px[k] - 1))
            median_26w = float(np.median(market_26w)) if market_26w else None
            breadth_26w = float(np.mean(np.asarray(market_26w) > 0)) if market_26w else None
            for kod in sold:
                own = fwd8(returns, dates, i, kod)
                r = by_code.get(kod)
                if own is not None and basket and r and kod in entry:
                    e = entry[kod]
                    out.append({"date": day, "target": own - float(np.mean(basket)),
                                "rank": rank[kod], "score": r["score"],
                                "m12": r["m12"], "m18": r["m18"],
                                "m12_rank": r["m12_rank"], "m18_rank": r["m18_rank"],
                                "rank_deterioration": rank[kod] - e["rank"],
                                "score_change": r["score"] - e["score"],
                                "tenure_panels": i - e["index"],
                                "rebalance_turnover": len(bought) / N,
                                "market_median_26w": median_26w,
                                "market_breadth_26w": breadth_26w})
                entry.pop(kod, None)
            for kod in bought:
                entry[kod] = {"rank": rank[kod], "score": by_code[kod]["score"], "index": i}
            prior = current
    return out


def condition_table(all_rows, label, fn):
    out = {"2014_2016": summary([r for r in all_rows if r["date"] < "2017-01-01" and fn(r)]),
           "2017_2019": summary([r for r in all_rows if r["date"] >= "2017-01-01" and fn(r)])}
    # A useful candidate must have enough data and a positive excess target in
    # both chronological slices. This is only a screen, not an approval test.
    out["screen_pass"] = all((x["n"] >= 15 and x["mean_target"] is not None and x["mean_target"] > 0) for x in out.values())
    return {"condition": label, **out}


def main():
    x = rows()
    candidates = [
        ("just_outside_rank_31_45", lambda r: 31 <= r["rank"] <= 45),
        ("far_outside_rank_ge_46", lambda r: r["rank"] >= 46),
        ("m12_rank_ge_80pct", lambda r: (r["m12_rank"] or -1) >= .80),
        ("m18_rank_ge_80pct", lambda r: (r["m18_rank"] or -1) >= .80),
        ("short_stronger_m12rank_minus_m18rank_ge_10pp", lambda r: r["m12_rank"] is not None and r["m18_rank"] is not None and r["m12_rank"] - r["m18_rank"] >= .10),
        ("long_stronger_m18rank_minus_m12rank_ge_10pp", lambda r: r["m12_rank"] is not None and r["m18_rank"] is not None and r["m18_rank"] - r["m12_rank"] >= .10),
        ("short_strong_and_just_outside", lambda r: (r["m12_rank"] or -1) >= .80 and 31 <= r["rank"] <= 45),
        ("long_strong_and_just_outside", lambda r: (r["m18_rank"] or -1) >= .80 and 31 <= r["rank"] <= 45),
        ("tenure_4_or_more_panels", lambda r: r["tenure_panels"] >= 4),
        ("tenure_under_4_panels", lambda r: r["tenure_panels"] < 4),
        ("rank_deterioration_under_20", lambda r: r["rank_deterioration"] < 20),
        ("rank_deterioration_20_or_more", lambda r: r["rank_deterioration"] >= 20),
        ("small_score_drop_ge_minus_10pp", lambda r: r["score_change"] >= -.10),
        ("large_score_drop_under_minus_10pp", lambda r: r["score_change"] < -.10),
        ("market_median_26w_positive", lambda r: r["market_median_26w"] is not None and r["market_median_26w"] > 0),
        ("market_median_26w_nonpositive", lambda r: r["market_median_26w"] is not None and r["market_median_26w"] <= 0),
        ("market_breadth_26w_ge_60pct", lambda r: r["market_breadth_26w"] is not None and r["market_breadth_26w"] >= .60),
        ("market_breadth_26w_under_60pct", lambda r: r["market_breadth_26w"] is not None and r["market_breadth_26w"] < .60),
        ("low_rotation_under_20pct", lambda r: r["rebalance_turnover"] < .20),
        ("high_rotation_ge_20pct", lambda r: r["rebalance_turnover"] >= .20),
    ]
    tables = [condition_table(x, label, fn) for label, fn in candidates]
    result = {"version": "H0_EXIT_PATTERN_EXPLORER_V1", "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "scope": "2014-2019 only; exploratory; later history intentionally unopened", "all_exits": summary(x), "tables": tables,
              "screen_passes": [t["condition"] for t in tables if t["screen_pass"]]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"all_exits": result["all_exits"], "screen_passes": result["screen_passes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
