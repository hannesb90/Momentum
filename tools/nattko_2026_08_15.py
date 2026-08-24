"""NATTKÖ 2026-08-15 — REPLIKATIONSPRÖVNING PÅ 2014-2019

Varje test i kön prövar en familj som redan är avfärdad eller svagt stödd på
2020-2026, nu mot det oberoende fönstret 2014-2019. Frågan per test är alltid
densamma: REPLIKERAR avslaget?

Detta är inte ett nytt svep i samma trädgård. Det är omprövning på ny data, och
utfallet är informativt åt båda hållen — ett avslag som replikerar är starkare
än ett avslag, och ett avslag som INTE replikerar är en varningsflagga för att
den ursprungliga slutsatsen var fönsterberoende.

Varje test skriver eget resultat direkt när det är klart. Loggen uppdateras
löpande så att avbrott inte förstör det som hunnit köras.

Kör: /opt/momentum/venv/bin/python tools/nattko_2026_08_15.py
"""
from __future__ import annotations
import json, math, sys, time, traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import h1419_motor as M

UT = Path("/home/hannesb/momentum_v2/research_k/nattko_2026_08_15")
UT.mkdir(parents=True, exist_ok=True)
LOGG = UT / "_logg.md"
N_SEEDS = 200


def logga(txt):
    with open(LOGG, "a", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt, flush=True)


