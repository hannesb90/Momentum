"""SAMMANSTÄLLNING — VAD REPLIKERAR ÖVER BÅDA FÖNSTREN

Lägger 2020-2026 (ablation_svansen_results.json) bredvid 2014-2019
(nattko Q1) steg för steg, och avgör per egenskap om den replikerar.

Regeln för "replikerar": samma tecken i båda fönstren. Storleken får skilja —
det är riktningen som är påståendet.

Kör: /opt/momentum/venv/bin/python tools/nattko_sammanstallning.py
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
UT = V2 / "research_k/nattko_2026_08_15/Q11_sammanstallning.json"

STEG = [("A_ren_rank_likavikt", "Ren rank, likavikt"),
        ("B_plus_SMA200", "+ SMA200-grind"),
        ("C_plus_invvol", "+ invers volvikt"),
        ("D_plus_tak_waterfill", "+ vikttak"),
        ("E_plus_FR", "+ FR-overlay"),
        ("F_stackD_legacytak", "= H0 / Stack D")]
STEG_2014 = {"F_stackD_legacytak": "F_legacytak_H0"}


def main():
    a2026 = json.loads((V2 / "research_k/ablation_svansen_results.json").read_text())
    a2019 = json.loads((V2 / "research_k/nattko_2026_08_15/Q1_ablation.json").read_text())["resultat"]

    ut = {"version": "NATTKO_SAMMANSTALLNING_V1",
          "run_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
          "regel": "replikerar = samma tecken i båda fönstren",
          "per_N": {}}

    for N in ("20", "30"):
        rader, marginal = [], []
        f26, f19 = a2026["per_N"][N], a2019["per_N"][N]
        for nyckel, etikett in STEG:
            k19 = STEG_2014.get(nyckel, nyckel)
            v26, v19 = f26.get(nyckel), f19.get(k19)
            if not v26 or not v19:
                continue
            rader.append({"steg": etikett,
                          "cagr_2020_2026": v26["cagr"], "cagr_2014_2019": v19["cagr"],
                          "vol_2020_2026": v26["vol"], "vol_2014_2019": v19["vol"],
                          "maxdd_2020_2026": v26["maxdd"], "maxdd_2014_2019": v19["maxdd"],
                          "sharpe_2020_2026": v26["sharpe"], "sharpe_2014_2019": v19["sharpe"]})
        for i in range(1, len(rader)):
            f, e = rader[i - 1], rader[i]
            d = {"steg": e["steg"]}
            for matt, tecken_bra in (("cagr", +1), ("vol", -1), ("maxdd", +1), ("sharpe", +1)):
                a = e[f"{matt}_2020_2026"] - f[f"{matt}_2020_2026"]
                b = e[f"{matt}_2014_2019"] - f[f"{matt}_2014_2019"]
                d[matt] = {"d_2020_2026": round(a, 4), "d_2014_2019": round(b, 4),
                           "replikerar": bool(a * b > 0),
                           "riktning_bra_i_bada": bool(a * tecken_bra > 0 and b * tecken_bra > 0)}
            marginal.append(d)
        ut["per_N"][N] = {"nivaer": rader, "marginaleffekter": marginal}

    UT.write_text(json.dumps(ut, ensure_ascii=False, indent=1))

    for N in ("20", "30"):
        print(f"\n{'='*96}\nN={N}   NIVÅER")
        print(f"{'steg':<24}{'CAGR 20-26':>11}{'CAGR 14-19':>11}{'DD 20-26':>10}"
              f"{'DD 14-19':>10}{'Sh 20-26':>10}{'Sh 14-19':>10}")
        for r in ut["per_N"][N]["nivaer"]:
            print(f"{r['steg']:<24}{r['cagr_2020_2026']:>11.2%}{r['cagr_2014_2019']:>11.2%}"
                  f"{r['maxdd_2020_2026']:>10.2%}{r['maxdd_2014_2019']:>10.2%}"
                  f"{r['sharpe_2020_2026']:>10.3f}{r['sharpe_2014_2019']:>10.3f}")
        print(f"\nN={N}   MARGINALEFFEKT PER ADD-ON (replikerar = samma tecken)")
        print(f"{'add-on':<24}{'ΔCAGR':>22}{'ΔmaxDD':>22}{'ΔSharpe':>22}")
        for m in ut["per_N"][N]["marginaleffekter"]:
            def f(x):
                s = "OK " if x["replikerar"] else "-- "
                return f"{s}{x['d_2020_2026']*100:+6.2f}/{x['d_2014_2019']*100:+6.2f}"
            print(f"{m['steg']:<24}{f(m['cagr']):>22}{f(m['maxdd']):>22}"
                  f"{'OK ' if m['sharpe']['replikerar'] else '-- '}"
                  f"{m['sharpe']['d_2020_2026']:+6.3f}/{m['sharpe']['d_2014_2019']:+6.3f}")
    print(f"\nSkrivet: {UT}")


if __name__ == "__main__":
    main()
