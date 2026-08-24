"""FÅNGSTGRAD H0 vs H1 vs H2 — alla paneler, inte bara 20 OOS.

Mäter:
  - Fångstgrad (capture rate) för vinnare och förlorare per modellvariant
  - Fångstasymmetri (vinnare minus förlorare)
  - CAGR, MaxDD, turnover
  - T2-motsägelsen (ökad vikt + utgång)

Använder exakt samma faktordefinitioner som LOCK.json:
  H0: 0.5*rank(mom_12m) + 0.5*rank(mom_18m)
  H1: 0.5*rank(H0) + 0.5*rank(drawdown_resilience)
  H2: 0.5*rank(H0) + 0.5*rank(trend_strength)

DIAGNOSTISKT. Rör ingen fryst modell, skriver inget till registret.
Kör:  /opt/momentum/venv/bin/python tools/fangstgrad_h0_h1_h2.py
"""
from __future__ import annotations
import importlib.util, json, math, statistics
from collections import defaultdict
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/fangstgrad_h0_h1_h2_results.json"
PPY, COST = 13.0, 0.002

# ── load data via the head-to-head module ──────────────────────────
def ladda():
    s = importlib.util.spec_from_file_location(
        "h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    core, prices, term = m.load_data()
    rmap, alld = m.execution_engine(core, prices, term)
    vmap, pser = m.compute_vols(prices, window=60)
    rk = m.derive_h0_scores(core, prices)
    return m, prices, rmap, alld, vmap, pser, rk


# ── factor computations (from spari_forward_challengers.py LOCK) ───
def _window(rs, panel, days=364):
    lo = (date.fromisoformat(panel) - timedelta(days=days)).isoformat()
    return [r for r in rs if lo <= r["d"] <= panel
            and r.get("adj") is not None and r["adj"] > 0]


def drawdown_resilience(rs, panel):
    w = _window(rs, panel)
    if len(w) < 200:
        return None
    peak = w[0]["adj"]
    m = 0.0
    for r in w:
        peak = max(peak, r["adj"])
        m = min(m, r["adj"] / peak - 1)
    return -abs(m)


def trend_strength(rs, panel):
    w = _window(rs, panel)
    if len(w) < 200:
        return None
    y = np.log(np.array([r["adj"] for r in w], float))
    x = np.arange(len(y), dtype=float)
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    res = y - X @ beta
    s2 = float(res @ res) / (len(x) - 2)
    se = math.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    return float(beta[1] / se) if se > 0 else None


# ── percentile rank (same logic as spari_forward_challengers.py) ───
def pct_rank(values):
    ok = sorted((x, i) for i, x in enumerate(values)
                if x is not None and math.isfinite(x))
    z = [None] * len(values)
    j = 0
    while j < len(ok):
        k = j + 1
        while k < len(ok) and ok[k][0] == ok[j][0]:
            k += 1
        q = ((j + 1) + k) / 2 / len(ok)
        for _, i in ok[j:k]:
            z[i] = q
        j = k
    return z


# ── build rankings for H1 and H2 ──────────────────────────────────
def build_challenger_rankings(rk, prices):
    """For each panel date, compute H1 and H2 scores and return rankings dicts."""
    # Build sorted price series per kod
    price_lists = {}
    for k, rs in prices.items():
        price_lists[k] = sorted(rs, key=lambda r: r["d"])

    h1_rankings = {}
    h2_rankings = {}

    for dt, rows in sorted(rk.items()):
        kods = [r["kod"] for r in rows]
        h0_scores = [r["score"] for r in rows]

        # Compute factors
        h1_factors = []
        h2_factors = []
        for r in rows:
            k = r["kod"]
            rs = price_lists.get(k, [])
            h1_factors.append(drawdown_resilience(rs, dt))
            h2_factors.append(trend_strength(rs, dt))

        # Rank factors
        h0_ranks = pct_rank(h0_scores)
        h1_ranks = pct_rank(h1_factors)
        h2_ranks = pct_rank(h2_factors)

        # Median fill for missing
        def med(v):
            x = [q for q in v if q is not None and math.isfinite(q)]
            return statistics.median(x) if x else 0.5

        h0_med = med(h0_ranks)
        h1_med = med(h1_ranks)
        h2_med = med(h2_ranks)

        # H1 score = 0.5*rank(H0) + 0.5*rank(drawdown_resilience)
        h1_scored = []
        for i, r in enumerate(rows):
            h0r = h0_ranks[i] if h0_ranks[i] is not None else h0_med
            h1r = h1_ranks[i] if h1_ranks[i] is not None else h1_med
            h1_scored.append({**r, "score": (h0r + h1r) / 2})

        # H2 score = 0.5*rank(H0) + 0.5*rank(trend_strength)
        h2_scored = []
        for i, r in enumerate(rows):
            h0r = h0_ranks[i] if h0_ranks[i] is not None else h0_med
            h2r = h2_ranks[i] if h2_ranks[i] is not None else h2_med
            h2_scored.append({**r, "score": (h0r + h2r) / 2})

        h1_scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)
        h2_scored.sort(key=lambda x: (x["score"], x["kod"]), reverse=True)

        h1_rankings[dt] = h1_scored
        h2_rankings[dt] = h2_scored

    return h1_rankings, h2_rankings


