"""G186 — EFFECTIVE NUMBER OF BETS på canonical locked H0

Förregistrering: research_k/g186_preregistration.json
sha256 891fc11c69aa06494074307bccf0b3a9d6be759b247d4de019b51aa4273add00

STRIKT DIAGNOSTISKT. Ingen regel, ingen viktoptimering, ingen G97-variant.

Meucci (2009) principalportföljer:
    Sigma = E Lambda E'          egenvärdesuppdelning av kovariansmatrisen
    w_tilde = E' w               vikter i principalbasen
    p_i = w_tilde_i^2 lambda_i / (w' Sigma w)
    ENB = exp(-sum p_i ln p_i)

Input: exakt de namn locked H0 äger vid panelen, veckovisa enkla avkastningar
ur ISO-veckorekonstruktionen, trailing 52 veckor, strikt PIT.

KÄND BIAS, förregistrerad: med 52 observationer och upp till 30 tillgångar är
sample-kovariansen dåligt konditionerad. Största egenvärdet överskattas och de
minsta underskattas, vilket biasar ENB NEDÅT. Ett lågt ENB ska därför läsas som
ett GOLV. Ledoit-Wolf-shrinkage körs som förregistrerad sensitivitet, aldrig
för att välja det snyggaste utfallet.

TRE SKILDA STORHETER som inte får blandas:
  antal innehav = 30
  viktbaserat effective N = 1/HHI = 30 vid likavikt
  effective number of CONTRIBUTORS (G55/G40: 40,2 och 56,4) — avkastningsbidrag

Kör: /opt/momentum/venv/bin/python tools/g186_effective_bets.py
"""
from __future__ import annotations
import bisect, json, math, sys
from collections import defaultdict
from datetime import date, timezone, datetime
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g186_results.json"
PANEL = V2 / "research_k/g186_paneldata.jsonl"
N, K = 30, 6
COST, PPY = 0.002, 13
MINV, MINN = 45, 20
_W = {}


def veckor(F, k):
    n = (id(F), k)
    if n in _W:
        return _W[n]
    if F is S.F19:
        s = M.SERIE.get(k)
        d = None if s is None else (s[0].astype("datetime64[D]").astype(str).tolist(), np.asarray(s[1]))
    else:
        s = S.PS26.get(k)
        d = None if s is None else (list(s[0]), np.asarray(s[1]))
    if d is None:
        _W[n] = None
        return None
    ds, adj = d
    sista = {}
    for i, x in enumerate(ds):
        y, w, _ = date.fromisoformat(x).isocalendar()
        sista[(y, w)] = i
    nyck = sorted(sista)
    idx = [sista[x] for x in nyck]
    _W[n] = (nyck, [ds[i] for i in idx], adj[idx])
    return _W[n]


def veckoret(F, k, dt):
    """-> dict {(år,vecka): avkastning} för de 52 veckor som slutar vid dt."""
    w = veckor(F, k)
    if w is None:
        return None
    nyck, wd, wp = w
    j = bisect.bisect_right(wd, dt)
    lo = max(0, j - 53)
    p, nk = wp[lo:j], nyck[lo + 1:j]
    if len(p) < MINV + 1:
        return None
    r = p[1:] / p[:-1] - 1
    return dict(zip(nk, r))


def vol52(F, k, dt):
    d = veckoret(F, k, dt)
    return None if d is None else float(np.std(list(d.values()), ddof=1))


def ledoit_wolf(X):
    """Shrinkage mot skalad enhetsmatris, standardformulering."""
    n, p = X.shape
    Xc = X - X.mean(0)
    S_ = (Xc.T @ Xc) / n
    mu = float(np.trace(S_) / p)
    d2 = float(np.sum((S_ - mu * np.eye(p)) ** 2) / p)
    b2 = float(sum(np.sum((np.outer(Xc[i], Xc[i]) - S_) ** 2) for i in range(n)) / (n ** 2 * p))
    b2 = min(b2, d2)
    delta = b2 / d2 if d2 > 0 else 0.0
    return (1 - delta) * S_ + delta * mu * np.eye(p), float(delta)


def enb(Sig, w):
    """Meucci ENB. Returnerar (ENB, största egenvärdets andel, topp-3 andel)."""
    lam, E = np.linalg.eigh(Sig)
    lam = np.clip(lam, 1e-14, None)
    wt = E.T @ w
    var = float(w @ Sig @ w)
    if var <= 0:
        return None, None, None
    p = (wt ** 2) * lam / var
    p = np.clip(p, 1e-14, None)
    p = p / p.sum()
    e = float(np.exp(-np.sum(p * np.log(p))))
    o = np.sort(lam)[::-1]
    return e, float(o[0] / lam.sum()), float(o[:3].sum() / lam.sum())


