"""KONFIDENS FÖR TIDIG REKRYTERING (N=10, köp rank 15-25)

Rutnätet i hysteres_kop_och_agande gav +3,79 pp för N=10 med köpband 15-25 och
ägandegräns 30. Placebot där jämförde mot slumpnamn ur topp-60, vilket är en för
svag motståndare — den mäter mest att rank 41-60 är sämre än 15-25.

Rätt jämförelser är dessa, alla parvis på samma paneler:
  1. mot kanonisk N=10 (köp topp-10, sälj utanför topp-10)
  2. mot samma konstruktion men köp ur topp-10 (isolerar KÖPBANDET från
     ägandegränsen H=30, som annars är ett confound)
  3. mot kanonisk N=20
Plus ett skarpare placebo: köp slumpvalda namn ur topp-25 (samma pool som det
riktiga bandet ligger i), lika många köp.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/tidig_rekrytering_konfidens.py
"""
from __future__ import annotations
import importlib.util, json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/tidig_rekrytering_konfidens_results.json"
COST, PPY = 0.002, 13.0
BLOCK, DRAWS, SEED, N_SEEDS = 13, 2000, 20260815, 300

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tspec = importlib.util.spec_from_file_location("takfel", V2 / "tools/takfel_diagnostik_och_n_svep.py")
tk = importlib.util.module_from_spec(tspec); tspec.loader.exec_module(tk)


