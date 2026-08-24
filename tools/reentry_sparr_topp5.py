"""ÅTERINTRÄDESSPÄRR FÖR TIDIGARE TOPP-5-NAMN

Förslaget: ett namn som varit topp-5 under ett tidigare innehav får inte köpas
tillbaka förrän X beslutsfönster passerat.

Testas i tre steg, i den ordningen, eftersom bara det första är brusfritt:

  STEG 1 (deterministiskt). Hur många återinträden finns över huvud taget, och
  hur många av dem gäller tidigare stämplade namn? Om händelsen är sällsynt kan
  regeln inte göra något oavsett vad den vore värd.

  STEG 2 (observationellt, hög n). Vad avkastar återinträdande stämplade namn
  jämfört med återinträdande ostämplade och med färska namn, 1/2/3 paneler
  framåt? Detta är den enda mätningen med rimlig kraft.

  STEG 3 (portföljnivå, låg kraft). CAGR för spärren vid X = 1, 2, 3, 6 fönster
  — och mot ett placebo som spärrar LIKA MÅNGA slumpvalda återinträden. Utan
  placebot är siffran oläsbar: bandet för den här typen av regel är ±2,4 pp.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/reentry_sparr_topp5.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/reentry_sparr_topp5_results.json"
COST, PPY = 0.002, 13.0
N_SEEDS = 300

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
    idx = {dt: i for i, dt in enumerate(eval_dates)}

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

    def fram(k, pi, horisont):
        """Summerad avkastning för k över horisont paneler från panelindex pi."""
        tot = 1.0
        for j in range(pi, min(pi + horisont, len(eval_dates))):
            tot *= 1.0 + returns_map.get((k, eval_dates[j]), 0.0)
        return tot - 1.0

    def sim(n_target, sparr_fonster=0, rng=None, kvot=None):
        """sparr_fonster=0: baslinjen. >0: tidigare stämplade namn spärras så många
        beslutsfönster efter utgång. rng satt: placebo, spärrar lika många
        slumpvalda återinträden i stället."""
        cap = tk.cap_for(n_target)
        prev, nets = [], []
        stamplad_nu = set()          # stämplad under pågående innehav
        var_stamplad = set()         # stämplad under SENASTE avslutade innehav
        har_haft = set()
        sparrad_till, beslut_nr = {}, 0
        entries, blockerade = [], []
        kvot_i = 0

        for pi, dt in enumerate(eval_dates):
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            topN = [r["kod"] for r in raw[:n_target]]

            if not prev:
                sel0 = list(topN)
            elif sched:
                beslut_nr += 1
                behall = [k for k in prev if k in elig and rank_map[(k, dt)] <= n_target]
                sel0 = sorted(behall, key=lambda k: rank_map[(k, dt)])
                # kandidater till inträde, i rankordning
                kand = [r["kod"] for r in raw if r["kod"] not in sel0]
                if rng is not None:
                    aterintraden = [k for k in kand[:max(0, n_target - len(sel0)) + 10] if k in har_haft]
                    antal = min(kvot[kvot_i] if kvot_i < len(kvot) else 0, len(aterintraden))
                    kvot_i += 1
                    slump = set(rng.choice(aterintraden, size=antal, replace=False)) if antal else set()
                for k in kand:
                    if len(sel0) >= n_target:
                        break
                    if rng is None and sparr_fonster and sparrad_till.get(k, -1) > beslut_nr:
                        blockerade.append({"kod": k, "panel": dt, "panel_index": pi,
                                           "avk_1p": fram(k, pi, 1), "avk_3p": fram(k, pi, 3)})
                        continue
                    if rng is not None and k in slump:
                        continue
                    sel0.append(k)
            else:
                sel0 = [k for k in prev if k in elig]
                for r in raw:
                    if len(sel0) >= n_target:
                        break
                    k = r["kod"]
                    if rng is None and sparr_fonster and sparrad_till.get(k, -1) > beslut_nr:
                        continue
                    if k not in sel0:
                        sel0.append(k)

            # logga inträden och utgångar
            for k in sel0:
                if k not in prev:
                    entries.append({"kod": k, "panel": dt, "panel_index": pi,
                                    "aterintrade": k in har_haft,
                                    "var_topp5_forra_gangen": k in var_stamplad,
                                    "rank": rank_map.get((k, dt)),
                                    "avk_1p": fram(k, pi, 1), "avk_2p": fram(k, pi, 2),
                                    "avk_3p": fram(k, pi, 3)})
            for k in prev:
                if k not in sel0:
                    har_haft.add(k)
                    if k in stamplad_nu:
                        var_stamplad.add(k)
                        if sparr_fonster:
                            sparrad_till[k] = beslut_nr + sparr_fonster
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
        return np.array(nets), entries, blockerade

    out = {
        "version": "REENTRY_SPARR_TOPP5_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "regel": "namn som varit topp-5 under föregående innehav spärras X beslutsfönster från återköp",
        "viktning": "waterfill (lagad)", "n_paneler": len(eval_dates),
        "per_N": {},
    }

    def welch(a, b):
        A, B = np.array(a), np.array(b)
        if len(A) < 3 or len(B) < 3:
            return None
        se = math.sqrt(A.var(ddof=1) / len(A) + B.var(ddof=1) / len(B))
        return round(float((A.mean() - B.mean()) / se), 3) if se > 0 else None

    for n_target in (20, 30):
        bas, entries, _ = sim(n_target)
        bas_cagr = tk.stats(bas)[0]

        farska = [e for e in entries if not e["aterintrade"]]
        ater = [e for e in entries if e["aterintrade"]]
        ater_st = [e for e in ater if e["var_topp5_forra_gangen"]]
        ater_ost = [e for e in ater if not e["var_topp5_forra_gangen"]]

        steg1 = {
            "intraden_totalt": len(entries),
            "farska_intraden": len(farska),
            "aterintraden": len(ater),
            "aterintraden_stamplade": len(ater_st),
            "aterintraden_ostamplade": len(ater_ost),
            "andel_intraden_som_ar_stamplat_aterintrade": round(len(ater_st) / len(entries), 4),
            "unika_stamplade_aterintraden": len({e["kod"] for e in ater_st}),
        }

        def grupp(g):
            if not g:
                return None
            return {"n": len(g),
                    "avk_1p": round(float(np.mean([e["avk_1p"] for e in g])), 4),
                    "avk_2p": round(float(np.mean([e["avk_2p"] for e in g])), 4),
                    "avk_3p": round(float(np.mean([e["avk_3p"] for e in g])), 4),
                    "medianrank": int(np.median([e["rank"] for e in g if e["rank"]]))}

        steg2 = {"farska": grupp(farska), "aterintrade_stamplade": grupp(ater_st),
                 "aterintrade_ostamplade": grupp(ater_ost)}
        for h in ("avk_1p", "avk_2p", "avk_3p"):
            steg2[f"t_stamplat_ater_mot_farska_{h}"] = welch([e[h] for e in ater_st], [e[h] for e in farska])
            steg2[f"t_stamplat_ater_mot_ostamplat_ater_{h}"] = welch([e[h] for e in ater_st],
                                                                     [e[h] for e in ater_ost])

        steg3 = {}
        for X in (1, 2, 3, 6):
            nets, _, blk = sim(n_target, sparr_fonster=X)
            c, v, dd, sh = tk.stats(nets)
            steg3[f"X{X}"] = {"cagr": round(c, 4), "delta": round(c - bas_cagr, 4), "vol": round(v, 4),
                              "maxdd": round(dd, 4), "sharpe": round(sh, 4),
                              "blockerade_intraden": len(blk),
                              "avk_1p_hos_blockerade": round(float(np.mean([b["avk_1p"] for b in blk])), 4) if blk else None}
        out["per_N"][str(n_target)] = {"baslinje_cagr": round(bas_cagr, 4),
                                       "steg1_frekvens": steg1, "steg2_avkastning": steg2,
                                       "steg3_portfolj": steg3}
        print(f"\n=== N={n_target}  baslinje {bas_cagr:.2%}")
        print(f"  STEG 1: {steg1['intraden_totalt']} inträden, varav {steg1['aterintraden']} återinträden, "
              f"varav {steg1['aterintraden_stamplade']} tidigare topp-5 "
              f"({steg1['andel_intraden_som_ar_stamplat_aterintrade']:.1%} av alla inträden, "
              f"{steg1['unika_stamplade_aterintraden']} unika namn)")
        print("  STEG 2 (avkastning efter inträde):")
        for namn, g in steg2.items():
            if isinstance(g, dict) and g:
                print(f"    {namn:<24} n={g['n']:>4}  1p {g['avk_1p']:+.2%}  2p {g['avk_2p']:+.2%}  "
                      f"3p {g['avk_3p']:+.2%}  medianrank {g['medianrank']}")
        print(f"    t stämplat återinträde mot färska: 1p {steg2['t_stamplat_ater_mot_farska_avk_1p']}, "
              f"3p {steg2['t_stamplat_ater_mot_farska_avk_3p']}")
        print("  STEG 3 (portfölj):")
        for X, d in steg3.items():
            print(f"    {X}: CAGR {d['cagr']:.2%}  Δ {d['delta']:+.2%}  Sharpe {d['sharpe']:.3f}  "
                  f"blockerade {d['blockerade_intraden']}")

    # placebo för den bäst utfallande X:en vid N=20
    n_target = 20
    steg3 = out["per_N"]["20"]["steg3_portfolj"]
    bastX = max(steg3, key=lambda k: steg3[k]["delta"])
    X = int(bastX[1:])
    bas, entries, _ = sim(n_target)
    bas_cagr = tk.stats(bas)[0]
    _, _, blk = sim(n_target, sparr_fonster=X)
    # kvot per beslutspanel: hur många återinträden regeln blockerade
    per_beslut = defaultdict(int)
    for b in blk:
        per_beslut[b["panel_index"]] += 1
    kvot = []
    bn = 0
    for pi, dt in enumerate(eval_dates):
        if all_dates.index(dt) % 2 == anchor and pi > 0:
            kvot.append(per_beslut.get(pi, 0)); bn += 1
    placebo = []
    for s in range(N_SEEDS):
        rng = np.random.default_rng(70000 + s)
        p, _, _ = sim(n_target, rng=rng, kvot=kvot)
        placebo.append(tk.stats(p)[0] - bas_cagr)
    placebo = np.array(placebo)
    riktig = steg3[bastX]["delta"]
    out["placebo_N20"] = {
        "testad_X": X, "riktig_delta": round(riktig, 4),
        "placebo_median": round(float(np.median(placebo)), 4),
        "placebo_5e": round(float(np.percentile(placebo, 5)), 4),
        "placebo_95e": round(float(np.percentile(placebo, 95)), 4),
        "placebo_sd": round(float(placebo.std(ddof=1)), 4),
        "andel_placebon_minst_lika_bra": round(float((placebo >= riktig).mean()), 4),
    }
    p = out["placebo_N20"]
    print(f"\nPLACEBO N=20, X={X}: riktig Δ {riktig:+.2%} mot placebo median {p['placebo_median']:+.2%}, "
          f"5-95 % [{p['placebo_5e']:+.2%}, {p['placebo_95e']:+.2%}] → "
          f"{p['andel_placebon_minst_lika_bra']:.1%} av placebona minst lika bra")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