def matris(F, koder, dt):
    """-> (R som (veckor x namn), giltiga koder). Gemensamma veckor för alla."""
    per = {}
    for k in koder:
        d = veckoret(F, k, dt)
        if d is not None:
            per[k] = d
    if len(per) < MINN:
        return None, []
    gem = set.intersection(*[set(v) for v in per.values()])
    if len(gem) < MINV:
        # släpp namn som saknar för många veckor tills snittet räcker
        alla = sorted({w for v in per.values() for w in v})
        tack = {k: len(set(v) & set(alla[-52:])) for k, v in per.items()}
        behall = [k for k, c in tack.items() if c >= MINV]
        if len(behall) < MINN:
            return None, []
        per = {k: per[k] for k in behall}
        gem = set.intersection(*[set(v) for v in per.values()])
        if len(gem) < 30:
            return None, []
    g = sorted(gem)
    ks = sorted(per)
    R = np.array([[per[k][w] for k in ks] for w in g])
    return R, ks


def h0_urval(F):
    """Locked H0: urval per panel + nettoserie."""
    dts, ret, schedf = F["eval_dates"], F["returns_map"], F["sched_fn"]
    w, nets, urval = {}, [], []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w:
            sel = [r["kod"] for r in raw][:N]
            mal = {k: 1.0 / N for k in sel}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0)) for k in set(mal) | set(w)) / 2.0
        else:
            mal = dict(w); turn = 0.0
        urval.append(list(mal))
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        nets.append(float(sum(mal[k] * r[k] for k in mal)) - COST * turn)
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return np.array(nets), urval


