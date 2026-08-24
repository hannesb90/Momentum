"""G186-K — ENB-KALIBRERING: är H0:s låga ENB ovanligt?

G186 gav median ENB 2,99 / 2,96 för locked H0. Frågan här är inte om det är
lågt, utan om det är **lägre än andra rimliga 30-namnsportföljer** ur samma
universum.

FÖRREGISTRERAD HYPOTES
    |median ENB_H0 − median ENB_random| < 1,0 i båda fönstren.

PRIMÄRT PLACEBO
    RANDOM EW30 FROM SAME PIT UNIVERSE — 200 dragningar per panel, matchat på
    paneldatum, universum, pris-/historikkrav, 52v-lookback, long-only,
    likavikt och kovariansestimator.

IDENTISK BEHANDLING
    G186 använde parvis snitt av gemensamma veckor. Här används ett REKTANGULÄRT
    veckoraster: panelens 52 senaste ISO-veckor, och endast namn med fullständig
    avkastning för alla 52 behålls — i BÅDE H0-portföljen och slumpuniversumet.
    Det är nödvändigt för att jämförelsen ska vara rättvis, och H0:s ENB räknas
    därför om under samma regel och redovisas jämte G186:s tal.

SEKUNDÄR MATCHNING (endast diagnostiskt)
    Slumpdragning STRATIFIERAD på volatilitetskvintil, så att den slumpmässiga
    portföljen har ungefär H0:s volatilitetsprofil. Ersätter inte primärtestet.

Kör: /opt/momentum/venv/bin/python tools/g186k_enb_kalibrering.py
"""
from __future__ import annotations
import bisect, json, math, sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g186k_results.json"
PANEL = V2 / "research_k/g186k_paneldata.jsonl"
N = 30
COST, PPY = 0.002, 13
NVECKOR = 52
DRAG = 200
SEED = 20260818
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
    w = veckor(F, k)
    if w is None:
        return None
    nyck, wd, wp = w
    j = bisect.bisect_right(wd, dt)
    if j < 3:
        return None
    r = wp[1:j] / wp[:j - 1] - 1
    return dict(zip(nyck[1:j], r))


def ledoit_wolf(X):
    n, p = X.shape
    Xc = X - X.mean(0)
    S_ = (Xc.T @ Xc) / n
    mu = float(np.trace(S_) / p)
    d2 = float(np.sum((S_ - mu * np.eye(p)) ** 2) / p)
    b2 = float(sum(np.sum((np.outer(Xc[i], Xc[i]) - S_) ** 2) for i in range(n)) / (n ** 2 * p))
    b2 = min(b2, d2)
    delta = b2 / d2 if d2 > 0 else 0.0
    return (1 - delta) * S_ + delta * mu * np.eye(p)


def enb(Sig, w):
    lam, E = np.linalg.eigh(Sig)
    lam = np.clip(lam, 1e-14, None)
    wt = E.T @ w
    var = float(w @ Sig @ w)
    if var <= 0:
        return None
    p = (wt ** 2) * lam / var
    p = np.clip(p, 1e-14, None)
    p = p / p.sum()
    return float(np.exp(-np.sum(p * np.log(p))))


def panelraster(F, dt, koder):
    """Rektangulärt raster: panelens 52 senaste ISO-veckor, namn med full historik."""
    per = {}
    for k in koder:
        d = veckoret(F, k, dt)
        if d:
            per[k] = d
    if not per:
        return None, [], []
    alla = sorted({w for v in per.values() for w in v})
    if len(alla) < NVECKOR:
        return None, [], []
    grid = alla[-NVECKOR:]
    full = [k for k, v in per.items() if all(w in v for w in grid)]
    if len(full) < N + 20:
        return None, [], []
    R = np.array([[per[k][w] for k in full] for w in grid])
    return R, full, grid


