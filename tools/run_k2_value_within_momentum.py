"""K2 — value within momentum. Kör EXAKT den låsta preregistreringen.

Preregistrering: research_k/k2_value_within_momentum_preregistration.json
Lås:            research_k/K2_PREREG_FREEZE.json  sha256 aa046c08...

IC-definitionen är VERBATIM densamma som K3/K5 använde
(tools/spark_k5_k3_diagnostics.py:regime_ic): spearman(score, y) per paneldatum,
plus top30 efter score.

Ingen parameter får ändras efter att detta körts en gång.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

V2 = Path("/home/hannesb/momentum_v2")
PIT = V2 / "validated/kpi_pit"
OUT = V2 / "research_k/k2_value_within_momentum_results.json"

PRIMARY = ("17_EBIT_EV_r12", "ebit_ev_yield", +1)          # +1 = högre är bättre
SECONDARY = [("16_E_EV_r12", "earnings_ev_yield", +1),
             ("11_EV_EBITDA_r12", "ev_ebitda", -1),
             ("15_EV_S_r12", "ev_sales", -1)]


def pctrank(v: np.ndarray) -> np.ndarray:
    """Tvärsnittlig percentilrank, medelrank vid lika värden. 0..1, högre = bättre."""
    n = len(v)
    if n < 2:
        return np.full(n, 0.5)
    order = np.argsort(v, kind="mergesort")
    r = np.empty(n, float)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[order[j + 1]] == v[order[i]]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r / (n - 1)


def h0_and_target():
    src = V2 / "tools/research_all_6_models_head_to_head.py"
    spec = importlib.util.spec_from_file_location("h2h", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    core_df, prices, terminal = mod.load_data()
    rankings = mod.derive_h0_scores(core_df, prices)
    tm = {(r["kod"], r["panel_date"]): r["y52"] for _, r in core_df.iterrows()}
    return rankings, tm


def kpi_lookup(fil: str):
    rows = json.loads((PIT / f"{fil}.json").read_text(encoding="utf-8"))
    per = defaultdict(list)
    for r in rows:
        per[r["kod"]].append((r["report_date"], r["v"]))
    for k in per:
        per[k].sort()
    return {k: ([d for d, _ in v], [x for _, x in v]) for k, v in per.items()}


def value_at(lk, kod, panel_date):
    """Senaste report_date <= panel_date. Inget värde -> None."""
    e = lk.get(kod)
    if not e:
        return None
    d, v = e
    i = bisect_right(d, panel_date) - 1
    return v[i] if i >= 0 else None


def ic_pair(rankings, tm, lk, sign):
    """Per paneldatum: IC för blend och för matchad H0 på IDENTISKA rader."""
    per = []
    for dt in sorted(rankings.keys()):
        kod, h0, y, f = [], [], [], []
        for r in rankings[dt]:
            t = tm.get((r["kod"], dt))
            v = value_at(lk, r["kod"], dt)
            if t is None or v is None or r["score"] is None:
                continue
            if not (np.isfinite(t) and np.isfinite(v) and np.isfinite(r["score"])):
                continue
            kod.append(r["kod"]); h0.append(r["score"]); y.append(t); f.append(v)
        if len(kod) < 20:
            continue
        h0 = np.array(h0); y = np.array(y); f = np.array(f) * sign
        blend = 0.5 * pctrank(h0) + 0.5 * pctrank(f)
        o_b = np.argsort(-blend, kind="mergesort")[:30]
        o_h = np.argsort(-h0, kind="mergesort")[:30]
        per.append({
            "panel_date": dt, "n": len(kod),
            "ic_blend": float(spearmanr(blend, y).statistic),
            "ic_h0": float(spearmanr(h0, y).statistic),
            "top30_blend": float(spearmanr(blend[o_b], y[o_b]).statistic),
            "top30_h0": float(spearmanr(h0[o_h], y[o_h]).statistic)})
    return per


def summarise(per):
    b = np.array([p["ic_blend"] for p in per]); h = np.array([p["ic_h0"] for p in per])
    tb = np.array([p["top30_blend"] for p in per]); th = np.array([p["top30_h0"] for p in per])
    half = len(per) // 2
    return {
        "panel_dates": len(per),
        "mean_ic52_blend": float(b.mean()), "mean_ic52_h0": float(h.mean()),
        "delta_mean_ic52": float(b.mean() - h.mean()),
        "delta_median_ic52": float(np.median(b) - np.median(h)),
        "delta_top30_ic52": float(tb.mean() - th.mean()),
        "positive_ic_share_blend": float((b > 0).mean()),
        "positive_ic_share_h0": float((h > 0).mean()),
        "delta_mean_ic52_block1": float(b[:half].mean() - h[:half].mean()),
        "delta_mean_ic52_block2": float(b[half:].mean() - h[half:].mean()),
        "median_n_per_panel": int(np.median([p["n"] for p in per])),
    }


def classify(s, bounds_flip):
    bars = [s["delta_mean_ic52"] >= 0.01,
            s["delta_median_ic52"] > 0,
            s["delta_top30_ic52"] >= 0,
            s["positive_ic_share_blend"] >= s["positive_ic_share_h0"],
            s["delta_mean_ic52_block1"] > 0,
            s["delta_mean_ic52_block2"] > 0]
    if s["delta_mean_ic52"] <= 0 or (s["delta_median_ic52"] < 0 and s["delta_top30_ic52"] < 0):
        return "INGET STOD", bars
    if all(bars) and not bounds_flip:
        return "INKREMENTELLT INFORMATIONSSTOD", bars
    return "SVAGT STOD", bars


def survivorship_bounds(rankings, tm, lk, sign, s_obs):
    """Preregistrerad AD10-form: saknade rader ges (a) mest gynnsam värdering +
    sämsta utfall, och (b) spegelfallet. Rapportera båda gränserna."""
    out = {}
    for namn, fav in (("varsta_fall", True), ("spegel", False)):
        per = []
        for dt in sorted(rankings.keys()):
            h0, y, f, saknad = [], [], [], []
            for r in rankings[dt]:
                t = tm.get((r["kod"], dt))
                if t is None or r["score"] is None or not np.isfinite(t):
                    continue
                v = value_at(lk, r["kod"], dt)
                if v is None or not np.isfinite(v):
                    saknad.append((r["score"], t))
                else:
                    h0.append(r["score"]); y.append(t); f.append(v * sign)
            if len(h0) < 20 or not saknad:
                continue
            f_hi, f_lo = max(f), min(f)
            y_hi, y_lo = max(y), min(y)
            for sc, t in saknad:
                h0.append(sc); y.append(t)
                f.append(f_hi if fav else f_lo)
            # ersätt saknade rader med konstruerat utfall
            y = np.array(y, float)
            y[-len(saknad):] = y_lo if fav else y_hi
            h0 = np.array(h0); f = np.array(f)
            blend = 0.5 * pctrank(h0) + 0.5 * pctrank(f)
            per.append({"b": float(spearmanr(blend, y).statistic),
                        "h": float(spearmanr(h0, y).statistic)})
        if per:
            d = np.mean([p["b"] for p in per]) - np.mean([p["h"] for p in per])
            out[namn] = {"delta_mean_ic52": float(d), "panel_dates": len(per)}
    flip = any(v["delta_mean_ic52"] * s_obs["delta_mean_ic52"] < 0 for v in out.values())
    out["flips_sign"] = bool(flip)
    return out


def main() -> None:
    lock = json.loads((V2 / "research_k/K2_PREREG_FREEZE.json").read_text(encoding="utf-8"))
    print(f"preregistrering sha256 {lock['sha256']}  status {lock['status']}\n")

    rankings, tm = h0_and_target()
    res = {"version": "SPARK_K2_RESULT_V1",
           "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "prereg_sha256": lock["sha256"], "features": {}}

    fil, fid, sign = PRIMARY
    lk = kpi_lookup(fil)
    per = ic_pair(rankings, tm, lk, sign)
    s = summarise(per)
    bounds = survivorship_bounds(rankings, tm, lk, sign, s)
    cls, bars = classify(s, bounds["flips_sign"])
    res["features"][fid] = {"role": "PRIMARY", "kpi_file": fil, "summary": s,
                            "survivorship_bounds": bounds, "classification": cls,
                            "support_bars": bars}
    print("=" * 78); print(f"PRIMÄR: {fid}  ({fil})"); print("=" * 78)
    print(f"  paneldatum                {s['panel_dates']}   median n/panel {s['median_n_per_panel']}")
    print(f"  mean IC52  H0             {s['mean_ic52_h0']:+.4f}")
    print(f"  mean IC52  blend          {s['mean_ic52_blend']:+.4f}")
    print(f"  Δ mean IC52               {s['delta_mean_ic52']:+.4f}   (krav >= +0.0100)")
    print(f"  Δ median IC52             {s['delta_median_ic52']:+.4f}   (krav > 0)")
    print(f"  Δ Top30 IC52              {s['delta_top30_ic52']:+.4f}   (krav >= 0)")
    print(f"  positiv andel  H0/blend   {s['positive_ic_share_h0']:.3f} / {s['positive_ic_share_blend']:.3f}")
    print(f"  Δ block 1 / block 2       {s['delta_mean_ic52_block1']:+.4f} / {s['delta_mean_ic52_block2']:+.4f}")
    print(f"  survivorship-gränser      värsta {bounds.get('varsta_fall',{}).get('delta_mean_ic52',float('nan')):+.4f}"
          f"   spegel {bounds.get('spegel',{}).get('delta_mean_ic52',float('nan')):+.4f}"
          f"   vänder tecken: {bounds['flips_sign']}")
    print(f"\n  KLASSIFICERING: {cls}\n")

    print("=" * 78); print("SEKUNDÄRA (diagnostiska — får ej skapa stöd)"); print("=" * 78)
    for fil2, fid2, sg in SECONDARY:
        lk2 = kpi_lookup(fil2)
        p2 = ic_pair(rankings, tm, lk2, sg)
        s2 = summarise(p2)
        res["features"][fid2] = {"role": "SECONDARY_DIAGNOSTIC", "kpi_file": fil2, "summary": s2}
        print(f"  {fid2:20s} Δ mean IC52 {s2['delta_mean_ic52']:+.4f}   "
              f"Δ median {s2['delta_median_ic52']:+.4f}   Δ Top30 {s2['delta_top30_ic52']:+.4f}   "
              f"block {s2['delta_mean_ic52_block1']:+.4f}/{s2['delta_mean_ic52_block2']:+.4f}")

    res["primary_classification"] = cls
    res["stop_condition_applied"] = (
        "value_within_momentum flyttas fran DATABLOCKERAD till FALSIFIERAD och familjen stangs"
        if cls == "INGET STOD" else
        "familjen forblir oppen endast for forward-only observation; ingen challenger skapas")
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nskrev {OUT.relative_to(V2)}")
    print("sha256", hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