def spara(namn, data):
    (UT / f"{namn}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))


def placebo(bygg_sparr, N, n_seeds=N_SEEDS):
    """bygg_sparr(rng) -> kwargs till sim. Returnerar fördelningen av delta mot baslinjen."""
    bas = M.stat(M.sim(N=N))["cagr"]
    ut = []
    for s in range(n_seeds):
        rng = np.random.default_rng(41000 + s)
        ut.append(M.stat(M.sim(N=N, **bygg_sparr(rng)))["cagr"] - bas)
    a = np.array(ut)
    return {"median": round(float(np.median(a)), 4), "p5": round(float(np.percentile(a, 5)), 4),
            "p95": round(float(np.percentile(a, 95)), 4), "sd": round(float(a.std(ddof=1)), 4)}


# ---------------------------------------------------------------- Q1
def q1_ablation():
    univ = M.universum_likavikt()
    steg = [("A_ren_rank_likavikt", dict(sma=False, viktning="lika", fr=False, tak=None)),
            ("B_plus_SMA200", dict(sma=True, viktning="lika", fr=False, tak=None)),
            ("C_plus_invvol", dict(sma=True, viktning="invvol1.5", fr=False, tak=None)),
            ("D_plus_tak_waterfill", dict(sma=True, viktning="invvol1.5", fr=False, tak="waterfill")),
            ("E_plus_FR", dict(sma=True, viktning="invvol1.5", fr=True, tak="waterfill")),
            ("F_legacytak_H0", dict(sma=True, viktning="invvol1.5", fr=True, tak="legacy"))]
    res = {"referens_universum": M.stat(univ), "per_N": {}}
    for N in (20, 30):
        res["per_N"][str(N)] = {}
        for namn, kw in steg:
            nets = M.sim(N=N, **kw)
            res["per_N"][str(N)][namn] = {**M.stat(nets), **M.boot(nets, univ)}
    a20 = res["per_N"]["20"]
    res["nedbrytning_N20_pp"] = {
        "universum": round(res["referens_universum"]["cagr"] * 100, 2),
        "urval": round((a20["A_ren_rank_likavikt"]["cagr"] - res["referens_universum"]["cagr"]) * 100, 2),
        "SMA200": round((a20["B_plus_SMA200"]["cagr"] - a20["A_ren_rank_likavikt"]["cagr"]) * 100, 2),
        "invvol": round((a20["C_plus_invvol"]["cagr"] - a20["B_plus_SMA200"]["cagr"]) * 100, 2),
        "tak": round((a20["D_plus_tak_waterfill"]["cagr"] - a20["C_plus_invvol"]["cagr"]) * 100, 2),
        "FR": round((a20["E_plus_FR"]["cagr"] - a20["D_plus_tak_waterfill"]["cagr"]) * 100, 2)}
    return res, ("Ablation: urval {urval:+.2f} pp, SMA {SMA200:+.2f}, invvol {invvol:+.2f}, "
                 "tak {tak:+.2f}, FR {FR:+.2f}").format(**res["nedbrytning_N20_pp"])


# ---------------------------------------------------------------- Q2
def q2_nsvep():
    bas = M.sim(N=30)
    res = {}
    for N in (10, 15, 20, 25, 30):
        nets = M.sim(N=N)
        res[f"N{N}"] = {**M.stat(nets), **(M.boot(nets, bas) if N != 30 else {})}
    b = max((k for k in res if k != "N30"), key=lambda k: res[k].get("delta_cagr", -9))
    return res, (f"N-svep: bästa {b} med {res[b]['delta_cagr']:+.2%} "
                 f"KI [{res[b]['ki_lo']:+.2%},{res[b]['ki_hi']:+.2%}] t {res[b]['t_parvis']}")


# ---------------------------------------------------------------- Q3
def q3_rankniva():
    band = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 40), (41, 60)]
    res = {}
    for lo, hi in band:
        r1, r3 = [], []
        for pi, dt in enumerate(M.PANELER):
            for r in M.RANKNINGAR[dt][lo - 1:hi]:
                k = r["kod"]
                if not M.sma_ok(k, dt):
                    continue
                r1.append(M.RET.get((k, dt), 0.0))
                tot = 1.0
                for j in range(pi, min(pi + 3, len(M.PANELER))):
                    tot *= 1 + M.RET.get((k, M.PANELER[j]), 0.0)
                r3.append(tot - 1)
        a1, a3 = np.array(r1), np.array(r3)
        res[f"{lo}-{hi}"] = {"n": len(a1), "avk_1p": round(float(a1.mean()), 4),
                             "median_1p": round(float(np.median(a1)), 4),
                             "avk_3p": round(float(a3.mean()), 4),
                             "t_1p": round(float(a1.mean() / (a1.std(ddof=1) / math.sqrt(len(a1)))), 2)}
    t5, t2630 = res["1-5"]["avk_1p"], res["26-30"]["avk_1p"]
    return res, (f"Rankniva: band 1-5 {t5:+.2%}/panel mot band 26-30 {t2630:+.2%} — "
                 f"{'26-30 slår 1-5, replikerar' if t2630 > t5 else '1-5 slår 26-30, replikerar EJ'}")


# ---------------------------------------------------------------- Q4
def q4_rankforandring():
    res = {}
    for lag in (1, 3, 6):
        xs, ys = [], []
        for pi in range(lag, len(M.PANELER) - 1):
            dt, fore = M.PANELER[pi], M.PANELER[pi - lag]
            for r in M.RANKNINGAR[dt][:60]:
                k = r["kod"]
                r0, r1 = M.RANK.get((k, fore)), M.RANK.get((k, dt))
                if r0 and r1:
                    xs.append(r0 - r1)                # positivt = klättrat
                    ys.append(M.RET.get((k, dt), 0.0))
        x, y = np.array(xs, dtype=float), np.array(ys)
        ic = float(np.corrcoef(x, y)[0, 1])
        res[f"lag_{lag}p"] = {"n": len(x), "ic": round(ic, 4),
                              "t": round(float(ic * math.sqrt((len(x) - 2) / max(1e-12, 1 - ic ** 2))), 2)}
    return res, "Rankförändring: IC " + ", ".join(
        f"{k} {v['ic']:+.4f} (t {v['t']})" for k, v in res.items())


