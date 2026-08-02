"""Build isolated weekly features and recover Börsdata IDs for delisted stocks.

Nothing is written to production caches.  Börsdata IDs are recovered only from
daily return-path agreement between EODHD and cached Börsdata histories; names
and current instrument lists are not trusted for delisted securities.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import config
from features.feature_engineering import build_features


ROOT = Path(__file__).resolve().parents[1]
EOD = ROOT / "momentum_ml/cache/eodhd_delisted"
BORSDATA = ROOT / "momentum_ml/cache/borsdata"
COVERAGE = ROOT / "results/point_in_time/eodhd_delisted_coverage.csv"
OUTDIR = ROOT / "results/niva3_delisted_features"
MAPPING = ROOT / "results/niva3_delisted_borsdata_mapping.csv"
REPORT = ROOT / "results/niva3_delisted_feature_build.json"


def _returns(frame: pd.DataFrame, date: str, close: str) -> pd.Series:
    x = frame[[date, close]].copy(); x[date] = pd.to_datetime(x[date], errors="coerce")
    x[close] = pd.to_numeric(x[close], errors="coerce")
    return x.dropna().drop_duplicates(date).set_index(date)[close].sort_index().pct_change().dropna()


def match_score(eod: pd.DataFrame, bors: pd.DataFrame) -> dict:
    a = _returns(eod, "Date", "Close").rename("a")
    b = _returns(bors, "d", "c").rename("b")
    return match_return_score(a, b)


def match_return_score(a: pd.Series, b: pd.Series) -> dict:
    joined = pd.concat([a, b], axis=1, join="inner").dropna().tail(260)
    if len(joined) < 60:
        return {"overlap": len(joined), "correlation": np.nan, "median_abs_return_diff": np.nan}
    return {"overlap": len(joined), "correlation": float(joined.a.corr(joined.b)),
            "median_abs_return_diff": float((joined.a - joined.b).abs().median())}


def _load_borsdata() -> pd.DataFrame:
    out = {}
    for path in BORSDATA.glob("stockprices_*_max20.json"):
        try:
            payload = json.loads(path.read_text())
            frame = pd.DataFrame(payload.get("stockPricesList", []))
            if not frame.empty:
                out[int(payload["instrument"])] = _returns(frame, "d", "c")
        except Exception:
            continue
    return pd.DataFrame(out).sort_index()


def _all_match_scores(eod_returns: pd.Series, bors_returns: pd.DataFrame) -> pd.DataFrame:
    dates = eod_returns.index[-260:]
    matrix = bors_returns.reindex(dates)
    target = eod_returns.reindex(dates)
    overlap = matrix.notna().sum()
    corr = matrix.corrwith(target, axis=0)
    diff = matrix.sub(target, axis=0).abs().median()
    return pd.DataFrame({"overlap": overlap, "correlation": corr,
                         "median_abs_return_diff": diff})


def _weekly_adjusted(frame: pd.DataFrame) -> pd.DataFrame:
    x = frame.copy(); x["Date"] = pd.to_datetime(x.Date, errors="coerce"); x = x.dropna(subset=["Date", "Close"])
    ratio = (pd.to_numeric(x.AdjustedClose, errors="coerce") /
             pd.to_numeric(x.Close, errors="coerce")).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    for col in ("Open", "High", "Low", "Close"):
        x[col] = pd.to_numeric(x[col], errors="coerce") * ratio
    x["Volume"] = pd.to_numeric(x.Volume, errors="coerce").fillna(0)
    x = x.set_index("Date").sort_index()
    return x.resample("W-MON").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Close"])


def main():
    coverage = pd.read_csv(COVERAGE)
    tickers = coverage.loc[coverage.complete_from_listing.fillna(False).astype(bool), "ticker"].tolist()
    bors = _load_borsdata(); rows = []; built = []
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        path = EOD / f"{ticker.replace('.', '_')}.csv"
        eod = pd.read_csv(path)
        eod_returns = _returns(eod, "Date", "Close").rename("a")
        candidates = []
        scores = _all_match_scores(eod_returns, bors)
        for instrument, score_row in scores[scores.overlap.ge(60) & scores.correlation.notna()].iterrows():
            score = {"overlap": int(score_row.overlap), "correlation": float(score_row.correlation),
                     "median_abs_return_diff": float(score_row.median_abs_return_diff)}
            candidates.append((int(instrument), score))
        candidates.sort(key=lambda z: (z[1]["correlation"], -z[1]["median_abs_return_diff"]), reverse=True)
        best = candidates[0] if candidates else (None, {"overlap": 0, "correlation": np.nan,
                                                        "median_abs_return_diff": np.nan})
        second_corr = candidates[1][1]["correlation"] if len(candidates) > 1 else np.nan
        accepted = bool(best[0] is not None and best[1]["correlation"] >= .995
                        and best[1]["median_abs_return_diff"] <= .002
                        and (not np.isfinite(second_corr) or best[1]["correlation"] - second_corr >= .002))
        report_path = BORSDATA / f"reports_{best[0]}_max20.json" if best[0] is not None else None
        rows.append({"ticker": ticker, "borsdata_instrument": best[0], **best[1],
                     "second_correlation": second_corr, "accepted": accepted,
                     "reports_cached": bool(report_path and report_path.exists())})
        weekly = _weekly_adjusted(eod)
        feat = build_features(weekly)
        feat.to_pickle(OUTDIR / f"{ticker}.pkl")
        built.append({"ticker": ticker, "weekly_rows": len(weekly), "feature_rows": len(feat),
                      "start": str(weekly.index.min().date()), "end": str(weekly.index.max().date())})
        print(ticker, "features", len(feat), "match", best[0], f"corr={best[1]['correlation']:.5f}",
              "accepted", accepted, flush=True)
    mapping = pd.DataFrame(rows); mapping.to_csv(MAPPING, index=False)
    report = {"status": "PASS", "complete_eodhd_series": len(tickers), "feature_files": len(built),
              "accepted_borsdata_matches": int(mapping.accepted.sum()),
              "accepted_with_reports": int((mapping.accepted & mapping.reports_cached).sum()),
              "mapping_method": "daily_return_path_corr>=0.995,diff<=0.002,runnerup_margin>=0.002",
              "production_cache_modified": False, "builds": built}
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "builds"}, indent=2))


if __name__ == "__main__":
    main()