# ── simulation (same as beteendeaudit.py simulera, equal weight) ───
def simulera(rk, alld, rmap, pser, dates, anchor):
    """Run EW Top-30 with SMA200 gate. Returns holdings, returns, turnover."""
    prev, H, R, T = [], [], [], []
    for dt in dates:
        sched = alld.index(dt) % 2 == anchor
        raw = rk[dt]
        elig = {r["kod"] for r in raw}
        sel0 = ([r["kod"] for r in raw[:30]]
                if (sched or not prev)
                else [k for k in prev if k in elig])
        if not (sched or not prev) and len(sel0) < 30:
            sel0 += [r["kod"] for r in raw
                     if r["kod"] not in sel0][:30 - len(sel0)]
        turn = (0.0 if not prev
                else 1.0 - len(set(sel0) & set(prev)) / len(sel0))

        # SMA200 gate
        sel = []
        for k in sel0:
            ok = True
            if k in pser:
                ds, a = pser[k]
                i = next((j for j in range(len(ds) - 1, -1, -1)
                          if ds[j] <= dt), None)
                if (i is not None and i >= 200
                        and a[i] < float(np.mean(a[i - 200:i]))):
                    ok = False
            if ok:
                sel.append(k)

        n = len(sel)
        if n:
            w = np.full(n, 1.0 / 30.0)  # equal weight, 1/30 per slot
        else:
            w = np.array([])

        r = (np.array([rmap.get((k, dt), 0.0) for k in sel])
             if n else np.array([]))
        H.append(dict(zip(sel, w)))
        R.append(float((w * r).sum()) - COST * turn if n else 0.0)
        T.append(turn)
        prev = sel0

    return H, np.array(R), np.array(T)


# ── capture rate (T3 from beteendeaudit.py) ────────────────────────
def capture_rate(rk, rmap, H, dates):
    agg = defaultdict(lambda: [0.0, 0.0, 0, 0])
    for i, dt in enumerate(dates):
        for r in rk[dt]:
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


# ── T2: weight increase followed by exit ───────────────────────────
def t2_contradictions(H, rmap, dates):
    strid = 0
    kostnad = 0.0
    for i in range(1, len(dates)):
        for k, w in H[i].items():
            wp = H[i - 1].get(k)
            if (wp and w > wp * 1.02
                    and k not in H[min(i + 1, len(H) - 1)]):
                strid += 1
                kostnad += w * rmap.get((k, dates[i]), 0.0)
    return {"count": strid, "cumulative_return": kostnad}


# ── main ───────────────────────────────────────────────────────────
def main():
    print("Loading data...")
    m, prices, rmap, alld, vmap, pser, rk = ladda()
    dates = sorted(rk.keys())
    anchor = alld.index(m.PHASE_ANCHOR_H0) % 2
    print(f"  {len(dates)} paneler, {dates[0]} till {dates[-1]}")

    print("Building H1/H2 rankings...")
    h1_rk, h2_rk = build_challenger_rankings(rk, prices)

    results = {}
    for label, rankings in [("H0", rk), ("H1_DRAW_RESILIENCE", h1_rk),
                            ("H2_TREND_STRENGTH", h2_rk)]:
        print(f"\nSimulerar {label}...")
        H, R, T = simulera(rankings, alld, rmap, pser, dates, anchor)

        # Portfolio metrics
        def cagr(x):
            return float(np.prod(1 + x) ** (PPY / len(x)) - 1)

        w_ = np.cumprod(1 + R)
        dd = float((w_ / np.maximum.accumulate(w_) - 1).min())
        N = np.array([len(h) for h in H])

        # Capture rate
        cap = capture_rate(rankings, rmap, H, dates)

        # T2
        t2 = t2_contradictions(H, rmap, dates)

        res = {
            "cagr": cagr(R),
            "max_dd": dd,
            "mean_turnover": float(T[T > 0.001].mean()) if any(T > 0.001) else 0.0,
            "mean_holdings": float(N.mean()),
            "capture": cap,
            "t2_contradictions": t2,
        }
        results[label] = res

        print(f"  CAGR:       {res['cagr']:.2%}")
        print(f"  MaxDD:      {res['max_dd']:.2%}")
        print(f"  Turnover:   {res['mean_turnover']:.3f}")
        print(f"  Holdings:   {res['mean_holdings']:.1f}")
        print(f"  Vinnare:    {cap['vinnare_fangst_median']:.1%}"
              f"  (n={cap['n_vinnare']})")
        print(f"  Förlorare:  {cap['forlorare_fangst_median']:.1%}"
              f"  (n={cap['n_forlorare']})")
        print(f"  Asymmetri:  {cap['asymmetri']:+.1%}"
              f"  ({'FEL HÅLL' if cap['asymmetri'] < 0 else 'RÄTT HÅLL'})")
        print(f"  T2 (vikt↑→sälj): {t2['count']} fall,"
              f" bidrag {t2['cumulative_return']:+.2%}")

    # Summary comparison
    print("\n" + "=" * 96)
    print("FÅNGSTGRAD — H0 vs H1 vs H2 (alla paneler)")
    print("=" * 96)
    print(f"  {'Modell':25s} {'CAGR':>7s} {'MaxDD':>7s} {'Vinn%':>7s}"
          f" {'Förl%':>7s} {'Asym':>7s} {'T2':>5s}")
    for label, r in results.items():
        c = r["capture"]
        print(f"  {label:25s} {r['cagr']:>7.2%} {r['max_dd']:>7.2%}"
              f" {c['vinnare_fangst_median']:>7.1%}"
              f" {c['forlorare_fangst_median']:>7.1%}"
              f" {c['asymmetri']:>+7.1%}"
              f" {r['t2_contradictions']['count']:>5d}")
    print("=" * 96)

    OUT.write_text(json.dumps({
        "version": "FANGSTGRAD_H0_H1_H2_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_paneler": len(dates),
        "period": f"{dates[0]} — {dates[-1]}",
        "results": results,
    }, ensure_ascii=False, indent=2))
    print(f"\n  → {OUT.name}")


if __name__ == "__main__":
    main()
