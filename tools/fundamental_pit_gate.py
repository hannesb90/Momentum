"""FUNDAMENTAL_PIT_GATE — no_future_report_leakage.

En fundamental observation far anvandas tidigast dagen EFTER report_date.
Vi har bara datum, inte klockslag: en rapport kan ha publicerats efter
borsstangning. Den konservativa regeln ar darfor

    first_eligible_research_date = forsta handelsdagen STRIKT EFTER report_date

Ingen intradagsatkomst inferreras. Ingen backfill.

Anvandning:
    g = FundamentalPitGate()
    g.eligible("HUM", 2025, "year", asof="2026-02-09")   -> True/False
    rows = g.available("HUM", "year", asof="2026-03-01") -> endast publicerade rader
"""
from __future__ import annotations

import bisect
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
FUND = V2 / "validated/fundamentals"
TABLES = {"year": "fundamentals_year_validated.json",
          "quarter": "fundamentals_quarter_validated.json",
          "r12": "fundamentals_r12_validated.json"}
PRICES = V2 / "validated/prices_adjustment_repair_v4/prices_validated_adjustment_repair_v4.json"


class FundamentalLeakageError(RuntimeError):
    """Hart fel. Ett test forsokte lasa en rapport fore dess publicering."""


def _d(s: str) -> date:
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


class FundamentalPitGate:
    def __init__(self, log: list | None = None):
        self.log = log if log is not None else []
        self.tables = {}
        self.sha = {}
        for k, f in TABLES.items():
            p = FUND / f
            self.tables[k] = json.loads(p.read_text())
            self.sha[k] = hashlib.sha256(p.read_bytes()).hexdigest()
        P = json.loads(PRICES.read_text())
        self.trading_days = sorted({r["d"] for v in P.values() for r in v})
        self._idx = {}
        for k, rows in self.tables.items():
            for r in rows:
                self._idx.setdefault((r.get("kod"), k), []).append(r)

    def next_trading_day(self, d: str) -> str | None:
        i = bisect.bisect_right(self.trading_days, d)
        return self.trading_days[i] if i < len(self.trading_days) else None

    def first_eligible(self, row: dict) -> str | None:
        rd = row.get("report_date")
        if not rd:
            return None
        return self.next_trading_day(rd)

    def eligible(self, row: dict, asof: str) -> bool:
        fe = self.first_eligible(row)
        return bool(fe and asof >= fe)

    def available(self, kod: str, table: str, asof: str) -> list[dict]:
        """Endast rader vars forsta tillatna forskningsdatum har passerat."""
        out, blocked = [], 0
        for r in self._idx.get((kod, table), []):
            if self.eligible(r, asof):
                out.append(r)
            else:
                blocked += 1
        if blocked:
            self.log.append({"kod": kod, "table": table, "asof": asof, "blocked_rows": blocked})
        return out

    def assert_eligible(self, row: dict, asof: str) -> dict:
        if not self.eligible(row, asof):
            fe = self.first_eligible(row)
            self.log.append({"denied": "PIT", "kod": row.get("kod"), "period_end":
                             row.get("report_end_date"), "report_date": row.get("report_date"),
                             "first_eligible": fe, "asof": asof})
            raise FundamentalLeakageError(
                f"HARD FAIL — fundamental observation anvand fore publicering.\n"
                f"  instrument        : {row.get('kod')}\n"
                f"  periodslut        : {row.get('report_end_date')}\n"
                f"  report_date       : {row.get('report_date')}\n"
                f"  forsta tillatna   : {fe}\n  forskningsdatum   : {asof}\n"
                f"  Regel: forsta handelsdagen STRIKT EFTER report_date. "
                f"Ingen intradagsatkomst inferreras, ingen backfill.")
        return row

    # ---------- QA ----------
    def scan(self) -> dict:
        out = {}
        for k, rows in self.tables.items():
            n = len(rows)
            utan = [r for r in rows if not r.get("report_date")]
            lookahead = [r for r in rows if r.get("report_date") and r.get("report_end_date")
                         and r["report_date"] < r["report_end_date"]]
            lag = [r for r in rows if r.get("report_date") and r.get("report_end_date")
                   and (_d(r["report_date"]) - _d(r["report_end_date"])).days > 180]
            neg = [r for r in rows if r.get("report_date") and r["report_date"] < "1990-01-01"]
            key = {}
            for r in rows:
                key.setdefault((r.get("kod"), r.get("year"), r.get("period")), []).append(r)
            dup = {k2: v for k2, v in key.items() if len(v) > 1}
            noel = [r for r in rows if r.get("report_date") and not self.first_eligible(r)]
            lags = [(_d(r["report_date"]) - _d(r["report_end_date"])).days for r in rows
                    if r.get("report_date") and r.get("report_end_date")]
            lags.sort()
            out[k] = {"n_rader": n, "sha256": self.sha[k],
                      "utan_report_date": len(utan), "look_ahead": len(lookahead),
                      "eftersläpning_over_180d": len(lag), "epokfel": len(neg),
                      "duplicerade_perioder": len(dup),
                      "utan_eligibility_datum_efter_prisserien": len(noel),
                      "eftersläpning_dagar": {"min": lags[0] if lags else None,
                                              "median": lags[len(lags) // 2] if lags else None,
                                              "p95": lags[int(len(lags) * .95)] if lags else None,
                                              "max": lags[-1] if lags else None},
                      "instrument": len({r.get("kod") for r in rows}),
                      "period_span": [min(r["report_end_date"] for r in rows if r.get("report_end_date")),
                                      max(r["report_end_date"] for r in rows if r.get("report_end_date"))]}
        return out
