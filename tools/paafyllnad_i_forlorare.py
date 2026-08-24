"""FYLLER MODELLEN PÅ I FALLANDE INNEHAV OCH SÄLJER DEM STRAX EFTER?

Observationen: vid varje ombalansering återställs vikterna till mål. En position
som fallit sedan förra ombalanseringen har drivit NEDÅT i vikt, så återställning
betyder att köpa mer av den. Åtta veckor senare kan samma namn ha ramlat ur
topp-N och säljs — vi köpte alltså in oss i en förlorare strax före utgången.

STEG 1 (deterministiskt). Hur mycket kapital fylls på i fallande innehav, och
hur ofta säljs just de namnen vid nästa ombalansering?

STEG 2 (regel). Asymmetrisk ombalansering: vikta ned mot mål som vanligt, men
fyll ALDRIG på en position som fallit sedan förra ombalanseringen. Den frigjorda
vikten fördelas på övriga innehav.

Prövas i BÅDA fönstren med samma parameteruppsättning — kravet som gjorde att
köpbandsfamiljen räddades från felaktigt avfärdande.

Kör: /opt/momentum/venv/bin/python tools/paafyllnad_i_forlorare.py
"""
from __future__ import annotations
import importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/paafyllnad_i_forlorare_results.json"
sys.path.insert(0, str(V2 / "tools"))

_s = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
H = importlib.util.module_from_spec(_s); _s.loader.exec_module(H)
_t = importlib.util.spec_from_file_location("tk", V2 / "tools/takfel_diagnostik_och_n_svep.py")
TK = importlib.util.module_from_spec(_t); _t.loader.exec_module(TK)
import h1419_motor as M

core_df, prices, terminal = H.load_data()
RET26, ALLD = H.execution_engine(core_df, prices, terminal)
VOL26, PS26 = H.compute_vols(prices, window=60)
ROWS26 = H.derive_h0_scores(core_df, prices)
CONF26 = H.fetch_fundamental_confirmations(ROWS26, prices)
DT26 = sorted(ROWS26.keys())
ANCH26 = ALLD.index(H.PHASE_ANCHOR_H0) % 2
COST = 0.002
_sm = {}


def sma26(k, dt):
    if (k, dt) not in _sm:
        v = True
        if k in PS26:
            ds, adj = PS26[k]
            i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
            if i is not None and i >= 200:
                v = adj[i] >= float(np.mean(adj[i - 200:i]))
        _sm[(k, dt)] = v
    return _sm[(k, dt)]


def motor(rows, datum, ret, volf, smaf, conff, sched_fn, N=30, asymmetrisk=False, logga=False):
    """asymmetrisk=True: fyll aldrig på en position som fallit sedan förra ombalanseringen."""
    cap = TK.cap_for(N)
    prev, nets = [], []
    drift = {}                       # kod -> vikt just nu, efter avkastningsdrift
    logg = {"pafyllnad_i_fallande": 0.0, "pafyllnad_i_stigande": 0.0,
            "n_fallande_pafyllda": 0, "n_fallande_pafyllda_som_saljs_nasta": 0,
            "avk_fore_pafyllnad": [], "avk_efter_pafyllnad": []}
    for pi, dt in enumerate(datum):
        sched = sched_fn(pi, dt)
        raw = rows[dt]
        elig = {r["kod"] for r in raw}
        if sched or not prev:
            sel0 = [r["kod"] for r in raw[:N]]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev = sel0; drift = {}; continue
        ts = n / N
        inv = 1.0 / (np.maximum(np.array([volf(k, dt) for k in sel]), 0.05) ** 1.5)
        w = inv / np.sum(inv) * ts
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        w = TK.w_waterfill(w, ts, cap)

        if sched and drift:
            gammal = np.array([drift.get(k, 0.0) for k in sel])
            fallande = np.array([drift.get(k, 0.0) > 0 and ret.get((k, datum[pi - 1]), 0.0) < 0
                                 for k in sel])
            pafyll = np.maximum(0.0, w - gammal)
            if logga:
                logg["pafyllnad_i_fallande"] += float(np.sum(pafyll[fallande]))
                logg["pafyllnad_i_stigande"] += float(np.sum(pafyll[~fallande]))
                for j, k in enumerate(sel):
                    if fallande[j] and pafyll[j] > 1e-6:
                        logg["n_fallande_pafyllda"] += 1
                        logg["avk_efter_pafyllnad"].append(ret.get((k, dt), 0.0))
                        nxt = pi + 2
                        if nxt < len(datum):
                            fr = rows[datum[nxt]]
                            if k not in [r["kod"] for r in fr[:N]]:
                                logg["n_fallande_pafyllda_som_saljs_nasta"] += 1
            if asymmetrisk:
                # tillåt nedvikt, förbjud påfyllnad i fallande
                w = np.where(fallande, np.minimum(w, gammal), w)
                s = float(np.sum(w))
                if s > 0:
                    w = w / s * ts
                    w = np.clip(w, 0.01, cap)
                    w = w / float(np.sum(w)) * ts
        rets = np.array([ret.get((k, dt), 0.0) for k in sel])
        nets.append(float(np.sum(w * rets)) - COST * turn)
        drift = {k: float(x * (1 + r)) for k, x, r in zip(sel, w, rets)}
        prev = sel0
    return np.array(nets), logg