def h0_urval(F):
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
    ut = {"version": "G186K_ENB_KALIBRERING_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "seed": SEED, "n_dragningar_per_panel": DRAG,
          "hypotes": "|median ENB_H0 - median ENB_random| < 1,0 i bada fonstren",
          "estimator": "sample covariance (primar), Ledoit-Wolf (sensitivitet)",
          "rasterregel": "panelens 52 senaste ISO-veckor; endast namn med full historik, "
                         "identiskt for H0 och slumpportfoljer",
          "fonster": {}}
    rader = []

    for w_, F, namn, ref in (("2020_2026", S.F26, "2020-2026", 0.0720),
                             ("2014_2019", S.F19, "2014-2019", 0.3156)):
        nets, urval = h0_urval(F)
        cagr = float(np.prod(1 + nets) ** (PPY / len(nets)) - 1)
        dts = F["eval_dates"]
        rng = np.random.default_rng(SEED)
        print(f"\n{'='*78}\n{namn}")
        print(f"  A. locked H0 reproducerar: {cagr:.2%} mot {ref:.2%}  "
              f"{'OK' if abs(cagr - ref) < 0.001 else 'AVVIKER'}")

        res, bortfall = [], 0
        for pi, dt in enumerate(dts):
            univ = [r["kod"] for r in F["rankings"][dt]]
            R, full, grid = panelraster(F, dt, univ)
            if R is None:
                bortfall += 1; continue
            idx = {k: i for i, k in enumerate(full)}
            h0i = [idx[k] for k in urval[pi] if k in idx]
            if len(h0i) < 20:
                bortfall += 1; continue
            w0 = np.full(len(h0i), 1.0 / len(h0i))
            Sig0 = np.cov(R[:, h0i], rowvar=False)
            e0 = enb(Sig0, w0)
            e0lw = enb(ledoit_wolf(R[:, h0i]), w0)
            if e0 is None:
                bortfall += 1; continue

            # volatilitetskvintiler for sekundar stratifierad dragning
            v = np.std(R, axis=0, ddof=1)
            kv = np.digitize(v, np.quantile(v, [.2, .4, .6, .8]))
            h0kv = np.bincount(kv[h0i], minlength=5)

            slump, slump_strat = [], []
            wN = np.full(N, 1.0 / N)
            for _ in range(DRAG):
                pick = rng.choice(len(full), size=N, replace=False)
                x = enb(np.cov(R[:, pick], rowvar=False), wN)
                if x is not None:
                    slump.append(x)
                # stratifierad pa H0:s volatilitetsprofil
                sp = []
                for q in range(5):
                    pool = np.where(kv == q)[0]
                    m = min(int(h0kv[q]), len(pool))
                    if m:
                        sp.extend(rng.choice(pool, size=m, replace=False))
                if len(sp) >= 20:
                    ws = np.full(len(sp), 1.0 / len(sp))
                    y = enb(np.cov(R[:, sp], rowvar=False), ws)
                    if y is not None:
                        slump_strat.append(y)
            if len(slump) < 100:
                bortfall += 1; continue
            a = np.array(slump)
            b = np.array(slump_strat) if slump_strat else np.array([np.nan])
            res.append({"pi": pi, "dt": dt, "n_univ": len(full), "n_h0": len(h0i),
                        "enb_h0": e0, "enb_h0_lw": e0lw,
                        "rand_median": float(np.median(a)), "rand_medel": float(a.mean()),
                        "rand_q5": float(np.percentile(a, 5)), "rand_q10": float(np.percentile(a, 10)),
                        "rand_q25": float(np.percentile(a, 25)), "rand_q75": float(np.percentile(a, 75)),
                        "rand_q95": float(np.percentile(a, 95)),
                        "h0_percentil": float((a < e0).mean()),
                        "strat_median": float(np.nanmedian(b))})
            rader.append({"fonster": namn, **res[-1]})

        h0v = np.array([x["enb_h0"] for x in res])
        h0lw = np.array([x["enb_h0_lw"] for x in res])
        rm = np.array([x["rand_median"] for x in res])
        sm = np.array([x["strat_median"] for x in res])
        pc = np.array([x["h0_percentil"] for x in res])
        print(f"\n  B. SLUMPPORTFÖLJER: {DRAG} dragningar per panel, {len(res)} paneler, "
              f"bortfall {bortfall}")
        print(f"     universumstorlek med full 52v-historik: median {np.median([x['n_univ'] for x in res]):.0f}")
        print(f"\n  C/D. H0 MOT SLUMP")
        print(f"     {'':<26}{'median':>9}{'medel':>9}")
        print(f"     {'H0 ENB (rektangulart)':<26}{np.median(h0v):>9.2f}{h0v.mean():>9.2f}")
        print(f"     {'slump EW30 ENB':<26}{np.median(rm):>9.2f}{rm.mean():>9.2f}")
        print(f"     {'skillnad H0 - slump':<26}{np.median(h0v)-np.median(rm):>+9.2f}")
        print(f"     slumpens fordelning (panelmedian av percentiler): "
              f"Q5 {np.median([x['rand_q5'] for x in res]):.2f}  "
              f"Q25 {np.median([x['rand_q25'] for x in res]):.2f}  "
              f"Q75 {np.median([x['rand_q75'] for x in res]):.2f}  "
              f"Q95 {np.median([x['rand_q95'] for x in res]):.2f}")
        print(f"     H0:s percentil i slumpfordelningen: median {np.median(pc):.1%}  "
              f"medel {pc.mean():.1%}")
        print(f"     andel paneler dar H0 < slumpens median: "
              f"{float(np.mean(h0v < rm)):.1%}")
        print(f"     andel paneler dar H0 < slumpens Q10: "
              f"{float(np.mean([x['enb_h0'] < x['rand_q10'] for x in res])):.1%}")
        h = len(res) // 2
        print(f"     stabilitet: forsta halvan H0-slump {np.median(h0v[:h])-np.median(rm[:h]):+.2f}, "
              f"andra halvan {np.median(h0v[h:])-np.median(rm[h:]):+.2f}")
        print(f"\n  E. SEKUNDAR (volatilitetsstratifierad slump, endast diagnostisk)")
        print(f"     stratifierad slump median {np.nanmedian(sm):.2f}  "
              f"H0 minus stratifierad {np.median(h0v)-np.nanmedian(sm):+.2f}")
        print(f"\n  F. SENSITIVITET (Ledoit-Wolf pa H0)")
        print(f"     H0 LW median {np.median(h0lw):.2f} mot sample {np.median(h0v):.2f}")

        ut["fonster"][w_] = {
            "h0_cagr": round(cagr, 5), "h0_reproducerar": bool(abs(cagr - ref) < 0.001),
            "n_paneler": len(res), "n_bortfall": bortfall,
            "univ_median": float(np.median([x["n_univ"] for x in res])),
            "h0_enb_median": round(float(np.median(h0v)), 3),
            "h0_enb_lw_median": round(float(np.median(h0lw)), 3),
            "rand_enb_median": round(float(np.median(rm)), 3),
            "diff_median": round(float(np.median(h0v) - np.median(rm)), 3),
            "rand_q5": round(float(np.median([x["rand_q5"] for x in res])), 3),
            "rand_q25": round(float(np.median([x["rand_q25"] for x in res])), 3),
            "rand_q75": round(float(np.median([x["rand_q75"] for x in res])), 3),
            "rand_q95": round(float(np.median([x["rand_q95"] for x in res])), 3),
            "h0_percentil_median": round(float(np.median(pc)), 4),
            "andel_h0_under_randmedian": round(float(np.mean(h0v < rm)), 4),
            "andel_h0_under_randQ10": round(float(np.mean([x["enb_h0"] < x["rand_q10"] for x in res])), 4),
            "diff_forsta_halvan": round(float(np.median(h0v[:h]) - np.median(rm[:h])), 3),
            "diff_andra_halvan": round(float(np.median(h0v[h:]) - np.median(rm[h:])), 3),
            "strat_median": round(float(np.nanmedian(sm)), 3),
            "diff_mot_strat": round(float(np.median(h0v) - np.nanmedian(sm)), 3)}

    a = ut["fonster"]["2020_2026"]["diff_median"]
    b = ut["fonster"]["2014_2019"]["diff_median"]
    if abs(a) < 1.0 and abs(b) < 1.0:
        dom = "NORMAL LONG-ONLY ENB"
    elif a < -1.0 and b < -1.0:
        dom = "H0 UNUSUALLY CONCENTRATED"
    elif a > 1.0 and b > 1.0:
        dom = "H0 UNUSUALLY DIVERSIFIED"
    else:
        dom = "INCONCLUSIVE / PERIOD-DEPENDENT"
    ut["slutklassificering"] = dom
    print(f"\n{'='*78}\nH0 minus slump: {a:+.2f} (2020-2026) / {b:+.2f} (2014-2019)")
    print(f"SLUTKLASSIFICERING: {dom}")
    with open(PANEL, "w") as f:
        for r in rader:
            f.write(json.dumps(r, ensure_ascii=False, default=float) + "\n")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1, default=float))
    print(f"\nSkrivet: {OUT}\nPaneldata: {PANEL} ({len(rader)} paneler)")


if __name__ == "__main__":
    main()
