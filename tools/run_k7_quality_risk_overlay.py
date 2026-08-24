"""K7 — kvalitet som riskoverlay. Kör EXAKT den låsta preregistreringen.
Prereg: research_k/k7_quality_risk_overlay_preregistration.json  sha256 44fcbc8c...
Speglar research_ad AD2: pooled OLS med panelklustrade SE.
Ingen avkastningsprediktion. Ingen challenger.
"""
from __future__ import annotations
import importlib.util, json, math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
PIT = V2 / "validated/kpi_pit"
OUT = V2 / "research_k/k7_quality_risk_overlay_results.json"
PRIMARY = ("39_Soliditet_r12", "soliditet", -1)          # -1 = förväntat negativt beta
SECONDARY = [("37_ROIC_r12", "roic", -1), ("42_Nettoskuld_EBITDA_r12", "netdebt_ebitda", +1),
             ("24_FCF_Marginal_r12", "fcf_margin", -1)]


def pctrank(v):
    n = len(v)
    if n < 2: return np.full(n, .5)
    o = np.argsort(v, kind="mergesort"); r = np.empty(n, float); i = 0
    while i < n:
        j = i
        while j + 1 < n and v[o[j + 1]] == v[o[i]]: j += 1
        r[o[i:j + 1]] = (i + j) / 2.; i = j + 1
    return r / (n - 1)


def load_h0():
    spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    core_df, prices, terminal = m.load_data()
    return m.derive_h0_scores(core_df, prices), prices


def kpi_lookup(f):
    rows = json.loads((PIT / f"{f}.json").read_text(encoding="utf-8"))
    per = defaultdict(list)
    for r in rows: per[r["kod"]].append((r["report_date"], r["v"]))
    for k in per: per[k].sort()
    return {k: ([d for d, _ in v], [x for _, x in v]) for k, v in per.items()}


def val_at(lk, kod, dt):
    e = lk.get(kod)
    if not e: return None
    d, v = e; i = bisect_right(d, dt) - 1
    return v[i] if i >= 0 else None


def vols(prices):
    """(kod)->(dates, adj) samt hjälpare för trailing och forward realiserad vol."""
    return {k: (np.array([r["d"] for r in rs]), np.array([r["adj"] for r in rs], float))
            for k, rs in prices.items()}


def trail_fwd_vol(ps, kod, dt):
    e = ps.get(kod)
    if e is None: return None, None
    d, a = e
    i = bisect_right(list(d), dt) - 1
    if i < 60 or i + 20 >= len(a): return None, None
    lr = np.diff(np.log(np.maximum(a[i - 60:i + 1], 1e-9)))
    tv = float(np.std(lr, ddof=1) * math.sqrt(252)) if len(lr) > 5 else None
    j = min(i + 252, len(a) - 1)
    if j - i < 60: return tv, None
    fr = np.diff(np.log(np.maximum(a[i:j + 1], 1e-9)))
    fv = float(np.std(fr, ddof=1) * math.sqrt(252)) if len(fr) > 30 else None
    return tv, fv


def ols_clustered(X, y, groups):
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ (X.T @ y)
    r = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in np.unique(groups):
        m = groups == g
        s = X[m].T @ r[m]
        meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(V), 0))
    return b, se, b / np.where(se > 0, se, np.nan)


