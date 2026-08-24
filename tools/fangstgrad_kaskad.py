"""KASKADMODELL — snabb entry, långsam exit.

Testar tre rena momentumfönster + en kaskadmodell:
  M12: rank(mom_12w), Top 30, EW, SMA200
  M26: rank(mom_26w), Top 30, EW, SMA200
  M52: = H0 baseline
  CASCADE: Entry om rank(mom_12w) i Topp 40 OCH rank(mom_52w) i Topp 80.
           Behåll så länge rank(mom_52w) i Topp 40.
           Max 30 innehav, EW, SMA200.

Mäter fångstgrad, asymmetri, CAGR, MaxDD på alla paneler.

DIAGNOSTISKT. Rör ingen fryst modell.
Kör: /opt/momentum/venv/bin/python tools/fangstgrad_kaskad.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/fangstgrad_kaskad_results.json"
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
    return m, prices, core, rmap, alld, pser


def momentum_score(prices, kod, dt, weeks):
    """Compute price momentum over `weeks` weeks."""
    if kod not in prices:
        return None
    rs = prices[kod]
    ds = [r["d"] for r in rs]
    adj = [r["adj"] for r in rs]
    # find index for dt
    i = None
    for j in range(len(ds) - 1, -1, -1):
        if ds[j] <= dt:
            i = j
            break
    if i is None:
        return None
    # find index for dt - weeks*7 days
    from datetime import date, timedelta
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


def build_rankings_multi(core_df, prices, alld):
    """Build rankings for 12w, 26w, 52w momentum for all panel dates."""
    import pandas as pd
    dates = sorted(core_df.panel_date.unique())
    dates = [d for d in dates if d >= "2021-07-16" and d <= "2026-07-10"]

    rankings = {w: {} for w in [12, 26, 52, 78]}

    for dt in dates:
        panel = core_df[core_df.panel_date == dt]
        kods = list(panel.kod)

        for weeks in [12, 26, 52, 78]:
            scores = []
            for kod in kods:
                m = momentum_score(prices, kod, dt, weeks)
                scores.append({"kod": kod, "mom": m})

            # Percentile rank
            valid = [(s["mom"], i) for i, s in enumerate(scores)
                     if s["mom"] is not None]
            valid.sort()
            ranks = [None] * len(scores)
            j = 0
            while j < len(valid):
                k = j + 1
                while k < len(valid) and valid[k][0] == valid[j][0]:
                    k += 1
                avg = ((j + 1) + k) / 2 / len(valid)
                for _, idx in valid[j:k]:
                    ranks[idx] = avg
                j = k

            med = np.median([r for r in ranks if r is not None]) if any(
                r is not None for r in ranks) else 0.5

            scored = []
            for i, s in enumerate(scores):
                r = ranks[i] if ranks[i] is not None else med
                scored.append({"kod": s["kod"], "score": r, "mom": s["mom"]})

            scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
            rankings[weeks][dt] = scored

    return rankings, dates


def sma200_pass(pser, k, dt):
    """Check if stock passes SMA200 gate."""
    if k not in pser:
        return True
    ds, a = pser[k]
    i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
    if i is not None and i >= 200 and a[i] < float(np.mean(a[i - 200:i])):
        return False
    return True


def simulera_pure(rankings_w, alld, rmap, pser, dates, anchor, top_n=30):
    """Pure momentum simulation with a single lookback window."""
    prev, H, R, T = [], [], [], []
    for dt in dates:
        sched = alld.index(dt) % 2 == anchor
        raw = rankings_w[dt]
        elig = {r["kod"] for r in raw}

        if sched or not prev:
            sel0 = [r["kod"] for r in raw[:top_n]]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < top_n:
                sel0 += [r["kod"] for r in raw
                         if r["kod"] not in sel0][:top_n - len(sel0)]

        turn = (0.0 if not prev
                else 1.0 - len(set(sel0) & set(prev)) / max(len(sel0), 1))

        # SMA200 gate
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


def simulera_kaskad(rankings, alld, rmap, pser, dates, anchor):
    """Cascade model: enter on 12w top-40, keep while 52w top-40.

    Entry: stock is in 12w Top 40 AND 52w Top 80 (not total garbage long-term)
    Hold:  stock stays while in 52w Top 40 (slow exit)
    Max 30 holdings, equal weight.
    """
    prev_held = []
    H, R, T = [], [], []

    for dt in dates:
        sched = alld.index(dt) % 2 == anchor

        r12 = rankings[12][dt]
        r52 = rankings[52][dt]

        # Build rank lookup
        rank12 = {r["kod"]: i + 1 for i, r in enumerate(r12)}
        rank52 = {r["kod"]: i + 1 for i, r in enumerate(r52)}
        all_kods = set(rank12.keys()) | set(rank52.keys())

        if sched or not prev_held:
            # Full rebalance
            # Candidates: in 12w Top 40 AND 52w Top 80
            entry_candidates = [
                k for k in all_kods
                if rank12.get(k, 999) <= 40 and rank52.get(k, 999) <= 80
            ]
            # Also keep: anything in prev_held that's still in 52w Top 40
            keep = [k for k in prev_held
                    if rank52.get(k, 999) <= 40 and k in all_kods]
            # Union, deduplicate, sort by 52w rank (prefer mature momentum)
            pool = list(set(entry_candidates + keep))
        else:
            # Off-cycle: keep prev if still in 52w Top 40
            keep = [k for k in prev_held
                    if rank52.get(k, 999) <= 40 and k in all_kods]
            # Add new entries from 12w Top 40 AND 52w Top 80
            new_entries = [
                k for k in all_kods
                if rank12.get(k, 999) <= 40 and rank52.get(k, 999) <= 80
                and k not in keep
            ]
            pool = keep + new_entries

        # SMA200 gate
        pool = [k for k in pool if sma200_pass(pser, k, dt)]

        # Sort by combined rank: 0.5*rank12_pct + 0.5*rank52_pct (best first)
        n_total = max(len(rank12), len(rank52), 1)
        pool.sort(key=lambda k: (
            0.5 * rank12.get(k, n_total) / n_total +
            0.5 * rank52.get(k, n_total) / n_total
        ))

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


def capture_rate(base_rk, rmap, H, dates):
    """Measure capture rate using the FULL universe rankings as reference."""
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
        "vinnare_fangst_median": mv,
        "forlorare_fangst_median": mf,
        "asymmetri": mv - mf,
        "n_vinnare": len(vinn),
        "n_forlorare": len(forl),
    }


def main():
    print("Loading data...")
    m, prices, core, rmap, alld, pser = ladda()
    anchor = alld.index(PHASE_ANCHOR_H0) % 2

    print("Building multi-window rankings...")
    rankings, dates = build_rankings_multi(core, prices, alld)
    print(f"  {len(dates)} paneler, {dates[0]} till {dates[-1]}")

    # Also need H0 rankings for capture rate reference universe
    rk_h0 = m.derive_h0_scores(core, prices)

    results = {}

    # 1. Pure models
    for weeks, label in [(12, "M12_pure"), (26, "M26_pure"), (52, "M52_pure")]:
        print(f"\nSimulerar {label} (rank mom_{weeks}w, Top 30, EW, SMA200)...")
        H, R, T = simulera_pure(
            rankings[weeks], alld, rmap, pser, dates, anchor)
        cap = capture_rate(rk_h0, rmap, H, dates)

        def cagr(x):
            return float(np.prod(1 + x) ** (PPY / len(x)) - 1)

        w_ = np.cumprod(1 + R)
        dd = float((w_ / np.maximum.accumulate(w_) - 1).min())
        N = np.array([len(h) for h in H])

        res = {
            "cagr": cagr(R),
            "max_dd": dd,
            "mean_turnover": float(T[T > 0.001].mean()) if any(T > 0.001) else 0.0,
            "mean_holdings": float(N.mean()),
            "capture": cap,
        }
        results[label] = res
        print(f"  CAGR: {res['cagr']:.2%}  MaxDD: {res['max_dd']:.2%}"
              f"  Turn: {res['mean_turnover']:.3f}  Hold: {res['mean_holdings']:.1f}")
        print(f"  Vinnare: {cap['vinnare_fangst_median']:.1%} (n={cap['n_vinnare']})"
              f"  Förlorare: {cap['forlorare_fangst_median']:.1%} (n={cap['n_forlorare']})"
              f"  Asym: {cap['asymmetri']:+.1%}")

    # 2. H0 baseline (52w+78w blend)
    print(f"\nSimulerar H0 (52w+78w blend, fryst champion)...")
    H0, R0, T0 = simulera_pure(
        {dt: rk_h0[dt] for dt in dates}, alld, rmap, pser, dates, anchor)
    cap0 = capture_rate(rk_h0, rmap, H0, dates)

    def cagr(x):
        return float(np.prod(1 + x) ** (PPY / len(x)) - 1)

    w_ = np.cumprod(1 + R0)
    dd0 = float((w_ / np.maximum.accumulate(w_) - 1).min())
    results["H0_52w_78w"] = {
        "cagr": cagr(R0),
        "max_dd": dd0,
        "mean_turnover": float(T0[T0 > 0.001].mean()) if any(T0 > 0.001) else 0.0,
        "mean_holdings": float(np.array([len(h) for h in H0]).mean()),
        "capture": cap0,
    }
    print(f"  CAGR: {results['H0_52w_78w']['cagr']:.2%}"
          f"  MaxDD: {results['H0_52w_78w']['max_dd']:.2%}")
    print(f"  Vinnare: {cap0['vinnare_fangst_median']:.1%}"
          f"  Förlorare: {cap0['forlorare_fangst_median']:.1%}"
          f"  Asym: {cap0['asymmetri']:+.1%}")

    # 3. Cascade model
    print(f"\nSimulerar CASCADE (entry 12w Top40, keep 52w Top40)...")
    Hc, Rc, Tc = simulera_kaskad(rankings, alld, rmap, pser, dates, anchor)
    capc = capture_rate(rk_h0, rmap, Hc, dates)
    w_ = np.cumprod(1 + Rc)
    ddc = float((w_ / np.maximum.accumulate(w_) - 1).min())
    Nc = np.array([len(h) for h in Hc])
    results["CASCADE_12w_52w"] = {
        "cagr": cagr(Rc),
        "max_dd": ddc,
        "mean_turnover": float(Tc[Tc > 0.001].mean()) if any(Tc > 0.001) else 0.0,
        "mean_holdings": float(Nc.mean()),
        "capture": capc,
    }
    print(f"  CAGR: {results['CASCADE_12w_52w']['cagr']:.2%}"
          f"  MaxDD: {results['CASCADE_12w_52w']['max_dd']:.2%}"
          f"  Turn: {results['CASCADE_12w_52w']['mean_turnover']:.3f}"
          f"  Hold: {results['CASCADE_12w_52w']['mean_holdings']:.1f}")
    print(f"  Vinnare: {capc['vinnare_fangst_median']:.1%} (n={capc['n_vinnare']})"
          f"  Förlorare: {capc['forlorare_fangst_median']:.1%} (n={capc['n_forlorare']})"
          f"  Asym: {capc['asymmetri']:+.1%}")

    # Summary
    print("\n" + "=" * 100)
    print("FÅNGSTGRAD — rena fönster + kaskadmodell (alla paneler)")
    print("=" * 100)
    print(f"  {'Modell':22s} {'CAGR':>7s} {'MaxDD':>7s} {'Turn':>6s}"
          f" {'Hold':>5s} {'Vinn%':>7s} {'Förl%':>7s} {'Asym':>7s}")
    for label, r in results.items():
        c = r["capture"]
        print(f"  {label:22s} {r['cagr']:>7.2%} {r['max_dd']:>7.2%}"
              f" {r['mean_turnover']:>6.3f} {r['mean_holdings']:>5.1f}"
              f" {c['vinnare_fangst_median']:>7.1%}"
              f" {c['forlorare_fangst_median']:>7.1%}"
              f" {c['asymmetri']:>+7.1%}")
    print("=" * 100)

    OUT.write_text(json.dumps({
        "version": "FANGSTGRAD_KASKAD_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_paneler": len(dates),
        "period": f"{dates[0]} — {dates[-1]}",
        "results": results,
    }, ensure_ascii=False, indent=2))
    print(f"\n  → {OUT.name}")


if __name__ == "__main__":
    main()
