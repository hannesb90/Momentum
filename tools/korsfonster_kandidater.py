"""KORSFÖNSTERPRÖVNING AV KANDIDATERNA

Ablationen prövades i båda fönstren. Kandidaterna gjordes inte — varje familj
avfärdades på bästa-av-N inom ETT fönster. Det är en svagare test: en cell som
är positiv i båda fönstren är ett helt annat påstående än en cell som vann ett
rutnät i ett fönster.

Prövar här SAMMA parameteruppsättningar i båda fönstren:

  A. Två fönster (separat köpband och ägandegräns) — de celler som föll ut bäst
     i respektive fönster, plus de närmast intilliggande.
  B. Stämplade återinträden — det enda fyndet i hela sessionen med t > 2 i
     positiv riktning (+6,28 % mot färska namns +1,97 %, t 2,46 på tre paneler).

Kriteriet är detsamma som för add-onerna: samma tecken i båda fönstren.

Kör: /opt/momentum/venv/bin/python tools/korsfonster_kandidater.py
"""
from __future__ import annotations
import importlib.util, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/korsfonster_kandidater_results.json"
sys.path.insert(0, str(V2 / "tools"))

# ---------- fönster 2020-2026 ----------
_s = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
H = importlib.util.module_from_spec(_s); _s.loader.exec_module(H)
_t = importlib.util.spec_from_file_location("tk", V2 / "tools/takfel_diagnostik_och_n_svep.py")
TK = importlib.util.module_from_spec(_t); _t.loader.exec_module(TK)

core_df, prices, terminal = H.load_data()
RET26, ALLD = H.execution_engine(core_df, prices, terminal)
VOL26, PS26 = H.compute_vols(prices, window=60)
RANK26_ROWS = H.derive_h0_scores(core_df, prices)
CONF26 = H.fetch_fundamental_confirmations(RANK26_ROWS, prices)
DT26 = sorted(RANK26_ROWS.keys())
ANCHOR26 = ALLD.index(H.PHASE_ANCHOR_H0) % 2
RANK26 = {(r["kod"], dt): i + 1 for dt in DT26 for i, r in enumerate(RANK26_ROWS[dt])}
COST = 0.002
_sma26 = {}


def sma26(k, dt):
    if (k, dt) not in _sma26:
        v = True
        if k in PS26:
            ds, adj = PS26[k]
            i = next((j for j in range(len(ds) - 1, -1, -1) if ds[j] <= dt), None)
            if i is not None and i >= 200:
                v = adj[i] >= float(np.mean(adj[i - 200:i]))
        _sma26[(k, dt)] = v
    return _sma26[(k, dt)]


def sim26(N=30, kopband=None, exit_rank=None):
    cap = TK.cap_for(N)
    prev, nets = [], []
    lo, hi = kopband if kopband else (1, N)
    for dt in DT26:
        sched = ALLD.index(dt) % 2 == ANCHOR26
        raw = RANK26_ROWS[dt]
        elig = {r["kod"] for r in raw}
        if not prev:
            sel0 = [r["kod"] for r in raw[lo - 1:hi]][:N]
        elif sched:
            gr = exit_rank if exit_rank else N
            behall = [k for k in prev if k in elig and RANK26[(k, dt)] <= gr]
            sel0 = sorted(behall, key=lambda k: RANK26[(k, dt)])
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw[lo - 1:hi] if r["kod"] not in sel0][: N - len(sel0)]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < N:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
        turn = 0.0 if not prev else 1.0 - len(set(sel0) & set(prev)) / max(1, len(sel0))
        sel = [k for k in sel0 if sma26(k, dt)]
        n = len(sel)
        if n == 0:
            nets.append(0.0); prev = sel0; continue
        ts = n / N
        inv = 1.0 / (np.maximum(np.array([VOL26.get((k, dt), 0.25) for k in sel]), 0.05) ** 1.5)
        w = inv / np.sum(inv) * ts
        w = w * np.array([1.0 if CONF26.get((k, dt), False) else 0.75 for k in sel])
        w = TK.w_waterfill(w, ts, cap)
        nets.append(float(np.sum(w * np.array([RET26.get((k, dt), 0.0) for k in sel]))) - COST * turn)
        prev = sel0
    return np.array(nets)


