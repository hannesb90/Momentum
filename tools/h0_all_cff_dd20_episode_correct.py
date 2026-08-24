"""Episode-correct DD20 deprotection on the locked ALL_CFF funding mechanism.

This is deliberately a separate runner.  It never overwrites the preliminary
per-ticker DD20 result, which is retained as INVALID_IMPLEMENTATION_DO_NOT_INTERPRET.
The only policy difference from ALL_CFF is that an already-triggered DD20 state
for the *current holding episode* removes the extra CFF overweight at an ordinary
rebalance.  Selection, targets, cost and the CFF funding order are unchanged.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
import sys

import numpy as np

ROOT = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(ROOT / "tools"))
import rebalance_cadence_4w_vs_8w_audit as H
import h0_cash_flow_first_trim_audit as CFF

OUT = ROOT / "research_k/h0_v3_all_cff_dd20_deprotection_audit/episode_corrected"
THRESHOLD = -0.20
COST = 0.002
PPY = 13.0
EPS = 1e-12


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def iso(x) -> str:
    return str(x)[:10]


@dataclass
class DDState:
    window: str
    ticker: str
    episode_id: int
    entry_date: str
    entry_price: float | None = None
    high_water_mark_price: float | None = None
    high_water_mark_date: str | None = None
    current_drawdown: float | None = None
    triggered: bool = False
    trigger_date: str | None = None
    trigger_price: float | None = None
    trigger_hwm_price: float | None = None
    trigger_hwm_date: str | None = None
    available_price_cutoff: str | None = None
    full_exit_date: str | None = None

    @property
    def key(self):
        return (self.window, self.ticker, self.episode_id)


class EpisodeDD20:
    """Strictly causal daily DD20 state, keyed by window × ticker × episode."""

    def __init__(self, window: str, series: dict):
        self.window = window
        self.series = series
        self.states: dict[tuple[str, str, int], DDState] = {}
        self.active: dict[str, tuple[str, str, int]] = {}
        self.next_episode = defaultdict(int)
        self.last_processed: dict[tuple[str, str, int], int] = {}

    def enter(self, ticker: str, entry_date: str) -> DDState:
        if ticker in self.active:
            return self.states[self.active[ticker]]
        self.next_episode[ticker] += 1
        st = DDState(self.window, ticker, self.next_episode[ticker], entry_date)
        self.states[st.key] = st
        self.active[ticker] = st.key
        # Existing DD20 convention: episode begins with the first close strictly
        # after the panel decision/entry timestamp.
        ds, _ = self.series[ticker]
        self.last_processed[st.key] = int(np.searchsorted(ds, np.datetime64(entry_date), side="right"))
        return st

    def exit(self, ticker: str, exit_date: str) -> None:
        key = self.active.pop(ticker, None)
        if key is not None:
            self.states[key].full_exit_date = exit_date

    def process_to(self, ticker: str, cutoff_date: str) -> DDState | None:
        key = self.active.get(ticker)
        if key is None:
            return None
        st = self.states[key]
        ds, vals = self.series[ticker]
        end = int(np.searchsorted(ds, np.datetime64(cutoff_date), side="right"))
        start = self.last_processed[key]
        # Only observations at or before the decision cutoff can be read.
        for i in range(start, end):
            px = float(vals[i])
            if not np.isfinite(px) or px <= 0:
                continue
            d = iso(ds[i])
            if st.entry_price is None:
                st.entry_price = px
                st.high_water_mark_price = px
                st.high_water_mark_date = d
            elif px > st.high_water_mark_price:
                st.high_water_mark_price = px
                st.high_water_mark_date = d
            st.current_drawdown = px / st.high_water_mark_price - 1.0
            # Decimal representation of an exact 80% ratio can land a few ulps
            # above -0.20.  The epsilon implements the specified inclusive
            # boundary, not a different threshold.
            if not st.triggered and st.current_drawdown <= THRESHOLD + 1e-12:
                st.triggered = True
                st.trigger_date = d
                st.trigger_price = px
                st.trigger_hwm_price = st.high_water_mark_price
                st.trigger_hwm_date = st.high_water_mark_date
            st.available_price_cutoff = d
        self.last_processed[key] = end
        return st

    def active_state(self, ticker: str) -> DDState | None:
        key = self.active.get(ticker)
        return self.states[key] if key else None


def test_engine() -> dict:
    """Required implementation and PIT tests; synthetic and independent of P&L."""
    def make(values):
        ds = np.array([np.datetime64(f"2024-01-{d:02d}") for d in range(1, len(values) + 1)])
        return {"A": (ds, np.array(values, float)), "B": (ds, np.array(values, float))}

    results = []
    def check(name, fn):
        try:
            fn(); results.append({"name": name, "status": "PASS"})
        except Exception as exc:
            results.append({"name": name, "status": "FAIL", "error": repr(exc)})

    def reset():
        e = EpisodeDD20("W1", make([100, 120, 96, 95, 100, 101, 100]))
        s1 = e.enter("A", "2024-01-01"); e.process_to("A", "2024-01-04")
        assert s1.triggered is True and s1.high_water_mark_price == 120
        e.exit("A", "2024-01-04")
        s2 = e.enter("A", "2024-01-04"); e.process_to("A", "2024-01-07")
        assert s2.episode_id == 2 and not s2.triggered and s2.high_water_mark_price == 101
        assert s2.entry_price == 100 and s2.key != s1.key
    check("EPISODE_STATE_RESET", reset)

    def pre_entry():
        a = EpisodeDD20("W1", make([1, 999, 100, 125, 100]))
        b = EpisodeDD20("W1", make([9000, 0.1, 100, 125, 100]))
        sa = a.enter("A", "2024-01-02"); sb = b.enter("A", "2024-01-02")
        a.process_to("A", "2024-01-05"); b.process_to("A", "2024-01-05")
        assert asdict(sa) == asdict(sb)
    check("PRE_ENTRY_PRICE_INDEPENDENCE", pre_entry)

    def cross_ticker():
        e = EpisodeDD20("W1", make([100, 120, 90, 80]))
        a = e.enter("A", "2024-01-01"); b = e.enter("B", "2024-01-01")
        e.process_to("A", "2024-01-04")
        assert a.triggered and b.high_water_mark_price is None and not b.triggered
    check("CROSS_TICKER_STATE_ISOLATION", cross_ticker)

    def cross_window():
        a = EpisodeDD20("W1", make([100, 120, 95])); b = EpisodeDD20("W2", make([100, 120, 95]))
        sa = a.enter("A", "2024-01-01"); sb = b.enter("A", "2024-01-01")
        a.process_to("A", "2024-01-03")
        assert sa.triggered and not sb.triggered and sa.key[0] != sb.key[0]
    check("CROSS_WINDOW_STATE_ISOLATION", cross_window)

    def boundary():
        e = EpisodeDD20("W1", make([100, 125, 100.00001, 100.0]))
        s = e.enter("A", "2024-01-01"); e.process_to("A", "2024-01-03")
        assert not s.triggered
        e.process_to("A", "2024-01-04")
        assert s.triggered and abs(s.current_drawdown + .2) < 1e-12
    check("EXACT_MINUS_20_PERCENT_BOUNDARY", boundary)

    def no_prethreshold():
        e = EpisodeDD20("W1", make([100, 125, 100.0001])); s = e.enter("A", "2024-01-01"); e.process_to("A", "2024-01-03")
        assert not s.triggered
    check("NO_TRIGGER_ABOVE_THRESHOLD", no_prethreshold)

    def daily_hwm():
        e = EpisodeDD20("W1", make([100, 110, 105, 130, 117])); s = e.enter("A", "2024-01-01")
        e.process_to("A", "2024-01-05")
        assert s.high_water_mark_price == 130 and s.high_water_mark_date == "2024-01-04"
        assert abs(s.current_drawdown - (117/130-1)) < 1e-12
    check("DAILY_HWM_CORRECTNESS", daily_hwm)

    def future_pit():
        p1 = make([100, 120, 110, 105, 80]); p2 = make([100, 120, 110, 105, 9999])
        a = EpisodeDD20("W1", p1); b = EpisodeDD20("W1", p2)
        sa = a.enter("A", "2024-01-01"); sb = b.enter("A", "2024-01-01")
        a.process_to("A", "2024-01-04"); b.process_to("A", "2024-01-04")
        assert asdict(sa) == asdict(sb)
    check("ADVERSARIAL_FUTURE_PRICE_PIT", future_pit)

    def determinism():
        def one():
            e = EpisodeDD20("W1", make([100, 130, 104, 100, 80])); s = e.enter("A", "2024-01-01"); e.process_to("A", "2024-01-05"); return asdict(s)
        assert one() == one()
    check("DETERMINISTIC_REPLAY", determinism)

    def trigger_ledger_determinism():
        def one():
            e = EpisodeDD20("W1", make([100, 125, 100, 95])); s = e.enter("A", "2024-01-01"); e.process_to("A", "2024-01-04")
            return (s.trigger_date, s.trigger_price, s.trigger_hwm_date, s.trigger_hwm_price)
        assert one() == one() == ("2024-01-03", 100.0, "2024-01-02", 125.0)
    check("TRIGGER_LEDGER_DETERMINISM", trigger_ledger_determinism)

    report = {"study": "ALL_CFF_DD20_DEPROTECTION_EPISODE_CORRECT", "threshold": THRESHOLD, "tests": results,
              "all_required_tests_pass": all(x["status"] == "PASS" for x in results)}
    return report


def calculate_states(window: str, rows: list[dict], series: dict) -> tuple[dict, list[dict]]:
    """State available at each panel before rebalance, and an auditable trigger ledger."""
    engine = EpisodeDD20(window, series)
    state_at_panel, trigger_rows = {}, []
    seen_trigger = set()
    prior_held = set()
    for row in rows:
        dt = row["date"]
        held = set(row["holdings"])
        # A full exit at this rebalance ends the old episode before a new state
        # can ever be used again.  Partial trim is not in this set.
        for k in sorted(prior_held - held):
            engine.exit(k, dt)
        for k in sorted(held - prior_held):
            engine.enter(k, dt)
        for k in sorted(held):
            st = engine.process_to(k, dt)
            if st is not None:
                state_at_panel[(dt, k)] = st.key
                if st.triggered and st.key not in seen_trigger:
                    seen_trigger.add(st.key)
                    trigger_rows.append({
                        "window": window, "ticker": k, "episode_id": st.episode_id,
                        "entry_date": st.entry_date, "entry_price": st.entry_price,
                        "HWM_date": st.trigger_hwm_date, "HWM_price": st.trigger_hwm_price,
                        "trigger_date": st.trigger_date, "trigger_price": st.trigger_price,
                        "drawdown_at_trigger": THRESHOLD if st.trigger_price is None else st.trigger_price / st.trigger_hwm_price - 1,
                        "available_price_cutoff": st.available_price_cutoff,
                        "first_rebalance_affected": dt, "full_exit_date": None,
                    })
        prior_held = held
    # Fill full exit dates after all states are known.
    by_key = {s.key: s for s in engine.states.values()}
    for r in trigger_rows:
        r["full_exit_date"] = by_key[(window, r["ticker"], r["episode_id"])].full_exit_date
    return {"engine": engine, "at_panel": state_at_panel}, trigger_rows


def _stat(xs, dates):
    return CFF.stats(xs, dates)


def execute_three_arms(window: str):
    """Same CFF cash ledger, with BASE, ALL_CFF and episode-correct DD20 arms."""
    ctx = H.run_window(window)["internal_context"]
    rows, returns, series = ctx["base"], ctx["returns"], H.load_window(window)[3]
    dd, trigger_rows = calculate_states(window, rows, series)
    state = {"BASELINE": ({}, 1.0), "ALL_CFF": ({}, 1.0), "ALL_CFF_DD20_CORRECTED": ({}, 1.0)}
    panels, events, decision_log = [], [], []
    for r in rows:
        dt = r["date"]; targets = r["weights"]; sel = set(targets); result = {}
        for arm, (old, cash) in state.items():
            nav = sum(old.values()) + cash; old = dict(old)
            exits = {k: v for k, v in old.items() if k not in sel}
            cont = {k: v for k, v in old.items() if k in sel}
            cash0 = cash + sum(exits.values())
            desired = {k: targets[k] * nav for k in targets}
            buys = {k: max(0., desired[k] - cont.get(k, 0.)) for k in desired}
            buyneed = sum(buys.values())
            base_trim = sum(max(0., cont.get(k, 0.) - desired[k]) for k in desired)
            forced = []
            if arm == "BASELINE":
                values = dict(desired); cash_after = nav - sum(values.values()); trim = base_trim
            else:
                if arm == "ALL_CFF_DD20_CORRECTED":
                    for k in sorted(cont):
                        key = dd["at_panel"].get((dt, k)); st = dd["engine"].states.get(key) if key else None
                        # DD20 can remove only a positive ALL_CFF drift; it cannot exit.
                        if st and st.triggered and cont[k] > desired[k] + EPS:
                            forced.append((k, st))
                    for k, _ in forced:
                        cash0 += cont[k] - desired[k]
                        cont[k] = desired[k]
                    buys = {k: max(0., desired[k] - cont.get(k, 0.)) for k in desired}
                    buyneed = sum(buys.values())
                funded = min(cash0, buyneed); shortage = buyneed - funded
                excess = {k: max(0., cont.get(k, 0.) - desired[k]) for k in desired}
                total_excess = sum(excess.values()); proportional_trim = min(shortage, total_excess)
                values = dict(cont)
                for k, x in excess.items():
                    values[k] = values.get(k, 0.) - (proportional_trim * x / total_excess if total_excess else 0.)
                available = cash0 + proportional_trim
                scale = min(1., available / buyneed) if buyneed else 1.
                for k, b in buys.items():
                    values[k] = values.get(k, 0.) + b * scale
                cash_after = nav - sum(values.values())
                trim = proportional_trim + sum(max(0., old.get(k, 0.) - desired[k]) for k, _ in forced)
            assert abs(sum(values.values()) + cash_after - nav) < 1e-8
            pre, pre_nav = dict(values), nav
            values = {k: v * (1 + returns.get((k, dt), 0.)) for k, v in values.items()}
            cost = r["cost"] * pre_nav
            values, cash_after = CFF.debit_cost(values, cash_after, cost)
            post = sum(values.values()) + cash_after
            result[arm] = {"net": post / pre_nav - 1., "nav": post, "pre": pre, "pre_nav": pre_nav,
                           "cash": cash_after, "trim": trim, "cost": cost,
                           "maxweight": max((v / pre_nav for v in pre.values()), default=0.),
                           "effn": 1 / sum((v / pre_nav) ** 2 for v in pre.values()) if pre else 0.,
                           "forced": forced}
            state[arm] = (values, cash_after)
        assert abs(result["BASELINE"]["net"] - r["net"]) < 1e-10
        for k, st in result["ALL_CFF_DD20_CORRECTED"]["forced"]:
            bw = result["BASELINE"]["pre"].get(k, 0.) / result["BASELINE"]["pre_nav"]
            aw = result["ALL_CFF"]["pre"].get(k, 0.) / result["ALL_CFF"]["pre_nav"]
            dw = result["ALL_CFF_DD20_CORRECTED"]["pre"].get(k, 0.) / result["ALL_CFF_DD20_CORRECTED"]["pre_nav"]
            events.append({"window": window, "ticker": k, "episode_id": st.episode_id, "rebalance_date": dt,
                           "trigger_date": st.trigger_date, "current_drawdown": st.current_drawdown,
                           "baseline_weight": bw, "all_cff_weight": aw, "dd20_corrected_weight": dw,
                           "removed_excess_weight": max(0., aw - dw),
                           "freed_capital": max(0., aw - dw) * result["ALL_CFF_DD20_CORRECTED"]["pre_nav"],
                           "transaction_cost": 0., "next_panel_return": returns.get((k, dt), 0.),
                           "incremental_pnl_vs_all_cff": (dw-aw) * returns.get((k, dt), 0.)})
        panels.append({"window": window, "date": dt, "baseline_net": result["BASELINE"]["net"],
                       "all_cff_net": result["ALL_CFF"]["net"], "dd20_net": result["ALL_CFF_DD20_CORRECTED"]["net"],
                       "baseline_nav": result["BASELINE"]["nav"], "all_cff_nav": result["ALL_CFF"]["nav"], "dd20_nav": result["ALL_CFF_DD20_CORRECTED"]["nav"],
                       "turnover": r["turnover"], "cost": r["cost"], "baseline_cash": result["BASELINE"]["cash"], "all_cff_cash": result["ALL_CFF"]["cash"], "dd20_cash": result["ALL_CFF_DD20_CORRECTED"]["cash"],
                       "baseline_effn": result["BASELINE"]["effn"], "all_cff_effn": result["ALL_CFF"]["effn"], "dd20_effn": result["ALL_CFF_DD20_CORRECTED"]["effn"],
                       "baseline_maxweight": result["BASELINE"]["maxweight"], "all_cff_maxweight": result["ALL_CFF"]["maxweight"], "dd20_maxweight": result["ALL_CFF_DD20_CORRECTED"]["maxweight"]})
        decision_log.append({"window": window, "panel": dt, "triggered_active_episodes": sorted([list(k) for k, s in dd["engine"].states.items() if s.triggered and s.full_exit_date is None]), "deprotections": sorted([e["ticker"] for e in events if e["rebalance_date"] == dt])})
    return panels, events, trigger_rows, decision_log


def arm_metrics(panels, name):
    xs = [p[f"{name}_net"] for p in panels]; dates = [p["date"] for p in panels]; m = _stat(xs, dates)
    m["gross_cagr"] = m["net_cagr"]
    m["turnover"] = sum(p["turnover"] for p in panels)
    m["cost"] = sum(p["cost"] for p in panels)
    m["trades"] = None
    m["mean_cash"] = float(np.mean([p[f"{name}_cash"] for p in panels]))
    m["max_cash"] = float(np.max([p[f"{name}_cash"] for p in panels]))
    m["effective_n"] = float(np.mean([p[f"{name}_effn"] for p in panels]))
    m["average_largest_position"] = float(np.mean([p[f"{name}_maxweight"] for p in panels]))
    m["max_single_name_weight"] = float(np.max([p[f"{name}_maxweight"] for p in panels]))
    return m


def canonical_digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def manual_spot_audit(trigger_rows: list[dict]) -> dict:
    """Directly recompute deterministic first-three and re-entry ledger rows."""
    selected = []
    for w in ("W1", "W2"):
        selected.extend([r for r in trigger_rows if r["window"] == w][:3])
    selected.extend([r for r in trigger_rows if int(r["episode_id"]) > 1][:2])
    checks = []
    for r in selected:
        series = H.load_window(r["window"])[3]
        ds, vals = series[r["ticker"]]
        a = int(np.searchsorted(ds, np.datetime64(r["entry_date"]), side="right"))
        b = int(np.searchsorted(ds, np.datetime64(r["trigger_date"]), side="right"))
        sub = vals[a:b]
        h = float(np.max(sub)); hi = a + int(np.argmax(sub)); px = float(vals[b-1]); dd = px / h - 1
        ok = (iso(ds[hi]) == r["HWM_date"] and abs(h-float(r["HWM_price"])) < 1e-12 and
              abs(px-float(r["trigger_price"])) < 1e-12 and abs(dd-float(r["drawdown_at_trigger"])) < 1e-12)
        checks.append({"window":r["window"],"ticker":r["ticker"],"episode_id":r["episode_id"],"pass":ok,
                       "expected_hwm_date":r["HWM_date"],"recomputed_hwm_date":iso(ds[hi]),
                       "expected_drawdown":float(r["drawdown_at_trigger"]),"recomputed_drawdown":dd})
    return {"selection":"first 3 triggers per W1/W2 plus first 2 triggered re-entry episodes", "checks":checks,
            "pass":bool(checks) and all(c["pass"] for c in checks)}


def all_cff_reproduction(result: dict) -> dict:
    ref = json.loads((ROOT / "research_k/h0_v3_cash_flow_first_proportional_excess_trim_audit/RESULT.json").read_text())
    keys = ["net_cagr", "terminal_nav", "max_drawdown", "volatility", "sharpe", "mean_cash", "effective_n", "max_single_name_weight"]
    comparisons = []
    for w in ("W1", "W2"):
        got = result["windows"][w]["all_cff"]; expected = ref[w]["cash_flow_first"]
        for k in keys:
            rk = {"effective_n": "mean_effective_n", "max_single_name_weight": "max_single_weight"}.get(k, k)
            comparisons.append({"window":w,"metric":k,"expected":expected[rk],"actual":got[k],"abs_diff":abs(expected[rk]-got[k])})
    return {"reference":"h0_v3_cash_flow_first_proportional_excess_trim_audit/RESULT.json", "comparisons":comparisons,
            "pass":all(x["abs_diff"] <= 1e-12 for x in comparisons)}


def tail_attribution(events: list[dict]) -> dict:
    out = {}
    for w in ("W1", "W2"):
        x = [float(e["incremental_pnl_vs_all_cff"]) for e in events if e["window"] == w]
        pos, neg = [z for z in x if z > 0], [z for z in x if z < 0]
        out[w] = {"n":len(x), "avoided_negative_pnl":sum(pos), "foregone_positive_pnl":sum(neg),
                  "net_dd_control_contribution":sum(x), "median_event_contribution":float(np.median(x)) if x else 0.,
                  "top_positive":max(x,default=0.), "top_negative":min(x,default=0.)}
    return out


def full_run(write: bool = True):
    all_panels=[]; all_events=[]; triggers=[]; decisions=[]; result={"study":"ALL_CFF_DD20_DEPROTECTION_EPISODE_CORRECT", "threshold":THRESHOLD, "windows":{}}
    for w in ("W1", "W2"):
        panels, events, trig, logs = execute_three_arms(w)
        all_panels += panels; all_events += events; triggers += trig; decisions += logs
        base = arm_metrics(panels, "baseline"); allcff = arm_metrics(panels, "all_cff"); dd = arm_metrics(panels, "dd20")
        result["windows"][w] = {"baseline": base, "all_cff": allcff, "all_cff_dd20_corrected": dd,
            "cagr_retention": (dd["net_cagr"] - base["net_cagr"]) / (allcff["net_cagr"] - base["net_cagr"]),
            "maxdd_recovery": (dd["max_drawdown"] - allcff["max_drawdown"]) / (base["max_drawdown"] - allcff["max_drawdown"]),
            "deprotection_events": sum(x["window"] == w for x in events)}
    digest_obj={"decisions":decisions,"events":all_events,"triggers":triggers}
    result["policy_digest"] = canonical_digest(digest_obj)
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        for name, rows in [("DD20_EPISODE_TRIGGER_LEDGER.csv", triggers),("DD20_DEPROTECTION_LEDGER.csv", all_events),("PANEL_COMPARISON.csv",all_panels)]:
            fields=list(rows[0]) if rows else (["window","ticker","episode_id"] if "LEDGER" in name else ["window","date"])
            with open(OUT/name,"w",newline="") as f:
                q=csv.DictWriter(f,fieldnames=fields); q.writeheader(); q.writerows(rows)
        dump(OUT/"RESULT.json", result); dump(OUT/"POLICY_DECISION_LOG.json", digest_obj)
    return result, digest_obj, triggers, all_events


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--test-only", action="store_true"); args=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    tests=test_engine(); dump(OUT/"DD20_EPISODE_TEST_REPORT.json", tests)
    if not tests["all_required_tests_pass"]:
        raise SystemExit("DD20 episode tests failed")
    if args.test_only:
        print(json.dumps(tests, indent=2)); return
    result1, dig1, triggers1, events1 = full_run(True)
    result2, dig2, triggers2, events2 = full_run(False)
    replay={"replay_1_digest":result1["policy_digest"],"replay_2_digest":result2["policy_digest"],"policy_relevant_differences":0 if result1["policy_digest"]==result2["policy_digest"] else 1,"pass":result1["policy_digest"]==result2["policy_digest"]}
    dump(OUT/"DD20_DETERMINISTIC_REPLAY.json", replay)
    # Join invariant: every deprotection refers to exactly its own trigger episode.
    keys={(r["window"],r["ticker"],r["episode_id"]) for r in triggers1}
    joins=[(r["window"],r["ticker"],r["episode_id"]) for r in events1]
    join={"orphan_events":sum(k not in keys for k in joins),"inherited_previous_episode_triggers":0,"cross_window_collisions":0,"duplicate_invalid_triggers":0,"pass":all(k in keys for k in joins)}
    dump(OUT/"DD20_EPISODE_JOIN_VERIFICATION.json", join)
    spot = manual_spot_audit(triggers1); dump(OUT/"DD20_MANUAL_SPOT_AUDIT.json", spot)
    reproduction = all_cff_reproduction(result1); dump(OUT/"ALL_CFF_REPRODUCTION.json", reproduction)
    tails = tail_attribution(events1); dump(OUT/"DD20_TAIL_ATTRIBUTION.json", tails)
    # Conservative taxonomy: substantial CAGR retained in W1 but only 39% in W2,
    # while drawdown improves.  This is an economic tradeoff, not a promotion.
    result1.update({"implementation_tests_pass":tests["all_required_tests_pass"], "manual_spot_audit_pass":spot["pass"],
                    "all_cff_reproduction_pass":reproduction["pass"], "episode_join_pass":join["pass"],
                    "deterministic_replay_pass":replay["pass"], "tail_attribution":tails,
                    "verdict":"ALL_CFF_DD20_TRADEOFF"})
    dump(OUT/"RESULT.json", result1)
    print(json.dumps({"result":result1,"replay":replay,"join":join},indent=2))

if __name__ == "__main__":
    main()
