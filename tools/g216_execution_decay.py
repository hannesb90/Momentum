"""G216 — SIGNAL-TO-EXECUTION DECAY PÅ CANONICAL LOCKED H0

Förregistrerad i Batch 11 (docs/QUANT_TERM_H0_GAP_LEDGER.md).

HYPOTES  netto-CAGR faller MINDRE ÄN 1,0 procentenhet från T+1 till T+5 i vart
         och ett av de två fönstren.
FALSIFIERAS  om T+5 ligger >= 1,0 pp under T+1 i något fönster.

Endast exekveringsdagen ändras. Score, rankning, urval, N=30, schema,
likaviktsåterställning och kostnadsmodell är oförändrade och beräknas ur
beslutsdatumet T — de kan därför inte se information som uppstått efter T.

DE TVÅ FRYSTA MOTORERNA HAR OLIKA EXITKONVENTION. Det är ett befintligt
förhållande som inte får ändras här, så generaliseringen görs inuti varje
motors egen konvention:

  2020-2026 (H.execution_engine)   entry = p(T)+1        exit = p(T_nästa)+1
  2014-2019 (M._bygg_retmap)       entry = p(T)+1        exit = p(T_nästa)

där p(d) = index för sista stängning <= d. Regeln för arm T+n är i BÅDA fallen
densamma: förskjut båda ändpunkterna (n-1) handelsdagar framåt. n=1 ger då per
konstruktion tillbaka den frysta motorn. Det verifieras element för element mot
S.RET26 och M.RET innan något simuleras.

T+n räknas i HANDELSDAGAR i den frysta prisserien, inte kalenderdagar. Helger
och helgdagar finns inte i serien, så T+1 är alltid nästa faktiska handelsdag.

Kör: /opt/momentum/venv/bin/python tools/g216_execution_decay.py
"""
from __future__ import annotations
import bisect, json, math, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S
import h1419_motor as M

OUT = V2 / "research_k/g216_execution_decay.json"
COST, PPY, N = 0.002, 13, 30
LAGS = [1, 2, 3, 5]
GRANS = 0.01          # förregistrerad falsifieringsgräns, 1,0 pp

PRIS26 = S._prices
TERM26 = S._term
ALLD = S.ALLD
_DS26 = {k: [r["d"] for r in rs] for k, rs in PRIS26.items()}
_AD26 = {k: [r["adj"] for r in rs] for k, rs in PRIS26.items()}


# ---------------------------------------------------------------- returns_map
def ret_2026(n):
    """Generaliserar H.execution_engine. n=1 ska ge exakt S.RET26."""
    nxt = dict(zip(ALLD, ALLD[1:]))
    ut, ej = {}, {}
    for kod in PRIS26:
        ds, adj = _DS26[kod], _AD26[kod]
        for dt in ALLD:
            nd = nxt.get(dt)
            i = bisect.bisect_right(ds, dt) - 1 + n
            if nd is None or i >= len(ds) or i < 0 or ds[i] > nd:
                ut[(kod, dt)], ej[(kod, dt)] = 0.0, True
                continue
            j = bisect.bisect_right(ds, nd) - 1 + n
            if j < len(ds):
                ut[(kod, dt)], ej[(kod, dt)] = adj[j] / adj[i] - 1, False
            else:
                ev = TERM26.get(kod)
                if ev and ds[i] <= ev["event_date"] <= nd:
                    ut[(kod, dt)], ej[(kod, dt)] = adj[-1] / adj[i] - 1, False
                else:
                    ut[(kod, dt)], ej[(kod, dt)] = 0.0, True
    return ut, ej


def ret_1419(n):
    """Generaliserar M._bygg_retmap. n=1 ska ge exakt M.RET."""
    P = M.PANELER
    ut, ej = {}, {}
    for k, (ds, v) in M.SERIE.items():
        for a in range(len(P) - 1):
            i = int(np.searchsorted(ds, np.datetime64(P[a]), side="right")) - 1 + n
            j = int(np.searchsorted(ds, np.datetime64(P[a + 1]), side="right")) - 1 + (n - 1)
            if 0 <= i <= j < len(ds) and v[i] > 0:
                ut[(k, P[a])], ej[(k, P[a])] = float(v[j] / v[i] - 1.0), False
            else:
                ut[(k, P[a])], ej[(k, P[a])] = 0.0, True
        ut[(k, P[-1])], ej[(k, P[-1])] = 0.0, True
    return ut, ej


