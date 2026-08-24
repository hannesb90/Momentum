"""LÅG VÅRA SÄMSTA INNEHAV OCKSÅ I TOPP-5?

Spegeln till mätningen 2026-08-15: samtliga femton största bidragsgivare hade
någon gång stått på rankplats 1-5, men längdmatchad basrat var 72 % — nästan
allt förklarades av innehavstiden.

Rätt kontroll är den andra svansen. Om de SÄMSTA innehaven har varit topp-5 i
samma utsträckning bär stämpeln ingen information alls. Om de varit det klart
mer sällan finns något kvar att titta på.

Rapporterar därför sämsta 15, bästa 15 och längdmatchade basrater för båda,
vid N=30 (samma bas som förra mätningen) och N=20.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/topp5_samsta_innehav.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/topp5_samsta_innehav_results.json"
COST = 0.002

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

    def sma_ok(k, dt):
        if k not in price_series:
            return True
        ds, adj = price_series[k]
        i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
        if i is None or i < 200:
            return True
        return adj[i] >= float(np.mean(adj[i - 200:i]))

    def bygg(n_target):
        """Returnerar hist (per innehav) och obs (per innehavspanel, med stämpelstatus).

        Stämpeln sätts när namnet nått rank<=5 TIDIGARE under samma innehav, så
        varje observation är framåtblickande: 'vad hände efter att den varit topp-5'.
        """
        cap = tk.cap_for(n_target)
        prev = []
        hist = defaultdict(list)
        obs = []
        stamplade = set()
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
            sel = [k for k in sel0 if sma_ok(k, dt)]
            prev = sel0
            if not sel:
                continue
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            target_sum = len(sel) / n_target
            w_raw = inv / np.sum(inv) * target_sum
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = tk.w_waterfill(w_raw * conf, target_sum, cap)
            for k, wi in zip(sel, w):
                r = rank_map.get((k, dt))
                ret = float(returns_map.get((k, dt), 0.0))
                hist[k].append((r, float(wi), ret))
                obs.append({"kod": k, "rank": r, "ret": ret, "stamplad": k in stamplade,
                            "panel_i_innehav": len(hist[k])})
            stamplade &= set(sel0)
            for k in sel0:
                if rank_map.get((k, dt), 999) <= 5:
                    stamplade.add(k)
        return hist, obs

    out = {
        "version": "TOPP5_SAMSTA_INNEHAV_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "viktning": "waterfill (lagad)", "n_paneler": len(eval_dates),
        "period": f"{eval_dates[0]} — {eval_dates[-1]}",
        "per_N": {},
    }

    for n_target in (30, 20):
        hist, obs = bygg(n_target)
        contrib = {k: sum(w * r for _, w, r in v) for k, v in hist.items()}
        langd = {k: len(v) for k, v in hist.items()}

        def nagonsin5(k):
            return any(r is not None and r <= 5 for r, _, _ in hist[k])

        def rad(k):
            rs = [r for r, _, _ in hist[k] if r is not None]
            t5 = sum(1 for r in rs if r <= 5)
            return {"kod": k, "bidrag": round(contrib[k], 4), "paneler": langd[k],
                    "basta_rank": min(rs) if rs else None,
                    "medianrank": int(np.median(rs)) if rs else None,
                    "rank_vid_intrade": rs[0] if rs else None,
                    "paneler_i_topp5": t5,
                    "andel_tid_i_topp5": round(t5 / len(rs), 3) if rs else None}

        ordnade = sorted(contrib.items(), key=lambda kv: kv[1])
        samsta = [rad(k) for k, _ in ordnade[:15]]
        basta = [rad(k) for k, _ in ordnade[-15:][::-1]]

        def matchad_basrat(rows):
            v = []
            for r in rows:
                peers = [p for p in hist if p != r["kod"] and abs(langd[p] - r["paneler"]) <= 2]
                if peers:
                    v.append(sum(nagonsin5(p) for p in peers) / len(peers))
            return round(float(np.mean(v)), 3) if v else None

        def andel5(rows):
            return round(sum(1 for r in rows if r["basta_rank"] and r["basta_rank"] <= 5) / len(rows), 3)

        # tid i topp-5 som andel av innehavstiden, aggregerat per svans
        def tidsandel(rows):
            p5 = sum(r["paneler_i_topp5"] for r in rows)
            tot = sum(r["paneler"] for r in rows)
            return round(p5 / tot, 3)

        alla = [rad(k) for k in hist]
        out["per_N"][str(n_target)] = {
            "unika_innehav": len(hist),
            "samsta_15": samsta, "basta_15": basta,
            "andel_samsta15_nagonsin_topp5": andel5(samsta),
            "andel_basta15_nagonsin_topp5": andel5(basta),
            "andel_alla_nagonsin_topp5": andel5(alla),
            "langdmatchad_basrat_samsta15": matchad_basrat(samsta),
            "langdmatchad_basrat_basta15": matchad_basrat(basta),
            "tid_i_topp5_samsta15": tidsandel(samsta),
            "tid_i_topp5_basta15": tidsandel(basta),
            "tid_i_topp5_alla": tidsandel(alla),
            "medianlangd_samsta15": int(np.median([r["paneler"] for r in samsta])),
            "medianlangd_basta15": int(np.median([r["paneler"] for r in basta])),
            "medianintrade_samsta15": int(np.median([r["rank_vid_intrade"] for r in samsta])),
            "medianintrade_basta15": int(np.median([r["rank_vid_intrade"] for r in basta])),
            "summa_bidrag_samsta15": round(sum(r["bidrag"] for r in samsta), 4),
            "summa_bidrag_basta15": round(sum(r["bidrag"] for r in basta), 4),
        }

        # Stämpeltestet utan längdkonfundering: jämför panelobservationer där
        # namnet REDAN varit topp-5 mot dem där det inte varit det, matchat på
        # hur långt in i innehavet observationen ligger.
        stratifierat = {}
        for lo, hi, namn in [(1, 3, "panel 1-3"), (4, 8, "panel 4-8"), (9, 99, "panel 9+")]:
            a = [o["ret"] for o in obs if o["stamplad"] and lo <= o["panel_i_innehav"] <= hi]
            b = [o["ret"] for o in obs if not o["stamplad"] and lo <= o["panel_i_innehav"] <= hi]
            if len(a) < 5 or len(b) < 5:
                continue
            A, B = np.array(a), np.array(b)
            se = math.sqrt(A.var(ddof=1) / len(A) + B.var(ddof=1) / len(B))
            stratifierat[namn] = {
                "n_stamplade": len(A), "n_ostamplade": len(B),
                "medelavk_stamplad": round(float(A.mean()), 4),
                "medelavk_ostamplad": round(float(B.mean()), 4),
                "t_welch": round(float((A.mean() - B.mean()) / se), 3) if se > 0 else None,
            }
        allaA = np.array([o["ret"] for o in obs if o["stamplad"]])
        allaB = np.array([o["ret"] for o in obs if not o["stamplad"]])
        se = math.sqrt(allaA.var(ddof=1) / len(allaA) + allaB.var(ddof=1) / len(allaB))
        out["per_N"][str(n_target)]["stampeltest_per_panelobs"] = {
            "totalt": {"n_stamplade": len(allaA), "n_ostamplade": len(allaB),
                       "medelavk_stamplad": round(float(allaA.mean()), 4),
                       "medelavk_ostamplad": round(float(allaB.mean()), 4),
                       "t_welch": round(float((allaA.mean() - allaB.mean()) / se), 3)},
            "stratifierat_pa_innehavsfas": stratifierat,
        }

        d = out["per_N"][str(n_target)]
        print(f"\n=== N={n_target}, {len(hist)} unika innehav")
        print(f"  någonsin topp-5:  sämsta15 {d['andel_samsta15_nagonsin_topp5']:.0%}  "
              f"bästa15 {d['andel_basta15_nagonsin_topp5']:.0%}  alla {d['andel_alla_nagonsin_topp5']:.0%}")
        print(f"  längdmatchad basrat:  sämsta15 {d['langdmatchad_basrat_samsta15']:.0%}  "
              f"bästa15 {d['langdmatchad_basrat_basta15']:.0%}")
        print(f"  andel av tiden i topp-5:  sämsta15 {d['tid_i_topp5_samsta15']:.1%}  "
              f"bästa15 {d['tid_i_topp5_basta15']:.1%}  alla {d['tid_i_topp5_alla']:.1%}")
        print(f"  medianlängd {d['medianlangd_samsta15']} mot {d['medianlangd_basta15']} paneler, "
              f"medianrank vid inträde {d['medianintrade_samsta15']} mot {d['medianintrade_basta15']}")
        st = d["stampeltest_per_panelobs"]
        print(f"  STÄMPELTEST per panelobs: stämplade {st['totalt']['medelavk_stamplad']:+.2%} "
              f"(n={st['totalt']['n_stamplade']}) mot ostämplade {st['totalt']['medelavk_ostamplad']:+.2%} "
              f"(n={st['totalt']['n_ostamplade']}), t {st['totalt']['t_welch']}")
        for f, v in st["stratifierat_pa_innehavsfas"].items():
            print(f"    {f:<10} {v['medelavk_stamplad']:+.2%} (n={v['n_stamplade']:>4}) mot "
                  f"{v['medelavk_ostamplad']:+.2%} (n={v['n_ostamplade']:>4}), t {v['t_welch']}")
        print("  SÄMSTA 15:")
        for r in samsta:
            print(f"    {r['kod']:<10} bidrag {r['bidrag']:+.4f}  paneler {r['paneler']:>2}  "
                  f"bästa rank {str(r['basta_rank']):>3}  median {str(r['medianrank']):>3}  "
                  f"topp5-paneler {r['paneler_i_topp5']:>2}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
