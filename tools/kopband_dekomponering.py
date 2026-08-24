"""DEKOMPONERING — FÖLL KÖPBANDET PÅ N=30, PÅ MODELLEN, ELLER PÅ GEOMETRIN?

Förra testet ändrade tre saker samtidigt: portföljstorlek (10/20 -> 30),
viktmodell (hybrid -> V_A/ERC) och bandgeometri. Slutsatsen "faller vid N=30"
gick därför inte att dra.

De celler som replikerade var N=10, köp 15-25, håll 30 — alltså RELATIVT:
köp mellan 1,5N och 2,5N, håll till 3N. Vid N=30 testades i stället köp 11-40
och håll 50, vilket är [0,37N, 1,33N] och håll 1,67N. En annan regel.

Detta skript håller den relativa geometrin KONSTANT och varierar bara N, på
båda viktmodellerna och i båda fönstren. Då går effekten att tillskriva rätt
faktor.

Förbehåll: de frysta modellerna är definierade endast vid N=30 (run_simulation
har /30.0 hårdkodat). För N=10 och N=20 används projektets N-svepskonvention:
target_sum = n/N och tak = max(0,06; 1,5/N).

Kör: /opt/momentum/venv/bin/python tools/kopband_dekomponering.py
"""
from __future__ import annotations
import importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/kopband_dekomponering_results.json"
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


def kor(rows, datum, ret, volf, smaf, rank, sched_fn, N, exponent, kopband=None, exit_rank=None):
    cap = max(0.06, 1.5 / N)
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
        ts = n / N
        inv = 1.0 / (np.maximum(np.array([volf(k, dt) for k in sel]), 0.05) ** exponent)
        w = inv / np.sum(inv) * ts
        w = np.clip(w, 0.01, cap)
        w = w / np.sum(w) * ts
        nets.append(float(np.sum(w * np.array([ret.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev = sel0
    return np.array(nets)


def cagr(x):
    return float(np.prod(1 + x) ** (13 / len(x)) - 1)


F26 = dict(rows=ROWS26, datum=DT26, ret=RET26, volf=lambda k, dt: VOL26.get((k, dt), 0.25),
           smaf=sma26, rank=RANK26, sched_fn=lambda pi, dt: ALLD.index(dt) % 2 == ANCH26)
F19 = dict(rows=M.RANKNINGAR, datum=M.PANELER, ret=M.RET, volf=M.vol, smaf=M.sma_ok,
           rank=M.RANK, sched_fn=lambda pi, dt: pi % 2 == 0)


def main():
    M.verifiera_baslinje()
    ut = {"version": "KOPBAND_DEKOMPONERING_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "geometri": "köp [1,5N, 2,5N], håll till 3N — samma relativa regel vid alla N",
          "forbehall": "frysta modeller finns bara vid N=30; N=10/20 använder N-svepskonventionen",
          "resultat": {}}
    print("KÖP [1,5N, 2,5N], HÅLL TILL 3N — samma relativa regel, varierande N\n")
    print(f"  {'modell':<6}{'N':>4}{'köpband':>12}{'håll':>6}"
          f"{'bas 20-26':>11}{'kand 20-26':>12}{'Δ':>8}"
          f"{'bas 14-19':>11}{'kand 14-19':>12}{'Δ':>8}{'repl':>6}")
    for mnamn, exp in (("V_A", 1.0), ("ERC", 1.5)):
        for N in (10, 20, 30):
            lo, hi, hall = int(round(1.5 * N)), int(round(2.5 * N)), int(round(3 * N))
            b26 = cagr(kor(**F26, N=N, exponent=exp))
            a26 = cagr(kor(**F26, N=N, exponent=exp, kopband=(lo, hi), exit_rank=hall))
            b19 = cagr(kor(**F19, N=N, exponent=exp))
            a19 = cagr(kor(**F19, N=N, exponent=exp, kopband=(lo, hi), exit_rank=hall))
            rep = (a26 - b26) > 0 and (a19 - b19) > 0
            ut["resultat"][f"{mnamn}_N{N}"] = {
                "kopband": [lo, hi], "hall": hall,
                "f2020_2026": {"baslinje": round(b26, 4), "kandidat": round(a26, 4),
                               "delta": round(a26 - b26, 4)},
                "f2014_2019": {"baslinje": round(b19, 4), "kandidat": round(a19, 4),
                               "delta": round(a19 - b19, 4)},
                "bada_positiva": bool(rep)}
            print(f"  {mnamn:<6}{N:>4}{f'{lo}-{hi}':>12}{hall:>6}"
                  f"{b26:>11.2%}{a26:>12.2%}{a26-b26:>+8.2%}"
                  f"{b19:>11.2%}{a19:>12.2%}{a19-b19:>+8.2%}{('JA' if rep else '-'):>6}")
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    bada = [k for k, v in ut["resultat"].items() if v["bada_positiva"]]
    print(f"\nPositiva i båda fönstren: {len(bada)}  {bada}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
