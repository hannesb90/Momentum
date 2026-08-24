"""KONTROLLER TILL TOPP5-FRÅGAN

Rådatan visar att 100 % av de femton största bidragsgivarna någon gång stod i
topp-5. Två confounders måste bort innan det betyder något:

  1. LÄNGDEN. Ett innehav som hållits 30 paneler har trettio chanser att råka
     stå i topp-5. Jämför därför mot längdmatchade innehav, inte mot snittet.
  2. RIKTNINGEN. Rankpoängen ÄR prishistorik. En aktie som gått upp klättrar
     mekaniskt. Frågan är om bidraget skapades EFTER att den nått topp-5
     (då är rank en signal) eller SAMTIDIGT/FÖRE (då är den en kvittens).

Mäter därför bidrag per panel uppdelat på rankbandet VID PANELENS INGÅNG.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/topp5_kontroller.py
"""
from __future__ import annotations
import importlib.util, json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/topp5_kontroller_results.json"
COST, FLOOR, CAP, N_TARGET = 0.002, 0.01, 0.06, 30

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

    prev = []
    # per innehav: lista av (panelindex, rank_vid_ingang, vikt, avkastning)
    hist = defaultdict(list)
    for pi, dt in enumerate(eval_dates):
        sched = all_dates.index(dt) % 2 == anchor
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        if sched or not prev:
            sel0 = [r["kod"] for r in raw[:N_TARGET]]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N_TARGET:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N_TARGET - len(sel0)]
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
        prev = sel0
        if not sel:
            continue
        vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
        inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
        target_sum = len(sel) / N_TARGET
        w_raw = inv / np.sum(inv) * target_sum
        conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
        w = tk.w_waterfill(w_raw * conf, target_sum, CAP)
        for k, wi in zip(sel, w):
            hist[k].append((pi, rank_map.get((k, dt)), float(wi), float(returns_map.get((k, dt), 0.0))))

    contrib = {k: sum(wi * ri for _, _, wi, ri in v) for k, v in hist.items()}
    langd = {k: len(v) for k, v in hist.items()}
    basta15 = [k for k, _ in sorted(contrib.items(), key=lambda kv: -kv[1])[:15]]
    langsta15 = sorted(hist, key=lambda k: -langd[k])[:15]

    def nagonsin_topp5(k):
        return any(r is not None and r <= 5 for _, r, _, _ in hist[k])

    # 1. längdmatchad basrat
    band = {"1-3": (1, 3), "4-8": (4, 8), "9-15": (9, 15), "16-25": (16, 25), "26+": (26, 999)}
    per_band = {}
    for namn, (lo, hi) in band.items():
        ks = [k for k in hist if lo <= langd[k] <= hi]
        if not ks:
            continue
        per_band[namn] = {
            "n_innehav": len(ks),
            "andel_nagonsin_topp5": round(sum(nagonsin_topp5(k) for k in ks) / len(ks), 3),
            "andel_av_basta15_i_bandet": sum(1 for k in basta15 if lo <= langd[k] <= hi),
        }

    # längdmatchad jämförelse: för varje av bästa 15, alla innehav med samma längd ±2 paneler
    matchade = []
    for k in basta15:
        peers = [p for p in hist if p != k and abs(langd[p] - langd[k]) <= 2]
        if peers:
            matchade.append(sum(nagonsin_topp5(p) for p in peers) / len(peers))
    langdmatchad_basrat = round(float(np.mean(matchade)), 3) if matchade else None

    # 2. bidrag per panel efter rankband VID INGÅNGEN
    def bandnamn(r):
        if r is None: return "okand"
        if r <= 5: return "1-5"
        if r <= 10: return "6-10"
        if r <= 20: return "11-20"
        if r <= 30: return "21-30"
        return "31+"

    agg = defaultdict(lambda: {"paneler": 0, "bidrag": 0.0, "avk_summa": 0.0})
    agg_b15 = defaultdict(lambda: {"paneler": 0, "bidrag": 0.0, "avk_summa": 0.0})
    for k, v in hist.items():
        for _, r, wi, ri in v:
            b = bandnamn(r)
            agg[b]["paneler"] += 1; agg[b]["bidrag"] += wi * ri; agg[b]["avk_summa"] += ri
            if k in basta15:
                agg_b15[b]["paneler"] += 1; agg_b15[b]["bidrag"] += wi * ri; agg_b15[b]["avk_summa"] += ri

    def snygga(a):
        return {b: {"paneler": d["paneler"], "bidrag": round(d["bidrag"], 4),
                    "bidrag_per_panel_bp": round(1e4 * d["bidrag"] / d["paneler"], 1) if d["paneler"] else None,
                    "medelavkastning": round(d["avk_summa"] / d["paneler"], 4) if d["paneler"] else None}
                for b, d in sorted(a.items())}

    # 3. timing: kom topp-5 före eller efter bidraget?
    timing = []
    for k in basta15:
        v = hist[k]
        first5 = next((i for i, (_, r, _, _) in enumerate(v) if r is not None and r <= 5), None)
        cum, tot = 0.0, sum(wi * ri for _, _, wi, ri in v)
        halv = None
        for i, (_, _, wi, ri) in enumerate(v):
            cum += wi * ri
            if tot > 0 and cum >= 0.5 * tot and halv is None:
                halv = i
        fore = sum(wi * ri for i, (_, _, wi, ri) in enumerate(v) if first5 is not None and i < first5)
        efter = sum(wi * ri for i, (_, _, wi, ri) in enumerate(v) if first5 is not None and i >= first5)
        timing.append({
            "kod": k, "paneler": len(v), "bidrag": round(tot, 4),
            "rank_vid_intrade": v[0][1],
            "panel_index_forsta_topp5": first5,
            "panel_index_halva_bidraget": halv,
            "bidrag_fore_forsta_topp5": round(fore, 4),
            "bidrag_fran_forsta_topp5": round(efter, 4),
        })

    tot_fore = sum(t["bidrag_fore_forsta_topp5"] for t in timing)
    tot_efter = sum(t["bidrag_fran_forsta_topp5"] for t in timing)

    out = {
        "version": "TOPP5_KONTROLLER_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "n_paneler": len(eval_dates), "period": f"{eval_dates[0]} — {eval_dates[-1]}",
        "viktning": "waterfill (lagad)",
        "unika_innehav": len(hist),
        "basta15": basta15, "langsta15": langsta15,
        "andel_basta15_nagonsin_topp5": round(sum(nagonsin_topp5(k) for k in basta15) / 15, 3),
        "andel_langsta15_nagonsin_topp5": round(sum(nagonsin_topp5(k) for k in langsta15) / 15, 3),
        "andel_alla_nagonsin_topp5": round(sum(nagonsin_topp5(k) for k in hist) / len(hist), 3),
        "langdmatchad_basrat_for_basta15": langdmatchad_basrat,
        "per_langdband": per_band,
        "bidrag_per_rankband_vid_ingang_ALLA": snygga(agg),
        "bidrag_per_rankband_vid_ingang_BASTA15": snygga(agg_b15),
        "timing_basta15": timing,
        "bidrag_fore_forsta_topp5_summa": round(tot_fore, 4),
        "bidrag_fran_forsta_topp5_summa": round(tot_efter, 4),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"Skrivet: {OUT}\n")
    print(f"någonsin topp-5: bästa15 {out['andel_basta15_nagonsin_topp5']:.0%}, "
          f"längsta15 {out['andel_langsta15_nagonsin_topp5']:.0%}, alla {out['andel_alla_nagonsin_topp5']:.0%}, "
          f"längdmatchad basrat {langdmatchad_basrat:.0%}")
    print("\nper längdband:")
    for b, d in per_band.items():
        print(f"  {b:<6} n={d['n_innehav']:>3}  någonsin topp-5 {d['andel_nagonsin_topp5']:.0%}  "
              f"(av bästa15: {d['andel_av_basta15_i_bandet']})")
    print("\nbidrag per rankband VID INGÅNGEN (alla innehav):")
    for b, d in out["bidrag_per_rankband_vid_ingang_ALLA"].items():
        print(f"  {b:<6} paneler {d['paneler']:>4}  bidrag {d['bidrag']:+.4f}  "
              f"per panel {d['bidrag_per_panel_bp']:>6} bp  medelavk {d['medelavkastning']:+.4f}")
    print("\nsamma för bästa 15:")
    for b, d in out["bidrag_per_rankband_vid_ingang_BASTA15"].items():
        print(f"  {b:<6} paneler {d['paneler']:>4}  bidrag {d['bidrag']:+.4f}  "
              f"per panel {d['bidrag_per_panel_bp']:>6} bp  medelavk {d['medelavkastning']:+.4f}")
    print(f"\ntiming: bidrag FÖRE första topp-5 {tot_fore:+.4f}, FRÅN första topp-5 {tot_efter:+.4f}")
    for t in timing:
        print(f"  {t['kod']:<10} intrade rank {str(t['rank_vid_intrade']):>3}  "
              f"forsta topp-5 @panel {str(t['panel_index_forsta_topp5']):>3}  "
              f"halva bidraget @panel {str(t['panel_index_halva_bidraget']):>3}  "
              f"fore {t['bidrag_fore_forsta_topp5']:+.4f} / fran {t['bidrag_fran_forsta_topp5']:+.4f}")


if __name__ == "__main__":
    main()
