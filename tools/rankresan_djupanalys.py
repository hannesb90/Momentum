"""RANKRESAN — DJUPANALYS AV ALLA INNEHAVS VÄG GENOM RANKINGEN

Varje innehav har en bana: det närmar sig uppifrån eller nedifrån, kommer in,
rör sig, toppar någonstans och lämnar. Den här analysen bryter ned var i den
banan pengarna faktiskt tjänas.

Mäter, per innehavsperiod (spell) och per panelobservation:

  A. BANANS FORM      inträdesrank, topprank, utgångsrank, längd, bidrag
  B. ARKETYPER        klättrare som stannade / klättrare som föll tillbaka /
                      sidledare / direkta fall — frekvens, bidrag, längd
  C. FASEN            avkastning per panel i innehavet, betingat på överlevnad
                      (annars mäter man bara att vinnare hålls längre)
  D. AVSTÅND TILL EGEN TOPP  bär "har fallit K platser från sin bästa rank"
                      information framåt? Detta är den enda formen av rank vi
                      inte redan avfärdat.
  E. ÖVERGÅNGSMATRIS  sannolikhet att gå mellan rankband, och avkastningen
                      betingad på övergången
  F. FÖRE OCH EFTER   rankbanan 3 paneler före inträde och 3 efter utgång,
                      samt avkastningen efter att vi sålt

Allt mäts på panelnivå (4 veckor). Ingen daglig upplösning finns.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/rankresan_djupanalys.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/rankresan_djupanalys_results.json"
COST = 0.002

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tspec = importlib.util.spec_from_file_location("takfel", V2 / "tools/takfel_diagnostik_och_n_svep.py")
tk = importlib.util.module_from_spec(tspec); tspec.loader.exec_module(tk)


def sammanfatta(v):
    if not v:
        return None
    a = np.array(v, dtype=float)
    return {"n": len(a), "medel": round(float(a.mean()), 4), "median": round(float(np.median(a)), 4),
            "sd": round(float(a.std(ddof=1)), 4) if len(a) > 1 else None,
            "t_mot_noll": round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 3)
            if len(a) > 1 and a.std(ddof=1) > 0 else None}


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

    def kor(n_target):
        """Kör baslinjen och logga varje innehavsperiod som en bana."""
        cap = tk.cap_for(n_target)
        prev, nets = [], []
        oppna = {}          # kod -> spell dict
        spells = []
        obs = []            # panelobservationer

        for pi, dt in enumerate(eval_dates):
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            if sched or not prev:
                sel0 = [r["kod"] for r in raw[:n_target]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < n_target:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: n_target - len(sel0)]

            for k in prev:
                if k not in sel0 and k in oppna:
                    s = oppna.pop(k)
                    s["utgangsrank"] = rank_map.get((k, dt))
                    s["utgang_panel_index"] = pi
                    spells.append(s)
            for k in sel0:
                if k not in oppna:
                    oppna[k] = {"kod": k, "start_panel_index": pi,
                                "intradesrank": rank_map.get((k, dt)),
                                "rankbana": [], "avkbana": [], "viktbana": []}

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
            wmap = dict(zip(sel, w))
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            nets.append(float(np.sum(w * rets)) - COST * turn)

            for k in sel0:
                r = rank_map.get((k, dt))
                ret = float(returns_map.get((k, dt), 0.0))
                wi = float(wmap.get(k, 0.0))
                s = oppna[k]
                bast_hittills = min([x for x in s["rankbana"] if x] or [999]) if s["rankbana"] else 999
                s["rankbana"].append(r)
                s["avkbana"].append(ret)
                s["viktbana"].append(wi)
                obs.append({"kod": k, "panel_index": pi, "fas": len(s["rankbana"]),
                            "rank": r, "ret": ret, "vikt": wi,
                            "bast_hittills": min(bast_hittills, r) if r else bast_hittills,
                            "avstand_till_egen_topp": (r - bast_hittills) if (r and bast_hittills < 999) else None,
                            "rankandring": (r - s["rankbana"][-2]) if len(s["rankbana"]) > 1 and r and s["rankbana"][-2] else None})
            prev = sel0

        for k, s in oppna.items():
            s["utgangsrank"] = None
            s["utgang_panel_index"] = len(eval_dates)
            spells.append(s)

        for s in spells:
            rb = [x for x in s["rankbana"] if x]
            s["langd"] = len(s["rankbana"])
            s["topprank"] = min(rb) if rb else None
            s["panel_till_topp"] = (rb.index(min(rb)) + 1) if rb else None
            s["bidrag"] = float(np.sum(np.array(s["viktbana"]) * np.array(s["avkbana"])))
            s["avk_total"] = float(np.prod(1 + np.array(s["avkbana"])) - 1)
            # avkastning efter utgång
            ui = s["utgang_panel_index"]
            s["avk_efter_1p"] = float(returns_map.get((s["kod"], eval_dates[ui]), 0.0)) if ui < len(eval_dates) else None
            e3 = 1.0
            for j in range(ui, min(ui + 3, len(eval_dates))):
                e3 *= 1 + returns_map.get((s["kod"], eval_dates[j]), 0.0)
            s["avk_efter_3p"] = float(e3 - 1) if ui < len(eval_dates) else None
            # rank före inträde
            si = s["start_panel_index"]
            s["rank_1p_fore"] = rank_map.get((s["kod"], eval_dates[si - 1])) if si >= 1 else None
            s["rank_3p_fore"] = rank_map.get((s["kod"], eval_dates[si - 3])) if si >= 3 else None
        return np.array(nets), spells, obs

    out = {
        "version": "RANKRESAN_DJUPANALYS_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "viktning": "waterfill (lagad)", "upplosning": "panel (4 veckor); ingen daglig rankserie finns",
        "per_N": {},
    }

    for n_target in (20, 30):
        nets, spells, obs = kor(n_target)
        cagr = tk.stats(nets)[0]
        d = {"baslinje_cagr": round(cagr, 4), "n_spells": len(spells), "n_panelobs": len(obs)}

        # A. banans form
        d["A_banans_form"] = {
            "intradesrank": sammanfatta([s["intradesrank"] for s in spells if s["intradesrank"]]),
            "topprank": sammanfatta([s["topprank"] for s in spells if s["topprank"]]),
            "utgangsrank": sammanfatta([s["utgangsrank"] for s in spells if s["utgangsrank"]]),
            "langd": sammanfatta([s["langd"] for s in spells]),
            "panel_till_topp": sammanfatta([s["panel_till_topp"] for s in spells if s["panel_till_topp"]]),
            "andel_som_toppar_i_forsta_panelen": round(
                float(np.mean([1.0 if s["panel_till_topp"] == 1 else 0.0 for s in spells if s["panel_till_topp"]])), 3),
        }

        # B. arketyper
        def arketyp(s):
            if s["langd"] <= 2:
                return "genomfart (<=2 paneler)"
            tr, ir, ur = s["topprank"], s["intradesrank"], s["utgangsrank"]
            if tr is None or ir is None:
                return "okand"
            klattrade = ir - tr >= 5
            foll = (ur is not None and ur - tr >= 10)
            if klattrade and not foll:
                return "klattrare som stannade"
            if klattrade and foll:
                return "klattrare som foll tillbaka"
            if not klattrade and foll:
                return "direkt fall"
            return "sidledare"

        ark = defaultdict(list)
        for s in spells:
            ark[arketyp(s)].append(s)
        d["B_arketyper"] = {
            a: {"n": len(v), "andel": round(len(v) / len(spells), 3),
                "medel_bidrag": round(float(np.mean([x["bidrag"] for x in v])), 4),
                "summa_bidrag": round(float(np.sum([x["bidrag"] for x in v])), 4),
                "medel_langd": round(float(np.mean([x["langd"] for x in v])), 1),
                "medel_avk_total": round(float(np.mean([x["avk_total"] for x in v])), 4)}
            for a, v in sorted(ark.items(), key=lambda kv: -len(kv[1]))
        }

        # C. fasen, betingat på överlevnad
        fas = {}
        for f in range(1, 13):
            overlevare = [s for s in spells if s["langd"] >= f]
            if len(overlevare) < 10:
                break
            fas[f"panel_{f}"] = {
                "n_spells_kvar": len(overlevare),
                "medelavk": round(float(np.mean([s["avkbana"][f - 1] for s in overlevare])), 4),
                "medelrank": round(float(np.mean([s["rankbana"][f - 1] for s in overlevare
                                                  if s["rankbana"][f - 1]])), 1),
            }
        # samma sak men bara för spells som lever minst 9 paneler (fast kohort)
        fast = [s for s in spells if s["langd"] >= 9]
        d["C_fas"] = {"betingat_pa_overlevnad": fas,
                      "fast_kohort_9plus": {"n": len(fast),
                                            "avk_per_fas": [round(float(np.mean([s["avkbana"][i] for s in fast])), 4)
                                                            for i in range(9)],
                                            "rank_per_fas": [round(float(np.mean([s["rankbana"][i] for s in fast
                                                                                  if s["rankbana"][i]])), 1)
                                                             for i in range(9)]}}

        # D. avstånd till egen topp
        band_avst = {"0 (på egen topp)": (0, 0), "1-5": (1, 5), "6-10": (6, 10),
                     "11-20": (11, 20), "21+": (21, 999)}
        d["D_avstand_till_egen_topp"] = {}
        for namn, (lo, hi) in band_avst.items():
            v = [o for o in obs if o["avstand_till_egen_topp"] is not None
                 and lo <= o["avstand_till_egen_topp"] <= hi]
            if len(v) < 20:
                continue
            d["D_avstand_till_egen_topp"][namn] = {
                "n": len(v),
                "medelavk": round(float(np.mean([o["ret"] for o in v])), 4),
                "medianavk": round(float(np.median([o["ret"] for o in v])), 4),
                "bidrag_per_panel_bp": round(1e4 * float(np.sum([o["ret"] * o["vikt"] for o in v])) / len(v), 1),
                "andel_negativa": round(float(np.mean([1.0 if o["ret"] < 0 else 0.0 for o in v])), 3),
            }
        # regression: avkastning mot avstånd
        xs = np.array([o["avstand_till_egen_topp"] for o in obs if o["avstand_till_egen_topp"] is not None], dtype=float)
        ys = np.array([o["ret"] for o in obs if o["avstand_till_egen_topp"] is not None], dtype=float)
        if len(xs) > 30:
            b = float(np.polyfit(xs, ys, 1)[0])
            r = float(np.corrcoef(xs, ys)[0, 1])
            d["D_regression"] = {"n": len(xs), "lutning_per_plats": round(b, 6),
                                 "korrelation": round(r, 4),
                                 "t": round(float(r * math.sqrt((len(xs) - 2) / max(1e-12, 1 - r ** 2))), 3)}

        # E. övergångsmatris mellan rankband
        def bandet(r):
            if r is None: return None
            if r <= 5: return "1-5"
            if r <= 10: return "6-10"
            if r <= 20: return "11-20"
            if r <= 30: return "21-30"
            return "31+"
        trans = defaultdict(lambda: defaultdict(int))
        trans_ret = defaultdict(list)
        for s in spells:
            rb = s["rankbana"]
            for i in range(len(rb) - 1):
                a, b2 = bandet(rb[i]), bandet(rb[i + 1])
                if a and b2:
                    trans[a][b2] += 1
                    trans_ret[(a, b2)].append(s["avkbana"][i + 1])
        d["E_overgangar"] = {
            a: {"n": sum(v.values()),
                "till": {b2: {"andel": round(c / sum(v.values()), 3),
                              "avk_nasta_panel": round(float(np.mean(trans_ret[(a, b2)])), 4)}
                         for b2, c in sorted(v.items(), key=lambda kv: -kv[1])}}
            for a, v in sorted(trans.items())
        }

        # G. ankomst mot avfärd i topp-5 — matrisens skarpaste cell, formellt prövad
        ankomst, avfard, kvar = [], [], []
        for s in spells:
            rb, ab = s["rankbana"], s["avkbana"]
            for i in range(len(rb) - 1):
                if rb[i] is None or rb[i + 1] is None:
                    continue
                fore, nu, r_efter = rb[i], rb[i + 1], ab[i + 1]
                if fore > 5 and nu <= 5:
                    ankomst.append(r_efter)
                elif fore <= 5 and nu > 5:
                    avfard.append(r_efter)
                elif fore <= 5 and nu <= 5:
                    kvar.append(r_efter)
        def welch(a, b):
            A, B = np.array(a), np.array(b)
            if len(A) < 3 or len(B) < 3:
                return None
            se = math.sqrt(A.var(ddof=1) / len(A) + B.var(ddof=1) / len(B))
            return round(float((A.mean() - B.mean()) / se), 3) if se > 0 else None
        d["G_topp5_ankomst_vs_avfard"] = {
            "just_anlant_till_topp5": sammanfatta(ankomst),
            "just_lamnat_topp5_nedat": sammanfatta(avfard),
            "kvar_i_topp5": sammanfatta(kvar),
            "t_ankomst_mot_avfard": welch(ankomst, avfard),
            "t_ankomst_mot_kvar": welch(ankomst, kvar),
            "tolkning_forbehall": "kort-horisonts rankförändring är prisförändring; detta är "
                                  "klassisk kortsiktig reversal, inte en oberoende signal",
        }

        # F. före och efter
        d["F_fore_och_efter"] = {
            "rank_3p_fore_intrade": sammanfatta([s["rank_3p_fore"] for s in spells if s["rank_3p_fore"]]),
            "rank_1p_fore_intrade": sammanfatta([s["rank_1p_fore"] for s in spells if s["rank_1p_fore"]]),
            "avk_1p_efter_utgang": sammanfatta([s["avk_efter_1p"] for s in spells if s["avk_efter_1p"] is not None]),
            "avk_3p_efter_utgang": sammanfatta([s["avk_efter_3p"] for s in spells if s["avk_efter_3p"] is not None]),
            "avk_sista_panelen_i_innehav": sammanfatta([s["avkbana"][-1] for s in spells if s["avkbana"]]),
        }
        # efter utgång, uppdelat på om namnet nått topp-5
        for etikett, filt in [("var_topp5", lambda s: s["topprank"] and s["topprank"] <= 5),
                              ("aldrig_topp5", lambda s: s["topprank"] and s["topprank"] > 5)]:
            v = [s["avk_efter_3p"] for s in spells if filt(s) and s["avk_efter_3p"] is not None]
            d["F_fore_och_efter"][f"avk_3p_efter_utgang_{etikett}"] = sammanfatta(v)

        out["per_N"][str(n_target)] = d
        print(f"\n=== N={n_target}: {len(spells)} innehavsperioder, {len(obs)} panelobservationer")
        A = d["A_banans_form"]
        print(f"  A. inträdesrank median {A['intradesrank']['median']}, topprank median {A['topprank']['median']}, "
              f"utgångsrank median {A['utgangsrank']['median']}, längd median {A['langd']['median']}")
        print(f"     {A['andel_som_toppar_i_forsta_panelen']:.0%} toppar redan i första panelen")
        print("  B. arketyper:")
        for a, v in d["B_arketyper"].items():
            print(f"     {a:<28} n={v['n']:>3} ({v['andel']:.0%})  medelbidrag {v['medel_bidrag']:+.4f}  "
                  f"summa {v['summa_bidrag']:+.3f}  längd {v['medel_langd']}")
        print("  C. avkastning per fas (fast kohort >=9 paneler, n=%d):" % d["C_fas"]["fast_kohort_9plus"]["n"])
        print("     avk ", " ".join(f"{x:+.1%}" for x in d["C_fas"]["fast_kohort_9plus"]["avk_per_fas"]))
        print("     rank", " ".join(f"{x:5.1f}" for x in d["C_fas"]["fast_kohort_9plus"]["rank_per_fas"]))
        print("  D. avstånd till egen topp:")
        for b, v in d["D_avstand_till_egen_topp"].items():
            print(f"     {b:<18} n={v['n']:>4}  avk {v['medelavk']:+.2%}  bidrag/panel {v['bidrag_per_panel_bp']:>6.1f} bp  "
                  f"neg {v['andel_negativa']:.0%}")
        if "D_regression" in d:
            print(f"     regression: {d['D_regression']['lutning_per_plats']*100:+.4f} %/plats, "
                  f"korr {d['D_regression']['korrelation']:+.4f}, t {d['D_regression']['t']}")
        G = d["G_topp5_ankomst_vs_avfard"]
        print("  G. topp-5, ankomst mot avfärd (avkastning panelen EFTER):")
        for e in ("just_anlant_till_topp5", "kvar_i_topp5", "just_lamnat_topp5_nedat"):
            g = G[e]
            if g:
                print(f"     {e:<26} n={g['n']:>4}  {g['medel']:+.2%}  median {g['median']:+.2%}  t {g['t_mot_noll']}")
        print(f"     t ankomst mot avfärd {G['t_ankomst_mot_avfard']}, ankomst mot kvar {G['t_ankomst_mot_kvar']}")
        print("  F. efter utgång:")
        F = d["F_fore_och_efter"]
        print(f"     sista panelen i innehavet {F['avk_sista_panelen_i_innehav']['medel']:+.2%}, "
              f"1p efter {F['avk_1p_efter_utgang']['medel']:+.2%}, 3p efter {F['avk_3p_efter_utgang']['medel']:+.2%} "
              f"(t {F['avk_3p_efter_utgang']['t_mot_noll']})")
        for e in ("var_topp5", "aldrig_topp5"):
            g = F.get(f"avk_3p_efter_utgang_{e}")
            if g:
                print(f"     3p efter utgång, {e:<12} {g['medel']:+.2%} (n={g['n']}, t {g['t_mot_noll']})")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
