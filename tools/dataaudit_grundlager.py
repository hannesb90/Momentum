"""DATAAUDIT AV GRUNDLAGRET

Två konkreta misstankar ur koden, plus rutinkontroller:

  M1  execution_engine sätter avkastningen till EXAKT 0.0 som fallback när
      prisserien saknar en punkt efter nästa panel och inget terminal-event
      matchar. Nollor späder ut varje medelvärde och krymper varje t-värde.

  M2  derive_h0_scores ger namn UTAN momentumdata medianpoängen, vilket lägger
      dem mitt i ranglistan — exakt i banden 15–30 som testats mest.

Rutinkontroller: panelavstånd, universumsstorlek över tid, prisgap,
dubbletter, terminal-events mot serier som tar slut, adj-vs-close.

Kör: /opt/momentum/venv/bin/python tools/dataaudit_grundlager.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict, Counter
from datetime import datetime, timezone, date
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/dataaudit_grundlager_results.json"

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def d(s):
    return date.fromisoformat(s)


def main():
    core_df, prices, terminal = m.load_data()
    returns_map, all_dates = m.execution_engine(core_df, prices, terminal)
    rankings = m.derive_h0_scores(core_df, prices)
    eval_dates = sorted(rankings.keys())
    rank_map = {(r["kod"], dt): i + 1 for dt in eval_dates for i, r in enumerate(rankings[dt])}

    out = {"version": "DATAAUDIT_GRUNDLAGER_V1",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

    # ---- 0. struktur ----
    gaps = [(d(all_dates[i + 1]) - d(all_dates[i])).days for i in range(len(all_dates) - 1)]
    egaps = [(d(eval_dates[i + 1]) - d(eval_dates[i])).days for i in range(len(eval_dates) - 1)]
    out["struktur"] = {
        "n_paneldatum_i_core": len(all_dates),
        "n_evalpaneler": len(eval_dates),
        "panelavstand_dagar": dict(Counter(gaps)),
        "evalavstand_dagar": dict(Counter(egaps)),
        "forsta": eval_dates[0], "sista": eval_dates[-1],
        "n_prisserier": len(prices),
        "n_terminal_events": len(terminal),
    }
    print("STRUKTUR")
    print(f"  paneler i core: {len(all_dates)}, evalpaneler: {len(eval_dates)}, "
          f"avstånd: {dict(Counter(egaps))}")
    print(f"  prisserier: {len(prices)}, terminal-events: {len(terminal)}")

    # ---- 1. universumsstorlek per panel ----
    storlek = {dt: len(rankings[dt]) for dt in eval_dates}
    v = list(storlek.values())
    out["universum"] = {"min": min(v), "max": max(v), "medel": round(float(np.mean(v)), 1),
                        "forsta_panelen": v[0], "sista_panelen": v[-1]}
    print(f"\nUNIVERSUM per panel: min {min(v)}, max {max(v)}, medel {np.mean(v):.0f} "
          f"(första {v[0]}, sista {v[-1]})")

    # ---- 2. M2: medianpoäng-fallback ----
    fallback_rank = []
    fallback_per_panel = []
    for dt in eval_dates:
        rows = rankings[dt]
        n_fb = 0
        for i, r in enumerate(rows):
            if r.get("mom_12m") is None or r.get("mom_18m") is None:
                n_fb += 1
                fallback_rank.append(i + 1)
        fallback_per_panel.append(n_fb)
    band_fb = Counter()
    for r in fallback_rank:
        if r <= 5: band_fb["1-5"] += 1
        elif r <= 10: band_fb["6-10"] += 1
        elif r <= 20: band_fb["11-20"] += 1
        elif r <= 30: band_fb["21-30"] += 1
        elif r <= 60: band_fb["31-60"] += 1
        else: band_fb["61+"] += 1
    tot_rank_obs = sum(len(rankings[dt]) for dt in eval_dates)
    out["M2_medianpoang_fallback"] = {
        "namn_utan_momentum_totalt": len(fallback_rank),
        "andel_av_alla_rankobs": round(len(fallback_rank) / tot_rank_obs, 4),
        "per_panel_medel": round(float(np.mean(fallback_per_panel)), 2),
        "per_panel_max": int(np.max(fallback_per_panel)),
        "rankfordelning": dict(band_fb),
        "medianrank_for_fallback": float(np.median(fallback_rank)) if fallback_rank else None,
    }
    print(f"\nM2 — namn utan momentumdata (får medianpoäng): {len(fallback_rank)} obs "
          f"({len(fallback_rank)/tot_rank_obs:.2%} av alla), {np.mean(fallback_per_panel):.1f} per panel, "
          f"max {np.max(fallback_per_panel)}")
    print(f"   landar på median rank {np.median(fallback_rank) if fallback_rank else '-'}, "
          f"fördelning {dict(band_fb)}")

    # ---- 3. M1: exakta nollor i avkastningen ----
    def nollandel(par):
        if not par:
            return None
        z = sum(1 for p in par if returns_map.get(p, 0.0) == 0.0)
        return {"n": len(par), "nollor": z, "andel": round(z / len(par), 4)}

    alla_par = [(k, dt) for k in prices for dt in eval_dates]
    band_par = defaultdict(list)
    for dt in eval_dates:
        for i, r in enumerate(rankings[dt]):
            rk = i + 1
            b = ("1-5" if rk <= 5 else "6-10" if rk <= 10 else "11-20" if rk <= 20
                 else "21-30" if rk <= 30 else "31-60" if rk <= 60 else "61+")
            band_par[b].append((r["kod"], dt))
    out["M1_exakta_nollor"] = {"alla_prisserier_x_paneler": nollandel(alla_par),
                               "per_rankband": {b: nollandel(p) for b, p in sorted(band_par.items())}}
    print(f"\nM1 — exakt 0,0 i avkastningen:")
    a = out["M1_exakta_nollor"]["alla_prisserier_x_paneler"]
    print(f"   hela matrisen: {a['nollor']}/{a['n']} = {a['andel']:.2%}")
    for b, p in out["M1_exakta_nollor"]["per_rankband"].items():
        print(f"   rank {b:<6} {p['nollor']:>5}/{p['n']:<6} = {p['andel']:.2%}")

    # ---- 4. prisseriernas täckning ----
    slut_tidigt, gapiga, korta = [], [], []
    sista_panel = eval_dates[-1]
    for k, rs in prices.items():
        ds = [r["d"] for r in rs]
        if not ds:
            korta.append(k); continue
        if ds[-1] < sista_panel:
            slut_tidigt.append((k, ds[-1], k in terminal))
        dd = [(d(ds[i + 1]) - d(ds[i])).days for i in range(len(ds) - 1)]
        if dd and max(dd) > 14:
            gapiga.append((k, max(dd)))
    out["prisserier"] = {
        "serier_som_slutar_fore_sista_panelen": len(slut_tidigt),
        "darav_utan_terminal_event": sum(1 for _, _, t in slut_tidigt if not t),
        "exempel_utan_terminal_event": [[k, dt] for k, dt, t in slut_tidigt if not t][:10],
        "serier_med_gap_over_14_dagar": len(gapiga),
        "storsta_gap": sorted(gapiga, key=lambda x: -x[1])[:5],
        "tomma_serier": korta,
    }
    print(f"\nPRISSERIER: {len(slut_tidigt)} slutar före sista panelen, "
          f"varav {sum(1 for _,_,t in slut_tidigt if not t)} UTAN terminal-event")
    print(f"   {len(gapiga)} serier med gap > 14 dagar; största: "
          f"{sorted(gapiga, key=lambda x: -x[1])[:3]}")

    # ---- 5. dubbletter och paneltäckning i core ----
    par = Counter((r.kod, r.panel_date) for r in core_df.itertuples())
    dubbletter = {f"{k[0]}|{k[1]}": c for k, c in par.items() if c > 1}
    kod_per_panel = defaultdict(set)
    for r in core_df.itertuples():
        kod_per_panel[r.panel_date].add(r.kod)
    nya, forsvunna = [], []
    dts = sorted(kod_per_panel)
    for i in range(1, len(dts)):
        f, n = kod_per_panel[dts[i - 1]], kod_per_panel[dts[i]]
        nya.append(len(n - f)); forsvunna.append(len(f - n))
    out["core_panel"] = {"rader": len(core_df), "dubbletter": len(dubbletter),
                         "exempel_dubbletter": list(dubbletter)[:5],
                         "nya_namn_per_panel_medel": round(float(np.mean(nya)), 2),
                         "forsvunna_namn_per_panel_medel": round(float(np.mean(forsvunna)), 2),
                         "forsvunna_totalt": int(np.sum(forsvunna))}
    print(f"\nCORE_PANEL: {len(core_df)} rader, {len(dubbletter)} dubbletter, "
          f"nya {np.mean(nya):.1f}/panel, försvunna {np.mean(forsvunna):.1f}/panel "
          f"({int(np.sum(forsvunna))} totalt)")

    # ---- 6. avkastningsfördelning: rimlighetskontroll ----
    vals = [v for v in returns_map.values() if v != 0.0]
    a = np.array(vals)
    out["avkastningsfordelning"] = {
        "n_icke_noll": len(a), "medel": round(float(a.mean()), 4),
        "median": round(float(np.median(a)), 4), "sd": round(float(a.std(ddof=1)), 4),
        "min": round(float(a.min()), 4), "max": round(float(a.max()), 4),
        "andel_under_minus50": round(float(np.mean(a < -0.5)), 5),
        "andel_over_plus100": round(float(np.mean(a > 1.0)), 5),
    }
    print(f"\nAVKASTNING (icke-noll, n={len(a)}): medel {a.mean():+.2%}, median {np.median(a):+.2%}, "
          f"sd {a.std(ddof=1):.2%}, min {a.min():+.1%}, max {a.max():+.1%}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
