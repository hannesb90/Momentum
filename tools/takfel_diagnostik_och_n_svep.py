"""TAKFELSDIAGNOSTIK + N-SVEP PÅ LAGAD VIKTNING

Bakgrund. Alla sex frysta modeller viktar med mönstret

    w = clip(w_raw, 0.01, cap)
    w = w / sum(w) * target_sum          <-- kan skjuta vikter TILLBAKA över cap

Renormaliseringen sker EFTER clip och itereras inte, så det deklarerade taket
(1–6 % vid N=30) håller inte i utfallet. Sessionen 2026-08-14 observerade
8,13 % vid N=30 och 12–13,5 % vid N=15 (Axfood 13,53 %, Scandic 12,35 %).

Detta skript:
  1. mäter hur ofta och hur mycket taket bryts i den kanoniska viktningen,
  2. implementerar korrekt iterativ tak/golv-normalisering (water-filling),
  3. kör om Stack D-baslinjen och N-svepet {10,15,20,25,30} med BÅDA metoderna,
  4. mäter koncentrationsberoendet (andel avkastning som försvinner utan topp-3).

DIAGNOSTISKT. Ingen fryst fil ändras, ingen försegling bryts, ingen
challenger skapas. Registret och de sex modellernas definitioner är orörda.

Kör: /opt/momentum/venv/bin/python tools/takfel_diagnostik_och_n_svep.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/takfel_diagnostik_och_n_svep_results.json"
COST = 0.002          # 20 bp enkelriktat, kanonisk kostnad
PPY = 13.0            # 4-veckorspaneler per år
RF = 0.0224           # riskfritt, periodens snitt
FLOOR = 0.01

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def cap_for(n_target: int) -> float:
    """Taket skalas mot portföljstorleken: 1,5x likavikt, aldrig under 6 %.

    Vid N=30 ger detta exakt kanonikens 6 %, vilket är vad som gör legacy-
    och waterfill-armarna jämförbara med de frysta talen.
    """
    return max(0.06, 1.5 / n_target)


def w_legacy(w_raw, target_sum, cap):
    """Kanonisk viktning: clip en gång, renormalisera efteråt. Taket kan brytas."""
    w = np.clip(w_raw, FLOOR, cap)
    s = float(np.sum(w))
    if s <= 0:
        return w
    return w / s * target_sum


def w_waterfill(w_raw, target_sum, cap, iters=200):
    """Korrekt tak/golv: omfördela överskott bland icke-bindande vikter tills
    summan stämmer OCH inget tak eller golv är brutet."""
    w = np.array(w_raw, dtype=float)
    if w.size == 0:
        return w
    s0 = float(np.sum(w))
    if s0 <= 0:
        return w
    w = w / s0 * target_sum
    for _ in range(iters):
        w = np.clip(w, FLOOR, cap)
        s = float(np.sum(w))
        diff = target_sum - s
        if abs(diff) < 1e-13:
            break
        free = (w > FLOOR + 1e-15) & (w < cap - 1e-15)
        if not free.any():
            break
        fs = float(np.sum(w[free]))
        if fs <= 0:
            w[free] += diff / float(free.sum())
        else:
            w[free] += diff * w[free] / fs
    return np.clip(w, FLOOR, cap)


def stats(x):
    x = np.asarray(x, dtype=float)
    wealth = np.cumprod(1.0 + x)
    dd = wealth / np.maximum.accumulate(wealth) - 1.0
    cagr = float(wealth[-1] ** (PPY / len(x)) - 1.0)
    vol = float(x.std(ddof=1) * math.sqrt(PPY))
    return cagr, vol, float(dd.min()), (cagr - RF) / vol if vol > 0 else 0.0


def main():
    print("Laddar kanonisk data...")
    core_df, prices, terminal = m.load_data()
    returns_map, all_dates = m.execution_engine(core_df, prices, terminal)
    vol_map, price_series = m.compute_vols(prices, window=60)
    rankings = m.derive_h0_scores(core_df, prices)
    eval_dates = sorted(rankings.keys())
    anchor = all_dates.index(m.PHASE_ANCHOR_H0) % 2
    confirm_map = m.fetch_fundamental_confirmations(rankings, prices)
    print(f"  {len(eval_dates)} paneler, {eval_dates[0]} — {eval_dates[-1]}")

    def sim(n_target, weighting):
        """Stack D-konstruktion: H0 topp-N, SMA200 skip, invvol^1.5, FR 0.75x.

        weighting: 'legacy' (kanoniskt clip+renorm) eller 'waterfill' (lagat).
        Returnerar nettoserie, takbrottsdiagnostik och bidrag per ticker.
        """
        cap = cap_for(n_target)
        wfun = w_legacy if weighting == "legacy" else w_waterfill
        prev, nets = [], []
        contrib = defaultdict(float)
        breaches, n_weights, max_w, excesses = 0, 0, 0.0, []
        panels_with_breach = 0

        for dt in eval_dates:
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            if sched or not prev:
                sel0 = [r["kod"] for r in raw[:n_target]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < n_target:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: n_target - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)

            sel = []
            for k in sel0:
                ok = True
                if k in price_series:
                    ds, adj = price_series[k]
                    i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
                    if i is not None and i >= 200 and adj[i] < float(np.mean(adj[i - 200:i])):
                        ok = False
                if ok:
                    sel.append(k)

            n = len(sel)
            if n == 0:
                nets.append(0.0)
                prev = sel0
                continue

            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            target_sum = n / n_target
            w_raw = inv / np.sum(inv) * target_sum
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = wfun(w_raw * conf, target_sum, cap)

            over = w > cap + 1e-9
            n_weights += n
            breaches += int(over.sum())
            if over.any():
                panels_with_breach += 1
                excesses.extend((w[over] - cap).tolist())
            max_w = max(max_w, float(w.max()))

            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            for k, wi, ri in zip(sel, w, rets):
                contrib[k] += float(wi * ri)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0

        diag = {
            "cap": cap,
            "vikter_totalt": n_weights,
            "takbrott": breaches,
            "andel_takbrott": breaches / n_weights if n_weights else 0.0,
            "paneler_med_takbrott": panels_with_breach,
            "andel_paneler_med_takbrott": panels_with_breach / len(eval_dates),
            "max_vikt": max_w,
            "max_overskridande_pp": (max_w - cap) if max_w > cap else 0.0,
            "median_overskridande": float(np.median(excesses)) if excesses else 0.0,
        }
        return np.array(nets), diag, dict(contrib)

    def utan_topp3(nets, contrib, n_target, weighting):
        """Räkna om serien med de tre största bidragsgivarnas avkastning nollad.

        Vikterna behålls (positionen finns kvar men ger 0 %), vilket isolerar
        avkastningsberoendet från viktomfördelning.
        """
        top3 = [k for k, _ in sorted(contrib.items(), key=lambda kv: -kv[1])[:3]]
        cap = cap_for(n_target)
        wfun = w_legacy if weighting == "legacy" else w_waterfill
        prev, out = [], []
        for dt in eval_dates:
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            if sched or not prev:
                sel0 = [r["kod"] for r in raw[:n_target]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < n_target:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: n_target - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)
            sel = []
            for k in sel0:
                ok = True
                if k in price_series:
                    ds, adj = price_series[k]
                    i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
                    if i is not None and i >= 200 and adj[i] < float(np.mean(adj[i - 200:i])):
                        ok = False
                if ok:
                    sel.append(k)
            n = len(sel)
            if n == 0:
                out.append(0.0)
                prev = sel0
                continue
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            target_sum = n / n_target
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = wfun(inv / np.sum(inv) * target_sum * conf, target_sum, cap)
            rets = np.array([0.0 if k in top3 else returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            out.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(out), top3

    print("\n" + "=" * 92)
    print("1. TAKBROTT I DEN KANONISKA VIKTNINGEN (Stack D-konstruktion)")
    print("=" * 92)
    print(f"  {'N':>3s} {'tak':>7s} {'andel vikter över':>18s} {'paneler med brott':>18s} {'max vikt':>10s} {'median över':>12s}")

    results = {"legacy": {}, "waterfill": {}}
    series_store = {"legacy": {}, "waterfill": {}}
    diags = {}
    for n_t in (10, 15, 20, 25, 30):
        nets, diag, contrib = sim(n_t, "legacy")
        diags[n_t] = diag
        series_store["legacy"][n_t] = nets
        c, v, d, sh = stats(nets)
        nets3, top3 = utan_topp3(nets, contrib, n_t, "legacy")
        c3, _, _, _ = stats(nets3)
        results["legacy"][n_t] = {
            "cagr": c, "vol": v, "maxdd": d, "sharpe": sh,
            "cagr_utan_topp3": c3, "andel_forlorad": (c - c3) / c if c > 0 else None,
            "topp3": top3, "takdiagnostik": diag,
        }
        print(f"  {n_t:3d} {diag['cap']:7.1%} {diag['andel_takbrott']:18.1%} "
              f"{diag['andel_paneler_med_takbrott']:18.1%} {diag['max_vikt']:10.2%} "
              f"{diag['median_overskridande']:12.2%}")

    print("\n" + "=" * 92)
    print("2. N-SVEP: KANONISK VIKTNING MOT LAGAD (water-filling)")
    print("=" * 92)
    print(f"  {'N':>3s} | {'CAGR':>8s} {'vol':>8s} {'MaxDD':>8s} {'Sharpe':>7s} {'utan T3':>8s} {'tappat':>7s} "
          f"| {'CAGR':>8s} {'vol':>8s} {'MaxDD':>8s} {'Sharpe':>7s} {'utan T3':>8s} {'tappat':>7s} | {'ΔCAGR':>7s}")

    for n_t in (10, 15, 20, 25, 30):
        nets, diag, contrib = sim(n_t, "waterfill")
        series_store["waterfill"][n_t] = nets
        c, v, d, sh = stats(nets)
        nets3, top3 = utan_topp3(nets, contrib, n_t, "waterfill")
        c3, _, _, _ = stats(nets3)
        results["waterfill"][n_t] = {
            "cagr": c, "vol": v, "maxdd": d, "sharpe": sh,
            "cagr_utan_topp3": c3, "andel_forlorad": (c - c3) / c if c > 0 else None,
            "topp3": top3, "takdiagnostik": diag,
        }
        L = results["legacy"][n_t]
        W = results["waterfill"][n_t]
        print(f"  {n_t:3d} | {L['cagr']:8.2%} {L['vol']:8.2%} {L['maxdd']:8.2%} {L['sharpe']:7.2f} "
              f"{L['cagr_utan_topp3']:8.2%} {L['andel_forlorad']:7.1%} "
              f"| {W['cagr']:8.2%} {W['vol']:8.2%} {W['maxdd']:8.2%} {W['sharpe']:7.2f} "
              f"{W['cagr_utan_topp3']:8.2%} {W['andel_forlorad']:7.1%} "
              f"| {W['cagr'] - L['cagr']:+7.2%}")

    print("\n  Vänster block = kanonisk viktning (taket bryts). Höger = lagad.")
    print(f"  Stack D-baslinje N=30: kanoniskt {results['legacy'][30]['cagr']:.2%}, "
          f"lagat {results['waterfill'][30]['cagr']:.2%}")

    # ---- 3. Block-bootstrap KI och blockstabilitet på den LAGADE viktningen ----
    print("\n" + "=" * 92)
    print("3. KONFIDENSINTERVALL OCH TIDSSTABILITET (lagad viktning, N mot N=30)")
    print("=" * 92)

    rng = np.random.default_rng(20260814)
    BLOCK, DRAWS = 13, 2000          # 13 paneler = 52 veckor
    series = {n_t: series_store["waterfill"][n_t] for n_t in (10, 15, 20, 25, 30)}
    base = series[30]
    n_pan = len(base)

    def boot_indices():
        idx = []
        while len(idx) < n_pan:
            start = int(rng.integers(0, n_pan))
            idx.extend([(start + j) % n_pan for j in range(BLOCK)])
        return np.array(idx[:n_pan])

    draws = [boot_indices() for _ in range(DRAWS)]

    def cagr_of(x):
        wealth = np.cumprod(1.0 + x)
        return float(wealth[-1] ** (PPY / len(x)) - 1.0)

    print(f"  {'N':>3s} {'CAGR':>8s} {'KI 95 % (block-bootstrap)':>28s} {'ΔCAGR mot 30':>13s} "
          f"{'KI för Δ':>22s} {'t parvis':>9s} {'block1':>8s} {'block2':>8s}")
    ki = {}
    half = n_pan // 2
    for n_t in (10, 15, 20, 25, 30):
        x = series[n_t]
        cs = np.array([cagr_of(x[i]) for i in draws])
        lo, hi = np.percentile(cs, [2.5, 97.5])
        if n_t == 30:
            print(f"  {n_t:3d} {cagr_of(x):8.2%} {f'[{lo:.2%}, {hi:.2%}]':>28s} {'—':>13s} {'—':>22s} "
                  f"{'—':>9s} {'—':>8s} {'—':>8s}")
            ki[n_t] = {"cagr": cagr_of(x), "ki_lo": float(lo), "ki_hi": float(hi)}
            continue
        d = x - base
        ds = np.array([cagr_of(x[i]) - cagr_of(base[i]) for i in draws])
        dlo, dhi = np.percentile(ds, [2.5, 97.5])
        t = float(d.mean() / d.std(ddof=1) * math.sqrt(len(d))) if d.std(ddof=1) > 0 else 0.0
        b1 = cagr_of(x[:half]) - cagr_of(base[:half])
        b2 = cagr_of(x[half:]) - cagr_of(base[half:])
        print(f"  {n_t:3d} {cagr_of(x):8.2%} {f'[{lo:.2%}, {hi:.2%}]':>28s} {cagr_of(x)-cagr_of(base):+13.2%} "
              f"{f'[{dlo:+.2%}, {dhi:+.2%}]':>22s} {t:+9.2f} {b1:+8.2%} {b2:+8.2%}")
        ki[n_t] = {
            "cagr": cagr_of(x), "ki_lo": float(lo), "ki_hi": float(hi),
            "delta_vs_30": cagr_of(x) - cagr_of(base),
            "delta_ki_lo": float(dlo), "delta_ki_hi": float(dhi),
            "t_parvis": t, "block1_delta": float(b1), "block2_delta": float(b2),
        }
    print(f"\n  {DRAWS} dragningar, {BLOCK}-panelsblock (52 veckor). KI som innehåller noll = ej skiljbart från N=30.")

    OUT.write_text(json.dumps({
        "version": "TAKFEL_DIAGNOSTIK_OCH_N_SVEP_V1",
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, ingen challenger skapad",
        "n_paneler": len(eval_dates),
        "period": f"{eval_dates[0]} — {eval_dates[-1]}",
        "konstruktion": "H0 topp-N, SMA200 skip, invvol^1.5 (ERC), FR-overlay 0.75x, ombalansering var 8:e vecka, 20 bp enkelriktat",
        "takregel": "cap = max(0.06, 1.5/N); vid N=30 identisk med kanonikens 6 %",
        "takfel_beskrivning": "clip(w,0.01,cap) följt av w/sum(w)*target_sum utan iteration skjuter vikter tillbaka över cap",
        "kanonisk_kodplats": [
            "tools/research_ag_reconciliation_canonical.py:240-241",
            "tools/research_all_6_models_head_to_head.py:214-215,220-221,226-227,231-232",
            "tools/run_stack_k789.py:76,84",
            "tools/beslutsjournal.py:71,73",
            "tools/beteendeaudit.py:73,75",
        ],
        "topp3_metod": "de tre största bidragsgivarnas avkastning nollas, vikterna behålls",
        "bootstrap": {"block_paneler": BLOCK, "dragningar": DRAWS, "seed": 20260814,
                      "arm": "waterfill (lagad viktning)", "per_N": {str(k): v for k, v in ki.items()}},
        "nettoserier": {arm: {str(n): [float(x) for x in s] for n, s in d.items()}
                        for arm, d in series_store.items()},
        "results": {str(k): v for k, v in results.items()},
    }, ensure_ascii=False, indent=2))
    print(f"\n  → {OUT.name}")


if __name__ == "__main__":
    main()
