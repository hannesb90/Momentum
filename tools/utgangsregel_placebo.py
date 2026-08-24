"""PLACEBOBAND FÖR UTGÅNGSREGLER

Frågan: när en utgångsregel ger +1,93 pp och en annan −0,97 pp, är det regeln
som skiljer dem åt eller är det bara vilka namn som råkade åka ut?

Nollhypotesen mäts direkt. För varje beslutspanel kastar placebot ut LIKA MÅNGA
innehav som den riktiga regeln gjorde, men slumpmässigt valda bland innehaven,
med samma karens och samma påfyllnad. Allt utom VALET av namn är identiskt:
samma antal transaktioner, samma omsättning, samma kostnader, samma N.

Om den riktiga regelns utfall ligger inuti placebofördelningen är regeln
oskiljaktig från att kasta tärning — och då är hela svepet över utgångsrank
brus, inte en kurva att optimera på.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/utgangsregel_placebo.py
"""
from __future__ import annotations
import importlib.util, json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/utgangsregel_placebo_results.json"
COST, PPY, N_SEEDS = 0.002, 13.0, 300

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
        if key in sma_cache:
            return sma_cache[key]
        v = True
        if k in price_series:
            ds, adj = price_series[k]
            i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
            if i is not None and i >= 200:
                v = adj[i] >= float(np.mean(adj[i - 200:i]))
        sma_cache[key] = v
        return v

    def sim(n_target, T, karens, rng=None, kvot_per_panel=None):
        """rng=None: riktiga regeln (stämpel = nått rank<=5, utgång vid rank>T).
        rng satt: placebo — kastar ut lika många slumpvalda innehav per panel."""
        cap = tk.cap_for(n_target)
        prev, nets = [], []
        stamplade = set()
        sparrad_till, beslut_nr = {}, 0
        utkast_per_panel = []

        for pi, dt in enumerate(eval_dates):
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            topN = [r["kod"] for r in raw[:n_target]]

            if not prev:
                sel0 = list(topN)
            elif sched:
                beslut_nr += 1
                kandidater = [k for k in prev if k in elig and rank_map[(k, dt)] <= n_target]
                if rng is None:
                    utkast = [k for k in kandidater if k in stamplade and rank_map[(k, dt)] > T]
                    utkast_per_panel.append(len(utkast))
                else:
                    antal = min(kvot_per_panel[beslut_nr - 1], len(kandidater))
                    utkast = list(rng.choice(kandidater, size=antal, replace=False)) if antal else []
                behall = [k for k in kandidater if k not in utkast]
                for k in utkast:
                    sparrad_till[k] = beslut_nr + karens
                sel0 = sorted(behall, key=lambda k: rank_map[(k, dt)])
                for r in raw:
                    if len(sel0) >= n_target:
                        break
                    k = r["kod"]
                    if k in sel0 or sparrad_till.get(k, -1) > beslut_nr:
                        continue
                    sel0.append(k)
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < n_target:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: n_target - len(sel0)]

            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)
            stamplade &= set(sel0)
            for k in sel0:
                if rank_map.get((k, dt), 999) <= 5:
                    stamplade.add(k)

            sel = [k for k in sel0 if sma_ok(k, dt)]
            if not sel:
                nets.append(0.0); prev = sel0; continue
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            target_sum = len(sel) / n_target
            w_raw = inv / np.sum(inv) * target_sum
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = tk.w_waterfill(w_raw * conf, target_sum, cap)
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(nets), utkast_per_panel

    out = {
        "version": "UTGANGSREGEL_PLACEBO_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "fraga": "spelar det roll VILKA innehav som kastas ut, eller bara hur många?",
        "placebo": "lika många utkast per beslutspanel, slumpvalda bland innehaven, samma karens",
        "n_seeds": N_SEEDS, "n_paneler": len(eval_dates),
        "fall": {},
    }

    bas, _ = sim(20, 20, 1)
    bas_cagr = tk.stats(bas)[0]
    out["baslinje_N20_cagr"] = round(bas_cagr, 4)
    print(f"baslinje N=20: {bas_cagr:.2%}\n")

    for T, karens, etikett in [(10, 3, "N20_T10_k3"), (15, 1, "N20_T15_k1"), (5, 3, "N20_T5_k3")]:
        riktig, kvot = sim(20, T, karens)
        r_cagr = tk.stats(riktig)[0]
        placebo = []
        for s in range(N_SEEDS):
            rng = np.random.default_rng(90000 + s)
            p, _ = sim(20, T, karens, rng=rng, kvot_per_panel=kvot)
            placebo.append(tk.stats(p)[0])
        placebo = np.array(placebo)
        d_riktig = r_cagr - bas_cagr
        d_placebo = placebo - bas_cagr
        pct = float((d_placebo >= d_riktig).mean())
        out["fall"][etikett] = {
            "utkast_totalt": int(sum(kvot)),
            "riktig_cagr": round(r_cagr, 4),
            "riktig_delta": round(d_riktig, 4),
            "placebo_median_delta": round(float(np.median(d_placebo)), 4),
            "placebo_5e_percentil": round(float(np.percentile(d_placebo, 5)), 4),
            "placebo_95e_percentil": round(float(np.percentile(d_placebo, 95)), 4),
            "placebo_sd": round(float(d_placebo.std(ddof=1)), 4),
            "placebo_min": round(float(d_placebo.min()), 4),
            "placebo_max": round(float(d_placebo.max()), 4),
            "andel_placebon_minst_lika_bra": round(pct, 4),
        }
        d = out["fall"][etikett]
        print(f"{etikett}: riktig Δ {d_riktig:+.2%}  |  placebo median {d['placebo_median_delta']:+.2%}, "
              f"5-95 % [{d['placebo_5e_percentil']:+.2%}, {d['placebo_95e_percentil']:+.2%}], "
              f"sd {d['placebo_sd']:.2%}  →  {pct:.1%} av placebona minst lika bra")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
