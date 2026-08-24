"""GÅR GENOMFARTERNA ATT KÄNNA IGEN VID INTRÄDET?

Reseanalysen: 44 % av innehaven varar högst 2 paneler och förstör tillsammans
−0,317 av totalt +0,910. Den enda fråga som avgör om det är användbart är om de
går att skilja från de långa innehaven VID KÖPTILLFÄLLET.

Om de kommer in på sämre rank än övriga är gränsen vid rank 20 för slapp, och en
hysteresmarginal (kräv bättre rank för att komma in än för att få stanna) är en
väldefinierad kandidat. Om de kommer in på samma rank som alla andra går de inte
att identifiera, och 44 %-siffran är en efterhandsobservation utan handtag.

Mäter: inträdesrank, rankresa före inträde och SMA/vol-läge, korstabulerat mot
innehavslängd och bidrag. Plus ren prognoskraft: AUC för inträdesrank mot
utfallet "blev genomfart".

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/genomfarter_identifierbara.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/genomfarter_identifierbara_results.json"
COST = 0.002

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tspec = importlib.util.spec_from_file_location("takfel", V2 / "tools/takfel_diagnostik_och_n_svep.py")
tk = importlib.util.module_from_spec(tspec); tspec.loader.exec_module(tk)


def auc(scores, labels):
    """Sannolikheten att en slumpvis positiv får högre score än en slumpvis negativ."""
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return None
    v = 0.0
    for p in pos:
        for n in neg:
            v += 1.0 if p > n else (0.5 if p == n else 0.0)
    return v / (len(pos) * len(neg))


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
        if key not in sma_cache:
            v = True
            if k in price_series:
                ds, adj = price_series[k]
                i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
                if i is not None and i >= 200:
                    v = adj[i] >= float(np.mean(adj[i - 200:i]))
            sma_cache[key] = v
        return sma_cache[key]

    n_target = 20
    cap = tk.cap_for(n_target)
    prev, oppna, spells = [], {}, []
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
                spells.append(oppna.pop(k))
        for k in sel0:
            if k not in oppna:
                fore1 = rank_map.get((k, eval_dates[pi - 1])) if pi >= 1 else None
                fore3 = rank_map.get((k, eval_dates[pi - 3])) if pi >= 3 else None
                r0 = rank_map.get((k, dt))
                oppna[k] = {"kod": k, "start": pi, "intradesrank": r0,
                            "rank_1p_fore": fore1, "rank_3p_fore": fore3,
                            "klattring_1p": (fore1 - r0) if (fore1 and r0) else None,
                            "klattring_3p": (fore3 - r0) if (fore3 and r0) else None,
                            "vol": vol_map.get((k, dt)),
                            "bekraftad": bool(confirm_map.get((k, dt), False)),
                            "sma_ok": sma_ok(k, dt),
                            "bidrag": 0.0, "langd": 0}

        sel = [k for k in sel0 if sma_ok(k, dt)]
        if sel:
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            ts = len(sel) / n_target
            w_raw = inv / np.sum(inv) * ts
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = tk.w_waterfill(w_raw * conf, ts, cap)
            wmap = dict(zip(sel, w))
        else:
            wmap = {}
        for k in sel0:
            oppna[k]["langd"] += 1
            oppna[k]["bidrag"] += float(wmap.get(k, 0.0)) * float(returns_map.get((k, dt), 0.0))
        prev = sel0
    spells.extend(oppna.values())

    for s in spells:
        s["genomfart"] = s["langd"] <= 2

    G = [s for s in spells if s["genomfart"]]
    L = [s for s in spells if not s["genomfart"]]

    def sam(v):
        a = np.array([x for x in v if x is not None], dtype=float)
        if len(a) < 2:
            return None
        return {"n": len(a), "medel": round(float(a.mean()), 3), "median": round(float(np.median(a)), 3)}

    def welch(a, b):
        A = np.array([x for x in a if x is not None], dtype=float)
        B = np.array([x for x in b if x is not None], dtype=float)
        if len(A) < 3 or len(B) < 3:
            return None
        se = math.sqrt(A.var(ddof=1) / len(A) + B.var(ddof=1) / len(B))
        return round(float((A.mean() - B.mean()) / se), 3) if se > 0 else None

    out = {
        "version": "GENOMFARTER_IDENTIFIERBARA_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
        "definition_genomfart": "innehav som varar högst 2 paneler",
        "n_spells": len(spells), "n_genomfarter": len(G), "n_langa": len(L),
        "andel_genomfarter": round(len(G) / len(spells), 3),
        "summa_bidrag_genomfarter": round(float(np.sum([s["bidrag"] for s in G])), 4),
        "summa_bidrag_langa": round(float(np.sum([s["bidrag"] for s in L])), 4),
        "vid_intradet": {}, "prognoskraft": {}, "per_intradesrankband": {},
    }

    for falt in ("intradesrank", "rank_1p_fore", "rank_3p_fore", "klattring_1p", "klattring_3p", "vol"):
        out["vid_intradet"][falt] = {
            "genomfart": sam([s[falt] for s in G]),
            "lang": sam([s[falt] for s in L]),
            "t_welch": welch([s[falt] for s in G], [s[falt] for s in L]),
        }
    out["vid_intradet"]["andel_bekraftade"] = {
        "genomfart": round(float(np.mean([s["bekraftad"] for s in G])), 3),
        "lang": round(float(np.mean([s["bekraftad"] for s in L])), 3),
    }
    out["vid_intradet"]["andel_over_sma200"] = {
        "genomfart": round(float(np.mean([s["sma_ok"] for s in G])), 3),
        "lang": round(float(np.mean([s["sma_ok"] for s in L])), 3),
    }

    # prognoskraft: AUC för inträdesrank (högre rank = sämre = ska förutsäga genomfart)
    par = [(s["intradesrank"], s["genomfart"]) for s in spells if s["intradesrank"]]
    out["prognoskraft"]["auc_intradesrank"] = round(auc([p[0] for p in par], [p[1] for p in par]), 4)
    par2 = [(-s["klattring_3p"], s["genomfart"]) for s in spells if s["klattring_3p"] is not None]
    out["prognoskraft"]["auc_klattring_3p_invers"] = round(auc([p[0] for p in par2], [p[1] for p in par2]), 4)
    out["prognoskraft"]["tolkning"] = "0,50 = ingen prognoskraft; 0,60+ börjar vara användbart"

    # per inträdesrankband
    for lo, hi in [(1, 5), (6, 10), (11, 15), (16, 20), (21, 99)]:
        v = [s for s in spells if s["intradesrank"] and lo <= s["intradesrank"] <= hi]
        if len(v) < 5:
            continue
        out["per_intradesrankband"][f"{lo}-{hi}"] = {
            "n": len(v),
            "andel_genomfart": round(float(np.mean([s["genomfart"] for s in v])), 3),
            "medellangd": round(float(np.mean([s["langd"] for s in v])), 1),
            "summa_bidrag": round(float(np.sum([s["bidrag"] for s in v])), 4),
            "medelbidrag": round(float(np.mean([s["bidrag"] for s in v])), 5),
        }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(spells)} innehavsperioder, {len(G)} genomfarter ({len(G)/len(spells):.0%}), "
          f"bidrag {out['summa_bidrag_genomfarter']:+.3f} mot {out['summa_bidrag_langa']:+.3f}\n")
    print("VID INTRÄDET (median):")
    for falt, d in out["vid_intradet"].items():
        if isinstance(d, dict) and "genomfart" in d and isinstance(d["genomfart"], dict):
            print(f"  {falt:<16} genomfart {d['genomfart']['median']:>7}  lång {d['lang']['median']:>7}  "
                  f"t {d['t_welch']}")
    print(f"  bekräftade       genomfart {out['vid_intradet']['andel_bekraftade']['genomfart']:.0%}     "
          f"lång {out['vid_intradet']['andel_bekraftade']['lang']:.0%}")
    print(f"  över SMA200      genomfart {out['vid_intradet']['andel_over_sma200']['genomfart']:.0%}     "
          f"lång {out['vid_intradet']['andel_over_sma200']['lang']:.0%}")
    print(f"\nPROGNOSKRAFT: AUC inträdesrank {out['prognoskraft']['auc_intradesrank']}, "
          f"AUC klättring {out['prognoskraft']['auc_klattring_3p_invers']}")
    print("\nPER INTRÄDESRANKBAND:")
    for b, d in out["per_intradesrankband"].items():
        print(f"  rank {b:<6} n={d['n']:>3}  genomfart {d['andel_genomfart']:.0%}  "
              f"medellängd {d['medellangd']:>4}  summa bidrag {d['summa_bidrag']:+.4f}")
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
