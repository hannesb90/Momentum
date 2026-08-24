"""HJÄLPER TÄTARE MÄTNING? FREKVENS MOT STATISTISK KRAFT

Frågan: skulle dagliga beräkningspaneler i stället för fyraveckorspaneler ge
oss kraft att avgöra de frågor som fallit?

Teorin säger nej. För en serie med drift mu per tidsenhet och volatilitet sigma
gäller, vid n observationer av längd dt:

    medel per obs = mu*dt,  sd per obs = sigma*sqrt(dt)
    t = mu*dt/(sigma*sqrt(dt)) * sqrt(n) = mu*sqrt(dt*n)/sigma = mu*sqrt(T)/sigma

t beror bara på TOTAL KALENDERTID T, inte på hur fint man skivar den. Att gå
från 66 till 1 265 observationer över samma fem år ändrar ingenting.

Detta skript prövar påståendet EMPIRISKT på våra egna serier genom att
aggregera åt andra hållet — 1, 2, 3, 6 och 13 paneler per observation — och
visa att t-värdet är i stort sett oförändrat.

Mäter dessutom:
  - rankens autokorrelation över fyra veckor, som avgör hur mycket NY
    information en tätare rankberäkning ens kan innehålla
  - hur många år som krävs för t = 3 på grundsignalen

Kör: /opt/momentum/venv/bin/python tools/frekvens_vs_kraft.py
"""
from __future__ import annotations
import importlib.util, json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/frekvens_vs_kraft_results.json"
COST, PPY = 0.002, 13.0

spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tspec = importlib.util.spec_from_file_location("tk", V2 / "tools/takfel_diagnostik_och_n_svep.py")
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

    def stack_d(N=20):
        cap = tk.cap_for(N)
        prev, nets = [], []
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
            sel = [k for k in sel0 if sma_ok(k, dt)]
            n = len(sel)
            if n == 0:
                nets.append(0.0); prev = sel0; continue
            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            ts = n / N
            w_raw = inv / np.sum(inv) * ts
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = tk.w_waterfill(w_raw * conf, ts, cap)
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0
        return np.array(nets)

    univ = np.array([float(np.mean([returns_map.get((r["kod"], dt), 0.0) for r in rankings[dt]]))
                     for dt in eval_dates])
    modell = stack_d(20)
    diff_serie = modell - univ

    def aggregera(x, k):
        """Slå ihop k paneler till en observation genom komposition."""
        n = (len(x) // k) * k
        return np.array([np.prod(1 + x[i:i + k]) - 1 for i in range(0, n, k)])

    out = {"version": "FREKVENS_VS_KRAFT_V1",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "status": "DIAGNOSTISKT",
           "teori": "t = mu*sqrt(T)/sigma — beror på total kalendertid, inte på samplingsfrekvens",
           "aggregering": {}}

    print("AGGREGERINGSTEST — samma fem år, olika observationslängd")
    print(f"  {'paneler/obs':>12} {'veckor':>7} {'n':>5} {'medel':>9} {'sd':>9} {'t':>7}")
    for k in (1, 2, 3, 6, 13):
        a = aggregera(modell, k); b = aggregera(univ, k)
        d = a - b
        t = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))
        out["aggregering"][f"{k}_paneler"] = {
            "veckor_per_obs": 4 * k, "n_obs": len(d),
            "medel": round(float(d.mean()), 5), "sd": round(float(d.std(ddof=1)), 5),
            "t": round(t, 3)}
        print(f"  {k:>12} {4*k:>7} {len(d):>5} {d.mean():>9.3%} {d.std(ddof=1):>9.3%} {t:>7.2f}")

    # rankens tröghet över fyra veckor
    par = []
    for i in range(len(eval_dates) - 1):
        d0, d1 = eval_dates[i], eval_dates[i + 1]
        gemensam = [r["kod"] for r in rankings[d0][:60]]
        x = [rank_map[(k, d0)] for k in gemensam if (k, d1) in rank_map]
        y = [rank_map[(k, d1)] for k in gemensam if (k, d1) in rank_map]
        if len(x) > 10:
            par.append(float(np.corrcoef(x, y)[0, 1]))
    # samma sak för hela universumet
    par_alla = []
    for i in range(len(eval_dates) - 1):
        d0, d1 = eval_dates[i], eval_dates[i + 1]
        gemensam = [r["kod"] for r in rankings[d0]]
        x = [rank_map[(k, d0)] for k in gemensam if (k, d1) in rank_map]
        y = [rank_map[(k, d1)] for k in gemensam if (k, d1) in rank_map]
        if len(x) > 10:
            par_alla.append(float(np.corrcoef(x, y)[0, 1]))
    out["rankens_troghet"] = {
        "autokorr_4v_topp60": round(float(np.mean(par)), 4),
        "autokorr_4v_hela_universumet": round(float(np.mean(par_alla)), 4),
        "implicerad_daglig_autokorr": round(float(np.mean(par_alla)) ** (1 / 20), 4),
        "tolkning": "20 handelsdagar per panel; daglig autokorr = fyraveckorsvärdet upphöjt till 1/20",
    }
    rt = out["rankens_troghet"]
    print(f"\nRANKENS TRÖGHET: autokorrelation över fyra veckor "
          f"{rt['autokorr_4v_hela_universumet']:.3f} (topp-60: {rt['autokorr_4v_topp60']:.3f})")
    print(f"   implicerad DAGLIG autokorrelation: {rt['implicerad_daglig_autokorr']:.4f}")

    # år för t=3
    c_m = tk.stats(modell)[0]; c_u = tk.stats(univ)[0]
    d = diff_serie
    t_nu = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))
    ar_nu = len(eval_dates) / PPY
    out["ar_for_t3"] = {
        "grundsignal_delta_cagr": round(c_m - c_u, 4),
        "t_idag": round(t_nu, 3), "ar_idag": round(ar_nu, 2),
        "ar_for_t3": round(ar_nu * (3.0 / t_nu) ** 2, 1) if t_nu > 0 else None,
        "ar_for_t3_vid_2pp_effekt": round(ar_nu * (3.0 / (t_nu * 2.0 / max(1e-9, (c_m - c_u) * 100))) ** 2, 1)
        if t_nu > 0 and (c_m - c_u) > 0 else None,
    }
    a3 = out["ar_for_t3"]
    print(f"\nGRUNDSIGNALEN: Δ {a3['grundsignal_delta_cagr']:+.2%}, t {a3['t_idag']:.2f} på "
          f"{a3['ar_idag']} år → t = 3 kräver {a3['ar_for_t3']} år")

    # vad tätare data FAKTISKT förbättrar: volatilitetsskattningen
    out["vad_frekvens_hjalper"] = {
        "volatilitet": "sd-skattningens precision skalar med antalet observationer — "
                       "daglig data ger 20x fler och används redan (60-dagarsvol, SMA200)",
        "mean/drift": "precisionen skalar med kalendertid, INTE med frekvens — ingen vinst",
        "vagberoende_regler": "stop loss, trailing stop, intrapanel-drawdown kan bara testas "
                              "med finare data — detta är den enda reella öppningen",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