def st(x):
    w = np.cumprod(1 + x); dd = w / np.maximum.accumulate(w) - 1
    c = float(w[-1] ** (13 / len(x)) - 1); v = float(x.std(ddof=1) * math.sqrt(13))
    return {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(float(dd.min()), 4),
            "sharpe": round((c - 0.0224) / v, 3)}


def boot(a, b, seed=20260816):
    rng = np.random.default_rng(seed); n = len(a); nb = int(math.ceil(n / 13)); o = []
    for _ in range(2000):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, n - 13 + 1); idx.extend(range(s, s + 13))
        idx = np.array(idx[:n])
        o.append(np.cumprod(1 + a[idx])[-1] ** (13 / n) - np.cumprod(1 + b[idx])[-1] ** (13 / n))
    d = a - b; sd = d.std(ddof=1)
    return {"delta_cagr": round(st(a)["cagr"] - st(b)["cagr"], 4),
            "ki_lo": round(float(np.percentile(o, 2.5)), 4),
            "ki_hi": round(float(np.percentile(o, 97.5)), 4),
            "t": round(float(d.mean() / (sd / math.sqrt(len(d)))), 3)}


F26 = dict(rows=ROWS26, datum=DT26, ret=RET26, volf=lambda k, dt: VOL26.get((k, dt), 0.25),
           smaf=sma26, conff=lambda k, dt: CONF26.get((k, dt), False),
           sched_fn=lambda pi, dt: ALLD.index(dt) % 2 == ANCH26)
F19 = dict(rows=M.RANKNINGAR, datum=M.PANELER, ret=M.RET, volf=M.vol, smaf=M.sma_ok,
           conff=M.bekraftad, sched_fn=lambda pi, dt: pi % 2 == 0)


def main():
    ut = {"version": "PAAFYLLNAD_I_FORLORARE_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "steg1_frekvens": {}, "steg2_regel": {}}
    print("STEG 1 — hur mycket fylls på i fallande innehav?")
    for namn, F in (("2020-2026", F26), ("2014-2019", F19)):
        _, lg = motor(**F, logga=True)
        tot = lg["pafyllnad_i_fallande"] + lg["pafyllnad_i_stigande"]
        andel_saljs = (lg["n_fallande_pafyllda_som_saljs_nasta"] / lg["n_fallande_pafyllda"]
                       if lg["n_fallande_pafyllda"] else None)
        ut["steg1_frekvens"][namn] = {
            "pafyllnad_i_fallande": round(lg["pafyllnad_i_fallande"], 3),
            "pafyllnad_i_stigande": round(lg["pafyllnad_i_stigande"], 3),
            "andel_av_all_pafyllnad_till_fallande": round(lg["pafyllnad_i_fallande"] / tot, 3) if tot else None,
            "antal_pafyllda_fallande_positioner": lg["n_fallande_pafyllda"],
            "andel_av_dem_som_saljs_vid_nasta_ombalansering": round(andel_saljs, 3) if andel_saljs else None,
            "medelavkastning_panelen_efter_pafyllnad":
                round(float(np.mean(lg["avk_efter_pafyllnad"])), 4) if lg["avk_efter_pafyllnad"] else None}
        d = ut["steg1_frekvens"][namn]
        print(f"  {namn}: {d['antal_pafyllda_fallande_positioner']} påfyllda fallande positioner, "
              f"{d['andel_av_all_pafyllnad_till_fallande']:.0%} av all påfyllnad")
        print(f"     avkastning panelen EFTER påfyllnaden: {d['medelavkastning_panelen_efter_pafyllnad']:+.2%}")
        print(f"     andel som säljs vid nästa ombalansering: "
              f"{d['andel_av_dem_som_saljs_vid_nasta_ombalansering']:.0%}")

    print("\nSTEG 2 — asymmetrisk ombalansering (vikta ned, fyll aldrig på i fallande)")
    print(f"  {'fönster':<12}{'kanonisk':>11}{'asymmetrisk':>13}{'delta':>9}{'KI':>22}{'t':>7}")
    for namn, F in (("2020-2026", F26), ("2014-2019", F19)):
        a, _ = motor(**F)
        b, _ = motor(**F, asymmetrisk=True)
        d = boot(b, a)
        ut["steg2_regel"][namn] = {"kanonisk": st(a), "asymmetrisk": st(b), **d}
        ki = f"[{d['ki_lo']:+.2%}, {d['ki_hi']:+.2%}]"
        print(f"  {namn:<12}{st(a)['cagr']:>11.2%}{st(b)['cagr']:>13.2%}"
              f"{d['delta_cagr']:>+9.2%}{ki:>22}{d['t']:>7.2f}")
    rep = (ut["steg2_regel"]["2020-2026"]["delta_cagr"] *
           ut["steg2_regel"]["2014-2019"]["delta_cagr"] > 0)
    ut["replikerar"] = bool(rep)
    print(f"\n  Replikerar (samma tecken i båda fönstren): {'JA' if rep else 'NEJ'}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
