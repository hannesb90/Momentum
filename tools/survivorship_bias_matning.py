"""HUR STOR ÄR SURVIVORSHIP-BIASEN? MÄTT PÅ PERIODEN DÄR VI VET SVARET

Beslut 2026-08-15: köra 2010-2019 trots survivorship-hålet, med biasen
dokumenterad. Den körningen är bara tolkbar om vi vet hur stor biasen ÄR.

Det går att mäta exakt på 2020-2026, där universumet är korrekt hanterat med
68 verifierade terminala bolag. Metod: bygg om samma modell men med det
universum en nutida instrumentlista skulle ha gett — alltså bara de namn som
fortfarande finns hos leverantören idag. Skillnaden är biasen.

Tre armar:
  FULL        kanoniskt PIT-universum (sanningen)
  BLIND_BD    endast namn som finns i Börsdatas nutida instrumentlista
              (exakt vad en 20-årshämtning från Börsdata Pro hade gett)
  BLIND_SLUT  endast namn som finns kvar i sista panelens universum
              (den klassiska "dagens lista, bakåtfylld"-varianten)

Rapporterar också biasen per år, eftersom den växer med avståndet bakåt: ju
längre bak man går desto större andel av det dåtida universumet har hunnit
försvinna. Det ger en extrapolering till hur stor biasen vore 2010.

DIAGNOSTISKT. Kör: /opt/momentum/venv/bin/python tools/survivorship_bias_matning.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/survivorship_bias_matning_results.json"
BD = V2 / "trackj/j2a_borsdata_api_probe/raw/J2A_PROBE_2026-08-09T120000Z/instruments.json"
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

    bd = json.loads(BD.read_text())
    bd_rows = bd.get("instruments", bd) if isinstance(bd, dict) else bd
    bd_tickers = {(r.get("ticker") or "").upper().replace(" ", "") for r in bd_rows}
    overlevare_bd = {r["kod"] for dt in eval_dates for r in rankings[dt]
                     if r["kod"].upper().replace(" ", "") in bd_tickers}
    overlevare_slut = {r["kod"] for r in rankings[eval_dates[-1]]}
    alla = {r["kod"] for dt in eval_dates for r in rankings[dt]}

    print(f"Universum totalt: {len(alla)} koder")
    print(f"  finns i Börsdatas nutida lista: {len(overlevare_bd)} "
          f"({len(overlevare_bd)/len(alla):.1%})")
    print(f"  finns i sista panelen:          {len(overlevare_slut)} "
          f"({len(overlevare_slut)/len(alla):.1%})")
    print(f"  terminala bolag i vår data:     {len(terminal)}")

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

    def sim(N, tillatna=None):
        """tillatna=None: hela PIT-universumet. Annars filtreras ranglistan."""
        cap = tk.cap_for(N)
        prev, nets = [], []
        for dt in eval_dates:
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt] if tillatna is None else [r for r in rankings[dt] if r["kod"] in tillatna]
            elig = {r["kod"] for r in raw}
            if sched or not prev:
                sel0 = [r["kod"] for r in raw[:N]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < N:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
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

    out = {"version": "SURVIVORSHIP_BIAS_MATNING_V1",
           "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
           "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten",
           "universum": {"totalt": len(alla), "i_borsdata_idag": len(overlevare_bd),
                         "i_sista_panelen": len(overlevare_slut), "terminala": len(terminal)},
           "armar": {}, "bias_per_ar": {}}

    serier = {}
    for N in (20, 30):
        for namn, till in (("FULL", None), ("BLIND_BD", overlevare_bd), ("BLIND_SLUT", overlevare_slut)):
            nets = sim(N, till)
            serier[(N, namn)] = nets
            c, v, dd, sh = tk.stats(nets)
            out["armar"][f"N{N}_{namn}"] = {"cagr": round(c, 4), "vol": round(v, 4),
                                            "maxdd": round(dd, 4), "sharpe": round(sh, 4)}
        cf = tk.stats(serier[(N, "FULL")])[0]
        for namn in ("BLIND_BD", "BLIND_SLUT"):
            cb = tk.stats(serier[(N, namn)])[0]
            out["armar"][f"N{N}_{namn}"]["bias_pp"] = round(cb - cf, 4)

    print(f"\n{'arm':<18} {'CAGR':>8} {'vol':>8} {'maxDD':>9} {'Sharpe':>8} {'bias':>8}")
    for k, v in out["armar"].items():
        b = f"{v.get('bias_pp', 0):+.2%}" if "bias_pp" in v else "—"
        print(f"  {k:<16} {v['cagr']:>8.2%} {v['vol']:>8.2%} {v['maxdd']:>9.2%} "
              f"{v['sharpe']:>8.3f} {b:>8}")

    # biasen växer med avståndet bakåt: hur stor andel av panel t:s universum
    # finns kvar idag?
    kvar = []
    for dt in eval_dates:
        koder = {r["kod"] for r in rankings[dt]}
        kvar.append(len(koder & overlevare_slut) / len(koder))
    out["bias_per_ar"] = {
        "andel_av_universumet_kvar_i_sista_panelen": {
            eval_dates[i][:7]: round(kvar[i], 4) for i in range(0, len(eval_dates), 6)},
        "forsta_panelen": round(kvar[0], 4), "sista_panelen": round(kvar[-1], 4),
        "avgang_per_ar": round((1 - kvar[0]) / (len(eval_dates) / PPY), 4),
    }
    bp = out["bias_per_ar"]
    ar = len(eval_dates) / PPY
    print(f"\nAvgångstakt: {bp['forsta_panelen']:.1%} av det ursprungliga universumet finns kvar "
          f"efter {ar:.1f} år → {bp['avgang_per_ar']:.2%} per år")
    print(f"  extrapolerat till 2010 ({2026-2010} år bakåt): "
          f"{max(0.0, 1 - bp['avgang_per_ar']*(2026-2010)):.0%} av 2010 års universum skulle finnas kvar idag")

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
