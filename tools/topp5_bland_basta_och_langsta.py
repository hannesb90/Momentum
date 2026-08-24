"""HAR VÅRA BÄSTA OCH LÄNGSTA INNEHAV VARIT TOPP-5?

Frågan: bland de innehav som bidragit mest och de som hållits längst — hur
många har någonsin stått på rankplats 1–5, och hur stor del av sin innehavstid
tillbringade de där?

Bakgrunden är att nivån inom topp-30 saknar framåtinformation (rank 26–30 slår
1–5, t = 0,21). Om vinnarna ändå visar sig ha bott i topp-5 vore det en
motsägelse värd att veta om; om de inte har det bekräftas att topp-5 inte är
platsen där avkastningen görs.

Konstruktion: Stack D vid N=30 (H0 topp-30, SMA200-skip, invvol^1.5, FR 0.75x,
ombalansering var 8:e vecka, 20 bp). Båda viktningarna körs — legacy (kanonisk,
buggig) och waterfill (lagad) — eftersom bidragen är viktberoende.

DIAGNOSTISKT. Ingen fryst fil ändras, ingen försegling bryts.

Kör: /opt/momentum/venv/bin/python tools/topp5_bland_basta_och_langsta.py
"""
from __future__ import annotations
import importlib.util, json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/topp5_bland_basta_och_langsta_results.json"
COST = 0.002
FLOOR = 0.01
CAP = 0.06
N_TARGET = 30

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

tspec = importlib.util.spec_from_file_location("takfel", V2 / "tools/takfel_diagnostik_och_n_svep.py")
tk = importlib.util.module_from_spec(tspec)
tspec.loader.exec_module(tk)


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

    # rank per (kod, panel) över HELA rankinglistan, inte bara topp-30
    rank_map = {}
    for dt in eval_dates:
        for i, r in enumerate(rankings[dt]):
            rank_map[(r["kod"], dt)] = i + 1

    def sim(weighting):
        wfun = tk.w_legacy if weighting == "legacy" else tk.w_waterfill
        prev, nets = [], []
        contrib = defaultdict(float)
        panels_held = defaultdict(int)
        w_sum = defaultdict(float)
        ranks_held = defaultdict(list)
        for dt in eval_dates:
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            if sched or not prev:
                sel0 = [r["kod"] for r in raw[:N_TARGET]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < N_TARGET:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N_TARGET - len(sel0)]
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
            target_sum = n / N_TARGET
            w_raw = inv / np.sum(inv) * target_sum
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = wfun(w_raw * conf, target_sum, CAP)

            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            for k, wi, ri in zip(sel, w, rets):
                contrib[k] += float(wi * ri)
                panels_held[k] += 1
                w_sum[k] += float(wi)
                ranks_held[k].append(rank_map.get((k, dt)))
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(nets), contrib, panels_held, w_sum, ranks_held

    out = {
        "version": "TOPP5_BLAND_BASTA_OCH_LANGSTA_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "n_paneler": len(eval_dates),
        "period": f"{eval_dates[0]} — {eval_dates[-1]}",
        "konstruktion": f"Stack D, N={N_TARGET}, SMA200 skip, invvol^1.5, FR 0.75x, ombalansering var 8:e vecka, 20 bp",
        "rank_definition": "plats i H0:s fullständiga poänglista den panelen (1 = högst poäng)",
        "armar": {},
    }

    for weighting in ("legacy", "waterfill"):
        nets, contrib, panels_held, w_sum, ranks_held = sim(weighting)
        cagr, vol, mdd, sharpe = tk.stats(nets)
        alla = sorted(contrib.keys())

        def rad(k):
            rs = [r for r in ranks_held[k] if r is not None]
            top5 = sum(1 for r in rs if r <= 5)
            top10 = sum(1 for r in rs if r <= 10)
            return {
                "kod": k,
                "bidrag": round(contrib[k], 4),
                "paneler": panels_held[k],
                "medelvikt": round(w_sum[k] / panels_held[k], 4),
                "basta_rank": min(rs) if rs else None,
                "medianrank": int(np.median(rs)) if rs else None,
                "rank_vid_intrade": rs[0] if rs else None,
                "paneler_i_topp5": top5,
                "andel_paneler_i_topp5": round(top5 / len(rs), 3) if rs else None,
                "paneler_i_topp10": top10,
            }

        basta = [rad(k) for k, _ in sorted(contrib.items(), key=lambda kv: -kv[1])[:15]]
        langsta = [rad(k) for k in sorted(alla, key=lambda k: -panels_held[k])[:15]]

        def andel_ngn_topp5(rows):
            return round(sum(1 for r in rows if r["basta_rank"] is not None and r["basta_rank"] <= 5) / len(rows), 3)

        alla_rader = [rad(k) for k in alla]
        # tid tillbringad i topp-5, i panel-innehav
        tot_paneler = sum(r["paneler"] for r in alla_rader)
        tot_topp5 = sum(r["paneler_i_topp5"] for r in alla_rader)
        # bidrag genererat medan innehavet stod i topp-5 vs inte
        out["armar"][weighting] = {
            "portfolj": {"cagr": round(cagr, 4), "vol": round(vol, 4), "maxdd": round(mdd, 4), "sharpe": round(sharpe, 4)},
            "unika_innehav": len(alla),
            "basta_15_bidragsgivare": basta,
            "langsta_15_innehaven": langsta,
            "andel_av_basta15_som_nagonsin_var_topp5": andel_ngn_topp5(basta),
            "andel_av_langsta15_som_nagonsin_var_topp5": andel_ngn_topp5(langsta),
            "andel_av_alla_innehav_som_nagonsin_var_topp5": andel_ngn_topp5(alla_rader),
            "andel_av_all_innehavstid_i_topp5": round(tot_topp5 / tot_paneler, 4),
            "topp10_bidrag_summa": round(sum(r["bidrag"] for r in basta[:10]), 4),
            "totalt_positivt_bidrag": round(sum(v for v in contrib.values() if v > 0), 4),
            "totalt_negativt_bidrag": round(sum(v for v in contrib.values() if v < 0), 4),
        }

    # bidrag uppdelat på rankband vid ingången till panelen (waterfill-armen)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"Skrivet: {OUT}")
    for arm, d in out["armar"].items():
        print(f"\n=== {arm} — CAGR {d['portfolj']['cagr']:.2%}, {d['unika_innehav']} unika innehav")
        print(f"  någonsin topp-5: bästa 15 {d['andel_av_basta15_som_nagonsin_var_topp5']:.0%}, "
              f"längsta 15 {d['andel_av_langsta15_som_nagonsin_var_topp5']:.0%}, "
              f"alla {d['andel_av_alla_innehav_som_nagonsin_var_topp5']:.0%}")
        print(f"  andel av all innehavstid i topp-5: {d['andel_av_all_innehavstid_i_topp5']:.1%}")
        print("  BÄSTA:")
        for r in d["basta_15_bidragsgivare"]:
            print(f"    {r['kod']:<10} bidrag {r['bidrag']:+.4f}  paneler {r['paneler']:>2}  "
                  f"bästa rank {r['basta_rank']:>3}  median {r['medianrank']:>3}  topp5 {r['paneler_i_topp5']:>2}")
        print("  LÄNGSTA:")
        for r in d["langsta_15_innehaven"]:
            print(f"    {r['kod']:<10} paneler {r['paneler']:>2}  bidrag {r['bidrag']:+.4f}  "
                  f"bästa rank {r['basta_rank']:>3}  median {r['medianrank']:>3}  topp5 {r['paneler_i_topp5']:>2}")


if __name__ == "__main__":
    main()
