"""KÖPBANDET MOT DE RIKTIGA MODELLERNA — V-A OCH ERC, BÅDA FÖNSTREN

Tidigare tester i sessionen kördes mot en hybrid ("Stack D": invvol^1.5 OCH
FR-overlay) som inte är någon av de sex frysta modellerna. Detta skript prövar
köpbandskandidaten mot de faktiska konstruktionerna:

  V_A      = Control C + invers vol 60d, tak 1-6 %          (frusen champion)
  ERC      = Control C + invers vol^1.5, tak 1-6 %          (frusen skuggmodell)

Kandidaten: behåll rankningen, men rekrytera nya innehav från ett band UNDER
toppen och håll till en vidare gräns. Mekanismen är kortsiktig reversal —
band 1-5 har stigit dubbelt så mycket senaste månaden som band 26-30 och
avkastar sämst framåt, i båda fönstren.

Kravet är detsamma som räddade kandidaten från felaktigt avfärdande: SAMMA
parameteruppsättning måste vara positiv i BÅDA fönstren.

Kör: /opt/momentum/venv/bin/python tools/kopband_mot_ratt_modeller.py
"""
from __future__ import annotations
import importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/kopband_mot_ratt_modeller_results.json"
sys.path.insert(0, str(V2 / "tools"))

_s = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
H = importlib.util.module_from_spec(_s); _s.loader.exec_module(H)
import h1419_motor as M

core_df, prices, terminal = H.load_data()
RET26, ALLD = H.execution_engine(core_df, prices, terminal)
VOL26, PS26 = H.compute_vols(prices, window=60)
ROWS26 = H.derive_h0_scores(core_df, prices)
DT26 = sorted(ROWS26.keys())
ANCH26 = ALLD.index(H.PHASE_ANCHOR_H0) % 2
RANK26 = {(r["kod"], dt): i + 1 for dt in DT26 for i, r in enumerate(ROWS26[dt])}
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


def kanonisk_vikt(vols, n_held, N, exponent):
    """Exakt som run_simulation: clip en gång, renormalisera. Inklusive takfelet."""
    inv = 1.0 / (np.maximum(vols, 0.05) ** exponent)
    w = inv / np.sum(inv) * (n_held / N)
    w = np.clip(w, 0.01, 0.06)
    return w / np.sum(w) * (n_held / N)


def kor(rows, datum, ret, volf, smaf, rank, sched_fn, N=30, exponent=1.0,
        kopband=None, exit_rank=None):
    prev, nets = [], []
    lo, hi = kopband if kopband else (1, N)
    for pi, dt in enumerate(datum):
        raw = rows[dt]
        elig = {r["kod"] for r in raw}
        if not prev:
            sel0 = [r["kod"] for r in raw[lo - 1:hi]][:N]
        elif sched_fn(pi, dt):
            gr = exit_rank if exit_rank else N
            behall = [k for k in prev if k in elig and rank[(k, dt)] <= gr]
            sel0 = sorted(behall, key=lambda k: rank[(k, dt)])
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw[lo - 1:hi] if r["kod"] not in sel0][: N - len(sel0)]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev = sel0; continue
        w = kanonisk_vikt(np.array([volf(k, dt) for k in sel]), n, N, exponent)
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev = sel0
    return np.array(nets)


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
           smaf=sma26, rank=RANK26, sched_fn=lambda pi, dt: ALLD.index(dt) % 2 == ANCH26)
F19 = dict(rows=M.RANKNINGAR, datum=M.PANELER, ret=M.RET, volf=M.vol, smaf=M.sma_ok,
           rank=M.RANK, sched_fn=lambda pi, dt: pi % 2 == 0)

CELLER = [(None, None), ((1, 30), 40), ((6, 35), 45), ((11, 40), 50), ((16, 45), 55)]


def main():
    M.verifiera_baslinje()
    ut = {"version": "KOPBAND_MOT_RATT_MODELLER_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "modeller": {"V_A": "Control C + invers vol 60d ^1.0, tak 1-6 % (frusen champion)",
                       "ERC": "Control C + invers vol ^1.5, tak 1-6 % (frusen skuggmodell)"},
          "kriterium": "samma parameteruppsättning positiv i BÅDA fönstren",
          "resultat": {}}
    for mnamn, exp in (("V_A", 1.0), ("ERC", 1.5)):
        bas26 = kor(**F26, exponent=exp)
        bas19 = kor(**F19, exponent=exp)
        print(f"\n=== {mnamn}  (2020-26 {st(bas26)['cagr']:.2%} · 2014-19 {st(bas19)['cagr']:.2%})")
        print(f"  {'cell':<20}{'Δ 20-26':>10}{'Δ 14-19':>10}{'KI 20-26':>20}{'repl':>7}")
        for kb, ex in CELLER:
            if kb is None:
                continue
            a26 = kor(**F26, exponent=exp, kopband=kb, exit_rank=ex)
            a19 = kor(**F19, exponent=exp, kopband=kb, exit_rank=ex)
            d26, d19 = boot(a26, bas26), boot(a19, bas19)
            rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
            nyckel = f"{mnamn}_kop{kb[0]}-{kb[1]}_H{ex}"
            ut["resultat"][nyckel] = {"f2020_2026": {**st(a26), **d26},
                                      "f2014_2019": {**st(a19), **d19},
                                      "bada_positiva": bool(rep)}
            ki = f"[{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]"
            print(f"  köp {kb[0]}-{kb[1]}, håll {ex:<5}{d26['delta_cagr']:>+10.2%}"
                  f"{d19['delta_cagr']:>+10.2%}{ki:>20}{('JA' if rep else '-'):>7}")
        ut["resultat"][f"{mnamn}_baslinje"] = {"f2020_2026": st(bas26), "f2014_2019": st(bas19)}
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    bada = [k for k, v in ut["resultat"].items() if v.get("bada_positiva")]
    print(f"\nPositiva i båda fönstren: {len(bada)}  {bada}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
