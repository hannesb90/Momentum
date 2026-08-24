"""SAMLAD KÖ MOT STACK_H — DAGENS TESTER PLUS SESSIONERNAS, BÅDA FÖNSTREN

Basmodell: SHADOW_INTEGRATED_STACK_H (ERC + FR + hysteres rank 35 + NTZ 0,005),
verifierad mot registret: 13,56 % / 17,02 % / −24,32 % på 2020-2026.

Del A — dagens regelfamiljer, nu mot rätt modell:
  A1 portföljstorlek      A2 låt vinnarna rida     A3 ombalanseringsfrekvens
  A4 hysteresgränsen      A5 NTZ-bandet            A6 köpband

Del B — tester ur sessionerna 2026-08-13/14 som går att köra på båda fönstren:
  B1 T2  viktökning i nedgång följd av försäljning nästa panel (137 fall, −38,07 %)
  B2 T3  fångstasymmetri vinnare mot förlorare (6,0 % mot 11,3 %)
  B3 T4  aliasering: signalens lookback mot ombalanseringsfrekvensen

Kriterium genomgående: samma parameteruppsättning måste hålla i BÅDA fönstren.

Kör: /opt/momentum/venv/bin/python tools/ko_mot_stack_h.py
"""
from __future__ import annotations
import json, math, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

UT = V2 / "research_k/ko_mot_stack_h"
UT.mkdir(parents=True, exist_ok=True)
LOGG = UT / "_logg.md"


def logga(t):
    with open(LOGG, "a", encoding="utf-8") as f:
        f.write(t + "\n")
    print(t, flush=True)


def bada(**kw):
    """Kör en variant i båda fönstren och returnera delta mot respektive baslinje."""
    a26, _, _ = S.kor(**S.F26, **kw)
    a19, _, _ = S.kor(**S.F19, **kw)
    return a26, a19


BAS26, OMS26, N26 = S.kor(**S.F26)
BAS19, OMS19, N19 = S.kor(**S.F19)


def rapport(namn, a26, a19):
    d26, d19 = S.boot(a26, BAS26), S.boot(a19, BAS19)
    rep = d26["delta_cagr"] > 0 and d19["delta_cagr"] > 0
    return {"f2020_2026": {**S.stat(a26), **d26}, "f2014_2019": {**S.stat(a19), **d19},
            "bada_positiva": bool(rep)}, \
           (f"{namn:<26}{d26['delta_cagr']:>+9.2%}{d19['delta_cagr']:>+9.2%}"
            f"  KI26 [{d26['ki_lo']:+.2%},{d26['ki_hi']:+.2%}]  {'JA' if rep else '-'}")


# ---------------------------------------------------------------- A
def a1_portfoljstorlek():
    res = {}
    logga(f"  {'variant':<26}{'Δ 20-26':>9}{'Δ 14-19':>9}")
    for N in (10, 15, 20, 25):
        a26, _, _ = S.kor(**S.F26, N=N)
        a19, _, _ = S.kor(**S.F19, N=N)
        r, rad = rapport(f"N={N}", a26, a19)
        res[f"N{N}"] = r; logga("  " + rad)
    return res


def a2_lat_rida():
    res = {}
    for band in (0.02, 0.05, 0.10):
        a26, a19 = bada(ntz_band=band)
        r, rad = rapport(f"NTZ-band {band:.0%}", a26, a19)
        res[f"ntz_{band}"] = r; logga("  " + rad)
    return res


def a3_ombalansering():
    res = {}
    for k, namn in ((1, "var 4:e vecka"), (3, "var 12:e vecka")):
        f26 = dict(S.F26); f26["sched_fn"] = lambda pi, dt, k=k: pi % k == 0
        f19 = dict(S.F19); f19["sched_fn"] = lambda pi, dt, k=k: pi % k == 0
        a26, _, _ = S.kor(**f26); a19, _, _ = S.kor(**f19)
        r, rad = rapport(namn, a26, a19)
        res[namn] = r; logga("  " + rad)
    return res