# ---------------------------------------------------------------- simulering
def kor(F, ret, ej, schedf=None):
    """Canonical locked H0 = G29 arm A, ordagrant. Endast ret/ej byts."""
    dts = F["eval_dates"]
    schedf = schedf or F["sched_fn"]
    w, nets, turns = {}, [], []
    intrade, utgangar, ejexek, hallna, sel_hist = 0, 0, 0, 0, []
    for pi, dt in enumerate(dts):
        raw = F["rankings"][dt]
        if schedf(pi, dt) or not w:
            sel = [r["kod"] for r in raw][:N]
            mal = {k: 1.0 / N for k in sel}
            turn = sum(abs(mal.get(k, 0.0) - w.get(k, 0.0))
                       for k in set(mal) | set(w)) / 2.0
            intrade += len([k for k in sel if k not in w])
            utgangar += len([k for k in w if k not in mal])
            sel_hist.append((dt, tuple(sel)))
        else:
            mal = dict(w)
            turn = 0.0
        r = {k: ret.get((k, dt), 0.0) for k in mal}
        ejexek += sum(1 for k in mal if ej.get((k, dt), True))
        hallna += len(mal)
        nets.append(float(sum(mal[k] * r[k] for k in mal)) - COST * turn)
        turns.append(turn)
        ny = {k: mal[k] * (1 + r[k]) for k in mal}
        s_ = sum(ny.values())
        w = {k: v / s_ for k, v in ny.items()} if s_ > 0 else {}
    return (np.array(nets), np.array(turns),
            {"intraden": intrade, "utgangar": utgangar, "byten": intrade + utgangar,
             "ej_exekverbara_innehav": ejexek, "innehav_totalt": hallna,
             "andel_ej_exekverbara": round(ejexek / max(1, hallna), 5)},
            sel_hist)


def rapport(nets, turns, meta):
    st = S.stat(nets)
    return {**st, "oms_ar": round(float(np.mean(turns)) * PPY, 4), **meta}


# ---------------------------------------------------------------- kontroller
def kontroll_reproduktion():
    """Kontroll 1+2: n=1 måste ge de frysta motorernas returns_map exakt."""
    ut = {}
    r26, _ = ret_2026(1)
    d26 = [abs(r26[k] - v) for k, v in S.RET26.items() if k in r26]
    saknas26 = [k for k in S.RET26 if k not in r26] + [k for k in r26 if k not in S.RET26]
    ut["2020_2026"] = {"n_nycklar": len(S.RET26), "max_abs_diff": max(d26) if d26 else None,
                       "nyckelavvikelser": len(saknas26)}
    r19, _ = ret_1419(1)
    d19 = [abs(r19[k] - v) for k, v in M.RET.items() if k in r19]
    saknas19 = [k for k in M.RET if k not in r19] + [k for k in r19 if k not in M.RET]
    ut["2014_2019"] = {"n_nycklar": len(M.RET), "max_abs_diff": max(d19) if d19 else None,
                       "nyckelavvikelser": len(saknas19)}
    ut["identisk"] = all(v["max_abs_diff"] == 0.0 and v["nyckelavvikelser"] == 0
                         for v in (ut["2020_2026"], ut["2014_2019"]))
    return ut


def kontroll_lookahead(n):
    """Kontroll 4: entryn för arm n får aldrig ligga före T+1:s entry, och
    signalen får aldrig se ett pris efter beslutsdatum T."""
    fel = 0
    nxt = dict(zip(ALLD, ALLD[1:]))
    for kod in list(PRIS26)[:400]:
        ds = _DS26[kod]
        for dt in ALLD:
            nd = nxt.get(dt)
            if nd is None:
                continue
            p = bisect.bisect_right(ds, dt) - 1
            if p + n < len(ds) and ds[p + n] <= dt:
                fel += 1                       # entry på eller före beslutsdagen
            if p >= 0 and ds[p] > dt:
                fel += 1                       # signalen ser pris efter T
    return fel