def stat26(x):
    w = np.cumprod(1 + x); dd = w / np.maximum.accumulate(w) - 1
    c = float(w[-1] ** (13 / len(x)) - 1); v = float(x.std(ddof=1) * math.sqrt(13))
    return {"cagr": round(c, 4), "vol": round(v, 4), "maxdd": round(float(dd.min()), 4),
            "sharpe": round((c - 0.0224) / v, 3)}


def boot26(a, b, seed=20260816):
    rng = np.random.default_rng(seed); n = len(a); nb = int(math.ceil(n / 13)); o = []
    for _ in range(2000):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, n - 13 + 1); idx.extend(range(s, s + 13))
        idx = np.array(idx[:n])
        o.append(np.cumprod(1 + a[idx])[-1] ** (13 / n) - np.cumprod(1 + b[idx])[-1] ** (13 / n))
    d = a - b; sd = d.std(ddof=1)
    return {"delta_cagr": round(stat26(a)["cagr"] - stat26(b)["cagr"], 4),
            "ki_lo": round(float(np.percentile(o, 2.5)), 4),
            "ki_hi": round(float(np.percentile(o, 97.5)), 4),
            "t": round(float(d.mean() / (sd / math.sqrt(len(d)))), 3)}


# ---------- fönster 2014-2019 ----------
import h1419_motor as M