# ---------------------------------------------------------------- Q5
def q5_lat_rida():
    res = {}
    for N in (15, 20, 30):
        a, b = M.sim(N=N, lat_rida=True), M.sim(N=N)
        res[f"N{N}"] = {"lat_rida": M.stat(a), "viktas_om": M.stat(b), **M.boot(a, b)}
    return res, "Låt vinnarna rida: " + ", ".join(
        f"N{n.replace('N','')} {v['delta_cagr']:+.2%} (t {v['t_parvis']})" for n, v in res.items())


# ---------------------------------------------------------------- Q6
def q6_ombalansering():
    bas = M.sim(N=30, ombalansering=2)
    res = {}
    for omb in (1, 2, 3, 4):
        nets = M.sim(N=30, ombalansering=omb)
        res[f"var_{omb*4}e_vecka"] = {**M.stat(nets), **(M.boot(nets, bas) if omb != 2 else {})}
    return res, "Ombalansering: " + ", ".join(
        f"{k} {v['cagr']:.2%}" for k, v in res.items())


# ---------------------------------------------------------------- Q7
def q7_viktning():
    bas = M.sim(N=30, viktning="invvol1.5")
    res = {}
    for v in ("lika", "invvol1.0", "invvol1.5", "invvol2.0"):
        nets = M.sim(N=30, viktning=v)
        res[v] = {**M.stat(nets), **(M.boot(nets, bas) if v != "invvol1.5" else {})}
    return res, "Viktning: " + ", ".join(f"{k} {v['cagr']:.2%}" for k, v in res.items())


# ---------------------------------------------------------------- Q8
def q8_utgangsregler():
    bas = M.sim(N=30)
    basc = M.stat(bas)["cagr"]
    res = {"baslinje": M.stat(bas), "spärr": {}, "snav_utgang": {}}
    for gr in (35, 40, 50):
        nets = M.sim(N=30, exit_rank=gr)
        res["spärr"][f"behall_till_{gr}"] = {**M.stat(nets), **M.boot(nets, bas)}
    # placebo: samma antal extra behållna, slumpvalda
    pl = placebo(lambda rng: dict(exit_rank=40, rng=rng), 30, n_seeds=100)
    res["placebo_exit40"] = pl
    res["riktig_exit40_delta"] = res["spärr"]["behall_till_40"]["delta_cagr"]
    return res, (f"Utgångsspärr: behåll till 40 ger {res['riktig_exit40_delta']:+.2%}, "
                 f"placebo median {pl['median']:+.2%} [{pl['p5']:+.2%},{pl['p95']:+.2%}]")


# ---------------------------------------------------------------- Q9
def q9_tva_fonster():
    res = {"baslinjer": {"N10": M.stat(M.sim(N=10)), "N20": M.stat(M.sim(N=20)),
                         "N30": M.stat(M.sim(N=30))}}
    rut = {}
    for N, lo, hi, H in [(10, 1, 10, 10), (10, 1, 10, 20), (10, 1, 10, 30),
                         (10, 11, 20, 30), (10, 15, 25, 30), (10, 15, 25, 40),
                         (20, 1, 10, 30), (20, 1, 15, 30), (20, 1, 15, 40)]:
        nets = M.sim(N=N, kopband=(lo, hi), exit_rank=H)
        ref = M.sim(N=N)
        rut[f"N{N}_kop{lo}-{hi}_H{H}"] = {**M.stat(nets), **M.boot(nets, ref)}
    res["rutnat"] = rut
    b = max(rut, key=lambda k: rut[k]["delta_cagr"])
    return res, (f"Två fönster: bästa {b} {rut[b]['delta_cagr']:+.2%} "
                 f"KI [{rut[b]['ki_lo']:+.2%},{rut[b]['ki_hi']:+.2%}] t {rut[b]['t_parvis']}")