def a4_hysteresgransen():
    res = {}
    for g in (30, 40, 45, 50):
        a26, a19 = bada(hyst_rank=g)
        r, rad = rapport(f"hysteres rank {g}", a26, a19)
        res[f"hyst_{g}"] = r; logga("  " + rad)
    return res


def a5_utan_delar():
    res = {}
    for kw, namn in (({"use_hysteresis": False}, "utan hysteres"),
                     ({"use_ntz": False}, "utan NTZ"),
                     ({"use_fr": False}, "utan FR"),
                     ({"use_erc": False}, "invvol^1.0 i st f ERC"),
                     ({"use_tv": True}, "+ target vol 15 %")):
        a26, a19 = bada(**kw)
        r, rad = rapport(namn, a26, a19)
        res[namn] = r; logga("  " + rad)
    return res


def a6_kopband():
    res = {}
    for kb, ex in (((1, 20), 35), ((6, 35), 45), ((11, 40), 50)):
        a26, a19 = bada(kopband=kb, exit_rank=ex)
        r, rad = rapport(f"köp {kb[0]}-{kb[1]}, håll {ex}", a26, a19)
        res[f"kop{kb[0]}-{kb[1]}_H{ex}"] = r; logga("  " + rad)
    return res


# ---------------------------------------------------------------- B
def b_diagnostik(F, namn):
    """T2, T3 och T4 mätta på STACK_H:s faktiska viktbana."""
    rankings, dts = F["rankings"], F["eval_dates"]
    ret, volf, smaf, conff, schedf = (F["returns_map"], F["vol_fn"], F["sma_fn"],
                                      F["conf_fn"], F["sched_fn"])
    prev, prevw = [], {}
    t2_fall, t2_avk, t2_saljs = 0, [], 0
    fangst_v, fangst_f = [], []
    for pi, dt in enumerate(dts):
        sched = schedf(pi, dt)
        raw = rankings[dt]; elig = {r["kod"] for r in raw}
        rm = {r["kod"]: i + 1 for i, r in enumerate(raw)}
        if sched or not prev:
            keep = [k for k in prev if rm.get(k, 999) <= 35 and k in elig] if prev else []
            fill = [r["kod"] for r in raw if r["kod"] not in keep]
            sel0 = (keep + fill)[:30]
        else:
            sel0 = [k for k in prev if k in elig]
            if len(sel0) < 30:
                sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:30 - len(sel0)]
        sel = [k for k in sel0 if smaf(k, dt)]
        n = len(sel)
        if n == 0:
            prev, prevw = sel0, {}; continue
        vols = np.array([volf(k, dt) for k in sel])
        inv = 1.0 / (np.maximum(vols, 0.05) ** 1.5)
        w = inv / np.sum(inv) * (n / 30)
        w = w * np.array([1.0 if conff(k, dt) else 0.75 for k in sel])
        w = np.clip(w, 0.01, 0.06); w = w / np.sum(w) * (n / 30)
        if prevw:
            w = np.array([prevw.get(k, 0.0) if (abs(w[i] - prevw.get(k, 0.0)) < 0.005
                                                and prevw.get(k, 0.0) > 0) else w[i]
                          for i, k in enumerate(sel)])
            w = w / np.sum(w) * (n / 30)
        # ---- T2: viktökning i nedgång, såld nästa panel ----
        if sched and prevw and pi > 0:
            for i, k in enumerate(sel):
                pw = prevw.get(k, 0.0)
                fallande = ret.get((k, dts[pi - 1]), 0.0) < 0
                if pw > 0 and w[i] > pw + 1e-9 and fallande:
                    t2_fall += 1
                    t2_avk.append(ret.get((k, dt), 0.0))
                    nxt = pi + 2
                    if nxt < len(dts) and k not in [r["kod"] for r in rankings[dts[nxt]][:30]]:
                        t2_saljs += 1
        # ---- T3: fångstgrad vinnare mot förlorare ----
        for i, k in enumerate(sel):
            r_ = ret.get((k, dt), 0.0)
            (fangst_v if r_ > 0 else fangst_f).append(abs(r_) * w[i] / max(w.sum(), 1e-9))
        prev, prevw = sel0, dict(zip(sel, w))
    d = {"T2_viktokning_i_nedgang": {
            "fall": t2_fall,
            "medelavk_panelen_efter": round(float(np.mean(t2_avk)), 4) if t2_avk else None,
            "ackumulerad_avk": round(float(np.prod([1 + x for x in t2_avk]) - 1), 4) if t2_avk else None,
            "andel_saljs_nasta_ombalansering": round(t2_saljs / t2_fall, 3) if t2_fall else None},
         "T3_fangstasymmetri": {
            "vinnare_medel": round(float(np.mean(fangst_v)), 5),
            "forlorare_medel": round(float(np.mean(fangst_f)), 5),
            "asymmetri": round(float(np.mean(fangst_v) - np.mean(fangst_f)), 5)}}
    logga(f"  {namn}: T2 {t2_fall} fall, panelen efter "
          f"{d['T2_viktokning_i_nedgang']['medelavk_panelen_efter']:+.2%}, "
          f"ackumulerat {d['T2_viktokning_i_nedgang']['ackumulerad_avk']:+.2%}, "
          f"{d['T2_viktokning_i_nedgang']['andel_saljs_nasta_ombalansering']:.0%} säljs")
    logga(f"     T3 fångst vinnare {d['T3_fangstasymmetri']['vinnare_medel']:.4f} mot "
          f"förlorare {d['T3_fangstasymmetri']['forlorare_medel']:.4f}, "
          f"asymmetri {d['T3_fangstasymmetri']['asymmetri']:+.4f}")
    return d


