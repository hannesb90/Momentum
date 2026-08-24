from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path


ROOT = Path("/home/hannesb/momentum_v2")
RETURNS_PATH = ROOT / "sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3/returns.json"
XACT_PATH = Path("/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST/active/eod/XACT-SVERIGE.json.gz")
OUT_DIR = ROOT / "research_k/h0_external_omx_benchmark_v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def annualized(period_returns: list[float], periods_per_year: int = 13) -> float | None:
    if not period_returns:
        return None
    wealth = 1.0
    for ret in period_returns:
        wealth *= 1.0 + ret
    return wealth ** (periods_per_year / len(period_returns)) - 1.0


def max_drawdown(period_returns: list[float]) -> float | None:
    if not period_returns:
        return None
    wealth = 1.0
    peak = 1.0
    worst = 0.0
    for ret in period_returns:
        wealth *= 1.0 + ret
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    return worst


def first_strictly_after(dates: list[str], boundary: str) -> str | None:
    return next((d for d in dates if d > boundary), None)


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    returns = json.loads(RETURNS_PATH.read_text())
    xact = json.loads(gzip.open(XACT_PATH, "rt").read())
    xact_dates = [row["date"] for row in xact]
    xact_adj = {row["date"]: row["adjusted_close"] for row in xact}

    aligned = []
    for idx, row in enumerate(returns[:-1]):
        next_panel = returns[idx + 1]["panel_date"]
        entry_date = first_strictly_after(xact_dates, row["panel_date"])
        exit_date = first_strictly_after(xact_dates, next_panel)
        if not entry_date or not exit_date:
            raise RuntimeError(f"Missing XACT execution date for {row['panel_date']} -> {next_panel}")
        omx_return = xact_adj[exit_date] / xact_adj[entry_date] - 1.0
        aligned.append(
            {
                "panel_date": row["panel_date"],
                "next_panel_date": next_panel,
                "h0_net_return": row["net_return"],
                "internal_benchmark_return": row["benchmark_return"],
                "omx_proxy_return": omx_return,
                "entry_execution_date": entry_date,
                "exit_execution_date": exit_date,
                "execution_rule": "FIRST_CLOSE_STRICTLY_AFTER_DECISION",
                "omx_proxy_label": "OMX Sthlm bred (XACT Sverige ETF proxy)",
                "omx_proxy_ticker": "XACT-SVERIGE.ST",
            }
        )

    h0_returns = [row["h0_net_return"] for row in aligned]
    internal_returns = [row["internal_benchmark_return"] for row in aligned]
    omx_returns = [row["omx_proxy_return"] for row in aligned]

    summary = {
        "version": "H0_EXTERNAL_OMX_BENCHMARK_V1",
        "scope": "Secondary external benchmark addendum; does not replace the frozen internal equal-weight PIT benchmark.",
        "champion_source": str(RETURNS_PATH.relative_to(ROOT)),
        "omx_proxy_source": str(XACT_PATH),
        "omx_proxy_label": "OMX Sthlm bred (XACT Sverige ETF proxy)",
        "period_count": len(aligned),
        "start_panel_date": aligned[0]["panel_date"],
        "end_panel_date": aligned[-1]["panel_date"],
        "first_execution_date": aligned[0]["entry_execution_date"],
        "last_exit_execution_date": aligned[-1]["exit_execution_date"],
        "h0_cagr": annualized(h0_returns),
        "internal_benchmark_cagr": annualized(internal_returns),
        "omx_proxy_cagr": annualized(omx_returns),
        "h0_excess_vs_internal_cagr": annualized(h0_returns) - annualized(internal_returns),
        "h0_excess_vs_omx_proxy_cagr": annualized(h0_returns) - annualized(omx_returns),
        "omx_proxy_max_drawdown": max_drawdown(omx_returns),
        "omx_proxy_total_return": math.prod(1.0 + x for x in omx_returns) - 1.0,
        "method_note": "OMX is proxied by XACT-SVERIGE adjusted-close returns chained over the same frozen H0 post-decision 8-week boundaries.",
        "limitations": [
            "This is an external market comparator, not the frozen internal benchmark used in preregistered D-G decisions.",
            "The comparator uses an ETF proxy rather than an official index file.",
            "No transaction cost is applied to the external OMX proxy."
        ],
    }

    period_path = OUT_DIR / "period_returns.json"
    summary_path = OUT_DIR / "summary.json"
    manifest_path = OUT_DIR / "manifest.json"

    period_path.write_text(json.dumps(aligned, ensure_ascii=False, indent=2) + "\n")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    manifest = {
        "version": "H0_EXTERNAL_OMX_BENCHMARK_V1",
        "inputs": [
            {"path": str(RETURNS_PATH.relative_to(ROOT)), "sha256": sha256_path(RETURNS_PATH)},
            {"path": str(XACT_PATH), "sha256": sha256_path(XACT_PATH)},
        ],
        "outputs": [
            {"path": str(period_path.relative_to(ROOT)), "sha256": sha256_path(period_path)},
            {"path": str(summary_path.relative_to(ROOT)), "sha256": sha256_path(summary_path)},
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    build()