def run(rankings, ps, lk, sign):
    rows = []
    for dt in sorted(rankings.keys()):
        top = rankings[dt][:30]
        for r in top:
            v = val_at(lk, r["kod"], dt)
            if v is None or not np.isfinite(v): continue
            tv, fv = trail_fwd_vol(ps, r["kod"], dt)
            if tv is None or fv is None: continue
            rows.append((dt, r["kod"], float(v), tv, fv, r["score"]))
    if len(rows) < 100: return None
    dts = np.array([x[0] for x in rows])
    feat = np.array([x[2] for x in rows]); tv = np.array([x[3] for x in rows])
    fv = np.array([x[4] for x in rows]); h0 = np.array([x[5] for x in rows])
    fp = np.empty(len(rows)); hp = np.empty(len(rows))
    for d in np.unique(dts):
        m = dts == d
        fp[m] = pctrank(feat[m]); hp[m] = pctrank(h0[m])
    X = np.column_stack([np.ones(len(rows)), tv, hp, fp])
    b, se, t = ols_clustered(X, fv, dts)
    half = len(np.unique(dts)) // 2
    cut = np.unique(dts)[half]
    out = {"n_obs": len(rows), "n_panels": int(len(np.unique(dts))),
           "beta_trailing_vol": float(b[1]), "beta_h0_rank": float(b[2]),
           "beta_feature": float(b[3]), "t_feature": float(t[3]), "se_feature": float(se[3]),
           "mean_fwd_vol": float(fv.mean())}
    for lbl, m in (("block1", dts < cut), ("block2", dts >= cut)):
        if m.sum() > 50:
            bb, _, tt = ols_clustered(X[m], fv[m], dts[m])
            out[f"beta_feature_{lbl}"] = float(bb[3]); out[f"t_feature_{lbl}"] = float(tt[3])
    return out


def classify(o, sign):
    if o is None: return "INGET STOD (otillracklig data)"
    right = (o["beta_feature"] < 0) if sign < 0 else (o["beta_feature"] > 0)
    b1 = o.get("beta_feature_block1"); b2 = o.get("beta_feature_block2")
    both = (b1 is not None and b2 is not None and
            ((b1 < 0 and b2 < 0) if sign < 0 else (b1 > 0 and b2 > 0)))
    if not right or abs(o["t_feature"]) < 2.0: return "INGET STOD"
    if abs(o["t_feature"]) >= 3.0 and both: return "ORTOGONAL RISKSIGNAL"
    return "SVAGT STOD"


def main():
    lock = json.loads((V2 / "research_k/K7_PREREG_FREEZE.json").read_text())
    print(f"prereg sha256 {lock['sha256']}\n")
    rankings, prices = load_h0(); ps = vols(prices)
    res = {"version": "SPARK_K7_RESULT_V1", "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "prereg_sha256": lock["sha256"], "features": {}}
    f, fid, sg = PRIMARY
    o = run(rankings, ps, kpi_lookup(f), sg); c = classify(o, sg)
    res["features"][fid] = {"role": "PRIMARY", "sign_expected": sg, "result": o, "classification": c}
    print("=" * 74); print(f"PRIMÄR: {fid}  (förväntat beta-tecken {'negativt' if sg<0 else 'positivt'})"); print("=" * 74)
    if o:
        print(f"  observationer {o['n_obs']}  paneler {o['n_panels']}  medel fwd-vol {o['mean_fwd_vol']:.3f}")
        print(f"  beta trailing vol   {o['beta_trailing_vol']:+.4f}")
        print(f"  beta H0-rank        {o['beta_h0_rank']:+.4f}")
        print(f"  beta FEATURE        {o['beta_feature']:+.4f}   t = {o['t_feature']:+.2f}   (krav |t|>=3.0)")
        print(f"  block1 / block2     {o.get('beta_feature_block1',float('nan')):+.4f} (t {o.get('t_feature_block1',float('nan')):+.2f})"
              f"  /  {o.get('beta_feature_block2',float('nan')):+.4f} (t {o.get('t_feature_block2',float('nan')):+.2f})")
    print(f"\n  KLASSIFICERING: {c}\n")
    print("=" * 74); print("SEKUNDÄRA (diagnostiska)"); print("=" * 74)
    for f2, fid2, sg2 in SECONDARY:
        try: o2 = run(rankings, ps, kpi_lookup(f2), sg2)
        except FileNotFoundError: print(f"  {fid2:16s} PIT-fil saknas"); continue
        res["features"][fid2] = {"role": "SECONDARY", "sign_expected": sg2, "result": o2}
        if o2: print(f"  {fid2:16s} beta {o2['beta_feature']:+.4f}  t {o2['t_feature']:+.2f}  "
                     f"block {o2.get('beta_feature_block1',float('nan')):+.4f}/{o2.get('beta_feature_block2',float('nan')):+.4f}  n={o2['n_obs']}")
    res["primary_classification"] = c
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nskrev {OUT.name}")


if __name__ == "__main__":
    main()
