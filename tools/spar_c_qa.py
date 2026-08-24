"""Spar C, steg 3: PIT-/lackage-QA och coverage-QA pa bade CORE och
CORE+FUNDAMENTA. Verifierar, gissar inte. Ingen radata andras.

PIT/lackage:
  1. Panel-nycklar (kod, panel_date) identiska mellan target/CORE/CORE+FUND.
  2. Varje CORE-features prisdatum <= panel_date (empirisk, inte bara
     litad pa konstruktionen) - rekonstruerar direkt fran VALIDATED-priserna.
  3. Varje fundamenta-rads report_date <= panel_date, alltid.
  4. target_table anvander ENDAST datum > panel_date (target-fonstret).
  5. Ingen kolumn i feature-panelerna innehaller "target"/framtida avkastning.
  6. Slumpmassigt stickprov (inte bara aggregat) manuellt aterrraknat fran
     radata for ett urval rader, per featuretyp.

Coverage: tackning per ar och instrument, per falt. Extremvarden FLAGGAS
(percentilbaserat), klipps aldrig.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

V2 = Path("/home/hannesb/momentum_v2")
PANELS = V2 / "panels"
PRICES = V2 / "validated/prices/prices_validated.json"
R12 = V2 / "validated/fundamentals/fundamentals_r12_validated.json"
OUT = V2 / "docs/probes/spar_c_qa.json"

random.seed(42)


def main() -> None:  # noqa: C901
    target = json.loads((PANELS / "target_table.json").read_text(encoding="utf-8"))
    core = json.loads((PANELS / "core_panel.json").read_text(encoding="utf-8"))
    fund = json.loads((PANELS / "core_fundamenta_panel.json").read_text(encoding="utf-8"))
    priser = json.loads(PRICES.read_text(encoding="utf-8"))
    r12 = json.loads(R12.read_text(encoding="utf-8"))
    terminal_events = json.loads((V2 / "validated/terminal_events.json").read_text(encoding="utf-8"))

    rep = {"production": False}

    # ================================================================
    # 1. NYCKELKONSISTENS
    # ================================================================
    print("=" * 100)
    print("1. NYCKELKONSISTENS — (kod, panel_date) identiska mellan target/CORE/FUND")
    print("=" * 100)
    target_nycklar = {(k, r["panel_date"]) for k, rs in target.items() for r in rs}
    core_nycklar = {(r["kod"], r["panel_date"]) for r in core}
    fund_nycklar = {(r["kod"], r["panel_date"]) for r in fund}
    print(f"  target: {len(target_nycklar)}  CORE: {len(core_nycklar)}  "
          f"CORE+FUND: {len(fund_nycklar)}")
    print(f"  target == CORE: {target_nycklar == core_nycklar}")
    print(f"  CORE == CORE+FUND: {core_nycklar == fund_nycklar}")
    rep["nyckelkonsistens"] = {
        "n_target": len(target_nycklar), "n_core": len(core_nycklar),
        "n_fund": len(fund_nycklar),
        "target_eq_core": target_nycklar == core_nycklar,
        "core_eq_fund": core_nycklar == fund_nycklar}
    assert target_nycklar == core_nycklar == fund_nycklar, "NYCKLAR SKILJER — STOPP"

    # ================================================================
    # 2. INGA TARGET-/FRAMTIDSKOLUMNER I FEATUREPANELERNA
    # ================================================================
    print("\n" + "=" * 100)
    print("2. INGA TARGET-KOLUMNER LÄCKER IN I FEATUREPANELERNA")
    print("=" * 100)
    core_kolumner = set(core[0].keys())
    fund_kolumner = set(fund[0].keys())
    farliga = {"target", "fwd", "forward", "framtid"}
    träff_core = [c for c in core_kolumner if any(f in c.lower() for f in farliga)]
    träff_fund = [c for c in fund_kolumner if any(f in c.lower() for f in farliga)]
    print(f"  misstänkta kolumnnamn i CORE: {träff_core or 'inga'}")
    print(f"  misstänkta kolumnnamn i CORE+FUND: {träff_fund or 'inga'}")
    assert not träff_core and not träff_fund
    rep["inga_target_kolumner"] = {"core": träff_core, "fund": träff_fund}

    # ================================================================
    # 3. EMPIRISK PIT-KONTROLL — CORE (återräkning från VALIDATED-priser)
    # ================================================================
    print("\n" + "=" * 100)
    print("3. EMPIRISK PIT-KONTROLL — CORE (independent återräkning, stickprov)")
    print("=" * 100)
    stickprov = random.sample(core, min(400, len(core)))
    fel = []
    for rad in stickprov:
        kod, pdate = rad["kod"], rad["panel_date"]
        if rad["price_date"] > pdate:
            fel.append(("price_date_efter_panel_date", kod, pdate, rad["price_date"]))
            continue
        serie = priser.get(kod, [])
        priser_pd = {r["d"]: r["adj"] for r in serie}
        # price_date måste finnas i den faktiska serien och vara <= panel_date
        if rad["price_date"] not in priser_pd:
            fel.append(("price_date_saknas_i_serie", kod, pdate, rad["price_date"]))
            continue
        # mom_4w återräknad oberoende
        if rad.get("mom_4w") is not None:
            mål = (date.fromisoformat(pdate) - __import__("datetime").timedelta(weeks=4))
            kandidater = [r for r in serie if r["d"] <= mål.isoformat()]
            if kandidater:
                a4 = kandidater[-1]["adj"]
                a0 = priser_pd[rad["price_date"]]
                förväntat = a0 / a4 - 1
                if abs(förväntat - rad["mom_4w"]) > 1e-6:
                    fel.append(("mom_4w_avviker", kod, pdate, förväntat, rad["mom_4w"]))
        # inget prisdatum i mom-beräkningen får vara > panel_date (by construction, verifieras
        # indirekt via ovan eftersom serie redan filtrerats <= mål <= panel_date)
    print(f"  stickprov: {len(stickprov)} rader | avvikelser: {len(fel)}")
    for f in fel[:10]:
        print("   ", f)
    rep["empirisk_pit_core"] = {"n_stickprov": len(stickprov), "n_fel": len(fel),
                                "exempel": fel[:10]}
    assert len(fel) == 0, "PIT-FEL I CORE — STOPP"

    # ================================================================
    # 4. EMPIRISK PIT-KONTROLL — FUNDAMENTA (report_date <= panel_date, alltid)
    # ================================================================
    print("\n" + "=" * 100)
    print("4. EMPIRISK PIT-KONTROLL — FUNDAMENTA (samtliga rader, ej stickprov)")
    print("=" * 100)
    la_fel = [r for r in fund if r["has_fundamenta"]
              and r["fundamenta_report_date"] > r["panel_date"]]
    print(f"  rader med has_fundamenta=True: {sum(1 for r in fund if r['has_fundamenta'])}")
    print(f"  look-ahead (report_date > panel_date): {len(la_fel)}")
    for f in la_fel[:5]:
        print("   ", f["kod"], f["panel_date"], f["fundamenta_report_date"])
    rep["empirisk_pit_fund"] = {"n_look_ahead": len(la_fel)}
    assert len(la_fel) == 0, "LOOK-AHEAD I FUNDAMENTA — STOPP"

    # stickprov: är report_date verkligen den SENASTE ≤ panel_date i R12-tabellen?
    r12_by_kod = defaultdict(list)
    for r in r12:
        r12_by_kod[r["kod"]].append(r["report_date"])
    for kod in r12_by_kod:
        r12_by_kod[kod].sort()
    fel2 = []
    stickprov2 = random.sample([r for r in fund if r["has_fundamenta"]], 300)
    for rad in stickprov2:
        datum = r12_by_kod.get(rad["kod"], [])
        giltiga = [d for d in datum if d <= rad["panel_date"]]
        if not giltiga:
            fel2.append(("ingen_giltig_rapport_trots_has_fundamenta", rad["kod"], rad["panel_date"]))
            continue
        if max(giltiga) != rad["fundamenta_report_date"]:
            fel2.append(("ej_senaste_rapport_anvand", rad["kod"], rad["panel_date"],
                         max(giltiga), rad["fundamenta_report_date"]))
    print(f"  stickprov (senaste-rapport-kontroll): {len(stickprov2)} | avvikelser: {len(fel2)}")
    rep["empirisk_pit_fund_senaste"] = {"n_stickprov": len(stickprov2), "n_fel": len(fel2),
                                        "exempel": fel2[:10]}
    assert len(fel2) == 0

    # ================================================================
    # 5. TARGET — FULLSTÄNDIG ÅTERRÄKNING (C-4-fix, CODEX_SECOND_OPINION_V2_ABC.md)
    # Tidigare kontrollerade denna sektion ENDAST att price_date <= panel_date
    # (entrypunkten). Den räknade ALDRIG om det faktiska target_fwd52w-värdet
    # eller verifierade terminalklassningen (target_typ) - ett fel i C-2:s
    # censurerings-/delisting-return-logik hade passerat "target PIT passed"
    # helt obemärkt. Nu: full oberoende återräkning från VALIDATED-priser för
    # samtliga rader, plus verifiering av terminalklassningen.
    # ================================================================
    print("\n" + "=" * 100)
    print("5. TARGET — full återräkning från VALIDATED-priser (samtliga rader)")
    print("=" * 100)
    HORISONT_DAGAR = 52 * 7
    MAX_LAG_DAGAR = 8
    sista_global = max(date.fromisoformat(rader[-1]["d"]) for rader in priser.values())
    fel3, fel_varde, fel_typ = [], [], []
    n_kontrollerade = 0
    for kod, rader in target.items():
        serie = priser.get(kod, [])
        if not serie:
            fel3.append(("instrument_saknas_i_priser", kod))
            continue
        datum_lista = [r["d"] for r in serie]
        adj_by_d = {r["d"]: r["adj"] for r in serie}
        serie_slut = date.fromisoformat(datum_lista[-1])
        terminal = terminal_events.get(kod)
        for r in rader:
            n_kontrollerade += 1
            pdate = r["panel_date"]
            if r["price_date"] > pdate:
                fel3.append(("price_date_efter_panel_date", kod, pdate, r["price_date"]))
                continue
            if r["price_date"] not in adj_by_d:
                fel3.append(("price_date_saknas_i_serie", kod, pdate, r["price_date"]))
                continue
            a0 = adj_by_d[r["price_date"]]
            mål = date.fromisoformat(pdate) + timedelta(days=HORISONT_DAGAR)
            if mål > serie_slut:
                # Canonical 52v-target måste alltid vara null vid kort horisont.
                if r["target_fwd52w"] is not None:
                    fel_typ.append(("kort_terminalutfall_i_52v_target", kod, pdate))
                if r["target_typ"] is not None:
                    fel_typ.append(("typ_satt_pa_null_target", kod, pdate, r["target_typ"]))
                terminal_giltig = terminal and terminal["event_date"] >= r["price_date"]
                if r.get("terminal_return") is not None:
                    if not terminal_giltig:
                        fel_typ.append(("terminal_return_utan_verifierad_event", kod, pdate))
                    else:
                        förv = adj_by_d[datum_lista[-1]] / a0 - 1.0
                        if abs(förv - r["terminal_return"]) > 1e-6:
                            fel_varde.append(("terminal_return_avviker", kod, pdate,
                                              förv, r["terminal_return"]))
                        if r.get("terminal_event_date") != terminal["event_date"]:
                            fel_typ.append(("terminaldatum_avviker", kod, pdate))
                elif terminal_giltig:
                    fel_typ.append(("verifierad_terminal_saknar_separat_utfall", kod, pdate))
            else:
                # ska vara forward_52w med korrekt atterraknat varde
                kandidater = [x for x in serie if x["d"] <= mål.isoformat()]
                if not kandidater:
                    continue
                t1_förv = kandidater[-1]["d"]
                lag = (mål - date.fromisoformat(t1_förv)).days
                if lag > MAX_LAG_DAGAR:
                    if r["target_fwd52w"] is not None or r["target_typ"] is not None:
                        fel_typ.append(("forward_utan_pris_inom_fast_tolerans", kod, pdate, lag))
                    continue
                a1_förv = adj_by_d[t1_förv]
                förv = a1_förv / a0 - 1.0
                if r["target_fwd52w"] is None:
                    continue  # instrumentspecifik saknad prispunkt, redan täckt av byggloggen
                if r["target_typ"] != "forward_52w":
                    fel_typ.append(("fel_typ_forvantad_forward", kod, pdate, r["target_typ"]))
                if abs(förv - r["target_fwd52w"]) > 1e-6:
                    fel_varde.append(("forward_target_avviker", kod, pdate,
                                      förv, r["target_fwd52w"]))
    print(f"  {n_kontrollerade} rader återräknade | PIT-fel: {len(fel3)} | "
          f"värdefel: {len(fel_varde)} | typfel: {len(fel_typ)}")
    for f in (fel3[:5] + fel_varde[:5] + fel_typ[:5]):
        print("   ", f)
    rep["target_pit"] = {"n_kontrollerade": n_kontrollerade, "n_pit_fel": len(fel3),
                         "n_vardefel": len(fel_varde), "n_typfel": len(fel_typ),
                         "exempel_pit": fel3[:10], "exempel_varde": fel_varde[:10],
                         "exempel_typ": fel_typ[:10]}
    assert len(fel3) == 0, "PIT-FEL I TARGET — STOPP"
    assert len(fel_varde) == 0, "TARGET-VÄRDE AVVIKER FRÅN ÅTERRÄKNING — STOPP"
    assert len(fel_typ) == 0, "TARGET-TERMINALKLASSNING FEL — STOPP"

    # ================================================================
    # 6. COVERAGE — per fält, år, instrument
    # ================================================================
    print("\n" + "=" * 100)
    print("6. COVERAGE — CORE (per fält, totalt och per år)")
    print("=" * 100)
    core_fält = [k for k in core[0] if k not in
                 ("kod", "panel_date", "price_date", "membership_verified", "membership_basis")]
    cov = {}
    for f in core_fält:
        vals = [r[f] for r in core]
        n_ok = sum(1 for v in vals if v is not None)
        per_år = Counter()
        per_år_ok = Counter()
        for r in core:
            år = r["panel_date"][:4]
            per_år[år] += 1
            if r[f] is not None:
                per_år_ok[år] += 1
        cov[f] = {"tackning_pct": 100 * n_ok / len(core),
                  "per_ar": {y: round(100 * per_år_ok[y] / per_år[y], 1) for y in sorted(per_år)}}
        print(f"  {f:20s} {cov[f]['tackning_pct']:>6.1f} %  "
              f"per år: {cov[f]['per_ar']}")
    rep["coverage_core"] = cov

    print("\n" + "=" * 100)
    print("6b. COVERAGE — FUNDAMENTA (per fält, totalt och per år)")
    print("=" * 100)
    fund_fält = [k for k in fund[0] if k not in
                ("kod", "panel_date", "price_date", "membership_verified", "membership_basis", "has_fundamenta",
                 "fundamenta_report_date", "fundamenta_days_since")]
    covf = {}
    for f in fund_fält:
        vals = [r[f] for r in fund]
        n_ok = sum(1 for v in vals if v is not None)
        per_år, per_år_ok = Counter(), Counter()
        for r in fund:
            år = r["panel_date"][:4]
            per_år[år] += 1
            if r[f] is not None:
                per_år_ok[år] += 1
        covf[f] = {"tackning_pct": 100 * n_ok / len(fund),
                   "per_ar": {y: round(100 * per_år_ok[y] / per_år[y], 1) for y in sorted(per_år)}}
        print(f"  {f:22s} {covf[f]['tackning_pct']:>6.1f} %  per år: {covf[f]['per_ar']}")
    rep["coverage_fundamenta"] = covf

    n_instr_med = len({r["kod"] for r in fund if r["has_fundamenta"]})
    n_instr_tot = len({r["kod"] for r in fund})
    print(f"\n  instrument med ≥1 fundamenta-rad: {n_instr_med}/{n_instr_tot} "
          f"({100*n_instr_med/n_instr_tot:.1f} %)")
    rep["instrument_med_fundamenta"] = {"n": n_instr_med, "n_totalt": n_instr_tot}

    # ================================================================
    # 7. EXTREMVÄRDEN — FLAGGAS, ALDRIG KLIPPS
    # ================================================================
    print("\n" + "=" * 100)
    print("7. EXTREMVÄRDEN — p1/p99 per fält (endast rapporterat, inget klippt)")
    print("=" * 100)
    extremrep = {}
    for namn, data, fält in (("CORE", core, core_fält), ("FUND", fund, fund_fält)):
        for f in fält:
            vals = np.array([r[f] for r in data if r[f] is not None], dtype=float)
            if len(vals) < 20:
                continue
            p1, p50, p99 = np.percentile(vals, [1, 50, 99])
            mx, mn = vals.max(), vals.min()
            extremrep[f"{namn}.{f}"] = {"p1": float(p1), "p50": float(p50), "p99": float(p99),
                                        "min": float(mn), "max": float(mx)}
            flagga = " ⚠" if (mx > p99 * 20 and abs(mx) > 10) or (mn < p1 * 20 and mn < -10) else ""
            print(f"  {namn}.{f:22s} p1={p1:>10.4f} p50={p50:>10.4f} p99={p99:>10.4f} "
                  f"min={mn:>12.4f} max={mx:>12.4f}{flagga}")
    rep["extremvarden"] = extremrep

    OUT.write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSAMTLIGA STRUKTURELLA KONTROLLER PASSERADE. artefakt: {OUT}")


if __name__ == "__main__":
    main()
