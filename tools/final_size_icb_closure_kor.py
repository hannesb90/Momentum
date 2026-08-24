"""FINAL_SIZE_ICB_CLOSURE — Studie A (ICB-crosswalk-rerun) + Studie B (regimberoende heterogenitet).

Forregistrering: research_k/final_size_icb_closure/FINAL_SIZE_ICB_CLOSURE_PREREGISTRATION.json
INGA MODELLER TRANAS. Ingen routing. Inget trad. Ingen troskelsokning.
Aterbrukar build() och estimationsmaskineriet ur model_heterogeneity_controls_kor.py oforandrat.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/final_size_icb_closure"
CW_PATH = V2 / "research_k/model_heterogeneity_controls/ICB_HISTORICAL_CROSSWALK.json"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

if sha(UT / "FINAL_SIZE_ICB_CLOSURE_PREREGISTRATION.json") != json.loads((UT / "PREREG_FREEZE.json").read_text())["sha256"]:
    sys.exit("AVBRYTER: forregistreringen har andrats efter frysningen.")
if sha(CW_PATH) != "ee3868a28b487b0d6d8dc955193df4247cd4719c8e1f440e8d72a89470a905b9":
    sys.exit("AVBRYTER: ICB-crosswalken har andrats efter frysningen.")
if sha(V2 / "tools/h0_v3_kor.py") != "f844eaea4492d53976c3565b5a194c40f1c0c0d1324aad743059f2e85a1715af":
    sys.exit("AVBRYTER: H0 V3 ar inte den frysta versionen.")

PPY, LOOKBACK, MERE = 13.0, 400, 2.5
MIN_PANELER_PER_TILLSTAND, MIN_OBS_CELL, MIN_GRUPPER = 10, 100, 6

# ---- crosswalk: gammal industry-etikett -> ekonomiskt jamforbar grupp
CW = json.loads(CW_PATH.read_text())
def crosswalk_map():
    m = {}
    for g, dd in CW["JAMFORBARA_EKONOMISKA_GRUPPER"]["grupper"].items():
        for w in ("W1", "W2"):
            for lbl in dd[w]: m[lbl] = g
    return m
CWMAP = crosswalk_map()

# ---- maskineri ur den tidigare studien, oforandrat
_c = importlib.util.spec_from_file_location("MHC", V2 / "tools/model_heterogeneity_controls_kor.py")
MHC = importlib.util.module_from_spec(_c); _c.loader.exec_module(MHC)
dm, ols_cl, wald, build = MHC.dm, MHC.ols_cl, MHC.wald, MHC.build


def holm(pvals):
    """Holm-Bonferroni. Returnerar justerade p i ursprunglig ordning."""
    idx = sorted(range(len(pvals)), key=lambda i: (pvals[i] is None, pvals[i]))
    out = [None] * len(pvals); run = 0.0
    for r, i in enumerate(idx):
        if pvals[i] is None: continue
        adj = min(1.0, (len(pvals) - r) * pvals[i])
        run = max(run, adj); out[i] = round(run, 5)
    return out


# =====================================================================
# REGIMER — definitioner lasta i forregistreringen, byggs enbart av
# priser till och med beslutsdagen for de PIT-eligible namnen den dagen.
# =====================================================================
def regimer(dagar, rk, ser, idxf):
    ut = {}
    for d in dagar:
        E = [r["kod"] for r in rk.get(d, [])]
        rets, ovan, n_sma = [], 0, 0
        for k in E:
            i = idxf(k, d)
            if i is None or i < LOOKBACK: continue
            _, v = ser[k]
            w = v[i - LOOKBACK:i + 1]
            if not np.all(np.isfinite(w)) or np.any(w <= 0): continue
            rets.append(np.diff(w) / w[:-1])
            if len(w) >= 200:
                n_sma += 1
                if w[-1] > float(np.mean(w[-200:])): ovan += 1
        if len(rets) < 20 or n_sma < 20:
            ut[d] = None; continue
        R = np.vstack(rets)                      # namn x dagar
        mkt = np.nanmean(R, axis=0)              # likaviktad marknadsavkastning per dag
        lvl = np.cumprod(1.0 + mkt)
        trend = "UP" if lvl[-1] > float(np.mean(lvl[-200:])) else "DOWN"
        vols = np.array([np.std(mkt[j - 60:j]) * math.sqrt(252) for j in range(60, len(mkt) + 1)])
        vol_nu = float(vols[-1]); vol_med = float(np.median(vols[-252:])) if len(vols) >= 252 else float(np.median(vols))
        volr = "HIGH" if vol_nu > vol_med else "LOW"
        andel = ovan / n_sma
        breadth = "BROAD" if andel >= 0.50 else "NARROW"
        ut[d] = {"TREND": trend, "VOLATILITY": volr, "BREADTH": breadth,
                 "diag": {"vol_ann": round(vol_nu, 4), "vol_median": round(vol_med, 4),
                          "andel_over_sma200": round(andel, 4), "n_namn": len(rets)}}
    return ut


def panel_datum(wn, R, rk):
    RACE = V2 / "research_k/global_ml_full_pit_race"
    preds = json.loads((RACE / f"preds_{wn}_EXTRATREES_F0.json").read_text())
    return [d for d in sorted(preds) if d in rk]


# =====================================================================
# STUDIE A — ICB med crosswalk
# =====================================================================
def icb_spec(rows, d_, y, pid0, grp, spec, s=None, ctrl=False):
    n = len(rows)
    C = [dm(np.array([d_[i] if rows[i]["cw"] == g else 0. for i in range(n)]), pid0) for g in grp]
    idxg = list(range(len(grp)))
    for g in grp[1:]:
        C.append(dm(np.array([1. if rows[i]["cw"] == g else 0. for i in range(n)]), pid0))
    if spec in ("EFTER_SIZE", "FULLT"):
        C.append(dm(s, pid0)); C.append(dm(d_ * s, pid0))
    if spec == "FULLT":
        for c in ("vol", "liq", "spr"):
            v = np.array([r[c] for r in rows])
            C.append(dm(v, pid0)); C.append(dm(d_ * v, pid0))
    return np.column_stack(C), idxg


def studie_a(allrows, popn):
    rows = allrows if popn == "FULL" else [r for r in allrows if r["inpool"] == 1.0]
    grp = sorted({r["cw"] for r in rows})
    y = np.array([r["ret"] for r in rows]); pid0 = np.array([r["p"] for r in rows])
    s = np.array([r["s"] for r in rows])
    o = {"n_obs": len(rows), "n_grupper": len(grp), "grupper": grp,
         "obs_per_grupp": {g: sum(1 for r in rows if r["cw"] == g) for g in grp}, "icb": {}}
    for mod, key in (("ET", "pET"), ("XGB", "pXGB")):
        d_ = np.array([r[key] for r in rows]) - np.array([r["pH0"] for r in rows])
        sd_d = float(np.std(d_)); res = {"sd_d": round(sd_d, 4)}
        for lbl in ("RAW", "EFTER_SIZE", "FULLT"):
            X, idxg = icb_spec(rows, d_, y, pid0, grp, lbl, s)
            b, V = ols_cl(dm(y, pid0), X, pid0)
            Wv, pv, df = wald(b, V, idxg)
            per = {g: round(100 * float(b[idxg[i]]) * sd_d * PPY, 3) for i, g in enumerate(grp)} if b is not None else {}
            res[lbl] = {"omnibus_W": Wv, "omnibus_p": round(pv, 5) if pv is not None else None, "df": df,
                        "std_edge_per_grupp_pp_per_ar_DESCRIPTIVE_ONLY": per,
                        "mellan_grupp_sd_pp": round(float(np.std(list(per.values()), ddof=1)), 3) if per else None}
        # leave-one-group-out pa FULLT
        logo = {}
        for gx in grp:
            sub = [r for r in rows if r["cw"] != gx]
            if len(sub) < 500: logo[gx] = "FOR_FA_OBS"; continue
            g2 = sorted({r["cw"] for r in sub})
            y2 = np.array([r["ret"] for r in sub]); p2 = np.array([r["p"] for r in sub])
            s2 = np.array([r["s"] for r in sub])
            d2 = np.array([r[key] for r in sub]) - np.array([r["pH0"] for r in sub])
            X2, i2 = icb_spec(sub, d2, y2, p2, g2, "FULLT", s2)
            b2, V2_ = ols_cl(dm(y2, p2), X2, p2)
            _, pv2, _ = wald(b2, V2_, i2)
            logo[gx] = round(pv2, 5) if pv2 is not None else None
        res["leave_one_group_out_p"] = logo
        o["icb"][mod] = res
    return o


# =====================================================================
# STUDIE B — regimberoende
# =====================================================================
def size_x_regime(rows, key, rgm, pid0, y):
    n = len(rows)
    d_ = np.array([r[key] for r in rows]) - np.array([r["pH0"] for r in rows])
    s = np.array([r["s"] for r in rows]); sd_d = float(np.std(d_))
    X = np.column_stack([dm(d_, pid0), dm(s, pid0), dm(s * rgm, pid0),
                         dm(d_ * s, pid0), dm(d_ * rgm, pid0), dm(d_ * s * rgm, pid0)])
    b, V = ols_cl(dm(y, pid0), X, pid0)
    if b is None: return {"status": "SINGULAR"}
    se = math.sqrt(V[5, 5]); t = float(b[5] / se)
    p = float(2 * (1 - stats.t.cdf(abs(t), len(np.unique(pid0)) - 1)))
    return {"status": "OK", "b_trippel": round(float(b[5]), 6), "t": round(t, 3), "p": round(p, 5),
            "std_effekt_pp_per_ar_vid_1SD_size": round(100 * float(b[5]) * sd_d * PPY, 3),
            "b_d_s": round(float(b[3]), 6), "b_d_rgm": round(float(b[4]), 6), "sd_d": round(sd_d, 4)}


def icb_x_regime(rows, key, rgm, pid0, y, grp):
    n = len(rows)
    d_ = np.array([r[key] for r in rows]) - np.array([r["pH0"] for r in rows])
    s = np.array([r["s"] for r in rows]); sd_d = float(np.std(d_))
    C, nm = [], []
    for g in grp:  # Sum_g d*1[g]*rgm == d*rgm -> fristaende term utesluts
        C.append(dm(np.array([d_[i] * rgm[i] if rows[i]["cw"] == g else 0. for i in range(n)]), pid0)); nm.append(f"dg_rgm_{g}")
    idxg = list(range(len(grp)))
    for g in grp:  # Sum_g d*1[g] == d -> fristaende term utesluts
        C.append(dm(np.array([d_[i] if rows[i]["cw"] == g else 0. for i in range(n)]), pid0)); nm.append(f"dg_{g}")
    for g in grp[1:]:
        C.append(dm(np.array([1. if rows[i]["cw"] == g else 0. for i in range(n)]), pid0)); nm.append(f"g_{g}")
    C.append(dm(s, pid0)); C.append(dm(s * rgm, pid0)); C.append(dm(d_ * s, pid0))
    b, V = ols_cl(dm(y, pid0), np.column_stack(C), pid0)
    Wv, pv, df = wald(b, V, idxg)
    per = {g: round(100 * float(b[idxg[i]]) * sd_d * PPY, 3) for i, g in enumerate(grp)} if b is not None else {}
    return {"status": "OK" if b is not None else "SINGULAR", "omnibus_W": Wv,
            "omnibus_p": round(pv, 5) if pv is not None else None, "df": df,
            "regimskifte_per_grupp_pp_per_ar_DESCRIPTIVE_ONLY": per,
            "mellan_grupp_sd_pp": round(float(np.std(list(per.values()), ddof=1)), 3) if per else None}


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    _g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
    G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R

    ut = {"version": "FINAL_SIZE_ICB_CLOSURE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": sha(UT / "FINAL_SIZE_ICB_CLOSURE_PREREGISTRATION.json"),
          "crosswalk_sha256": sha(CW_PATH),
          "h0_v3_sha256": sha(V2 / "tools/h0_v3_kor.py"),
          "ingen_traning": True, "fonster": {}}

    for wn in ("W1_2014_2019", "W2_2020_2026"):
        W = R.load_window(wn); rk, ser, idxf = W["rankings"], W["serie"], W["idx"]
        allrows = build(wn, G, R, H, WK)
        dagar = panel_datum(wn, R, rk)

        # ---- DEL 2: crosswalk-coverage
        etiketter = {}
        for r in allrows: etiketter[r["icb"]] = etiketter.get(r["icb"], 0) + 1
        omappade = {k: v for k, v in etiketter.items() if k not in CWMAP}
        if omappade:
            sys.exit(f"AVBRYTER: etiketter utanfor crosswalken i {wn}: {omappade}")
        for r in allrows: r["cw"] = CWMAP[r["icb"]]
        cov = {"observerade_etiketter": dict(sorted(etiketter.items())),
               "n_etiketter": len(etiketter), "omappade": omappade,
               "andel_mappade": 1.0, "n_obs": len(allrows),
               "grupper_efter_crosswalk": sorted({r["cw"] for r in allrows})}

        res = {"DEL2_coverage": cov, "STUDIE_A": {}}
        for popn in ("FULL", "POOL"):
            res["STUDIE_A"][popn] = studie_a(allrows, popn)

        # ---- Holm inom fonster over FULLT-specifikationen, 4 tester
        nycklar = [(p, m) for p in ("FULL", "POOL") for m in ("ET", "XGB")]
        praw = [res["STUDIE_A"][p]["icb"][m]["FULLT"]["omnibus_p"] for p, m in nycklar]
        for (p, m), pa in zip(nycklar, holm(praw)):
            res["STUDIE_A"][p]["icb"][m]["FULLT"]["holm_p"] = pa

        # ---- STUDIE B
        rg = regimer(dagar, rk, ser, idxf)
        pid_all = sorted({r["p"] for r in allrows})
        rgm_panel = {pi: rg.get(dagar[pi]) for pi in pid_all}
        n_saknas = sum(1 for pi in pid_all if rgm_panel[pi] is None)
        B = {"n_paneler_med_data": len(pid_all), "n_paneler_utan_regim": n_saknas,
             "panel_diagnostik": {dagar[pi]: (rgm_panel[pi] or {}) for pi in pid_all},
             "SIZE_x_REGIME": {}, "ICB_x_REGIME": {}, "paneltal": {}}

        for fam, (a, bl) in (("TREND", ("UP", "DOWN")), ("VOLATILITY", ("HIGH", "LOW")),
                             ("BREADTH", ("BROAD", "NARROW"))):
            sub = [r for r in allrows if rgm_panel[r["p"]] is not None]
            pa_ = sorted({r["p"] for r in sub if rgm_panel[r["p"]][fam] == a})
            pb_ = sorted({r["p"] for r in sub if rgm_panel[r["p"]][fam] == bl})
            B["paneltal"][fam] = {a: len(pa_), bl: len(pb_)}
            if min(len(pa_), len(pb_)) < MIN_PANELER_PER_TILLSTAND:
                B["SIZE_x_REGIME"][fam] = {"status": "NOT_IDENTIFIABLE_WITH_CURRENT_HISTORY",
                                           "paneler": B["paneltal"][fam]}
                B["ICB_x_REGIME"][fam] = {"status": "NOT_IDENTIFIABLE_WITH_CURRENT_HISTORY",
                                          "paneler": B["paneltal"][fam]}
                continue
            y = np.array([r["ret"] for r in sub]); pid0 = np.array([r["p"] for r in sub])
            rgm = np.array([1.0 if rgm_panel[r["p"]][fam] == a else 0.0 for r in sub])
            B["SIZE_x_REGIME"][fam] = {m: size_x_regime(sub, k, rgm, pid0, y)
                                       for m, k in (("ET", "pET"), ("XGB", "pXGB"))}
            B["SIZE_x_REGIME"][fam]["referens"] = f"rgm=1 betyder {a}"
            # ICB x regime: cellkrav
            grp = sorted({r["cw"] for r in sub})
            celler = {}
            for g in grp:
                na = sum(1 for i, r in enumerate(sub) if r["cw"] == g and rgm[i] == 1.0)
                nb = sum(1 for i, r in enumerate(sub) if r["cw"] == g and rgm[i] == 0.0)
                celler[g] = {a: na, bl: nb}
            gok = [g for g in grp if min(celler[g].values()) >= MIN_OBS_CELL]
            if len(gok) < MIN_GRUPPER:
                B["ICB_x_REGIME"][fam] = {"status": "NOT_IDENTIFIABLE_WITH_CURRENT_HISTORY",
                                          "celler": celler, "n_grupper_over_krav": len(gok)}
            else:
                sub2 = [r for r in sub if r["cw"] in gok]
                y2 = np.array([r["ret"] for r in sub2]); p2 = np.array([r["p"] for r in sub2])
                rg2 = np.array([1.0 if rgm_panel[r["p"]][fam] == a else 0.0 for r in sub2])
                B["ICB_x_REGIME"][fam] = {m: icb_x_regime(sub2, k, rg2, p2, y2, gok)
                                          for m, k in (("ET", "pET"), ("XGB", "pXGB"))}
                B["ICB_x_REGIME"][fam]["grupper"] = gok
                B["ICB_x_REGIME"][fam]["celler"] = celler
                B["ICB_x_REGIME"][fam]["referens"] = f"rgm=1 betyder {a}"

        # ---- Holm inom {3 regimer} x {ET,XGB} per strukturdimension
        for dim, ext in (("SIZE_x_REGIME", "p"), ("ICB_x_REGIME", "omnibus_p")):
            nyck, praw2 = [], []
            for fam in ("TREND", "VOLATILITY", "BREADTH"):
                blk = B[dim].get(fam, {})
                for m in ("ET", "XGB"):
                    e = blk.get(m)
                    if isinstance(e, dict) and e.get(ext) is not None:
                        nyck.append((fam, m)); praw2.append(e[ext])
            for (fam, m), pa in zip(nyck, holm(praw2)):
                B[dim][fam][m]["holm_p"] = pa
        res["STUDIE_B"] = B
        ut["fonster"][wn] = res
        print(f"{wn}: {len(allrows)} obs, {len(pid_all)} paneler, regimer {B['paneltal']}", flush=True)

    (UT / "results.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "results.json")


if __name__ == "__main__":
    main()
