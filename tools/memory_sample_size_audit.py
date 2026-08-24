"""STOCK-SPECIFIC MOMENTUM MEMORY — LEVERANS C + E + A-KVANTIFIERING

Detta är INGET prediction-test. Inga framtida avkastningar läses. Skriptet
räknar episoder i H0:s egen rankninghistorik och mäter hur mycket historik som
finns tillgänglig PIT vid varje beslutspanel.

EPISODDEFINITION (ex ante, byggd på H0:s EGEN gräns, inga uppfunna prisnivåer)
  STARK state    rank <= 30 i H0:s rankning (H0:s egen urvalsgräns)
  SVAG state     rank > 30 eller ej rankbar den panelen
  episod         maximal sammanhängande följd av STARK-paneler
  episodstart    STARK vid T, SVAG vid T-1
  försvagning    SVAG vid T, STARK vid T-1  -> episoden AVSLUTAS här
  återinträde    en senare episodstart för samma ticker
  recoverytid    antal paneler från försvagning till nästa episodstart

PIT-REGEL  vid panel T får endast episoder som AVSLUTATS strikt före T räknas.
           En pågående episod bidrar med noll. Detta kontrolleras explicit.

SIGNAL vs ÄGANDE  definitionen använder enbart rankning, aldrig innehav. Ett
           bolag kan ha en episod utan att någonsin ha fått plats i portföljen.

HYSTERESKÄNSLIGHET  allt räknas även med gräns 35 (STACK_H:s behållningsgräns)
           för att visa hur definitionsberoende episodräkningen är.

Kör: /opt/momentum/venv/bin/python tools/memory_sample_size_audit.py
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
sys.path.insert(0, str(V2 / "tools"))
import stack_h_motor as S

OUT = V2 / "research_k/memory_sample_size_audit.json"


def rankmatris(F):
    dts = F["eval_dates"]
    rk, sc = {}, {}
    for dt in dts:
        for i, r in enumerate(F["rankings"][dt]):
            rk[(r["kod"], dt)] = i + 1
            sc[(r["kod"], dt)] = r["score"]
    tickers = sorted({k for k, _ in rk})
    return dts, rk, sc, tickers


def episoder(dts, rk, tickers, gr):
    """Returnerar per ticker en lista av (start_idx, slut_idx) för AVSLUTADE
    episoder, samt pågående episodstart om sådan finns vid fönstrets slut."""
    ut = {}
    for t in tickers:
        stark = [(rk.get((t, dt), 10**6) <= gr) for dt in dts]
        eps, i = [], 0
        while i < len(dts):
            if stark[i]:
                j = i
                while j + 1 < len(dts) and stark[j + 1]:
                    j += 1
                avslutad = (j + 1 < len(dts))     # episoden slutade INOM fönstret
                eps.append((i, j, avslutad))
                i = j + 1
            else:
                i += 1
        ut[t] = eps
    return ut


def kvant(x):
    a = np.asarray(x, dtype=float)
    if len(a) == 0:
        return None
    return {"n": len(a), "median": round(float(np.median(a)), 3),
            "q25": round(float(np.percentile(a, 25)), 3),
            "q75": round(float(np.percentile(a, 75)), 3),
            "medel": round(float(a.mean()), 3), "max": round(float(a.max()), 3)}


def andelar(x):
    a = np.asarray(x)
    n = max(1, len(a))
    return {f"andel_{k}": round(float((a == k).mean()), 4) for k in (0, 1, 2, 3)} | \
           {"andel_5plus": round(float((a >= 5).mean()), 4),
            "andel_minst_2": round(float((a >= 2).mean()), 4),
            "andel_minst_3": round(float((a >= 3).mean()), 4)}


def analys(F, namn):
    dts, rk, sc, tickers = rankmatris(F)
    res = {"paneler": len(dts), "forsta_panel": dts[0], "sista_panel": dts[-1],
           "tickers": len(tickers)}

    for gr in (30, 35):
        eps = episoder(dts, rk, tickers, gr)
        # ---- episodlangder och gap (deskriptivt, hela fonstret)
        langder = [j - i + 1 for t in tickers for i, j, a in eps[t] if a]
        gap = []
        for t in tickers:
            e = [x for x in eps[t]]
            for a, b in zip(e, e[1:]):
                gap.append(b[0] - a[1] - 1)
        antal_per_ticker = [sum(1 for x in eps[t] if x[2]) for t in tickers]
        aktiva = [n for n in antal_per_ticker if n > 0]

        # ---- PIT: antal AVSLUTADE tidigare episoder vid varje panel
        pit = defaultdict(dict)
        for t in tickers:
            slut = sorted(j for i, j, a in eps[t] if a)
            for pi in range(len(dts)):
                # avslutad strikt fore T betyder att SVAG-panelen j+1 < pi
                pit[t][pi] = sum(1 for j in slut if j + 1 < pi)

        # kontroll: en pagaende episod far aldrig raknas
        brott = 0
        for t in tickers:
            for i, j, a in eps[t]:
                for pi in range(i, min(j + 2, len(dts))):
                    if pit[t][pi] > sum(1 for x, y, z in eps[t] if z and y + 1 < pi):
                        brott += 1

        pop = {"alla": [], "topp60": [], "topp30": []}
        for pi, dt in enumerate(dts):
            for t in tickers:
                r = rk.get((t, dt))
                if r is None:
                    continue
                v = pit[t][pi]
                pop["alla"].append(v)
                if r <= 60:
                    pop["topp60"].append(v)
                if r <= 30:
                    pop["topp30"].append(v)

        # ---- A-kvantifiering: korrelerar minnet med det H0 redan vet?
        rho_score, rho_rank = [], []
        for pi, dt in enumerate(dts):
            rows = [(rk[(t, dt)], sc[(t, dt)], pit[t][pi])
                    for t in tickers if (t, dt) in rk]
            if len(rows) < 30:
                continue
            m = np.array([x[2] for x in rows], dtype=float)
            if m.std() == 0:
                continue
            rr = np.array([x[0] for x in rows], dtype=float)
            ss = np.array([x[1] for x in rows], dtype=float)

            def sp(a, b):
                ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
                return float(np.corrcoef(ra, rb)[0, 1])
            rho_rank.append(sp(m, rr)); rho_score.append(sp(m, ss))

        res[f"grans_{gr}"] = {
            "episoder_avslutade_totalt": len(langder),
            "episodlangd_paneler": kvant(langder),
            "gap_mellan_episoder_paneler": kvant(gap),
            "avslutade_episoder_per_ticker_hela_fonstret": kvant(antal_per_ticker),
            "tickers_med_minst_en_episod": len(aktiva),
            "pit_kontroll_brott": brott,
            "pit_tidigare_episoder": {
                k: {**kvant(v), **andelar(v)} for k, v in pop.items() if v},
            "korr_minne_mot_H0": {
                "spearman_mot_score_medel": round(float(np.mean(rho_score)), 4),
                "spearman_mot_rank_medel": round(float(np.mean(rho_rank)), 4),
                "n_paneler": len(rho_score)},
        }
    return res


ut = {"version": "MEMORY_SAMPLE_SIZE_V1",
      "obs": "Deskriptiv rakning. Inga framtida avkastningar lasta.",
      "fonster": {}}
for namn, F in (("2020_2026", S.F26), ("2014_2019", S.F19)):
    ut["fonster"][namn] = analys(F, namn)
    r = ut["fonster"][namn]
    print(f"=== {namn} ===  {r['paneler']} paneler {r['forsta_panel']}..{r['sista_panel']}, "
          f"{r['tickers']} tickers")
    for gr in (30, 35):
        g = r[f"grans_{gr}"]
        print(f"  --- STARK = rank <= {gr} ---")
        print(f"  avslutade episoder totalt: {g['episoder_avslutade_totalt']}, "
              f"tickers med >=1: {g['tickers_med_minst_en_episod']}")
        print(f"  episodlangd (paneler): {g['episodlangd_paneler']}")
        print(f"  gap mellan episoder:   {g['gap_mellan_episoder_paneler']}")
        print(f"  episoder/ticker hela fonstret: {g['avslutade_episoder_per_ticker_hela_fonstret']}")
        print(f"  PIT-kontroll brott: {g['pit_kontroll_brott']}")
        for k, v in g["pit_tidigare_episoder"].items():
            print(f"  PIT tidigare episoder [{k}]: median {v['median']:.0f} "
                  f"q25 {v['q25']:.0f} q75 {v['q75']:.0f} max {v['max']:.0f} | "
                  f"0:{v['andel_0']:.1%} 1:{v['andel_1']:.1%} 2:{v['andel_2']:.1%} "
                  f"3:{v['andel_3']:.1%} 5+:{v['andel_5plus']:.1%} | "
                  f">=2:{v['andel_minst_2']:.1%} >=3:{v['andel_minst_3']:.1%}")
        c = g["korr_minne_mot_H0"]
        print(f"  Spearman minne mot H0-score {c['spearman_mot_score_medel']:+.4f}, "
              f"mot rank {c['spearman_mot_rank_medel']:+.4f} ({c['n_paneler']} paneler)")
    print()

OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
print(f"skrivet: {OUT}")