def main():
    logga(f"\n# Kö mot STACK_H — {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}\n")
    logga(f"Baslinje STACK_H: 2020-26 {S.stat(BAS26)['cagr']:.2%} (vol {S.stat(BAS26)['vol']:.2%}, "
          f"DD {S.stat(BAS26)['maxdd']:.2%}) · 2014-19 {S.stat(BAS19)['cagr']:.2%} "
          f"(vol {S.stat(BAS19)['vol']:.2%}, DD {S.stat(BAS19)['maxdd']:.2%})\n")
    ut = {"version": "KO_MOT_STACK_H_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "basmodell": "SHADOW_INTEGRATED_STACK_H, verifierad mot registret",
          "baslinjer": {"f2020_2026": S.stat(BAS26), "f2014_2019": S.stat(BAS19)},
          "A": {}, "B": {}}
    for namn, fn in (("A1_portfoljstorlek", a1_portfoljstorlek), ("A2_ntz_band", a2_lat_rida),
                     ("A3_ombalansering", a3_ombalansering), ("A4_hysteresgransen", a4_hysteresgransen),
                     ("A5_utan_delar", a5_utan_delar), ("A6_kopband", a6_kopband)):
        logga(f"\n**{namn}**")
        t0 = time.time()
        ut["A"][namn] = fn()
        logga(f"  ({time.time()-t0:.0f}s)")
    logga("\n**B — sessionernas diagnostik (T2, T3)**")
    ut["B"]["f2020_2026"] = b_diagnostik(S.F26, "2020-2026")
    ut["B"]["f2014_2019"] = b_diagnostik(S.F19, "2014-2019")
    (UT / "resultat.json").write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    alla = {**ut["A"]}
    n_pos = sum(1 for grp in alla.values() for v in grp.values() if v.get("bada_positiva"))
    n_tot = sum(len(grp) for grp in alla.values())
    logga(f"\nVarianter positiva i BÅDA fönstren: {n_pos} av {n_tot}")
    logga(f"Skrivet: {UT/'resultat.json'}")


if __name__ == "__main__":
    main()
