"""TVÅ ÅTGÄRDER: y52-VAKTEN OCH PLACEBOBANDET PÅ ETT LUGNT FÖNSTER

DEL 1 — y52-vakten.
y52 (target_fwd52w) är framåtblickande och ligger i varje rankrad. Den ska
ligga där: den är MÅLVARIABELN som IC-mätningarna använder
(research_l_long_horizon_head_to_head.py:417 beräknar ic52 mot den). Att ta
bort den vore att förstöra fyra revisionsskript.

Skyddet är i stället ett invariantest: kryptera y52 med slumptal och verifiera
att rankningen blir BITIDENTISK. Blir den inte det har någon börjat läsa
framtiden i en poängberäkning, och testet faller.

DEL 2 — placebobandet på 2014-2019.
±2,4 pp mättes på 2020-2026, ett ovanligt svansdrivet fönster (87,9 % av
uppgången ur tre paneler, negativ medianpanel). 2014-2019 var bredare (31,4 %,
medianpanel +1,05 %). Om bandet är smalare där är flera av de sju "avgjorda"
familjerna faktiskt avgörbara i ett lugnt fönster i stället för bara obesvarade.

Kör: /opt/momentum/venv/bin/python tools/vakt_y52_och_placebobandet.py
"""
from __future__ import annotations
import importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
OUT = V2 / "research_k/vakt_y52_och_placebobandet_results.json"
sys.path.insert(0, str(V2 / "tools"))


def del1_y52_vakt():
    spec = importlib.util.spec_from_file_location("h2h", V2 / "tools/research_all_6_models_head_to_head.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    core_df, prices, terminal = m.load_data()

    r1 = m.derive_h0_scores(core_df, prices)
    sig1 = {dt: [x["kod"] for x in rows] for dt, rows in r1.items()}
    poang1 = {dt: [round(x["score"], 10) for x in rows] for dt, rows in r1.items()}

    # kryptera y52 — rankningen får inte röra sig en millimeter
    df2 = core_df.copy()
    rng = np.random.default_rng(20260815)
    df2["y52"] = rng.permutation(df2["y52"].values)
    r2 = m.derive_h0_scores(df2, prices)
    sig2 = {dt: [x["kod"] for x in rows] for dt, rows in r2.items()}
    poang2 = {dt: [round(x["score"], 10) for x in rows] for dt, rows in r2.items()}

    lika_ordning = sig1 == sig2
    lika_poang = poang1 == poang2
    avvikande = [dt for dt in sig1 if sig1[dt] != sig2.get(dt)]
    return {"rankordning_identisk": lika_ordning, "poang_identiska": lika_poang,
            "n_paneler": len(sig1), "avvikande_paneler": avvikande[:10],
            "dom": "PASS — rankningen är oberoende av y52" if (lika_ordning and lika_poang)
                   else "FAIL — y52 påverkar rankningen, look-ahead i poängvägen",
            "notering": "y52 SKA finnas kvar i rankraderna: den är målvariabeln för "
                        "IC-mätningarna. Vakten skyddar mot att den används som feature."}


def del2_placebobandet():
    import h1419_motor as M
    M.verifiera_baslinje()
    res = {}
    for N in (20, 30):
        bas = M.stat(M.sim(N=N))["cagr"]
        # placebo: samma konstruktion men n slumpvalda köp per ombalansering
        pl = []
        for s in range(300):
            rng = np.random.default_rng(52000 + s)
            pl.append(M.stat(M.sim(N=N, rng=rng))["cagr"] - bas)
        a = np.array(pl)
        res[f"N{N}"] = {"baslinje_cagr": round(bas, 4),
                        "median": round(float(np.median(a)), 4),
                        "p5": round(float(np.percentile(a, 5)), 4),
                        "p95": round(float(np.percentile(a, 95)), 4),
                        "sd": round(float(a.std(ddof=1)), 4),
                        "bandbredd_pp": round(float(np.percentile(a, 95) - np.percentile(a, 5)) * 100, 2)}
    return res


def main():
    ut = {"version": "VAKT_Y52_OCH_PLACEBOBANDET_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    print("DEL 1 — y52-vakten")
    ut["y52_vakt"] = del1_y52_vakt()
    v = ut["y52_vakt"]
    print(f"  {v['dom']}")
    print(f"  rankordning identisk: {v['rankordning_identisk']}, "
          f"poäng identiska: {v['poang_identiska']}, paneler: {v['n_paneler']}")

    print("\nDEL 2 — placebobandet på 2014-2019")
    ut["placebobandet_2014_2019"] = del2_placebobandet()
    for k, d in ut["placebobandet_2014_2019"].items():
        print(f"  {k}: median {d['median']:+.2%}, 5-95 % [{d['p5']:+.2%}, {d['p95']:+.2%}], "
              f"sd {d['sd']:.2%}  ->  bandbredd {d['bandbredd_pp']:.2f} pp")
    ut["jamforelse"] = {
        "2020_2026": "sd 1,4-1,8 pp, 5-95 % ≈ ±2,4 pp (bandbredd ~4,8 pp)",
        "kommentar": "Om bandet är smalare 2014-2019 beror det på att fönstret var mindre "
                     "svansdrivet: 31,4 % av uppgången ur tre bästa paneler mot 87,9 %, "
                     "och positiv medianpanel mot negativ."}
    OUT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))
    print(f"\nSkrivet: {OUT}")


if __name__ == "__main__":
    main()