def main():
    core_df, prices, terminal = m.load_data()
    returns_map, all_dates = m.execution_engine(core_df, prices, terminal)
    vol_map, price_series = m.compute_vols(prices, window=60)
    rankings = m.derive_h0_scores(core_df, prices)
    eval_dates = sorted(rankings.keys())
    anchor = all_dates.index(m.PHASE_ANCHOR_H0) % 2
    confirm_map = m.fetch_fundamental_confirmations(rankings, prices)
    rank_map = {(r["kod"], dt): i + 1 for dt in eval_dates for i, r in enumerate(rankings[dt])}

    sma_cache = {}
    def sma_ok(k, dt):
        key = (k, dt)
        if key not in sma_cache:
            v = True
            if k in price_series:
                ds, adj = price_series[k]
                i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
                if i is not None and i >= 200:
                    v = adj[i] >= float(np.mean(adj[i - 200:i]))
            sma_cache[key] = v
        return sma_cache[key]

    def sim(N, lo, hi, H, rng=None, pool_hi=25):
        cap = tk.cap_for(N)
        prev, nets = [], []
        for pi, dt in enumerate(eval_dates):
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            if not prev:
                sel0 = [r["kod"] for r in raw[lo - 1:hi]][:N]
            elif sched:
                behall = [k for k in prev if k in elig and rank_map[(k, dt)] <= H]
                sel0 = sorted(behall, key=lambda k: rank_map[(k, dt)])
                plats = N - len(sel0)
                if plats > 0:
                    kand = [r["kod"] for r in raw[lo - 1:hi] if r["kod"] not in sel0]
                    if rng is not None:
                        pool = [r["kod"] for r in raw[:pool_hi] if r["kod"] not in sel0]
                        rng.shuffle(pool)
                        kand = pool[:len(kand)]
                    sel0 += kand[:plats]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < N:
                    kand = [r["kod"] for r in raw[lo - 1:hi] if r["kod"] not in sel0]
                    sel0 += kand[: N - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
            sel = [k for k in sel0 if sma_ok(k, dt)]
            n = len(sel)
            if n == 0:
                nets.append(0.0); prev = sel0; continue
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            ts = n / N
            w_raw = inv / np.sum(inv) * ts
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = tk.w_waterfill(w_raw * conf, ts, cap)
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(nets)

    def boot(a, b):
        rng = np.random.default_rng(SEED)
        n = len(a); nb = int(math.ceil(n / BLOCK)); outs = []
        for _ in range(DRAWS):
            idx = []
            for _ in range(nb):
                s = rng.integers(0, n - BLOCK + 1); idx.extend(range(s, s + BLOCK))
            idx = np.array(idx[:n])
            outs.append(np.cumprod(1 + a[idx])[-1] ** (PPY / n) - np.cumprod(1 + b[idx])[-1] ** (PPY / n))
        d = a - b; sd = d.std(ddof=1)
        lo, hi = np.percentile(outs, [2.5, 97.5])
        return {"delta_cagr": round(float(tk.stats(a)[0] - tk.stats(b)[0]), 4),
                "ki_lo": round(float(lo), 4), "ki_hi": round(float(hi), 4),
                "t_parvis": round(float(d.mean() / (sd / math.sqrt(n))), 3) if sd > 0 else None,
                "andel_bootstrap_positiva": round(float(np.mean(np.array(outs) > 0)), 3)}

    armar = {
        "tidig_N10_kop15-25_H30": sim(10, 15, 25, 30),
        "tidig_N10_kop15-25_H40": sim(10, 15, 25, 40),
        "toppkop_N10_kop1-10_H30": sim(10, 1, 10, 30),
        "kanonisk_N10": sim(10, 1, 10, 10),
        "kanonisk_N20": sim(20, 1, 20, 20),
    }
    out = {
        "version": "TIDIG_REKRYTERING_KONFIDENS_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, ingen challenger",
        "forbehall": "cellen är bästa av 23 i ett rutnät; jämförelserna nedan är efterhandsprövningar "
                     "av en vald cell och ersätter inte förregistrering",
        "armar": {k: {"cagr": round(tk.stats(v)[0], 4), "vol": round(tk.stats(v)[1], 4),
                      "maxdd": round(tk.stats(v)[2], 4), "sharpe": round(tk.stats(v)[3], 4)}
                  for k, v in armar.items()},
        "jamforelser": {},
    }
    a = armar["tidig_N10_kop15-25_H30"]
    for namn, b in [("mot_kanonisk_N10", armar["kanonisk_N10"]),
                    ("mot_toppkop_samma_H30", armar["toppkop_N10_kop1-10_H30"]),
                    ("mot_kanonisk_N20", armar["kanonisk_N20"])]:
        out["jamforelser"][namn] = boot(a, b)
    a2 = armar["tidig_N10_kop15-25_H40"]
    out["jamforelser"]["H40_mot_kanonisk_N10"] = boot(a2, armar["kanonisk_N10"])

    # skarpare placebo: slumpnamn ur topp-25, samma antal köp
    bas_c = tk.stats(armar["kanonisk_N10"])[0]
    riktig = tk.stats(a)[0] - bas_c
    pl = []
    for s in range(N_SEEDS):
        rng = np.random.default_rng(80000 + s)
        pl.append(tk.stats(sim(10, 15, 25, 30, rng=rng, pool_hi=25))[0] - bas_c)
    pl = np.array(pl)
    out["placebo_topp25"] = {"riktig_delta": round(float(riktig), 4),
                             "median": round(float(np.median(pl)), 4),
                             "p5": round(float(np.percentile(pl, 5)), 4),
                             "p95": round(float(np.percentile(pl, 95)), 4),
                             "sd": round(float(pl.std(ddof=1)), 4),
                             "andel_minst_lika_bra": round(float((pl >= riktig).mean()), 4)}

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("ARMAR:")
    for k, v in out["armar"].items():
        print(f"  {k:<26} CAGR {v['cagr']:7.2%}  vol {v['vol']:6.2%}  DD {v['maxdd']:7.2%}  Sharpe {v['sharpe']:.3f}")
    print("\nJÄMFÖRELSER (parvis block-bootstrap, 13-panelsblock):")
    for k, v in out["jamforelser"].items():
        print(f"  {k:<26} Δ {v['delta_cagr']:+.2%}  KI [{v['ki_lo']:+.2%}, {v['ki_hi']:+.2%}]  "
              f"t {v['t_parvis']:+.2f}  andel positiva {v['andel_bootstrap_positiva']:.0%}")
    p = out["placebo_topp25"]
    print(f"\nPLACEBO (slumpnamn ur topp-25, {N_SEEDS} seeds): riktig Δ {p['riktig_delta']:+.2%}  |  "
          f"median {p['median']:+.2%}, 5-95 % [{p['p5']:+.2%}, {p['p95']:+.2%}]  →  "
          f"{p['andel_minst_lika_bra']:.1%} minst lika bra")
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
