"""RESERVERAD PLATS FÖR STIGANDE ÅTERVÄNDARE

Förslaget: vig k av portföljens platser åt namn som (a) tidigare varit topp-5
under ett innehav, (b) just nu ligger UTANFÖR portföljgränsen, och (c) har
stigande rank. Alltså köpa tillbaka ledaren på väg upp, före den tagit sig
innanför gränsen på egen hand.

Bakgrund: stämplade återinträden var den bästa inträdeskohorten i mätningen
2026-08-15 (+6,28 % på en panel mot +1,97 % för färska namn vid N=30, t mot
färska 2,46 på tre paneler). Frågan är om det håller när man går längre ut.

Platsen är inte gratis. Varje reserverad plats tränger ut namnet på rank N,
så testet mäter kandidaternas avkastning MOT de utträngda, inte mot noll.

Tre kontroller, för att isolera vad som eventuellt bär:
  K1  samma regel utan topp-5-kravet (vilket tidigare innehav som helst)
  K2  samma regel utan kravet på tidigare innehav (vilket namn som helst)
  K3  slumpmässigt valda namn utanför gränsen, lika många platser

FÖRBEHÅLL: detta är den femte regelfamiljen som prövas mot samma 66 paneler.
Ett positivt utfall här är hypotesgenererande och kräver förregistrering innan
det får betyda något. Placebobandet för regler av den här typen är ±2,4 pp.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/satellitplats_atervandare.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/satellitplats_atervandare_results.json"
COST, PPY = 0.002, 13.0
YTTRE_GRANS = 60          # kandidater måste ligga innanför denna rank
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
    print(f"{len(eval_dates)} paneler, {eval_dates[0]} — {eval_dates[-1]}")

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

    def sim(n_target, k_platser=0, variant="stamplad", rng=None, logga=False):
        """variant: 'stamplad' (regeln), 'tidigare' (K1), 'valfri' (K2), 'slump' (K3)."""
        cap = tk.cap_for(n_target)
        prev, nets = [], []
        stamplad_nu, var_stamplad, har_haft = set(), set(), set()
        logg = {"kandidater": [], "uttrangda": []}
        antal_anvanda = 0

        for pi, dt in enumerate(eval_dates):
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            fore = eval_dates[pi - 1] if pi > 0 else None

            def stigande(kod):
                if fore is None:
                    return False
                r0, r1 = rank_map.get((kod, fore)), rank_map.get((kod, dt))
                return r0 is not None and r1 is not None and r1 < r0

            if sched or not prev:
                bas_sel = [r["kod"] for r in raw[:n_target]]
                sel0 = list(bas_sel)
                if k_platser and pi > 0:
                    utanfor = [r["kod"] for r in raw[n_target:YTTRE_GRANS]]
                    if variant == "stamplad":
                        kand = [c for c in utanfor if c in var_stamplad and stigande(c)]
                    elif variant == "tidigare":
                        kand = [c for c in utanfor if c in har_haft and stigande(c)]
                    elif variant == "valfri":
                        kand = [c for c in utanfor if stigande(c)]
                    else:
                        kand = list(utanfor)
                        if rng is not None and kand:
                            rng.shuffle(kand)
                    kand = [c for c in kand if c not in sel0][:k_platser]
                    if kand:
                        # varje kandidat tränger ut det sämst rankade namnet
                        sel0 = sel0[: n_target - len(kand)] + kand
                        antal_anvanda += len(kand)
                        if logga:
                            for c in kand:
                                logg["kandidater"].append({"kod": c, "panel": dt, "rank": rank_map.get((c, dt)),
                                                           "avk_1p": fram(c, pi, 1), "avk_2p": fram(c, pi, 2),
                                                           "avk_3p": fram(c, pi, 3)})
                            for u in bas_sel[n_target - len(kand):]:
                                logg["uttrangda"].append({"kod": u, "panel": dt, "rank": rank_map.get((u, dt)),
                                                          "avk_1p": fram(u, pi, 1), "avk_2p": fram(u, pi, 2),
                                                          "avk_3p": fram(u, pi, 3)})
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < n_target:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: n_target - len(sel0)]

            for k in prev:
                if k not in sel0:
                    har_haft.add(k)
                    if k in stamplad_nu:
                        var_stamplad.add(k)
                    else:
                        var_stamplad.discard(k)
            stamplad_nu &= set(sel0)
            for k in sel0:
                if rank_map.get((k, dt), 999) <= 5:
                    stamplad_nu.add(k)

            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)
            sel = [k for k in sel0 if sma_ok(k, dt)]
            if not sel:
                nets.append(0.0); prev = sel0; continue
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            ts = len(sel) / n_target
            w_raw = inv / np.sum(inv) * ts
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = tk.w_waterfill(w_raw * conf, ts, cap)
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(nets), antal_anvanda, logg

    def welch(a, b):
        A, B = np.array(a), np.array(b)
        if len(A) < 3 or len(B) < 3:
            return None
        se = math.sqrt(A.var(ddof=1) / len(A) + B.var(ddof=1) / len(B))
        return round(float((A.mean() - B.mean()) / se), 3) if se > 0 else None

    def sam(v):
        if not v:
            return None
        a = np.array(v, dtype=float)
        return {"n": len(a), "medel": round(float(a.mean()), 4), "median": round(float(np.median(a)), 4),
                "t_mot_noll": round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 3)
                if len(a) > 1 and a.std(ddof=1) > 0 else None}

    n_target = 20
    bas, _, _ = sim(n_target)
    bas_cagr = tk.stats(bas)[0]
    out = {
        "version": "SATELLITPLATS_ATERVANDARE_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, ingen challenger",
        "regel": f"k platser vigs åt tidigare topp-5-namn utanför topp-{n_target} med stigande rank, "
                 f"inom rank {YTTRE_GRANS}",
        "forbehall_multipeltest": "femte regelfamiljen mot samma 66 paneler; placebobandet är ±2,4 pp",
        "baslinje_cagr": round(bas_cagr, 4), "n_paneler": len(eval_dates),
        "frekvens": {}, "portfolj": {}, "observationellt": {},
    }

    print(f"baslinje N={n_target}: {bas_cagr:.2%}\n")

    # STEG 1: frekvens och observationell jämförelse (k=2 för loggning)
    _, antal, logg = sim(n_target, k_platser=2, variant="stamplad", logga=True)
    out["frekvens"] = {"anvanda_platser_k2": antal,
                       "unika_kandidatnamn": len({c["kod"] for c in logg["kandidater"]}),
                       "beslutspaneler": sum(1 for dt in eval_dates if all_dates.index(dt) % 2 == anchor)}
    print(f"STEG 1: {antal} använda platser, {out['frekvens']['unika_kandidatnamn']} unika namn "
          f"över {out['frekvens']['beslutspaneler']} beslutspaneler")

    for h in ("avk_1p", "avk_2p", "avk_3p"):
        out["observationellt"][f"kandidater_{h}"] = sam([c[h] for c in logg["kandidater"]])
        out["observationellt"][f"uttrangda_{h}"] = sam([u[h] for u in logg["uttrangda"]])
        out["observationellt"][f"t_kandidat_mot_uttrangd_{h}"] = welch(
            [c[h] for c in logg["kandidater"]], [u[h] for u in logg["uttrangda"]])
    print("STEG 2 (kandidat mot utträngd):")
    for h in ("avk_1p", "avk_2p", "avk_3p"):
        kk, uu = out["observationellt"][f"kandidater_{h}"], out["observationellt"][f"uttrangda_{h}"]
        if kk and uu:
            print(f"  {h}: kandidat {kk['medel']:+.2%} (median {kk['median']:+.2%}, n={kk['n']}) mot "
                  f"utträngd {uu['medel']:+.2%} (median {uu['median']:+.2%}), "
                  f"t {out['observationellt'][f't_kandidat_mot_uttrangd_{h}']}")

    # STEG 3: portföljutfall för regeln och de tre kontrollerna
    print("\nSTEG 3 (portfölj):")
    for variant in ("stamplad", "tidigare", "valfri"):
        for k in (1, 2, 3):
            nets, antal, _ = sim(n_target, k_platser=k, variant=variant)
            c, v, dd, sh = tk.stats(nets)
            out["portfolj"][f"{variant}_k{k}"] = {
                "cagr": round(c, 4), "delta": round(c - bas_cagr, 4), "vol": round(v, 4),
                "maxdd": round(dd, 4), "sharpe": round(sh, 4), "anvanda_platser": antal}
            print(f"  {variant:<9} k={k}: CAGR {c:7.2%}  Δ {c - bas_cagr:+.2%}  Sharpe {sh:.3f}  "
                  f"platser {antal:>3}")

    # STEG 4: placebo — slumpvalda namn utanför gränsen, k=2
    placebo = []
    for s in range(N_SEEDS):
        rng = np.random.default_rng(50000 + s)
        p, _, _ = sim(n_target, k_platser=2, variant="slump", rng=rng)
        placebo.append(tk.stats(p)[0] - bas_cagr)
    placebo = np.array(placebo)
    riktig = out["portfolj"]["stamplad_k2"]["delta"]
    out["placebo_k2"] = {
        "riktig_delta": riktig,
        "median": round(float(np.median(placebo)), 4),
        "p5": round(float(np.percentile(placebo, 5)), 4),
        "p95": round(float(np.percentile(placebo, 95)), 4),
        "sd": round(float(placebo.std(ddof=1)), 4),
        "andel_minst_lika_bra": round(float((placebo >= riktig).mean()), 4),
    }
    p = out["placebo_k2"]
    print(f"\nSTEG 4 placebo (k=2, slumpnamn utanför gränsen, {N_SEEDS} seeds):")
    print(f"  riktig Δ {riktig:+.2%}  |  placebo median {p['median']:+.2%}, "
          f"5-95 % [{p['p5']:+.2%}, {p['p95']:+.2%}], sd {p['sd']:.2%}  →  "
          f"{p['andel_minst_lika_bra']:.1%} av placebona minst lika bra")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
