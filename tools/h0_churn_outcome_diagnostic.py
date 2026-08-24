"""Descriptive audit of realised H0 sell/re-entry outcomes; no rule changes."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import h0_reentry_score_improvement as H

OUT = V2 / "research_k/h0_churn_outcome_diagnostic_results.json"
N = 30


def forward_8w(returns, dates, index, kod):
    if index + 1 >= len(dates):
        return None
    return float((1 + returns.get((kod, dates[index]), 0.0)) *
                 (1 + returns.get((kod, dates[index + 1]), 0.0)) - 1)


def summary(values):
    x = np.asarray([v for v in values if v is not None], dtype=float)
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "mean": round(float(x.mean()), 4), "median": round(float(np.median(x)), 4),
            "positive_share": round(float((x > 0).mean()), 4),
            "p10": round(float(np.percentile(x, 10)), 4), "p90": round(float(np.percentile(x, 90)), 4)}


def analyse(label, loader):
    rankings, dates, returns, entry, schedule = loader()
    prior, pending_sales, sales, reentries = [], {}, [], []
    for i, day in enumerate(dates):
        if not prior or schedule(i, day):
            current = [r["kod"] for r in rankings[day][:N]]
            removed, bought = set(prior) - set(current), set(current) - set(prior)
            for kod in removed:
                sale = {"kod": kod, "sale_date": day, "sale_index": i,
                        "forward_8w_return": forward_8w(returns, dates, i, kod), "reentered": False}
                sales.append(sale)
                pending_sales[kod] = sale
            for kod in bought:
                if kod in pending_sales:
                    sale = pending_sales.pop(kod)
                    sale["reentered"] = True
                    reentries.append({"kod": kod, "reentry_date": day, "reentry_index": i,
                                      "gap_panel_count": i - sale["sale_index"],
                                      "price_change_while_out": (entry.get((kod, day)) / entry.get((kod, sale["sale_date"])) - 1)
                                      if entry.get((kod, day)) and entry.get((kod, sale["sale_date"])) else None,
                                      "forward_8w_return": forward_8w(returns, dates, i, kod),
                                      "prior_sale_forward_8w_return": sale["forward_8w_return"]})
            prior = current
    return {
        "all_sales": summary([x["forward_8w_return"] for x in sales]),
        "sales_that_later_reentered": summary([x["forward_8w_return"] for x in sales if x["reentered"]]),
        "sales_never_reentered": summary([x["forward_8w_return"] for x in sales if not x["reentered"]]),
        "reentries": {"forward_8w_return": summary([x["forward_8w_return"] for x in reentries]),
                      "price_change_while_out": summary([x["price_change_while_out"] for x in reentries]),
                      "gap_panel_count": summary([x["gap_panel_count"] for x in reentries])},
        "counts": {"sales": len(sales), "reentries": len(reentries)},
        "samples": {"sales": sales, "reentries": reentries}
    }


def main():
    result = {"version": "H0_CHURN_OUTCOME_DIAGNOSTIC_V1", "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "diagnostic_only": True, "definition": "Underlying adjusted-price return over the two 4-week panels after a sell or re-entry; not a counterfactual portfolio alpha measure.",
              "results": {}}
    for label, loader in (("2021_2026", H.late_loader), ("2014_2019", H.early_loader)):
        print(f"analysing {label}", flush=True)
        result["results"][label] = analyse(label, loader)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for label, data in result["results"].items():
        print(label, json.dumps({"all_sales": data["all_sales"], "reentries": data["reentries"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
