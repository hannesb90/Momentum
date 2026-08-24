"""STATE/PATH FEASIBILITY — omraknad pa TRANSITIONSNIVA (uppdragets §22)

INGET prediction-test. Inga framtida avkastningar lases. Endast rankning.

STATE-SPACE (minimal, harledd ur H0:s EGEN urvalsgrans, inga uppfunna nivaer)
  S  rank <= 30      H0:s egen urvalsgrans
  N  rank 31-60      2 x samma grans
  W  rank > 60
  -  ej rankbar denna panel

PATH-VARIABLER (tva, bada preregistrerade, bada ur H0:s egna outputs)
  TIS  time-in-state: antal sammanhangande paneler i nuvarande band (PIT)
  DR2  rankforandring over 2 paneler = en full H0-rebalanscykel

PULLBACK/RECOVERY  event = S vid T-1, icke-S vid T. Loses PIT: RECOVERY om
  bandet ater blir S inom H=13 paneler, annars NO_RECOVERY. Endast event med
  T+H <= sista panel raknas som losta.

Kor: /opt/momentum/venv/bin/python tools/state_path_feasibility.py
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2"); sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
OUT = V2 / "research_k/state_path_feasibility.json"
H = 13


def band(r):
    if r is None: return "-"
    return "S" if r <= 30 else ("N" if r <= 60 else "W")


def kv(x):
    a = np.asarray(x, float)
    if not len(a): return None
    return {"n": len(a), "median": round(float(np.median(a)), 2),
            "q25": round(float(np.percentile(a, 25)), 2),
            "q75": round(float(np.percentile(a, 75)), 2),
            "medel": round(float(a.mean()), 2), "max": round(float(a.max()), 2)}


def sp(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 5 or a.std() == 0 or b.std() == 0: return None
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def analys(F, namn):
    dts = F["eval_dates"]
    rk, sc = {}, {}
    for dt in dts:
        for i, r in enumerate(F["rankings"][dt]):
            rk[(r["kod"], dt)] = i + 1; sc[(r["kod"], dt)] = r["score"]
    tick = sorted({k for k, _ in rk})
    P = len(dts)

    bands = {t: [band(rk.get((t, dt))) for dt in dts] for t in tick}
    tis = {}
    for t in tick:
        b, run, out = bands[t], 0, []
        for i in range(P):
            run = run + 1 if (i > 0 and b[i] == b[i - 1]) else 1
            out.append(run)
        tis[t] = out

    # ---- rankobservationer och transitioner
    n_rank = sum(1 for t in tick for i in range(P) if bands[t][i] != "-")
    trans = Counter(); trans_per_ticker = Counter(); loptal = 0
    for t in tick:
        b = bands[t]
        for i in range(P - 1):
            if b[i] == "-" or b[i + 1] == "-": continue
            trans[(b[i], b[i + 1])] += 1; trans_per_ticker[t] += 1
        loptal += sum(1 for i in range(P) if b[i] != "-" and (i == 0 or b[i] != b[i - 1]))

    # ---- pullback/recovery, PIT-losta
    pb = {"losta": 0, "recovery": 0, "no_recovery": 0, "olosta_censurerade": 0}
    pb_ticker = Counter()
    for t in tick:
        b = bands[t]
        for i in range(1, P):
            if b[i - 1] == "S" and b[i] in ("N", "W", "-"):
                if i + H < P:
                    pb["losta"] += 1; pb_ticker[t] += 1
                    if any(b[j] == "S" for j in range(i + 1, i + H + 1)):
                        pb["recovery"] += 1
                    else:
                        pb["no_recovery"] += 1
                else:
                    pb["olosta_censurerade"] += 1

    # ---- per panel: hur manga av topp-30 har definierad path
    per_panel_tis, per_panel_dr2 = [], []
    tis_S, obs_per_state = [], Counter()
    tv, sv, dv, rv = [], [], [], []
    for pi, dt in enumerate(dts):
        n_tis = n_dr2 = 0
        for t in tick:
            if bands[t][pi] == "-": continue
            obs_per_state[bands[t][pi]] += 1
            if bands[t][pi] == "S":
                tis_S.append(tis[t][pi])
                if tis[t][pi] >= 2: n_tis += 1
                if pi >= 2 and bands[t][pi - 2] != "-": n_dr2 += 1
            if pi >= 2 and bands[t][pi - 2] != "-":
                tv.append(tis[t][pi]); sv.append(sc[(t, dt)])
                dv.append(rk[(t, dts[pi - 2])] - rk[(t, dt)]); rv.append(rk[(t, dt)])
        per_panel_tis.append(n_tis); per_panel_dr2.append(n_dr2)

    obs_ticker = [sum(1 for i in range(P) if bands[t][i] != "-") for t in tick]
    res = {"paneler": P, "tickers": len(tick), "rankobservationer": n_rank,
           "transitioner_totalt": int(sum(trans.values())),
           "transitionsmatris": {f"{a}->{b}": c for (a, b), c in sorted(trans.items())},
           "obs_per_state": dict(obs_per_state),
           "obs_per_ticker": kv(obs_ticker),
           "transitioner_per_ticker": kv(list(trans_per_ticker.values())),
           "tickers_med_transitioner": len(trans_per_ticker),
           "loptal_state_runs_totalt": loptal,
           "time_in_state_i_S": kv(tis_S),
           "pullback_recovery": pb,
           "pullback_per_ticker": kv(list(pb_ticker.values())),
           "tickers_med_minst1_lost_pullback": len(pb_ticker),
           "tickers_med_minst3_losta_pullbacks": sum(1 for v in pb_ticker.values() if v >= 3),
           "topp30_med_TIS_minst2_per_panel": kv(per_panel_tis),
           "topp30_med_DR2_per_panel": kv(per_panel_dr2),
           "redundans_spearman": {"TIS_mot_score": round(sp(tv, sv), 4),
                                  "TIS_mot_rank": round(sp(tv, rv), 4),
                                  "DR2_mot_score": round(sp(dv, sv), 4),
                                  "DR2_mot_rank": round(sp(dv, rv), 4), "n": len(tv)},
           "effektivt_urval": {"kluster_ticker": len(trans_per_ticker),
                               "kluster_state_runs": loptal,
                               "raw_transitioner": int(sum(trans.values()))}}
    print(f"=== {namn} === {P} paneler, {len(tick)} tickers")
    print(f"  rankobservationer {n_rank}, transitioner {res['transitioner_totalt']}, "
          f"state-runs {loptal}")
    print(f"  obs per state: {dict(obs_per_state)}")
    print(f"  transitionsmatris: {res['transitionsmatris']}")
    print(f"  obs/ticker {res['obs_per_ticker']}")
    print(f"  transitioner/ticker {res['transitioner_per_ticker']}")
    print(f"  time-in-state i S: {res['time_in_state_i_S']}")
    print(f"  pullbacks: {pb}")
    print(f"  pullbacks/ticker {res['pullback_per_ticker']}, "
          f"tickers >=1 lost {res['tickers_med_minst1_lost_pullback']}, "
          f">=3 losta {res['tickers_med_minst3_losta_pullbacks']}")
    print(f"  topp-30 med TIS>=2 per panel: {res['topp30_med_TIS_minst2_per_panel']}")
    print(f"  topp-30 med DR2 per panel:    {res['topp30_med_DR2_per_panel']}")
    print(f"  REDUNDANS {res['redundans_spearman']}")
    print()
    return res


ut = {"version": "STATE_PATH_FEASIBILITY_V1",
      "obs": "Deskriptiv rakning pa transitionsniva. Inga framtida avkastningar lasta.",
      "state_space": "S rank<=30, N 31-60, W >60", "recovery_horisont_paneler": H,
      "fonster": {}}
for namn, F in (("2020_2026", S.F26), ("2014_2019", S.F19)):
    ut["fonster"][namn] = analys(F, namn)
OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
print("skrivet:", OUT)