# ---------------------------------------------------------------- Q10
def q10_svansstruktur():
    h0 = M.sim(N=30)
    univ = M.universum_likavikt()
    w = float(np.prod(1 + h0))
    b3 = np.sort(h0)[-3:]
    utan3 = float(np.prod(1 + np.array([x for x in h0 if x not in b3])))
    # hypotetiska innehav per rankband, utgång vid rank > 30
    band_res = {}
    for lo, hi in [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30)]:
        upptagen, tot = defaultdict(lambda: -1), []
        for pi, dt in enumerate(M.PANELER):
            for r in M.RANKNINGAR[dt][lo - 1:hi]:
                k = r["kod"]
                if pi <= upptagen[k] or not M.sma_ok(k, dt):
                    continue
                banor, j = [], pi
                while j < len(M.PANELER):
                    rk = M.RANK.get((k, M.PANELER[j]))
                    if rk is None or rk > 30:
                        break
                    banor.append(M.RET.get((k, M.PANELER[j]), 0.0))
                    j += 1
                if banor:
                    upptagen[k] = j - 1
                    tot.append(float(np.prod([1 + x for x in banor]) - 1))
        a = np.array(tot)
        band_res[f"{lo}-{hi}"] = {"n": len(a), "medel": round(float(a.mean()), 4),
                                  "median": round(float(np.median(a)), 4)}
    x = np.array([M.RET.get((r["kod"], dt), 0.0)
                  for dt in M.PANELER for r in M.RANKNINGAR[dt][:30]])
    res = {"h0": M.stat(h0), "universum": M.stat(univ),
           "andel_uppgang_fran_3_basta_paneler": round(1 - (utan3 - 1) / (w - 1), 3) if w > 1 else None,
           "topp30_panelobs": {"n": len(x), "medel": round(float(x.mean()), 4),
                               "median": round(float(np.median(x)), 4),
                               "andel_negativa": round(float(np.mean(x < 0)), 3)},
           "hypotetiska_innehav_per_band": band_res}
    return res, (f"Svans: topp-30-panelobs medel {res['topp30_panelobs']['medel']:+.2%} mot "
                 f"median {res['topp30_panelobs']['median']:+.2%}; "
                 f"{res['andel_uppgang_fran_3_basta_paneler']:.0%} av uppgången ur 3 bästa paneler")


KO = [("Q1_ablation", q1_ablation), ("Q2_nsvep", q2_nsvep), ("Q3_rankniva", q3_rankniva),
      ("Q4_rankforandring", q4_rankforandring), ("Q5_lat_rida", q5_lat_rida),
      ("Q6_ombalansering", q6_ombalansering), ("Q7_viktning", q7_viktning),
      ("Q8_utgangsregler", q8_utgangsregler), ("Q9_tva_fonster", q9_tva_fonster),
      ("Q10_svansstruktur", q10_svansstruktur)]


def main():
    logga(f"\n# Nattkö 2026-08-15 — replikationsprövning på 2014-2019\n")
    h0, u = M.verifiera_baslinje()
    logga(f"Baslinjekontroll OK: H0 {h0:.2%}, universum {u:.2%} "
          f"(förregistrering H1419_PREREG_FREEZE_V2)\n")
    sammanfattning = {}
    for namn, fn in KO:
        t0 = time.time()
        try:
            res, rad = fn()
            spara(namn, {"test": namn, "kord_utc": datetime.now(timezone.utc)
                         .replace(microsecond=0).isoformat(),
                         "sekunder": round(time.time() - t0, 1), "resultat": res})
            sammanfattning[namn] = rad
            logga(f"- **{namn}** ({time.time()-t0:.0f}s) — {rad}")
        except Exception as e:
            logga(f"- **{namn}** MISSLYCKADES: {type(e).__name__}: {e}")
            spara(namn + "_FEL", {"fel": str(e), "trace": traceback.format_exc()})
    spara("_sammanfattning", sammanfattning)
    logga(f"\nKön klar {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}")


if __name__ == "__main__":
    main()
