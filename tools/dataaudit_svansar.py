"""DATAAUDIT DEL 2 — SVANSAR, LUCKOR OCH VIKTNINGENS INDATA

Del 1 rensade två misstankar (medianpoäng-fallbacken landar på rank ~177 och
rör aldrig topp-60; exakta nollor är jämnt 2,3–2,6 % i alla rankband). Kvar
står fyra saker som kan förklara varför tester faller mot rimligheten:

  S1  Extremvärden. Panelavkastningen sträcker sig till +527 % och −90,6 %.
      Eftersom praktiskt taget varje medelvärde vi mätt är svansdrivet kan ett
      fåtal felaktiga kurser flytta hela slutsatser. Är de verkliga?

  S2  Prisluckor. NEOBO saknar 371 dagar, RIZZO-B 214. Om de namnen rankats
      och hållits under luckan är både momentum och avkastning fiktiva.

  S3  Nollor där de betyder mest. Efter-utgång-mätningen hade median exakt
      0,00 %. Hur stor andel av just det stickprovet är fallback-nollor?

  S4  Viktningens indata. vol_map faller tillbaka på 0,25 när volatilitet
      saknas, och confirm_map kräver 120 dagars historik. Hur ofta gäller det
      för namn vi faktiskt äger?

Kör: /opt/momentum/venv/bin/python tools/dataaudit_svansar.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone, date
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/dataaudit_svansar_results.json"

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tspec = importlib.util.spec_from_file_location("takfel", V2 / "tools/takfel_diagnostik_och_n_svep.py")
tk = importlib.util.module_from_spec(tspec); tspec.loader.exec_module(tk)


def main():
    core_df, prices, terminal = m.load_data()
    returns_map, all_dates = m.execution_engine(core_df, prices, terminal)
    vol_map, price_series = m.compute_vols(prices, window=60)
    rankings = m.derive_h0_scores(core_df, prices)
    confirm_map = m.fetch_fundamental_confirmations(rankings, prices)
    eval_dates = sorted(rankings.keys())
    anchor = all_dates.index(m.PHASE_ANCHOR_H0) % 2
    rank_map = {(r["kod"], dt): i + 1 for dt in eval_dates for i, r in enumerate(rankings[dt])}
    out = {"version": "DATAAUDIT_SVANSAR_V1",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

    # ---- S1: extremvärden ----
    par = [(k, dt, v) for (k, dt), v in returns_map.items() if v != 0.0]
    par.sort(key=lambda x: -x[2])
    def kontext(k, dt):
        r = rank_map.get((k, dt))
        ds, adj = price_series.get(k, (np.array([]), np.array([])))
        i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
        return {"rank": r, "pris_vid_panel": round(float(adj[i]), 3) if i is not None else None,
                "n_prispunkter": len(ds)}
    out["S1_extremvarden"] = {
        "topp10_positiva": [{"kod": k, "panel": dt, "avk": round(v, 3), **kontext(k, dt)} for k, dt, v in par[:10]],
        "topp10_negativa": [{"kod": k, "panel": dt, "avk": round(v, 3), **kontext(k, dt)} for k, dt, v in par[-10:]],
        "andel_over_plus_100pct": round(float(np.mean([1.0 if v > 1.0 else 0.0 for _, _, v in par])), 5),
        "andel_i_topp30_over_plus_100pct": round(float(np.mean(
            [1.0 if v > 1.0 else 0.0 for k, dt, v in par if (rank_map.get((k, dt)) or 999) <= 30])), 5),
    }
    print("S1 — extremvärden (panelavkastning):")
    print("  största positiva:")
    for r in out["S1_extremvarden"]["topp10_positiva"][:6]:
        print(f"    {r['kod']:<10} {r['panel']}  {r['avk']:+8.1%}  rank {str(r['rank']):>5}  "
              f"pris {r['pris_vid_panel']}")
    print("  största negativa:")
    for r in out["S1_extremvarden"]["topp10_negativa"][:6]:
        print(f"    {r['kod']:<10} {r['panel']}  {r['avk']:+8.1%}  rank {str(r['rank']):>5}  "
              f"pris {r['pris_vid_panel']}")

    # ---- S2: prisluckor mot rank och innehav ----
    def sma_ok(k, dt):
        if k not in price_series:
            return True
        ds, adj = price_series[k]
        i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
        if i is None or i < 200:
            return True
        return adj[i] >= float(np.mean(adj[i - 200:i]))

    misstankta = ["NEOBO", "RIZZO-B", "CARA"]
    S2 = {}
    for k in misstankta:
        rs = prices.get(k, [])
        ds = [r["d"] for r in rs]
        gap_start = None
        if len(ds) > 1:
            dd = [(date.fromisoformat(ds[i + 1]) - date.fromisoformat(ds[i])).days for i in range(len(ds) - 1)]
            gi = int(np.argmax(dd))
            gap_start = (ds[gi], ds[gi + 1], dd[gi])
        rk = [(dt, rank_map[(k, dt)]) for dt in eval_dates if (k, dt) in rank_map]
        basta = min((r for _, r in rk), default=None)
        i_topp30 = [dt for dt, r in rk if r <= 30]
        S2[k] = {"gap": gap_start, "basta_rank": basta, "paneler_i_topp30": len(i_topp30),
                 "exempel_paneler_i_topp30": i_topp30[:5],
                 "avk_under_gap": [round(returns_map.get((k, dt), 0.0), 4)
                                   for dt in eval_dates if gap_start and gap_start[0] <= dt <= gap_start[1]][:8]}
    out["S2_prisluckor"] = S2
    print("\nS2 — prisluckor:")
    for k, v in S2.items():
        print(f"  {k:<9} gap {v['gap']}  bästa rank {v['basta_rank']}  "
              f"paneler i topp-30: {v['paneler_i_topp30']}")

    # ---- S3: nollor i efter-utgång-stickprovet ----
    N = 20
    prev, spells, oppna = [], [], {}
    for pi, dt in enumerate(eval_dates):
        sched = all_dates.index(dt) % 2 == anchor
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        if sched or not prev:
            sel0 = [r["kod"] for r in raw[:N]]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        for k in prev:
            if k not in sel0:
                spells.append({"kod": k, "ut_pi": pi})
        for k in sel0:
            oppna[k] = True
        prev = sel0
    ut1 = [(s["kod"], eval_dates[s["ut_pi"]]) for s in spells if s["ut_pi"] < len(eval_dates)]
    z = sum(1 for p in ut1 if returns_map.get(p, 0.0) == 0.0)
    i_universum = sum(1 for k, dt in ut1 if (k, dt) in rank_map)
    out["S3_nollor_efter_utgang"] = {
        "n": len(ut1), "exakta_nollor": z, "andel": round(z / len(ut1), 4),
        "kvar_i_rankuniversum": i_universum,
        "andel_kvar_i_universum": round(i_universum / len(ut1), 4),
        "medel_med_nollor": round(float(np.mean([returns_map.get(p, 0.0) for p in ut1])), 4),
        "medel_utan_nollor": round(float(np.mean([returns_map[p] for p in ut1
                                                  if returns_map.get(p, 0.0) != 0.0])), 4),
    }
    s3 = out["S3_nollor_efter_utgang"]
    print(f"\nS3 — avkastning panelen efter utgång: n={s3['n']}, exakta nollor {s3['exakta_nollor']} "
          f"({s3['andel']:.1%}), kvar i rankuniversum {s3['andel_kvar_i_universum']:.1%}")
    print(f"   medel MED nollor {s3['medel_med_nollor']:+.2%}, UTAN nollor {s3['medel_utan_nollor']:+.2%}")

    # ---- S4: viktningens indata för ägda namn ----
    prev = []
    saknad_vol, tot_agda, ej_bekraftade, sma_saknas = 0, 0, 0, 0
    for pi, dt in enumerate(eval_dates):
        sched = all_dates.index(dt) % 2 == anchor
        raw = rankings[dt]
        elig = {r["kod"] for r in raw}
        if sched or not prev:
            sel0 = [r["kod"] for r in raw[:N]]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        for k in sel0:
            tot_agda += 1
            if (k, dt) not in vol_map:
                saknad_vol += 1
            if not confirm_map.get((k, dt), False):
                ej_bekraftade += 1
            ds, adj = price_series.get(k, (np.array([]), np.array([])))
            i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
            if i is None or i < 200:
                sma_saknas += 1
        prev = sel0
    out["S4_viktningens_indata"] = {
        "agda_panelobs": tot_agda,
        "saknad_volatilitet_faller_till_0.25": saknad_vol,
        "andel_saknad_vol": round(saknad_vol / tot_agda, 4),
        "ej_bekraftade_far_0.75x": ej_bekraftade,
        "andel_ej_bekraftade": round(ej_bekraftade / tot_agda, 4),
        "for_kort_historik_for_sma200_slapps_igenom": sma_saknas,
        "andel_sma_slapps_igenom": round(sma_saknas / tot_agda, 4),
    }
    s4 = out["S4_viktningens_indata"]
    print(f"\nS4 — indata för {tot_agda} ägda panelobservationer:")
    print(f"   saknad vol (faller till 0,25): {saknad_vol} ({s4['andel_saknad_vol']:.2%})")
    print(f"   ej bekräftade (0,75x vikt): {ej_bekraftade} ({s4['andel_ej_bekraftade']:.1%})")
    print(f"   för kort historik för SMA200, släpps igenom: {sma_saknas} "
          f"({s4['andel_sma_slapps_igenom']:.2%})")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
