"""DEL 19 — robusthet for de Holm-overlevande fynden.

Randomiseringsnoll: permutera REGIMETIKETTERNA over paneler. Panelstruktur, ICB-struktur,
avkastningar och modellrangordningar ror sig inte; bara kopplingen panel->regim bryts.
Ligger observerad Wald inuti permutationsfordelningen ar fyndet en artefakt av klustrad
Wald pa fa paneler, inte regiminformation.

Studie A:s POOL-omnibus nollkalibreras genom att permutera ICB-etiketter INOM panel.

Identisk specifikation som huvudkorningen. Endast implementationen ar snabbare: de
kolumner som inte beror av permutationen forberaknas, och paneldemeaningen ar
vektoriserad via reduceat i stallet for en pythonloop per kolumn.

INGEN ny parameter. INGEN modell tranas. SEED ur forregistreringen.
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import numpy as np
from scipy import stats

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
sys.path.append("/home/hannesb/momentum_prod_work/.research-libs")
UT = V2 / "research_k/final_size_icb_closure"
_f = importlib.util.spec_from_file_location("F", V2 / "tools/final_size_icb_closure_kor.py")
F = importlib.util.module_from_spec(_f); _f.loader.exec_module(F)
NPERM = 2000


class Panel:
    """Forberaknad panelstruktur: vektoriserad demeaning och klustrad sandwich."""
    def __init__(self, pid):
        self.pid = pid
        self.order = np.argsort(pid, kind="stable")
        sp = pid[self.order]
        self.starts = np.concatenate(([0], np.flatnonzero(np.diff(sp)) + 1))
        self.counts = np.diff(np.concatenate((self.starts, [len(pid)]))).astype(float)
        self.G = len(self.starts)
        self.inv = np.empty(len(pid), dtype=np.int64)
        self.inv[self.order] = np.repeat(np.arange(self.G), self.counts.astype(int))

    def dm(self, C):
        C = np.atleast_2d(C.T).T if C.ndim == 1 else C
        sums = np.add.reduceat(C[self.order], self.starts, axis=0)
        return C - (sums / self.counts[:, None])[self.inv]

    def ols(self, y, X):
        XtX = X.T @ X
        if np.linalg.cond(XtX) > 1e12: return None, None
        b = np.linalg.solve(XtX, X.T @ y); e = y - X @ b; XtXi = np.linalg.inv(XtX)
        S = X * e[:, None]
        g = np.add.reduceat(S[self.order], self.starts, axis=0)
        meat = g.T @ g
        n, k = X.shape
        c = (self.G / (self.G - 1)) * ((n - 1) / (n - k))
        return b, XtXi @ (c * meat) @ XtXi


def wald(b, V, idx):
    if b is None or len(idx) < 2: return None, None
    R = np.zeros((len(idx) - 1, len(b)))
    for i, j in enumerate(idx[1:]): R[i, j] = 1.; R[i, idx[0]] = -1.
    Rb = R @ b
    try: Wv = float(Rb @ np.linalg.solve(R @ V @ R.T, Rb))
    except np.linalg.LinAlgError: return None, None
    return Wv, float(1 - stats.chi2.cdf(Wv, len(idx) - 1))


def main():
    import h0_v3_kor as H, h0_v3_window2_kor as WK
    _g = importlib.util.spec_from_file_location("G", V2 / "tools/global_ml_full_pit_race_kor.py")
    G = importlib.util.module_from_spec(_g); _g.loader.exec_module(G); R = G.R
    ut = {"version": "FINAL_SIZE_ICB_CLOSURE_ROBUSTHET_V1", "n_perm": NPERM, "seed": 20260815,
          "prereg_sha256": F.sha(UT / "FINAL_SIZE_ICB_CLOSURE_PREREGISTRATION.json"),
          "metod": "permutation av regimetiketter over paneler; for POOL permutation av ICB inom panel",
          "fonster": {}}

    for wn in ("W1_2014_2019", "W2_2020_2026"):
        rng = np.random.default_rng(20260815)
        W = R.load_window(wn); rk, ser, idxf = W["rankings"], W["serie"], W["idx"]
        allrows = F.build(wn, G, R, H, WK)
        for r in allrows: r["cw"] = F.CWMAP[r["icb"]]
        dagar = F.panel_datum(wn, R, rk)
        rgd = F.regimer(dagar, rk, ser, idxf)
        rgm_panel = {pi: rgd.get(dagar[pi]) for pi in sorted({r["p"] for r in allrows})}
        res = {}

        # ================= A: POOL-omnibus, ICB permuterad inom panel
        pool = [r for r in allrows if r["inpool"] == 1.0]
        grp = sorted({r["cw"] for r in pool})
        P = Panel(np.array([r["p"] for r in pool]))
        y = P.dm(np.array([r["ret"] for r in pool]))[:, 0]
        s = np.array([r["s"] for r in pool])
        ctrl = {c: np.array([r[c] for r in pool]) for c in ("vol", "liq", "spr")}
        M0 = np.array([[1.0 if r["cw"] == g else 0.0 for g in grp] for r in pool])  # n x G
        res["STUDIE_A_POOL_permutation"] = {}
        for mod, key in (("ET", "pET"), ("XGB", "pXGB")):
            d_ = np.array([r[key] for r in pool]) - np.array([r["pH0"] for r in pool])
            fasta = [s, d_ * s] + [v for c in ("vol", "liq", "spr") for v in (ctrl[c], d_ * ctrl[c])]
            FIX = P.dm(np.column_stack(fasta))

            def stat(M):
                Xg = P.dm(M * d_[:, None])                 # d*1[g], G kolumner
                Xd = P.dm(M[:, 1:])                        # ICB-dummies, referens utesluten
                b, V = P.ols(y, np.column_stack([Xg, Xd, FIX]))
                return wald(b, V, list(range(len(grp))))

            Wobs, pobs = stat(M0)
            null = []
            for _ in range(NPERM):
                Mp = M0.copy()
                for a, b_ in zip(P.starts, np.concatenate((P.starts[1:], [len(pool)]))):
                    ii = P.order[a:b_]
                    Mp[ii] = M0[rng.permutation(ii)]
                Wp, _ = stat(Mp)
                if Wp is not None: null.append(Wp)
            null = np.array(null)
            res["STUDIE_A_POOL_permutation"][mod] = {
                "W_observerad": round(Wobs, 3), "asymptotisk_p": round(pobs, 5),
                "permutations_p": round(float((np.sum(null >= Wobs) + 1) / (len(null) + 1)), 5),
                "null_median_W": round(float(np.median(null)), 3),
                "null_p95_W": round(float(np.percentile(null, 95)), 3), "n_giltiga": len(null)}
            print(f"  {wn} POOL {mod}: W={Wobs:.2f} perm_p={res['STUDIE_A_POOL_permutation'][mod]['permutations_p']}", flush=True)

        # ================= B: ICB x REGIME, regim permuterad over paneler
        res["ICB_x_REGIME_permutation"] = {}
        for fam, (aa, bb) in (("TREND", ("UP", "DOWN")), ("VOLATILITY", ("HIGH", "LOW")),
                              ("BREADTH", ("BROAD", "NARROW"))):
            sub0 = [r for r in allrows if rgm_panel[r["p"]] is not None]
            pa_ = {r["p"] for r in sub0 if rgm_panel[r["p"]][fam] == aa}
            pb_ = {r["p"] for r in sub0 if rgm_panel[r["p"]][fam] == bb}
            if min(len(pa_), len(pb_)) < F.MIN_PANELER_PER_TILLSTAND:
                res["ICB_x_REGIME_permutation"][fam] = {"status": "NOT_IDENTIFIABLE"}; continue
            gg = sorted({r["cw"] for r in sub0})
            cel = {g: {aa: sum(1 for r in sub0 if r["cw"] == g and rgm_panel[r["p"]][fam] == aa),
                       bb: sum(1 for r in sub0 if r["cw"] == g and rgm_panel[r["p"]][fam] == bb)} for g in gg}
            gok = [g for g in gg if min(cel[g].values()) >= F.MIN_OBS_CELL]
            if len(gok) < F.MIN_GRUPPER:
                res["ICB_x_REGIME_permutation"][fam] = {"status": "NOT_IDENTIFIABLE"}; continue
            sub = [r for r in sub0 if r["cw"] in gok]
            Q = Panel(np.array([r["p"] for r in sub]))
            y2 = Q.dm(np.array([r["ret"] for r in sub]))[:, 0]
            s2 = np.array([r["s"] for r in sub])
            M = np.array([[1.0 if r["cw"] == g else 0.0 for g in gok] for r in sub])
            paneler = sorted({r["p"] for r in sub})
            tillst = np.array([1.0 if rgm_panel[p][fam] == aa else 0.0 for p in paneler])
            pos = {p: i for i, p in enumerate(paneler)}
            pmap = np.array([pos[r["p"]] for r in sub])
            blk = {"grupper": gok, "celler": cel}
            for mod, key in (("ET", "pET"), ("XGB", "pXGB")):
                d_ = np.array([r[key] for r in sub]) - np.array([r["pH0"] for r in sub])
                Xg_fast = Q.dm(M * d_[:, None])            # d*1[g], oberoende av permutation
                Xd_fast = Q.dm(M[:, 1:])
                ds = Q.dm(d_ * s2)

                def stat(rgm):
                    Xr = Q.dm(M * (d_ * rgm)[:, None])     # d*1[g]*rgm
                    Xs = Q.dm(np.column_stack([s2, s2 * rgm]))
                    b, V = Q.ols(y2, np.column_stack([Xr, Xg_fast, Xd_fast, Xs, ds]))
                    return wald(b, V, list(range(len(gok))))

                Wobs, pobs = stat(tillst[pmap])
                null = []
                for _ in range(NPERM):
                    Wp, _ = stat(rng.permutation(tillst)[pmap])
                    if Wp is not None: null.append(Wp)
                null = np.array(null)
                blk[mod] = {"W_observerad": round(Wobs, 3), "asymptotisk_p": round(pobs, 5),
                            "permutations_p": round(float((np.sum(null >= Wobs) + 1) / (len(null) + 1)), 5),
                            "null_median_W": round(float(np.median(null)), 3),
                            "null_p95_W": round(float(np.percentile(null, 95)), 3), "n_giltiga": len(null)}
                print(f"  {wn} {fam} {mod}: W={Wobs:.2f} asym_p={pobs:.4f} perm_p={blk[mod]['permutations_p']}", flush=True)
            res["ICB_x_REGIME_permutation"][fam] = blk
        ut["fonster"][wn] = res
        print(f"{wn} klart", flush=True)
    (UT / "robusthet.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print("skrivet:", UT / "robusthet.json")


if __name__ == "__main__":
    main()
