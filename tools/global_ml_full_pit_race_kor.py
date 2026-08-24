"""GLOBAL_ML_FULL_PIT_FEATURE_RACE — 6 modellfamiljer x 3 feature-armar x 2 fonster.

Forregistrering: research_k/global_ml_full_pit_race/preregistration.json
ICB-licens:      research_k/global_ml_full_pit_race/ICB_RESEARCH_USE_EXTENSION.json

Datapipeline, features F0, target, harness, kostnad och statistik importeras
ovarierade fran tools/rep_model_race_h0v3_kor.py. Endast Nasdaq-featurekopplingen
och walk-forward-orkestreringen ar ny.

Kor: /opt/momentum/venv/bin/python tools/global_ml_full_pit_race_kor.py
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
# XGBoost finns inte i forskningsvenv:en. Samma losning som REP_MODEL_RACE_H0V3:
# en fungerande 3.4.0 laggs till pa sys.path UTAN installation. Redovisas som provenanscaveat.
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/global_ml_full_pit_race"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(UT / "preregistration.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
if sha(UT / "ICB_RESEARCH_USE_EXTENSION.json") != json.loads((UT / "ICB_EXTENSION_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: ICB-licensen har andrats efter frysningen.")
PRE = json.loads((UT / "preregistration.json").read_text())

_s = importlib.util.spec_from_file_location("race", V2 / "tools/rep_model_race_h0v3_kor.py")
R = importlib.util.module_from_spec(_s); _s.loader.exec_module(R)
import h0_v3_eligibility as E

MODELS = ["EXTRATREES", "CATBOOST", "LIGHTGBM", "XGBOOST", "RANDOM_FOREST", "HIST_GRADIENT_BOOSTING"]
NUM = PRE["feature_armar"]["F1"]["nya"]
LOG1P = set(PRE["feature_armar"]["F1"]["transformationer"]["log1p"])
IVOC = PRE["feature_armar"]["F2"]["industry_vokabular"]
SVOC = PRE["feature_armar"]["F2"]["supersector_vokabular"]
SPLIT = {"W1_2014_2019": {"train_end": "2015-12-31", "refits": [2017, 2018, 2019]},
         "W2_2020_2026": {"train_end": "2022-12-30", "refits": [2024, 2025, 2026]}}

# ---------------- Nasdaq PIT-koppling ----------------
_M = json.loads((V2 / "research_k/nasdaq_historical_master/normalized/instrument_monthly_master.json").read_text())["rader"]
_BY = defaultdict(list)
for r in _M:
    _BY[r["orderbook_code"].upper()].append(r)
for v in _BY.values():
    v.sort(key=lambda r: r["known_from"])
_ISIN2OB = {}
for r in _M:
    _ISIN2OB.setdefault(r["isin"], r["orderbook_code"].upper())


def _ob(kod, isin):
    nk = E._norm(kod)
    if nk in _BY: return nk
    k2 = _ISIN2OB.get(isin) if isin else None
    return k2 if k2 in _BY else None


def nasdaq_rad(kod, isin, dt):
    """Senaste rad med known_from <= dt. Ingen interpolation, ingen forward fill."""
    ob = _ob(kod, isin)
    if ob is None: return None
    rows = _BY[ob]
    lo, hi = 0, len(rows)
    while lo < hi:
        m = (lo + hi) // 2
        if rows[m]["known_from"] <= dt: lo = m + 1
        else: hi = m
    return rows[lo - 1] if lo else None


def nasdaq_vek(kod, isin, dt, med_icb):
    r = nasdaq_rad(kod, isin, dt)
    if r is None:
        return [np.nan] * (len(NUM) + (2 if med_icb else 0))
    out = []
    for f in NUM:
        v = r.get(f)
        v = np.nan if v is None else float(v)
        out.append(math.log1p(v) if (f in LOG1P and np.isfinite(v) and v >= 0) else v)
    if med_icb:
        out.append(float(IVOC[r["industry"]]) if r.get("industry") in IVOC else np.nan)
        out.append(float(SVOC[r["supersector"]]) if r.get("supersector") in SVOC else np.nan)
    return out


# ---------------- observationer ----------------
def build_all(W, isin_map):
    obs = R.build_obs(W)
    for o in obs:
        k = o["kod"]
        o["xn"] = nasdaq_vek(k, isin_map.get(k), o["date"], False)
        o["xi"] = nasdaq_vek(k, isin_map.get(k), o["date"], True)
    return obs


def X(obs, arm):
    if arm == "F0": return np.asarray([o["x"] for o in obs], float)
    if arm == "F1": return np.asarray([o["x"] + o["xn"] for o in obs], float)
    return np.asarray([o["x"] + o["xi"] for o in obs], float)


# ---------------- walk-forward ----------------
def kor_cell(W, obs, arm, model, split):
    """Expanderande walk-forward med arlig omtraning enligt temporal_split.json.

    Segment k tacker aren [start_k, start_{k+1}). Traningsmangden for segment k ar
    ALL observation vars target ar fullstandigt realiserad minst 12 veckor fore
    segmentets FORSTA beslutspanel (purge 8 v + embargo 4 v).
    """
    P = W["paneler"]
    byday = defaultdict(list)
    for i, o in enumerate(obs): byday[o["date"]].append(i)
    ar = lambda d: int(d[:4])
    start0 = ar(split["train_end"]) + 1
    starts = [start0] + list(split["refits"])
    first_eval = next(i for i, d in enumerate(P) if ar(d) >= start0)
    Xa = X(obs, arm)
    pred = {}
    for k, sy in enumerate(starts):
        ey = starts[k + 1] if k + 1 < len(starts) else 9999
        dagar = [d for d in P if sy <= ar(d) < ey]
        if not dagar: continue
        cut = np.datetime64(dagar[0]) - np.timedelta64(12 * 7, "D")
        tr = [i for i, o in enumerate(obs) if o["y"] is not None and np.datetime64(o["date"]) <= cut]
        if not tr: continue
        Xtr = Xa[tr]; ytr = np.asarray([obs[i]["y"] for i in tr], float)
        med = np.asarray([np.nanmedian(Xtr[:, j]) if np.isfinite(Xtr[:, j]).any() else 0.
                          for j in range(Xtr.shape[1])])
        Xtr = np.where(np.isnan(Xtr), med, Xtr)
        m = R.make(model); m.fit(Xtr, ytr)
        for d in dagar:
            ix = byday[d]
            if not ix: continue
            Xp = np.where(np.isnan(Xa[ix]), med, Xa[ix])
            pv = m.predict(Xp)
            pred[d] = {obs[j]["kod"]: float(v) for j, v in zip(ix, pv)}
    return pred, first_eval


def order_fn_of(pred, W):
    rk = W["rankings"]
    def f(day, i):
        s = pred.get(day)
        if not s: return [r["kod"] for r in rk[day]]
        return [k for k, _ in sorted(s.items(), key=lambda x: (-x[1], x[0]))]
    return f


def h0_order(W):
    rk = W["rankings"]
    return lambda day, i: [r["kod"] for r in rk[day]]


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 5 or a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(np.argsort(np.argsort(a)), np.argsort(np.argsort(b)))[0, 1])


def matt(W, pred, first_eval):
    rk, rm = W["rankings"], W["retmap"]
    ic, ic30, r30, ov, rho, cov = [], [], [], [], [], []
    for d, s in pred.items():
        h0 = {r["kod"]: r["score"] for r in rk[d]}
        c = [k for k in s if k in h0 and (k, d) in rm]
        if len(c) < 20: continue
        ms = [s[k] for k in c]; hs = [h0[k] for k in c]; y = [rm[(k, d)] for k in c]
        ic.append(spearman(ms, y)); rho.append(spearman(ms, hs))
        om = [k for _, k in sorted(zip([-x for x in ms], c))]
        oh = [k for _, k in sorted(zip([-x for x in hs], c))]
        t30 = om[:30]
        ic30.append(spearman([s[k] for k in t30], [rm[(k, d)] for k in t30]))
        r30.append(float(np.mean([rm[(k, d)] for k in t30])))
        ov.append(len(set(t30) & set(oh[:30]))); cov.append(len(c) / max(1, len(rk[d])))
    f = lambda L: round(float(np.nanmean(L)), 4) if L else None
    return {"ic_full": f(ic), "ic_top30": f(ic30), "top30_ret": f(r30),
            "h0_overlap": f(ov), "rho_h0": f(rho), "coverage": f(cov), "n_pred_paneler": len(pred)}


def main():
    ut = {"version": "GLOBAL_ML_FULL_PIT_RACE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "preregistration.json"),
          "icb_licens_sha256": sha(UT / "ICB_RESEARCH_USE_EXTENSION.json"), "celler": {}}
    import h0_v3_window2_kor as WK, h0_v3_kor as H
    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn)
        isin = H._ISIN if wn.startswith("W1") else WK.bygg_isin_hint()
        obs = build_all(W, isin)
        miss = {a: float(np.mean(~np.isfinite(X(obs, a)))) for a in ("F0", "F1", "F2")}
        sp = SPLIT[wn]
        h0f = h0_order(W)
        fe = next(i for i, d in enumerate(W["paneler"]) if int(d[:4]) > int(sp["train_end"][:4]))
        hb, _, _ = R.simulate(W, h0f, fe)
        ut["celler"][wn] = {"missingness": miss, "n_paneler": len(W["paneler"]), "first_eval": fe,
                            "H0_V3_EW_periodmatchad": {**R.stat(hb), "n_eval": len(hb)}, "modeller": {}}
        np.save(UT / f"h0base_{wn}.npy", hb)
        for mod in MODELS:
            ut["celler"][wn]["modeller"][mod] = {}
            for arm in ("F0", "F1", "F2"):
                pred, fe2 = kor_cell(W, obs, arm, mod, sp)
                of = order_fn_of(pred, W)
                nets, turns, _ = R.simulate(W, of, fe2)
                cell = {**R.stat(nets), "turnover": round(float(np.sum(turns)), 4),
                        "mean_turnover": round(float(np.mean(turns)), 4),
                        **matt(W, pred, fe2), **R.conc(W, of, fe2),
                        "cost_10bp": R.cost_sens(W, of, fe2, 0.001),
                        "cost_40bp": R.cost_sens(W, of, fe2, 0.004),
                        "vs_h0_ew": R.boot_ci(nets, hb)}
                ut["celler"][wn]["modeller"][mod][arm] = cell
                np.save(UT / f"nets_{wn}_{mod}_{arm}.npy", nets)
                (UT / f"preds_{wn}_{mod}_{arm}.json").write_text(json.dumps(
                    {d: {k: round(v, 8) for k, v in s.items()} for d, s in pred.items()}))
                print(f"{wn} {mod:24s} {arm}  CAGR {cell['cagr']:+.4f}  vs H0_EW {cell['vs_h0_ew']['delta_cagr']:+.4f}"
                      f"  IC {cell['ic_full']}  IC30 {cell['ic_top30']}  ov {cell['h0_overlap']}", flush=True)
        (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
