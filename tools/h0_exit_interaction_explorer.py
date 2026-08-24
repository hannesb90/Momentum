"""Exploratory chronological interaction screen; never reads 2021--2026."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.tree import DecisionTreeRegressor, export_text

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
from h0_exit_pattern_explorer import rows

OUT = V2 / "research_k/h0_exit_interaction_explorer_2014_2019.json"
FEATURES = ["rank", "m12_rank", "m18_rank", "rank_deterioration", "score_change",
            "tenure_panels", "rebalance_turnover", "market_median_26w", "market_breadth_26w"]


def matrix(data):
    # Median fill is fit only on the current training sample and then reused.
    return np.asarray([[np.nan if r[k] is None else r[k] for k in FEATURES] for r in data], float)


def main():
    all_rows = rows()
    train = [r for r in all_rows if r["date"] < "2017-01-01"]
    test = [r for r in all_rows if r["date"] >= "2017-01-01"]
    xtrain, xtest = matrix(train), matrix(test)
    med = np.nanmedian(xtrain, axis=0)
    xtrain = np.where(np.isnan(xtrain), med, xtrain)
    xtest = np.where(np.isnan(xtest), med, xtest)
    ytrain = np.asarray([r["target"] for r in train])
    ytest = np.asarray([r["target"] for r in test])
    # Fixed shallow model. It is a discovery screen, not a deployable rule.
    model = DecisionTreeRegressor(max_depth=2, min_samples_leaf=20, random_state=20260816)
    model.fit(xtrain, ytrain)
    ptrain, ptest = model.predict(xtrain), model.predict(xtest)
    def score(y, p):
        pick = p > 0
        return {"n": int(len(y)), "correlation": round(float(np.corrcoef(y, p)[0, 1]), 4) if p.std() and y.std() else None,
                "positive_prediction_n": int(pick.sum()),
                "positive_prediction_realised_mean": None if not pick.any() else round(float(y[pick].mean()), 4),
                "positive_prediction_realised_share": None if not pick.any() else round(float((y[pick] > 0).mean()), 4),
                "all_mean": round(float(y.mean()), 4)}
    result = {"version": "H0_EXIT_INTERACTION_EXPLORER_V1", "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "scope": "2014-2019 only; exploratory; 2021-2026 deliberately unread", "features": FEATURES,
              "model": {"type": "DecisionTreeRegressor", "max_depth": 2, "min_samples_leaf": 20, "random_state": 20260816},
              "tree": export_text(model, feature_names=FEATURES), "train_2014_2016": score(ytrain, ptrain), "test_2017_2019": score(ytest, ptest)}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"train": result["train_2014_2016"], "test": result["test_2017_2019"]}, ensure_ascii=False))
    print(result["tree"])


if __name__ == "__main__":
    main()
