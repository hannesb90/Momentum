"""TOPP-5-SPÄRR VID N=20

Regeln: ett innehav som under sitt innehav nått rankplats 1–5 får inte säljas
förrän det dripper ut till rank 40. Övriga innehav följer den vanliga regeln
(topp-N vid schemalagd ombalansering). Portföljstorleken hålls konstant på N —
skyddade namn tar platser, resten fylls på med högst rankade lediga namn.

Motfrågan testet finns till för: topp-5-stämpeln är en kvittens på att aktien
redan stigit (bidrag/panel i band 1-5 är 3,1 bp mot 7,1 bp i band 6-10, mätt
2026-08-15). Att förlänga innehavet i just de namnen kan lika gärna vara att
hålla kvar efter toppen.

KRAFT: differensserien mot baslinjen har ~1,0-1,5 % sd per panel. Vid +2 pp/år
krävs ~575 paneler (44 år) för t = 3. Med 66 paneler är detta INTE ett
signifikanstest — det mäter riktning, omsättning och mekanism.

DIAGNOSTISKT. Ingen fryst fil ändras, ingen försegling bryts, ingen challenger.

Kör: /opt/momentum/venv/bin/python tools/topp5_sparr_n20.py
"""
from __future__ import annotations
import importlib.util, json, math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/topp5_sparr_n20_results.json"
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
    print(f"{len(eval_dates)} paneler, {eval_dates[0]} — {eval_dates[-1]}")

    def sma_ok(k, dt):
        if k not in price_series:
            return True
        ds, adj = price_series[k]
        i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
        if i is None or i < 200:
            return True
        return adj[i] >= float(np.mean(adj[i - 200:i]))

    def sim(n_target, sparr, drip_rank=40, weighting="waterfill"):
        """sparr=False: kanonisk urvalsregel. sparr=True: topp-5-spärr med drip_rank."""
        cap = tk.cap_for(n_target)
        wfun = tk.w_legacy if weighting == "legacy" else tk.w_waterfill
        prev, nets, turns = [], [], []
        varit_topp5 = set()            # namn som nått topp-5 under pågående innehav
        skyddade_kvar = 0              # antal gånger spärren räddade ett namn
        extra_paneler = defaultdict(int)
        sparr_avk, ersattare_avk = [], []
        n_sparrade_namn = set()

        for dt in eval_dates:
            sched = all_dates.index(dt) % 2 == anchor
            raw = rankings[dt]
            elig = {r["kod"] for r in raw}
            topN = [r["kod"] for r in raw[:n_target]]

            if not prev:
                sel0 = list(topN)
            elif sched:
                if not sparr:
                    sel0 = list(topN)
                else:
                    behall = [k for k in prev if k in elig and k in varit_topp5
                              and rank_map[(k, dt)] <= drip_rank]
                    # skyddade som INTE hade kommit med ändå
                    raddade = [k for k in behall if k not in topN]
                    behall = sorted(behall, key=lambda k: rank_map[(k, dt)])[:n_target]
                    sel0 = list(behall)
                    for k in topN:
                        if len(sel0) >= n_target:
                            break
                        if k not in sel0:
                            sel0.append(k)
                    if len(sel0) < n_target:
                        for r in raw:
                            if len(sel0) >= n_target:
                                break
                            if r["kod"] not in sel0:
                                sel0.append(r["kod"])
                    # motfaktiskt: de högst rankade lediga namn som trängdes ut
                    utträngda = [r["kod"] for r in raw if r["kod"] not in sel0][:len(raddade)]
                    for k in raddade:
                        skyddade_kvar += 1
                        extra_paneler[k] += 1
                        n_sparrade_namn.add(k)
                        sparr_avk.append(returns_map.get((k, dt), 0.0))
                    for k in utträngda:
                        ersattare_avk.append(returns_map.get((k, dt), 0.0))
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < n_target:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: n_target - len(sel0)]

            turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / len(sel0)
            turns.append(turn)

            # uppdatera topp-5-stämpeln: sätts vid innehav, nollställs vid utgång
            varit_topp5 &= set(sel0)
            for k in sel0:
                if rank_map.get((k, dt), 999) <= 5:
                    varit_topp5.add(k)

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
            "arlig_omsattning_enkelriktad": round(float(np.mean(turns)) * PPY, 4),
            "raddade_positioner_totalt": skyddade_kvar,
            "unika_namn_som_spärrats": len(n_sparrade_namn),
            "extra_paneler_median": int(np.median(list(extra_paneler.values()))) if extra_paneler else 0,
            "extra_paneler_max": max(extra_paneler.values()) if extra_paneler else 0,
            "avk_i_sparrade_paneler": round(float(np.mean(sparr_avk)), 4) if sparr_avk else None,
            "avk_hos_uttrangda_ersattare": round(float(np.mean(ersattare_avk)), 4) if ersattare_avk else None,
            "n_sparrade_panelobs": len(sparr_avk),
        }
        if sparr_avk and ersattare_avk:
            a1, a2 = np.array(sparr_avk), np.array(ersattare_avk)
            se = math.sqrt(a1.var(ddof=1) / len(a1) + a2.var(ddof=1) / len(a2))
            diag["mekanik_t_welch"] = round(float((a1.mean() - a2.mean()) / se), 3) if se > 0 else None
            diag["mekanik_median_sparrad"] = round(float(np.median(a1)), 4)
            diag["mekanik_median_ersattare"] = round(float(np.median(a2)), 4)
            diag["mekanik_andel_sparrade_negativa"] = round(float((a1 < 0).mean()), 3)
        return np.array(nets), diag

    def boot_delta(a, b):
        """Block-bootstrap på den parvisa differensen a - b."""
        rng = np.random.default_rng(SEED)
        d = a - b
        n = len(d)
        nb = int(math.ceil(n / BOOT_BLOCK))
        outs = []
        for _ in range(BOOT_DRAWS):
            idx = []
            for _ in range(nb):
                s = rng.integers(0, n - BOOT_BLOCK + 1)
                idx.extend(range(s, s + BOOT_BLOCK))
            idx = np.array(idx[:n])
            wa = np.cumprod(1 + a[idx]); wb = np.cumprod(1 + b[idx])
            outs.append(wa[-1] ** (PPY / n) - wb[-1] ** (PPY / n))
        lo, hi = np.percentile(outs, [2.5, 97.5])
        t = float(d.mean() / (d.std(ddof=1) / math.sqrt(n))) if d.std(ddof=1) > 0 else 0.0
        ar_for_t3 = (3 * d.std(ddof=1) / d.mean()) ** 2 / PPY if d.mean() > 0 else None
        return {"ki_lo": round(float(lo), 4), "ki_hi": round(float(hi), 4),
                "t_parvis": round(t, 3), "sd_diff_per_panel": round(float(d.std(ddof=1)), 5),
                "ar_for_t3": round(float(ar_for_t3), 1) if ar_for_t3 else None}

    out = {
        "version": "TOPP5_SPARR_N20_V1",
        "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, ingen challenger",
        "regel": "innehav som nått rank<=5 under pågående innehav behålls tills rank>40; N hålls konstant",
        "kraftforbehall": "66 paneler. Differensserien kräver storleksordningen 40+ år för t=3. Riktning och omsättning, inte signifikans.",
        "viktning": "waterfill (lagad); cap = max(0.06, 1.5/N) som i N-svepet",
        "n_paneler": len(eval_dates), "period": f"{eval_dates[0]} — {eval_dates[-1]}",
        "armar": {}, "jamforelser": {}, "drip_svep": {},
    }

    serier = {}
    for n_t in (20, 30):
        for sp in (False, True):
            namn = f"N{n_t}_{'sparr40' if sp else 'bas'}"
            nets, diag = sim(n_t, sp, 40)
            serier[namn] = nets
            c, v, dd, sh = tk.stats(nets)
            out["armar"][namn] = {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(dd, 4),
                                  "sharpe": round(sh, 4), **diag}
            print(f"{namn:<16} CAGR {c:7.2%}  vol {v:6.2%}  DD {dd:7.2%}  Sharpe {sh:.3f}  "
                  f"oms {diag['arlig_omsattning_enkelriktad']:.0%}  räddade {diag['raddade_positioner_totalt']}")

    for n_t in (20, 30):
        a, b = serier[f"N{n_t}_sparr40"], serier[f"N{n_t}_bas"]
        ca, _, _, _ = tk.stats(a); cb, _, _, _ = tk.stats(b)
        out["jamforelser"][f"N{n_t}_sparr_minus_bas"] = {"delta_cagr": round(ca - cb, 4), **boot_delta(a, b)}
    a, b = serier["N20_sparr40"], serier["N30_bas"]
    ca, _, _, _ = tk.stats(a); cb, _, _, _ = tk.stats(b)
    out["jamforelser"]["N20_sparr_minus_N30_bas"] = {"delta_cagr": round(ca - cb, 4), **boot_delta(a, b)}

    # robusthetssvep över dripgränsen — rapporteras som brusband, inte som val
    for dr in (30, 35, 40, 45, 50):
        nets, diag = sim(20, True, dr)
        c, v, dd, sh = tk.stats(nets)
        out["drip_svep"][str(dr)] = {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(dd, 4),
                                     "sharpe": round(sh, 4),
                                     "delta_mot_bas": round(c - tk.stats(serier["N20_bas"])[0], 4),
                                     "raddade": diag["raddade_positioner_totalt"],
                                     "omsattning": diag["arlig_omsattning_enkelriktad"]}

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")
    print("\njämförelser:")
    for k, d in out["jamforelser"].items():
        print(f"  {k:<28} Δ {d['delta_cagr']:+.2%}  KI [{d['ki_lo']:+.2%}, {d['ki_hi']:+.2%}]  "
              f"t {d['t_parvis']:+.2f}  år för t=3: {d['ar_for_t3']}")
    print("\ndripsvep (N=20):")
    for k, d in out["drip_svep"].items():
        print(f"  rank>{k:<3} CAGR {d['cagr']:7.2%}  Δ {d['delta_mot_bas']:+.2%}  Sharpe {d['sharpe']:.3f}  "
              f"räddade {d['raddade']:>3}  oms {d['omsattning']:.0%}")
    print("\nmekanik (N=20, spärr 40):")
    d = out["armar"]["N20_sparr40"]
    print(f"  spärrade panelobs {d['n_sparrade_panelobs']}, unika namn {d['unika_namn_som_spärrats']}, "
          f"max extra paneler {d['extra_paneler_max']}")
    print(f"  avkastning i spärrade paneler {d['avk_i_sparrade_paneler']:+.2%} mot "
          f"utträngda ersättare {d['avk_hos_uttrangda_ersattare']:+.2%}")


if __name__ == "__main__":
    main()
