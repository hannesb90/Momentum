"""TVÅ FÖNSTER: ETT FÖR KÖP, ETT FÖR ÄGANDE

Två läsningar av samma idé, båda testade:

  A. STRAMT KÖP, VITT ÄGANDE   köp bara i topp-E (E < N), behåll tills rank > H.
     Kapitalet som inte får köpa nytt stannar i befintliga innehav.
  B. TIDIG REKRYTERING          äg få namn (N=10) men hämta dem kring rank 20 i
     stället för i toppen — alltså köp tidigare i klättringen och sitt kvar.

Generell parametrisering: köpband [lo, hi], ägandegräns H, portföljtak N.
Baslinjen är lo=1, hi=N, H=N.

STEG 1 (universumnivå, hög n) avgör frågan innan någon portfölj byggs: var i
ranglistan ligger framåtavkastningen? Om den är platt kan inget val av köpband
bära något, oavsett hur portföljen sedan konstrueras.

STEG 2 är tillgänglighet — hur många namn i ett köpband är lediga när vi redan
äger N? En regel som aldrig binder kan inte mätas.

STEG 3 är portföljrutnätet, STEG 4 placebo på bästa cellen.

KRAFT: 66 paneler, placebobandet ±2,4 pp, rutnätet har många celler. Bästa
cellen bär en urvalspremie i samma storleksordning som allt vi letar efter.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/hysteres_kop_och_agande.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/hysteres_kop_och_agande_results.json"
COST, PPY = 0.002, 13.0
N_SEEDS = 200

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

    def fram(k, pi, h):
        tot = 1.0
        for j in range(pi, min(pi + h, len(eval_dates))):
            tot *= 1.0 + returns_map.get((k, eval_dates[j]), 0.0)
        return tot - 1.0

    out = {
        "version": "HYSTERES_KOP_OCH_AGANDE_V2",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, ingen challenger",
        "regel": "köp endast om rank i [lo, hi]; behåll tills rank > H; portföljtak N",
        "kraftforbehall": "66 paneler, placebobandet ±2,4 pp, många celler i rutnätet",
        "n_paneler": len(eval_dates),
    }

    # ---------- STEG 1: var i ranglistan ligger framåtavkastningen? ----------
    band = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 40), (41, 60)]
    steg1 = {}
    for lo, hi in band:
        r1, r3, r6, r1_klattr = [], [], [], []
        for pi, dt in enumerate(eval_dates):
            raw = rankings[dt]
            fore = eval_dates[pi - 1] if pi > 0 else None
            for r in raw[lo - 1:hi]:
                k = r["kod"]
                if not sma_ok(k, dt):
                    continue
                r1.append(fram(k, pi, 1)); r3.append(fram(k, pi, 3)); r6.append(fram(k, pi, 6))
                if fore is not None:
                    r0, rn = rank_map.get((k, fore)), rank_map.get((k, dt))
                    if r0 and rn and rn < r0:
                        r1_klattr.append(fram(k, pi, 1))
        def s(v):
            a = np.array(v, dtype=float)
            return {"n": len(a), "medel": round(float(a.mean()), 4), "median": round(float(np.median(a)), 4),
                    "t": round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 2)} if len(a) > 2 else None
        steg1[f"{lo}-{hi}"] = {"1_panel": s(r1), "3_paneler": s(r3), "6_paneler": s(r6),
                               "1_panel_om_stigande": s(r1_klattr)}
    out["steg1_framatavkastning_per_rankband"] = steg1
    print("STEG 1 — framåtavkastning per rankband (hela universum, SMA-godkända):")
    print(f"  {'band':<8} {'n':>5} {'1p':>8} {'3p':>8} {'6p':>8}   {'1p om stigande':>16}")
    for b, d in steg1.items():
        if d["1_panel"]:
            st = d["1_panel_om_stigande"]
            print(f"  {b:<8} {d['1_panel']['n']:>5} {d['1_panel']['medel']:>8.2%} "
                  f"{d['3_paneler']['medel']:>8.2%} {d['6_paneler']['medel']:>8.2%}   "
                  f"{st['medel']:>10.2%} (n={st['n']})")

    # ---------- portföljmotor ----------
    def sim(N, lo, hi, H, exponering="flytande", rng=None):
        cap = tk.cap_for(N)
        prev, nets, antal, expo, turns, kop = [], [], [], [], [], 0
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
                        pool = [r["kod"] for r in raw[:60] if r["kod"] not in sel0]
                        rng.shuffle(pool)
                        kand = pool[:len(kand)]
                    sel0 += kand[:plats]
                    kop += min(plats, len(kand))
            else:
                # kanoniskt: mellan ombalanseringar säljs ingenting, oavsett rank
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < N:
                    kand = [r["kod"] for r in raw[lo - 1:hi] if r["kod"] not in sel0]
                    sel0 += kand[: N - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
            turns.append(turn)
            sel = [k for k in sel0 if sma_ok(k, dt)]
            n = len(sel)
            antal.append(len(sel0))
            if n == 0:
                nets.append(0.0); expo.append(0.0); prev = sel0; continue
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            ts = (n / N) if exponering == "flytande" else 1.0
            w_raw = inv / np.sum(inv) * ts
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = tk.w_waterfill(w_raw * conf, ts, cap)
            expo.append(float(np.sum(w)))
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(nets), {"medelantal": round(float(np.mean(antal)), 1),
                                "min_antal": int(np.min(antal)),
                                "medelexponering": round(float(np.mean(expo)), 3),
                                "arlig_omsattning": round(float(np.mean(turns)) * PPY, 3),
                                "kop_totalt": kop}

    # ---------- STEG 2: tillgänglighet ----------
    prev, ledig = [], defaultdict(list)
    for pi, dt in enumerate(eval_dates):
        sched = all_dates.index(dt) % 2 == anchor
        raw = rankings[dt]
        if prev and sched:
            for namn, (lo, hi) in {"1-10": (1, 10), "11-20": (11, 20), "15-25": (15, 25)}.items():
                ledig[namn].append(sum(1 for r in raw[lo - 1:hi] if r["kod"] not in prev))
        elig = {r["kod"] for r in raw}
        if sched or not prev:
            prev = [r["kod"] for r in raw[:10]]
        else:
            s2 = [k for k in prev if k in elig]
            if len(s2) < 10:
                s2 += [r["kod"] for r in raw if r["kod"] not in s2][: 10 - len(s2)]
            prev = s2
    out["steg2_tillganglighet_vid_N10"] = {
        b: {"medel_lediga": round(float(np.mean(v)), 2), "median": float(np.median(v)),
            "andel_paneler_med_noll": round(float(np.mean([1.0 if x == 0 else 0.0 for x in v])), 3)}
        for b, v in ledig.items()}
    print("\nSTEG 2 — lediga namn per köpband när vi äger 10:")
    for b, d in out["steg2_tillganglighet_vid_N10"].items():
        print(f"  {b:<7} medel {d['medel_lediga']:>5}  median {d['median']:>4}  noll lediga {d['andel_paneler_med_noll']:.0%}")

    # ---------- STEG 3: rutnät ----------
    bas20, _ = sim(20, 1, 20, 20)
    bas20_c = tk.stats(bas20)[0]
    bas10, _ = sim(10, 1, 10, 10)
    bas10_c = tk.stats(bas10)[0]
    out["baslinjer"] = {"N20_topp20": round(bas20_c, 4), "N10_topp10": round(bas10_c, 4)}
    print(f"\nbaslinjer: N=20 köp topp-20 → {bas20_c:.2%} · N=10 köp topp-10 → {bas10_c:.2%}")

    grid = []
    # A: stramt köp, vitt ägande (N=20)
    for lo, hi in [(1, 5), (1, 10), (1, 15)]:
        for H in (20, 30, 40):
            grid.append((20, lo, hi, H))
    # B: tidig rekrytering, litet ägande (N=10)
    for lo, hi in [(1, 10), (11, 20), (15, 25), (16, 30), (1, 20)]:
        for H in (10, 20, 30, 40):
            grid.append((10, lo, hi, H))
    out["steg3_rutnat"] = {}
    print("\nSTEG 3 — rutnät (kanonisk flytande exponering, cap = max(0,06, 1,5/N)):")
    for N, lo, hi, H in grid:
        if H < hi:
            continue
        nets, dd = sim(N, lo, hi, H)
        c, v, mdd, sh = tk.stats(nets)
        ref = bas20_c if N == 20 else bas10_c
        nyckel = f"N{N}_kop{lo}-{hi}_H{H}"
        out["steg3_rutnat"][nyckel] = {"cagr": round(c, 4), "delta_mot_egen_bas": round(c - ref, 4),
                                       "vol": round(v, 4), "maxdd": round(mdd, 4), "sharpe": round(sh, 4), **dd}
        print(f"  N={N:<3} köp {lo:>2}-{hi:<3} H={H:<3} CAGR {c:7.2%}  Δ {c-ref:+6.2%}  Sharpe {sh:.3f}  "
              f"antal {dd['medelantal']:>4}  oms {dd['arlig_omsattning']:>5.0%}  köp {dd['kop_totalt']:>3}")

    # ---------- STEG 4: placebo på bästa cellen ----------
    basta = max(out["steg3_rutnat"], key=lambda k: out["steg3_rutnat"][k]["delta_mot_egen_bas"])
    dele = basta.split("_")
    N = int(dele[0][1:]); lo, hi = [int(x) for x in dele[1][3:].split("-")]; H = int(dele[2][1:])
    ref = bas20_c if N == 20 else bas10_c
    placebo = []
    for s in range(N_SEEDS):
        rng = np.random.default_rng(60000 + s)
        p, _ = sim(N, lo, hi, H, rng=rng)
        placebo.append(tk.stats(p)[0] - ref)
    placebo = np.array(placebo)
    riktig = out["steg3_rutnat"][basta]["delta_mot_egen_bas"]
    out["steg4_placebo"] = {"cell": basta, "riktig_delta": riktig,
                            "beskrivning": "lika många köp, slumpvalda ur topp-60 i stället för ur köpbandet",
                            "median": round(float(np.median(placebo)), 4),
                            "p5": round(float(np.percentile(placebo, 5)), 4),
                            "p95": round(float(np.percentile(placebo, 95)), 4),
                            "sd": round(float(placebo.std(ddof=1)), 4),
                            "andel_minst_lika_bra": round(float((placebo >= riktig).mean()), 4)}
    p = out["steg4_placebo"]
    print(f"\nSTEG 4 — placebo på {basta}: riktig Δ {riktig:+.2%}  |  placebo median {p['median']:+.2%}, "
          f"5-95 % [{p['p5']:+.2%}, {p['p95']:+.2%}]  →  {p['andel_minst_lika_bra']:.1%} minst lika bra")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