def main():
    ut = {"version": "G186_ENB_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "prereg_sha256": "891fc11c69aa06494074307bccf0b3a9d6be759b247d4de019b51aa4273add00",
          "hypotes": "median ENB >= 10 i BADA fonstren", "fonster": {}}
    rader = []

    for w_, F, namn, ref in (("2020_2026", S.F26, "2020-2026", 0.0720),
                             ("2014_2019", S.F19, "2014-2019", 0.3156)):
        nets, urval = h0_urval(F)
        cagr = float(np.prod(1 + nets) ** (PPY / len(nets)) - 1)
        dts = F["eval_dates"]
        print(f"\n{'='*78}\n{namn}")
        print(f"  B. locked H0 reproducerar: {cagr:.2%} mot {ref:.2%}  "
              f"{'OK' if abs(cagr - ref) < 0.001 else 'AVVIKER'}")

        res, bortfall = [], []
        for pi, dt in enumerate(dts):
            R, ks = matris(F, urval[pi], dt)
            if R is None:
                bortfall.append(dt); continue
            n_ = len(ks)
            w = np.full(n_, 1.0 / n_)
            Sig = np.cov(R, rowvar=False)
            e, l1, l3 = enb(Sig, w)
            Sh, delta = ledoit_wolf(R)
            e_lw, _, _ = enb(Sh, w)
            C = np.corrcoef(R, rowvar=False)
            iu = np.triu_indices(n_, 1)
            res.append({"pi": pi, "dt": dt, "n": n_, "n_veckor": R.shape[0],
                        "enb": e, "enb_lw": e_lw, "lw_delta": delta,
                        "lambda1_andel": l1, "lambda3_andel": l3,
                        "medelkorr": float(np.mean(C[iu]))})
            rader.append({"fonster": namn, **res[-1]})

        v = np.array([x["enb"] for x in res])
        vlw = np.array([x["enb_lw"] for x in res])
        print(f"\n  C/D. ENB — {len(res)} giltiga paneler av {len(dts)}"
              f"   bortfall {len(bortfall)}")
        print(f"    {'':<16}{'median':>9}{'medel':>9}{'Q10':>8}{'Q25':>8}{'Q75':>8}{'Q90':>8}"
              f"{'min':>8}{'max':>8}")
        for et, a in (("sample (primär)", v), ("Ledoit-Wolf (sens.)", vlw)):
            print(f"    {et:<16}{np.median(a):>9.2f}{a.mean():>9.2f}"
                  f"{np.percentile(a,10):>8.2f}{np.percentile(a,25):>8.2f}"
                  f"{np.percentile(a,75):>8.2f}{np.percentile(a,90):>8.2f}"
                  f"{a.min():>8.2f}{a.max():>8.2f}")
        print(f"    andel paneler ENB<5: {(v<5).mean():.1%}   <10: {(v<10).mean():.1%}   "
              f"<15: {(v<15).mean():.1%}   ENB/30 median: {np.median(v)/30:.3f}")

        # stabilitet över tid
        h = len(res) // 2
        print(f"    stabilitet: forsta halvan median {np.median(v[:h]):.2f}, "
              f"andra halvan {np.median(v[h:]):.2f}")

        # F. eigen-/korrelationsdiagnostik
        l1 = np.array([x["lambda1_andel"] for x in res])
        l3 = np.array([x["lambda3_andel"] for x in res])
        mk = np.array([x["medelkorr"] for x in res])
        print(f"\n  F. EIGEN- OCH KORRELATIONSDIAGNOSTIK")
        print(f"    medel pairwise korrelation: median {np.median(mk):.3f}  "
              f"[{mk.min():.3f}, {mk.max():.3f}]")
        print(f"    storsta egenvardets andel av total varians: median {np.median(l1):.1%}")
        print(f"    tre storsta egenvardenas andel: median {np.median(l3):.1%}")
        print(f"    Ledoit-Wolf shrinkage delta: median "
              f"{np.median([x['lw_delta'] for x in res]):.3f}")

        # G. relation till efterföljande risk
        fut_vol, fut_dd = [], []
        for x in res:
            i = x["pi"]
            seg = nets[i:i + 3]
            if len(seg) < 3:
                fut_vol.append(np.nan); fut_dd.append(np.nan); continue
            fut_vol.append(float(np.std(seg, ddof=1) * math.sqrt(PPY)))
            cw = np.cumprod(1 + seg)
            fut_dd.append(float((cw / np.maximum.accumulate(cw) - 1).min()))
        fv, fd = np.array(fut_vol), np.array(fut_dd)
        m = ~np.isnan(fv)
        kv = float(np.corrcoef(v[m], fv[m])[0, 1]) if m.sum() > 10 else float("nan")
        kd = float(np.corrcoef(v[m], fd[m])[0, 1]) if m.sum() > 10 else float("nan")
        print(f"\n  G. DESKRIPTIVT SAMBAND (ingen gate far licensieras harav)")
        print(f"    korr(ENB, efterfoljande 3-panelsvol): {kv:+.3f}")
        print(f"    korr(ENB, efterfoljande 3-paneldrawdown): {kd:+.3f}")

        # H. G97-P riskkoncentration
        print(f"\n  H. G97-P RISKKONCENTRATION (befintliga exkluderingar, ingen omkorning)")
        cin, cout, ccross, denb, andel_var = [], [], [], [], []
        for x in res:
            pi, dt = x["pi"], x["dt"]
            koder = urval[pi]
            v52 = {k: vol52(F, k, dt) for k in koder}
            med = {k: y for k, y in v52.items() if y is not None}
            if len(med) < MINN:
                continue
            bort = set(sorted(med, key=lambda k: -med[k])[:K])
            R, ks = matris(F, koder, dt)
            if R is None:
                continue
            idx = {k: i for i, k in enumerate(ks)}
            bi = [idx[k] for k in bort if k in idx]
            oi = [idx[k] for k in ks if k not in bort]
            if len(bi) < 3 or len(oi) < 10:
                continue
            C = np.corrcoef(R, rowvar=False)
            cin.append(float(np.mean([C[a, b] for a in bi for b in bi if a < b])))
            cout.append(float(np.mean([C[a, b] for a in oi for b in oi if a < b])))
            ccross.append(float(np.mean([C[a, b] for a in bi for b in oi])))
            Sig = np.cov(R, rowvar=False)
            n_ = len(ks); w = np.full(n_, 1.0 / n_)
            tot = float(w @ Sig @ w)
            bidrag = float(sum(w[a] * (Sig[a] @ w) for a in bi)) / tot if tot > 0 else np.nan
            andel_var.append(bidrag)
            # ENB for G97-P:s redan definierade portfolj: behallna + rank 31-36
            raw = [r["kod"] for r in F["rankings"][dt]]
            ers = raw[N:N + K]
            nya = [k for k in koder if k not in bort] + ers
            R2, ks2 = matris(F, nya, dt)
            if R2 is not None:
                w2 = np.full(len(ks2), 1.0 / len(ks2))
                e2, _, _ = enb(np.cov(R2, rowvar=False), w2)
                if e2 is not None:
                    denb.append(e2 - x["enb"])
        if len(cin) > 8:
            print(f"    pairwise korr mellan de sex exkluderade: {np.mean(cin):+.3f}")
            print(f"    pairwise korr mellan ovriga:             {np.mean(cout):+.3f}")
            print(f"    korr high-vol mot ovriga:                {np.mean(ccross):+.3f}")
            print(f"    de sex andel av portfoljvariansen:       {np.mean(andel_var):.1%} "
                  f"(mot {K}/{N} = {K/N:.1%} vid likavikt och lika risk)")
            print(f"    delta ENB (G97-P minus H0):              {np.mean(denb):+.2f} "
                  f"(median {np.median(denb):+.2f}, andel positiva {np.mean(np.array(denb)>0):.0%})")
            g97 = {"korr_inom_high_vol": round(float(np.mean(cin)), 4),
                   "korr_inom_ovriga": round(float(np.mean(cout)), 4),
                   "korr_cross": round(float(np.mean(ccross)), 4),
                   "andel_portfoljvarians": round(float(np.mean(andel_var)), 4),
                   "delta_enb_medel": round(float(np.mean(denb)), 3),
                   "delta_enb_median": round(float(np.median(denb)), 3),
                   "andel_positiva": round(float(np.mean(np.array(denb) > 0)), 3),
                   "n_paneler": len(cin)}
        else:
            g97 = None; print("    for fa paneler")

        # I. robusthet
        loo = [float(np.median(np.delete(v, i))) for i in range(len(v))]
        print(f"\n  I. ROBUSTHET")
        print(f"    leave-one-panel-out pa medianen: [{min(loo):.2f}, {max(loo):.2f}]")
        print(f"    bortfall: {len(bortfall)} paneler utan tillracklig historik")
        print(f"    veckor per matris: median {np.median([x['n_veckor'] for x in res]):.0f}, "
              f"namn per matris: median {np.median([x['n'] for x in res]):.0f}")

        ut["fonster"][w_] = {
            "h0_cagr": round(cagr, 5), "h0_reproducerar": bool(abs(cagr - ref) < 0.001),
            "n_paneler": len(res), "n_bortfall": len(bortfall),
            "enb_sample": {"median": round(float(np.median(v)), 3), "medel": round(float(v.mean()), 3),
                           "q10": round(float(np.percentile(v, 10)), 3),
                           "q25": round(float(np.percentile(v, 25)), 3),
                           "q75": round(float(np.percentile(v, 75)), 3),
                           "q90": round(float(np.percentile(v, 90)), 3),
                           "min": round(float(v.min()), 3), "max": round(float(v.max()), 3),
                           "andel_under_5": round(float((v < 5).mean()), 4),
                           "andel_under_10": round(float((v < 10).mean()), 4),
                           "andel_under_15": round(float((v < 15).mean()), 4),
                           "enb_over_30_median": round(float(np.median(v) / 30), 4),
                           "forsta_halvan_median": round(float(np.median(v[:h])), 3),
                           "andra_halvan_median": round(float(np.median(v[h:])), 3)},
            "enb_ledoit_wolf": {"median": round(float(np.median(vlw)), 3),
                                "medel": round(float(vlw.mean()), 3),
                                "delta_median": round(float(np.median([x["lw_delta"] for x in res])), 4)},
            "eigen": {"medelkorr_median": round(float(np.median(mk)), 4),
                      "lambda1_andel_median": round(float(np.median(l1)), 4),
                      "lambda3_andel_median": round(float(np.median(l3)), 4)},
            "framtida_risk": {"korr_enb_vol": round(kv, 4), "korr_enb_drawdown": round(kd, 4)},
            "g97_riskkoncentration": g97,
            "robusthet": {"loo_median_min": round(min(loo), 3), "loo_median_max": round(max(loo), 3)}}

    a = ut["fonster"]["2020_2026"]["enb_sample"]["median"]
    b = ut["fonster"]["2014_2019"]["enb_sample"]["median"]
    alw = ut["fonster"]["2020_2026"]["enb_ledoit_wolf"]["median"]
    blw = ut["fonster"]["2014_2019"]["enb_ledoit_wolf"]["median"]
    if a >= 10 and b >= 10:
        dom = "ROBUSTLY DIVERSIFIED"
    elif a < 10 or b < 10:
        nara = abs(a - 10) < 1.5 or abs(b - 10) < 1.5
        instabil = (alw >= 10) != (a >= 10) or (blw >= 10) != (b >= 10)
        dom = "INCONCLUSIVE" if (nara or instabil) else "MATERIAL HIDDEN RISK CONCENTRATION"
    ut["slutklassificering"] = dom
    print(f"\n{'='*78}\nMedian ENB: {a:.2f} (2020-2026) / {b:.2f} (2014-2019)")
    print(f"Ledoit-Wolf sensitivitet: {alw:.2f} / {blw:.2f}")
    print(f"SLUTKLASSIFICERING: {dom}")
    with open(PANEL, "w") as f:
        for r in rader:
            f.write(json.dumps(r, ensure_ascii=False, default=float) + "\n")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nPaneldata: {PANEL} ({len(rader)} paneler)")


if __name__ == "__main__":
    main()