def main():
    M.verifiera_baslinje()
    ut = {"version": "KORSFONSTER_KANDIDATER_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "kriterium": "samma tecken i BÅDA fönstren, samma parameteruppsättning",
          "A_tva_fonster": {}, "B_stamplade_aterintraden": {}}

    # ---------- A ----------
    celler = [(10, (1, 10), 20), (10, (1, 10), 30), (10, (11, 20), 30),
              (10, (15, 25), 30), (10, (15, 25), 40), (10, (16, 30), 30),
              (20, (1, 10), 30), (20, (1, 15), 30), (20, (1, 15), 40)]
    print(f"{'cell':<24}{'Δ 2020-26':>12}{'Δ 2014-19':>12}{'replikerar':>12}")
    for N, kb, H_ in celler:
        b26 = sim26(N=N); a26 = sim26(N=N, kopband=kb, exit_rank=H_)
        d26 = boot26(a26, b26)
        b19 = M.sim(N=N); a19 = M.sim(N=N, kopband=kb, exit_rank=H_)
        d19 = M.boot(a19, b19)
        rep = d26["delta_cagr"] * d19["delta_cagr"] > 0
        nyckel = f"N{N}_kop{kb[0]}-{kb[1]}_H{H_}"
        ut["A_tva_fonster"][nyckel] = {
            "f2020_2026": {**stat26(a26), **d26}, "f2014_2019": {**M.stat(a19), **d19},
            "replikerar": bool(rep),
            "bada_positiva": bool(d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0)}
        print(f"{nyckel:<24}{d26['delta_cagr']:>+11.2%}{d19['delta_cagr']:>+12.2%}"
              f"{('JA' if rep else 'nej'):>12}")

    # ---------- B ----------
    def kohorter(rank_rows, dts, rank_map, ret, sma_fn, N=30, anchor_fn=None):
        prev, stamplad_nu, var_stamplad, har_haft = [], set(), set(), set()
        farska, ater_st, ater_ost = [], [], []
        for pi, dt in enumerate(dts):
            sched = anchor_fn(pi, dt)
            raw = rank_rows[dt]
            elig = {r["kod"] for r in raw}
            if sched or not prev:
                sel0 = [r["kod"] for r in raw[:N]]
            else:
                sel0 = [k for k in prev if k in elig]
                if len(sel0) < N:
                    sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][: N - len(sel0)]
            for k in sel0:
                if k not in prev:
                    tot = 1.0
                    for j in range(pi, min(pi + 3, len(dts))):
                        tot *= 1 + ret.get((k, dts[j]), 0.0)
                    v = tot - 1
                    if k not in har_haft:
                        farska.append(v)
                    elif k in var_stamplad:
                        ater_st.append(v)
                    else:
                        ater_ost.append(v)
            for k in prev:
                if k not in sel0:
                    har_haft.add(k)
                    (var_stamplad.add(k) if k in stamplad_nu else var_stamplad.discard(k))
            stamplad_nu &= set(sel0)
            for k in sel0:
                if rank_map.get((k, dt), 999) <= 5:
                    stamplad_nu.add(k)
            prev = sel0
        return farska, ater_st, ater_ost

    def welch(a, b):
        A, B = np.array(a), np.array(b)
        if len(A) < 3 or len(B) < 3:
            return None
        se = math.sqrt(A.var(ddof=1) / len(A) + B.var(ddof=1) / len(B))
        return round(float((A.mean() - B.mean()) / se), 3) if se > 0 else None

    f26, s26, o26 = kohorter(RANK26_ROWS, DT26, RANK26, RET26, sma26,
                             anchor_fn=lambda pi, dt: ALLD.index(dt) % 2 == ANCHOR26)
    f19, s19, o19 = kohorter(M.RANKNINGAR, M.PANELER, M.RANK, M.RET, M.sma_ok,
                             anchor_fn=lambda pi, dt: pi % 2 == 0)
    print(f"\n{'kohort (3 paneler framåt)':<30}{'2020-2026':>22}{'2014-2019':>22}")
    for namn, a, b in (("färska namn", f26, f19), ("återinträde, ostämplat", o26, o19),
                       ("återinträde, STÄMPLAT", s26, s19)):
        print(f"{namn:<30}{np.mean(a):>+15.2%} (n={len(a):>3}){np.mean(b):>+15.2%} (n={len(b):>3})")
    ut["B_stamplade_aterintraden"] = {
        "f2020_2026": {"farska": [len(f26), round(float(np.mean(f26)), 4)],
                       "ater_ostamplat": [len(o26), round(float(np.mean(o26)), 4)],
                       "ater_stamplat": [len(s26), round(float(np.mean(s26)), 4)],
                       "t_stamplat_mot_farska": welch(s26, f26)},
        "f2014_2019": {"farska": [len(f19), round(float(np.mean(f19)), 4)],
                       "ater_ostamplat": [len(o19), round(float(np.mean(o19)), 4)],
                       "ater_stamplat": [len(s19), round(float(np.mean(s19)), 4)],
                       "t_stamplat_mot_farska": welch(s19, f19)}}
    b = ut["B_stamplade_aterintraden"]
    rep = (b["f2020_2026"]["ater_stamplat"][1] - b["f2020_2026"]["farska"][1]) * \
          (b["f2014_2019"]["ater_stamplat"][1] - b["f2014_2019"]["farska"][1]) > 0
    b["replikerar"] = bool(rep)
    print(f"  t stämplat mot färska: 2020-26 {b['f2020_2026']['t_stamplat_mot_farska']}, "
          f"2014-19 {b['f2014_2019']['t_stamplat_mot_farska']}  ->  "
          f"{'REPLIKERAR' if rep else 'replikerar EJ'}")

    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    bada = [k for k, v in ut["A_tva_fonster"].items() if v["bada_positiva"]]
    print(f"\nCeller positiva i BÅDA fönstren: {len(bada)} av {len(celler)}  {bada}")
    print(f"Skrivet: {OUT}")


if __name__ == "__main__":
    main()
