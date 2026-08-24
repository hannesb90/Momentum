"""SNÄV UTGÅNG FÖR TOPP-5-STÄMPLADE INNEHAV

Omvändningen av spärrtestet. I stället för att SKYDDA ett innehav som nått
topp-5 får det en SNÄVARE utgång än övriga: säljs så snart ranken faller
förbi T (5, 10, 15). Ostämplade innehav följer den vanliga topp-N-regeln.

Varför bara på den stämplade delmängden: en generell regel "sälj allt utanför
topp-10" är omöjlig vid N=20 — tjugo innehav får inte plats i topp tio. Vid
T = N reduceras regeln exakt till baslinjen, vilket är kontrollen.

Beslutsfrekvens testas i två varianter, eftersom hela poängen med en snäv
utgång är att reagera snabbt:
  8v = bara vid schemalagd ombalansering (kanoniskt)
  4v = vid varje panel (dubbelt så snabbt, högre omsättning)
Snabbare än så finns inte i datan: rank beräknas per panel, inte dagligen.

KRAFT: samma förbehåll som spärrtestet. Delmängden är liten (30-50
positionspaneler), differensserien kräver decennier för t = 3. Riktning,
omsättning och mekanism — inte signifikans.

DIAGNOSTISKT. Ingen fryst fil ändras, ingen försegling bryts, ingen challenger.

Kör: /opt/momentum/venv/bin/python tools/topp5_snav_utgang.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/topp5_snav_utgang_results.json"
COST, FLOOR, PPY, RF = 0.002, 0.01, 13.0, 0.0224
BOOT_BLOCK, BOOT_DRAWS, SEED = 13, 2000, 20260815

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
    print(f"{len(eval_dates)} paneler, {eval_dates[0]} — {eval_dates[-1]}, beslut var 8:e vecka i kanoniken")

    def sma_ok(k, dt):
        if k not in price_series:
            return True
        ds, adj = price_series[k]
        i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
        if i is None or i < 200:
            return True
        return adj[i] >= float(np.mean(adj[i - 200:i]))

    def sim(n_target, T, varje_panel=False, weighting="waterfill", karens=1):
        """T = utgångsrank för STÄMPLADE innehav. T = n_target ger baslinjen.

        karens = antal beslutstillfällen som ett utkastat namn är återköpsspärrat.
        Utan spärr är regeln verkningslös: namnet ligger kvar i topp-N och köps
        tillbaka i samma påfyllnad.
        """
        cap = tk.cap_for(n_target)
        wfun = tk.w_legacy if weighting == "legacy" else tk.w_waterfill
        prev, nets, turns = [], [], []
        stamplade = set()
        sparrad_till = {}          # kod -> beslutsindex då återköp åter tillåts
        beslut_nr = 0
        sald_avk, ersattare_avk = [], []
        n_utkastade, unika_utkastade = 0, set()

        for dt in eval_dates:
            sched = all_dates.index(dt) % 2 == anchor
            beslut = sched or varje_panel
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            topN = [r["kod"] for r in raw[:n_target]]

            if not prev:
                sel0 = list(topN)
            elif beslut:
                beslut_nr += 1
                behall, utkast = [], []
                for k in prev:
                    if k not in elig:
                        continue
                    r = rank_map[(k, dt)]
                    grans = T if k in stamplade else n_target
                    if r <= grans:
                        behall.append(k)
                    elif k in stamplade and r <= n_target:
                        # hade fått stanna utan regeln — detta är regelns verkan
                        utkast.append(k)
                for k in utkast:
                    sparrad_till[k] = beslut_nr + karens
                sel0 = sorted(behall, key=lambda k: rank_map[(k, dt)])
                for r in raw:
                    if len(sel0) >= n_target:
                        break
                    k = r["kod"]
                    if k in sel0 or sparrad_till.get(k, -1) > beslut_nr:
                        continue
                    sel0.append(k)
                if utkast:
                    ers = [k for k in sel0 if k not in prev][:len(utkast)]
                    for k in utkast:
                        n_utkastade += 1
                        unika_utkastade.add(k)
                        sald_avk.append(returns_map.get((k, dt), 0.0))
                    for k in ers:
                        ersattare_avk.append(returns_map.get((k, dt), 0.0))
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < n_target:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: n_target - len(sel0)]

            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)
            turns.append(turn)

            stamplade &= set(sel0)
            for k in sel0:
                if rank_map.get((k, dt), 999) <= 5:
                    stamplade.add(k)

            sel = [k for k in sel0 if sma_ok(k, dt)]
            n = len(sel)
            if n == 0:
                nets.append(0.0); prev = sel0; continue

            vols = np.array([vol_map.get((k, dt), 0.25) for k in sel], dtype=float)
            inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
            target_sum = n / n_target
            w_raw = inv / np.sum(inv) * target_sum
            conf = np.array([1.0 if confirm_map.get((k, dt), False) else 0.75 for k in sel], dtype=float)
            w = wfun(w_raw * conf, target_sum, cap)
            rets = np.array([returns_map.get((k, dt), 0.0) for k in sel], dtype=float)
            nets.append(float(np.sum(w * rets)) - COST * turn)
            prev = sel0

        diag = {
            "arlig_omsattning": round(float(np.mean(turns)) * PPY, 4),
            "utkastade_positionspaneler": n_utkastade,
            "unika_namn_utkastade": len(unika_utkastade),
            "avk_hos_utkastade_samma_panel": round(float(np.mean(sald_avk)), 4) if sald_avk else None,
            "avk_hos_ersattare": round(float(np.mean(ersattare_avk)), 4) if ersattare_avk else None,
        }
        if sald_avk and ersattare_avk:
            a1, a2 = np.array(sald_avk), np.array(ersattare_avk)
            se = math.sqrt(a1.var(ddof=1) / len(a1) + a2.var(ddof=1) / len(a2))
            diag["mekanik_t_welch"] = round(float((a1.mean() - a2.mean()) / se), 3) if se > 0 else None
            diag["andel_utkastade_negativa"] = round(float((a1 < 0).mean()), 3)
        return np.array(nets), diag

    def boot(a, b):
        rng = np.random.default_rng(SEED)
        d = a - b; n = len(d); nb = int(math.ceil(n / BOOT_BLOCK)); outs = []
        for _ in range(BOOT_DRAWS):
            idx = []
            for _ in range(nb):
                s = rng.integers(0, n - BOOT_BLOCK + 1); idx.extend(range(s, s + BOOT_BLOCK))
            idx = np.array(idx[:n])
            outs.append(np.cumprod(1 + a[idx])[-1] ** (PPY / n) - np.cumprod(1 + b[idx])[-1] ** (PPY / n))
        lo, hi = np.percentile(outs, [2.5, 97.5])
        sd = d.std(ddof=1)
        t = float(d.mean() / (sd / math.sqrt(n))) if sd > 0 else 0.0
        ar = (3 * sd / abs(d.mean())) ** 2 / PPY if d.mean() != 0 else None
        return {"ki_lo": round(float(lo), 4), "ki_hi": round(float(hi), 4), "t_parvis": round(t, 3),
                "ar_for_t3": round(float(ar), 1) if ar else None}

    out = {
        "version": "TOPP5_SNAV_UTGANG_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, ingen challenger",
        "regel": "innehav som nått rank<=5 säljs så snart rank>T; ostämplade följer topp-N",
        "matupplosning": {
            "rank": "beräknas per panel (4 veckor) — ingen daglig rankserie finns",
            "handel": "var 8:e vecka i kanoniken; 4v-varianten handlar varje panel",
            "avkastning": "panel-till-panel, inte daglig",
            "dagligt_i_modellen": "endast SMA200-filtret och 60-dagarsvolen",
        },
        "kraftforbehall": "delmängden är 20-60 positionspaneler; differensserien kräver decennier för t=3",
        "viktning": "waterfill (lagad); cap = max(0.06, 1.5/N)",
        "n_paneler": len(eval_dates), "period": f"{eval_dates[0]} — {eval_dates[-1]}",
        "armar": {}, "jamforelser": {},
    }

    serier = {}

    def kor(namn, n_t, T, vp, karens):
        nets, diag = sim(n_t, T, vp, karens=karens)
        serier[namn] = nets
        c, v, dd, sh = tk.stats(nets)
        out["armar"][namn] = {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(dd, 4),
                              "sharpe": round(sh, 4), "karens_beslut": karens, **diag}
        print(f"{namn:<22} CAGR {c:7.2%}  vol {v:6.2%}  DD {dd:7.2%}  Sharpe {sh:.3f}  "
              f"oms {diag['arlig_omsattning']:.0%}  utkast {diag['utkastade_positionspaneler']:>3}")

    for n_t in (20, 30):
        for vp in (False, True):
            frek = "4v" if vp else "8v"
            kor(f"N{n_t}_bas_{frek}", n_t, n_t, vp, 1)
            for T in (5, 10, 15):
                for ka in (1, 3):
                    kor(f"N{n_t}_T{T}_k{ka}_{frek}", n_t, T, vp, ka)

    for n_t in (20, 30):
        for frek in ("8v", "4v"):
            bas = serier[f"N{n_t}_bas_{frek}"]
            for T in (5, 10, 15):
                for ka in (1, 3):
                    a = serier[f"N{n_t}_T{T}_k{ka}_{frek}"]
                    out["jamforelser"][f"N{n_t}_T{T}_k{ka}_{frek}_minus_bas"] = {
                        "delta_cagr": round(tk.stats(a)[0] - tk.stats(bas)[0], 4), **boot(a, bas)}
    out["jamforelser"]["N20_bas_4v_minus_N20_bas_8v"] = {
        "delta_cagr": round(tk.stats(serier["N20_bas_4v"])[0] - tk.stats(serier["N20_bas_8v"])[0], 4),
        **boot(serier["N20_bas_4v"], serier["N20_bas_8v"])}
    out["jamforelser"]["N30_bas_4v_minus_N30_bas_8v"] = {
        "delta_cagr": round(tk.stats(serier["N30_bas_4v"])[0] - tk.stats(serier["N30_bas_8v"])[0], 4),
        **boot(serier["N30_bas_4v"], serier["N30_bas_8v"])}

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}\n")
    for k, d in out["jamforelser"].items():
        print(f"  {k:<28} Δ {d['delta_cagr']:+.2%}  KI [{d['ki_lo']:+.2%}, {d['ki_hi']:+.2%}]  "
              f"t {d['t_parvis']:+.2f}  år för t=3: {d['ar_for_t3']}")
    print("\nmekanik (avkastning samma panel hos utkastade mot deras ersättare):")
    for k, d in out["armar"].items():
        if d.get("avk_hos_utkastade_samma_panel") is not None:
            print(f"  {k:<18} utkastade {d['avk_hos_utkastade_samma_panel']:+.2%} mot ersättare "
                  f"{d['avk_hos_ersattare']:+.2%}  (n={d['utkastade_positionspaneler']}, "
                  f"t {d.get('mekanik_t_welch')})")


if __name__ == "__main__":
    main()