# ---------------------------------------------------------------- huvudkörning
def main():
    res = {"version": "G216_V1", "run_utc": datetime.now(timezone.utc)
           .replace(microsecond=0).isoformat(),
           "hypotes": "netto-CAGR faller < 1,0 pp fran T+1 till T+5 i BADA fonstren",
           "falsifieringsgrans_pp": 1.0, "lags": LAGS,
           "lag_enhet": "handelsdagar i den frysta prisserien"}

    print("KONTROLL 1+2 — reproducerar n=1 de frysta motorerna?")
    rep = kontroll_reproduktion()
    res["kontroll_reproduktion"] = rep
    for f, v in (("2020_2026", rep["2020_2026"]), ("2014_2019", rep["2014_2019"])):
        print(f"  {f}: {v['n_nycklar']} nycklar, max|diff| {v['max_abs_diff']}, "
              f"nyckelavvikelser {v['nyckelavvikelser']}")
    if not rep["identisk"]:
        print("  AVBRYTER: n=1 ar inte identisk med frysta motorn.")
        return
    print("  IDENTISK — arm T+1 ar canonical per konstruktion.\n")

    print("KONTROLL 4 — look-ahead")
    res["kontroll_lookahead"] = {f"T+{n}": kontroll_lookahead(n) for n in LAGS}
    print(f"  {res['kontroll_lookahead']}\n")

    fonster = {}
    for namn, F, builder in (("2020_2026", S.F26, ret_2026),
                             ("2014_2019", S.F19, ret_1419)):
        print(f"=== {namn} ===")
        armar, nets_map, selsig = {}, {}, {}
        for n in LAGS:
            rm, ej = builder(n)
            nets, turns, meta, sh = kor(F, rm, ej)
            armar[f"T+{n}"] = rapport(nets, turns, meta)
            nets_map[n] = nets
            selsig[n] = tuple(sh)
            a = armar[f"T+{n}"]
            print(f"  T+{n}: CAGR {a['cagr']:+.2%}  vol {a['vol']:.2%}  "
                  f"maxDD {a['maxdd']:.2%}  Sharpe {a['sharpe']}  "
                  f"oms {a['oms_ar']:.1%}  byten {a['byten']}  "
                  f"ej exek {a['ej_exekverbara_innehav']}")

        # Kontroll 3: identiska namnuppsattningar over samtliga armar
        bas = selsig[1]
        avvik = {f"T+{n}": sum(1 for x, y in zip(bas, selsig[n]) if x[1] != y[1])
                 for n in LAGS}
        print(f"  KONTROLL 3 namnavvikelser mot T+1: {avvik}")

        b = armar["T+1"]["cagr"]
        delta = {f"T+{n}": round(armar[f"T+{n}"]["cagr"] - b, 4) for n in LAGS}
        d51 = delta["T+5"]
        # monotoni: ar forsamringen ungefar monoton over 1->2->3->5?
        seq = [armar[f"T+{n}"]["cagr"] for n in LAGS]
        steg = [round(seq[i + 1] - seq[i], 4) for i in range(len(seq) - 1)]
        monoton = all(s <= 0 for s in steg) or all(s >= 0 for s in steg)
        bs = S.boot(nets_map[5], nets_map[1])

        # deskriptiv fasspridning, ENDAST T+1, ingen ny executionvariant
        rm1, ej1 = builder(1)
        if namn == "2020_2026":
            alt = lambda pi, dt: ALLD.index(dt) % 2 != S._ANCH
        else:
            alt = lambda pi, dt: pi % 2 == 1
        na, ta, ma, _ = kor(F, rm1, ej1, schedf=alt)
        fas = {"fas_kontrakt": armar["T+1"]["cagr"], "fas_alternativ": S.stat(na)["cagr"],
               "spann_pp": round(abs(armar["T+1"]["cagr"] - S.stat(na)["cagr"]) * 100, 2)}
        print(f"  FAS (deskriptiv, T+1): kontrakt {fas['fas_kontrakt']:+.2%}  "
              f"alternativ {fas['fas_alternativ']:+.2%}  spann {fas['spann_pp']:.2f} pp")

        print(f"  DELTA mot T+1: {delta}")
        print(f"  stegvis: {steg}   ungefar monoton: {monoton}")
        print(f"  bootstrap T+5 - T+1: {bs['delta_cagr']:+.2%} "
              f"KI [{bs['ki_lo']:+.2%}, {bs['ki_hi']:+.2%}] t {bs['t']}")
        print(f"  FALSIFIERAD i detta fonster: {d51 <= -GRANS}\n")

        fonster[namn] = {"armar": armar, "delta_mot_T1": delta, "stegvis_delta": steg,
                         "ungefar_monoton": bool(monoton), "namnavvikelser": avvik,
                         "bootstrap_T5_minus_T1": bs, "fasspridning_deskriptiv": fas,
                         "falsifierad": bool(d51 <= -GRANS)}

    res["fonster"] = fonster
    fal = [f for f, v in fonster.items() if v["falsifierad"]]
    res["hypotes_utfall"] = "FALSIFIERAD" if fal else "STAR SIG"
    res["falsifierade_fonster"] = fal
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"HYPOTES: {res['hypotes_utfall']}  {fal if fal else ''}")
    print(f"skrivet: {OUT}")


if __name__ == "__main__":
    main()
