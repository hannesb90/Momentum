"""VAR UPPSTÅR SVANSEN? ABLATIONSSTEGE FRÅN REN RANK TILL STACK D

Frågan: är den tunga högersvansen (median −0,18 % mot medel +0,77 % per
panelposition) en egenskap hos DATAN, eller skapas den av någon add-on i
konstruktionen — SMA-grinden, invers volvikt, FR-overlayen eller vikttaket?

Stegen, varje nivå lägger till exakt en sak:

  A  ren rank        likavikt topp-N, ingen SMA, ingen FR, inget tak
  B  + SMA200-skip   entrégrinden
  C  + invvol^1.5    riskparitetsvikt utan tak
  D  + vikttak       waterfill (lagat)
  E  + FR-overlay    = Stack D kanonisk (med lagat tak)
  F  E med legacy-tak = den frysta modellen som den faktiskt kör

Referenspunkt: likavikt HELA universumet (~353 namn), som visar marknadens
egen svans utan någon urvalseffekt alls.

Mäts per arm: CAGR/vol/DD/Sharpe plus svansmått — median mot medel,
skevhet, överkurtos, andel av slutförmögenheten som kommer ur de tre bästa
panelerna, och koncentrationen i namn (andel av bidraget från topp-3 namn).

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/ablation_svansen.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/ablation_svansen_results.json"
COST, PPY, RF = 0.002, 13.0, 0.0224

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tspec = importlib.util.spec_from_file_location("takfel", V2 / "tools/takfel_diagnostik_och_n_svep.py")
tk = importlib.util.module_from_spec(tspec); tspec.loader.exec_module(tk)


def moments(x):
    a = np.asarray(x, dtype=float)
    mu, sd = a.mean(), a.std(ddof=1)
    skev = float(np.mean(((a - mu) / sd) ** 3)) if sd > 0 else None
    kurt = float(np.mean(((a - mu) / sd) ** 4) - 3.0) if sd > 0 else None
    return {"medel": round(float(mu), 4), "median": round(float(np.median(a)), 4),
            "sd": round(float(sd), 4), "skevhet": round(skev, 3) if skev is not None else None,
            "overkurtos": round(kurt, 2) if kurt is not None else None,
            "andel_negativa": round(float(np.mean(a < 0)), 3)}


def main():
    core_df, prices, terminal = m.load_data()
    returns_map, all_dates = m.execution_engine(core_df, prices, terminal)
    vol_map, price_series = m.compute_vols(prices, window=60)
    rankings = m.derive_h0_scores(core_df, prices)
    eval_dates = sorted(rankings.keys())
    anchor = all_dates.index(m.PHASE_ANCHOR_H0) % 2
    confirm_map = m.fetch_fundamental_confirmations(rankings, prices)
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

    def sim(N, sma=False, invvol=False, tak=None, fr=False):
        """tak: None | 'waterfill' | 'legacy'."""
        cap = tk.cap_for(N)
        prev, nets = [], []
        contrib = defaultdict(float)
        for dt in eval_dates:
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            if sched or not prev:
                sel0 = [r["kod"] for r in raw[:N]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < N:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)
            sel = [k for k in sel0 if sma_ok(k, dt)] if sma else list(sel0)
            n = len(sel)
            if n == 0:
                nets.append(0.0); prev = sel0; continue
            ts = n / N
            if invvol:
                vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
                inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
                w_raw = inv / np.sum(inv) * ts
            else:
                w_raw = np.full(n, ts / n)
            if fr:
                conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
                w_raw = w_raw * conf
            if tak == "waterfill":
                w = tk.w_waterfill(w_raw, ts, cap)
            elif tak == "legacy":
                w = tk.w_legacy(w_raw, ts, cap)
            else:
                w = w_raw / np.sum(w_raw) * ts
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            for k, wi, ri in zip(sel, w, rets):
                contrib[k] += float(wi * ri)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(nets), dict(contrib)

    def universum_likavikt():
        nets = []
        for dt in eval_dates:
            koder = [r["kod"] for r in rankings[dt]]
            rets = np.array([returns_map.get((k, dt), 0.0) for k in koder], dtype=float)
            nets.append(float(rets.mean()))
        return np.array(nets), {}

    def rapport(nets, contrib):
        c, v, dd, sh = tk.stats(nets)
        wealth = float(np.prod(1 + nets))
        bast3 = np.sort(nets)[-3:]
        utan3 = float(np.prod(1 + np.array([x for x in nets if x not in bast3])))
        tot = sum(contrib.values()) if contrib else None
        t3 = sorted(contrib.values(), reverse=True)[:3] if contrib else None
        return {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(dd, 4), "sharpe": round(sh, 4),
                "panelmoment": moments(nets),
                "slutformogenhet": round(wealth, 3),
                "slutformogenhet_utan_3_basta_paneler": round(utan3, 3),
                "andel_av_uppgangen_fran_3_basta_paneler": round(1 - (utan3 - 1) / (wealth - 1), 3)
                if wealth > 1 else None,
                "andel_bidrag_fran_3_basta_namn": round(sum(t3) / tot, 3) if tot and tot > 0 else None}

    steg = [
        ("A_ren_rank_likavikt", dict(sma=False, invvol=False, tak=None, fr=False)),
        ("B_plus_SMA200", dict(sma=True, invvol=False, tak=None, fr=False)),
        ("C_plus_invvol", dict(sma=True, invvol=True, tak=None, fr=False)),
        ("D_plus_tak_waterfill", dict(sma=True, invvol=True, tak="waterfill", fr=False)),
        ("E_plus_FR_stackD_lagat", dict(sma=True, invvol=True, tak="waterfill", fr=True)),
        ("F_stackD_legacytak", dict(sma=True, invvol=True, tak="legacy", fr=True)),
    ]

    out = {"version": "ABLATION_SVANSEN_V1",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
           "n_paneler": len(eval_dates), "per_N": {}}

    nu, _ = universum_likavikt()
    out["referens_universum_likavikt"] = rapport(nu, {})
    r = out["referens_universum_likavikt"]
    print(f"\nREFERENS — likavikt hela universumet (~353 namn):")
    print(f"  CAGR {r['cagr']:7.2%}  vol {r['vol']:6.2%}  DD {r['maxdd']:7.2%}  Sharpe {r['sharpe']:.3f}")
    pm = r["panelmoment"]
    print(f"  panel: medel {pm['medel']:+.2%}  median {pm['median']:+.2%}  skevhet {pm['skevhet']}  "
          f"överkurtos {pm['overkurtos']}  negativa {pm['andel_negativa']:.0%}")

    for N in (20, 30):
        out["per_N"][str(N)] = {}
        print(f"\n=== N={N}")
        print(f"  {'steg':<24} {'CAGR':>7} {'vol':>7} {'DD':>8} {'Sharpe':>7} "
              f"{'medel':>7} {'median':>7} {'skev':>6} {'kurt':>6} {'topp3 panel':>12} {'topp3 namn':>11}")
        for namn, kw in steg:
            nets, contrib = sim(N, **kw)
            rp = rapport(nets, contrib)
            out["per_N"][str(N)][namn] = rp
            pm = rp["panelmoment"]
            print(f"  {namn:<24} {rp['cagr']:>7.2%} {rp['vol']:>7.2%} {rp['maxdd']:>8.2%} "
                  f"{rp['sharpe']:>7.3f} {pm['medel']:>7.2%} {pm['median']:>7.2%} "
                  f"{str(pm['skevhet']):>6} {str(pm['overkurtos']):>6} "
                  f"{str(rp['andel_av_uppgangen_fran_3_basta_paneler']):>12} "
                  f"{str(rp['andel_bidrag_fran_3_basta_namn']):>11}")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
