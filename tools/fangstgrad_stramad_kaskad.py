"""STRAMAD KASKAD — entry M12 Top-30 + M52 Top-N, långsam exit.

Testar fyra varianter baserat på graduationsanalysen:
  CASCADE_50:  Entry M12 Top-30 + M52 Top-50.  Exit: faller ur M52 Top-40.
  CASCADE_60:  Entry M12 Top-30 + M52 Top-60.  Exit: faller ur M52 Top-40.
  CASCADE_70:  Entry M12 Top-30 + M52 Top-70.  Exit: faller ur M52 Top-40.
  CASCADE_H1:  Entry M12 Top-30 + M52 Top-70 + drawdown_resilience > median.
               Exit: faller ur M52 Top-40.

Alla: Max 30 innehav, EW 1/30, SMA200 gate, 20bp kostnad.
Jämförs mot H0 (52w+78w) och förra kaskaden (M52 Top-80).

DIAGNOSTISKT. Rör ingen fryst modell.
"""
from __future__ import annotations
import importlib.util, json, math, statistics
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/fangstgrad_stramad_kaskad_results.json"
PPY, COST = 13.0, 0.002
PHASE_ANCHOR_H0 = "2024-01-26"


def ladda():
    s = importlib.util.spec_from_file_location(
        "h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    core, prices, term = m.load_data()
    rmap, alld = m.execution_engine(core, prices, term)
    _, pser = m.compute_vols(prices, window=60)
    rk_h0 = m.derive_h0_scores(core, prices)
    return m, prices, core, rmap, alld, pser, rk_h0


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
    rankings = {w: {} for w in [12, 52]}
    for dt in dates:
        panel = core_df[core_df.panel_date == dt]
        kods = list(panel.kod)
        for weeks in [12, 52]:
            scores = []
            for kod in kods:
                m = momentum_score(prices, kod, dt, weeks)
                scores.append({"kod": kod, "mom": m})
            scores.sort(key=lambda x: (-(x["mom"] or -999), x["kod"]))
            for i, s in enumerate(scores):
                s["rank"] = i + 1
            rankings[weeks][dt] = scores
    return rankings, dates


def sma200_pass(pser, k, dt):
    if k not in pser:
        return True
    ds, a = pser[k]
    i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
    if i is not None and i >= 200 and a[i] < float(np.mean(a[i - 200:i])):
        return False
    return True


def simulera_kaskad(rankings, prices, alld, rmap, pser, dates, anchor,
                    m12_entry_n=30, m52_entry_n=80, m52_exit_n=40,
                    require_dr_above_median=False):
    prev_held = []
    H, R, T = [], [], []

    for dt in dates:
        sched = alld.index(dt) % 2 == anchor
        r12 = rankings[12][dt]
        r52 = rankings[52][dt]
        rank12 = {r["kod"]: r["rank"] for r in r12}
        rank52 = {r["kod"]: r["rank"] for r in r52}
        all_kods = set(rank12.keys()) | set(rank52.keys())

        # Drawdown resilience filter
        if require_dr_above_median:
            dr_vals = {}
            for kod in all_kods:
                dr_vals[kod] = drawdown_resilience(prices, kod, dt)
            dr_valid = [v for v in dr_vals.values()
                        if v is not None and math.isfinite(v)]
            dr_median = statistics.median(dr_valid) if dr_valid else -0.5
        else:
            dr_vals = {}
            dr_median = -999

        if sched or not prev_held:
            # Entry candidates: M12 Top-N AND M52 Top-N
            entry_candidates = [
                k for k in all_kods
                if rank12.get(k, 999) <= m12_entry_n
                and rank52.get(k, 999) <= m52_entry_n
                and (not require_dr_above_median
                     or (dr_vals.get(k) is not None
                         and dr_vals[k] >= dr_median))
            ]
            # Keep: anything in prev that's still in M52 Top exit_n
            keep = [k for k in prev_held
                    if rank52.get(k, 999) <= m52_exit_n and k in all_kods]
            pool = list(set(entry_candidates + keep))
        else:
            # Off-cycle: keep prev if still in M52 Top exit_n
            keep = [k for k in prev_held
                    if rank52.get(k, 999) <= m52_exit_n and k in all_kods]
            # New entries from M12+M52 filter
            new_entries = [
                k for k in all_kods
                if rank12.get(k, 999) <= m12_entry_n
                and rank52.get(k, 999) <= m52_entry_n
                and k not in keep
                and (not require_dr_above_median
                     or (dr_vals.get(k) is not None
                         and dr_vals[k] >= dr_median))
            ]
            pool = keep + new_entries

        # SMA200 gate
        pool = [k for k in pool if sma200_pass(pser, k, dt)]
        # Sort by M52 rank (prefer mature momentum)
        pool.sort(key=lambda k: rank52.get(k, 999))
        # Cap at 30
        sel = pool[:30]

        turn = (0.0 if not prev_held
                else 1.0 - len(set(sel) & set(prev_held)) / max(len(sel), 1))
        n = len(sel)
        w = np.full(n, 1.0 / 30.0) if n else np.array([])
        ret = (np.array([rmap.get((k, dt), 0.0) for k in sel])
               if n else np.array([]))
        H.append(dict(zip(sel, w)))
        R.append(float((w * ret).sum()) - COST * turn if n else 0.0)
        T.append(turn)
        prev_held = sel

    return H, np.array(R), np.array(T)


def simulera_h0(rk_h0, alld, rmap, pser, dates, anchor):
    prev, H, R, T = [], [], [], []
    for dt in dates:
        sched = alld.index(dt) % 2 == anchor
        raw = rk_h0[dt]
        elig = {r["kod"] for r in raw}
        sel0 = ([r["kod"] for r in raw[:30]]
                if (sched or not prev)
                else [k for k in prev if k in elig])
        if not (sched or not prev) and len(sel0) < 30:
            sel0 += [r["kod"] for r in raw
                     if r["kod"] not in sel0][:30 - len(sel0)]
        turn = (0.0 if not prev
                else 1.0 - len(set(sel0) & set(prev)) / max(len(sel0), 1))
        sel = [k for k in sel0 if sma200_pass(pser, k, dt)]
        n = len(sel)
        w = np.full(n, 1.0 / 30.0) if n else np.array([])
        r = (np.array([rmap.get((k, dt), 0.0) for k in sel])
             if n else np.array([]))
        H.append(dict(zip(sel, w)))
        R.append(float((w * r).sum()) - COST * turn if n else 0.0)
        T.append(turn)
        prev = sel0
    return H, np.array(R), np.array(T)


def capture_rate(base_rk, rmap, H, dates):
    agg = defaultdict(lambda: [0.0, 0.0, 0, 0])
    for i, dt in enumerate(dates):
        for r in base_rk[dt]:
            k = r["kod"]
            x = rmap.get((k, dt))
            if x is None or not np.isfinite(x) or x <= -0.99:
                continue
            lg = math.log1p(x)
            agg[k][1] += lg
            agg[k][3] += 1
            if k in H[i]:
                agg[k][0] += lg
                agg[k][2] += 1
    agd = [v for v in agg.values() if v[2] > 0 and v[3] >= 20]
    vinn = [a / b for a, b, _, _ in agd if b > 0.2]
    forl = [a / b for a, b, _, _ in agd if b < -0.2]
    mv = float(np.median(vinn)) if vinn else 0.0
    mf = float(np.median(forl)) if forl else 0.0
    return {
        "vinnare": mv, "forlorare": mf, "asymmetri": mv - mf,
        "n_vinnare": len(vinn), "n_forlorare": len(forl),
    }


def main():
    print("Loading data...")
    m, prices, core, rmap, alld, pser, rk_h0 = ladda()
    anchor = alld.index(PHASE_ANCHOR_H0) % 2

    print("Building rankings...")
    rankings, dates = build_rankings(core, prices)
    print(f"  {len(dates)} paneler")

    def cagr(R):
        return float(np.prod(1 + R) ** (PPY / len(R)) - 1)

    def maxdd(R):
        w = np.cumprod(1 + R)
        return float((w / np.maximum.accumulate(w) - 1).min())

    results = {}

    # H0 baseline
    print("\nH0 baseline...")
    H0, R0, T0 = simulera_h0(rk_h0, alld, rmap, pser, dates, anchor)
    c0 = capture_rate(rk_h0, rmap, H0, dates)
    results["H0_baseline"] = {
        "cagr": cagr(R0), "max_dd": maxdd(R0),
        "turnover": float(T0[T0 > 0.001].mean()),
        "holdings": float(np.mean([len(h) for h in H0])),
        "capture": c0,
    }

    # Cascade variants
    configs = [
        ("CASCADE_80", 30, 80, 40, False),
        ("CASCADE_70", 30, 70, 40, False),
        ("CASCADE_60", 30, 60, 40, False),
        ("CASCADE_50", 30, 50, 40, False),
        ("CASCADE_70_H1", 30, 70, 40, True),
        ("CASCADE_60_H1", 30, 60, 40, True),
    ]

    for label, m12n, m52n, m52exit, use_dr in configs:
        dr_label = " + DR>median" if use_dr else ""
        print(f"\n{label} (M12 Top-{m12n} + M52 Top-{m52n}{dr_label},"
              f" exit M52 Top-{m52exit})...")
        Hc, Rc, Tc = simulera_kaskad(
            rankings, prices, alld, rmap, pser, dates, anchor,
            m12_entry_n=m12n, m52_entry_n=m52n, m52_exit_n=m52exit,
            require_dr_above_median=use_dr)
        cc = capture_rate(rk_h0, rmap, Hc, dates)
        results[label] = {
            "cagr": cagr(Rc), "max_dd": maxdd(Rc),
            "turnover": float(Tc[Tc > 0.001].mean()) if any(Tc > 0.001) else 0,
            "holdings": float(np.mean([len(h) for h in Hc])),
            "capture": cc,
        }

    # Summary
    print(f"\n{'='*105}")
    print("STRAMAD KASKAD — fångstgrad (alla 66 paneler)")
    print(f"{'='*105}")
    print(f"  {'Modell':20s} {'CAGR':>7s} {'MaxDD':>7s} {'Turn':>6s}"
          f" {'Hold':>5s} {'Vinn%':>7s} {'Förl%':>7s} {'Asym':>8s}"
          f" {'nV':>4s} {'nF':>4s}")
    for label, r in results.items():
        c = r["capture"]
        asym_flag = "✓" if c["asymmetri"] > 0 else ""
        print(f"  {label:20s} {r['cagr']:>7.2%} {r['max_dd']:>7.2%}"
              f" {r['turnover']:>6.3f} {r['holdings']:>5.1f}"
              f" {c['vinnare']:>7.1%} {c['forlorare']:>7.1%}"
              f" {c['asymmetri']:>+7.1%} {asym_flag}"
              f" {c['n_vinnare']:>4d} {c['n_forlorare']:>4d}")
    print(f"{'='*105}")

    OUT.write_text(json.dumps({
        "version": "STRAMAD_KASKAD_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_paneler": len(dates),
        "results": results,
    }, ensure_ascii=False, indent=2))
    print(f"\n  → {OUT.name}")


if __name__ == "__main__":
    main()
