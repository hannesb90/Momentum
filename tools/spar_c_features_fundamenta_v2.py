"""Spar C v2: CORE+FUNDAMENTA-panelen, utokad enligt feature blueprint.

MATERIALITETSREGEL (preregistrerad HAR, INNAN nagon targetkoppling gjorts -
tröskeln ar vald pa ekonomiska grunder, inte kalibrerad mot framtida
avkastning):

  Ett resultatmatt (`revenues` for marginalmatt; `profit_To_Equity_Holders`
  for EPS-tillvaxtens bas) racknas som en giltig, ekonomiskt tolkningsbar bas
  for en kvot ENDAST om dess ABSOLUTBELOPP ar minst 1% av `total_Assets`
  SAMMA period. Uppfylls inte detta satts kvoten till null - aldrig klippt,
  aldrig imputerad.

  Motiv: en verksamhet som genererar mindre an 1% av sin balansomslutning i
  intakter under ett rullande ar ar i praktiken inte en "opererande"
  verksamhet i den mening marginalmatt forutsatter (pre-revenue-bolag,
  skalbolag, brytningsfas) - marginalen blir da en artefakt av en nastan
  obefintlig namnare, oavsett bolagets absoluta storlek. 1% ar en rund,
  konservativ trosekel, val under vad normala operativa verksamheter uppvisar
  aven i lagmarginalbranscher.

  For TILLVAXTKVOTER (revenue_growth_yoy, eps_growth_yoy) maste BADA
  periodernas bas uppfylla testet OBEROENDE av varandra.

Detta loser de 6 fait som stod KRAVER ATGARD i forsta Spar C-omgangen:
gross_margin_ttm, operating_margin_ttm, net_margin_ttm, fcf_margin_ttm,
revenue_growth_yoy, eps_growth_yoy - samt tillampas konsekvent pa de NYA
marginalmatt som laggs till har (ocf_margin_ttm).
"""
from __future__ import annotations

import bisect
import hashlib
import json
from datetime import date
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
R12 = V2 / "validated/fundamentals/fundamentals_r12_validated.json"
KPI_EXTRA = V2 / "validated/fundamenta_extra/kpi_ebitda_capex.json"
CORE_PANEL = V2 / "panels/core_panel.json"
PRICES = V2 / "validated/prices/prices_validated.json"
REGISTRY = V2 / "docs/probes/feature_registry.json"
OUT_PANEL = V2 / "panels/core_fundamenta_panel.json"

MATERIALITET_TROSKEL = 0.01     # 1 % av total_Assets

FUND_REGISTRY = [
    {"id": "roe_ttm", "formel": "profit_To_Equity_Holders/total_Equity",
     "hypotes": "Lönsamhet på eget kapital."},
    {"id": "roa_ttm", "formel": "profit_To_Equity_Holders/total_Assets",
     "hypotes": "Lönsamhet på totalt kapital."},
    {"id": "roic_proxy_ttm", "formel": "operating_Income/(total_Equity+net_Debt)",
     "hypotes": "Avkastning på investerat kapital, FÖRE-skatt-approximation "
               "(ingen skattefältvariabel bland godkända Spår B-fält)."},
    {"id": "gross_margin_ttm", "formel": "gross_Income/revenues [materialitetsgrind]",
     "hypotes": "Prissättningsmakt/kostnadsstruktur."},
    {"id": "operating_margin_ttm", "formel": "operating_Income/revenues [materialitetsgrind]",
     "hypotes": "Rörelselönsamhet."},
    {"id": "ebitda_margin_ttm", "formel": "B-extra EBITDA value_sek/revenues [materialitetsgrind]",
     "hypotes": "Rörelselönsamhet före av- och nedskrivningar."},
    {"id": "net_margin_ttm", "formel": "profit_To_Equity_Holders/revenues [materialitetsgrind]",
     "hypotes": "Nettolönsamhet."},
    {"id": "fcf_margin_ttm", "formel": "free_Cash_Flow/revenues [materialitetsgrind]",
     "hypotes": "Kassaflödeskvalitet."},
    {"id": "ocf_margin_ttm", "formel": "cash_Flow_From_Operating_Activities/revenues "
            "[materialitetsgrind]", "hypotes": "Operativt kassaflöde relativt omsättning, "
            "före investeringar."},
    {"id": "accruals_ttm", "formel": "(profit_To_Equity_Holders-cash_Flow_From_Operating"
            "_Activities)/total_Assets", "hypotes": "Sloan accruals — earnings quality."},
    {"id": "net_debt_to_equity", "formel": "net_Debt/total_Equity",
     "hypotes": "Finansiell risk/belåningsgrad."},
    {"id": "equity_ratio_ttm", "formel": "total_Equity/total_Assets",
     "hypotes": "Soliditet."},
    {"id": "current_ratio", "formel": "current_Assets/current_Liabilities",
     "hypotes": "Kortsiktig likviditet."},
    {"id": "asset_turnover_ttm", "formel": "revenues/total_Assets",
     "hypotes": "Kapitaleffektivitet (DuPont-komponent)."},
    {"id": "revenue_growth_yoy", "formel": "revenues[T]/revenues[T-52v]-1 "
            "[materialitetsgrind på BÅDA punkterna]", "hypotes": "Omsättningstillväxt TTM."},
    {"id": "eps_growth_yoy", "formel": "EPS[T]/EPS[T-52v]-1, samma tecken krävs "
            "[materialitetsgrind via profit_To_Equity_Holders på BÅDA punkterna]",
     "hypotes": "Resultattillväxt per aktie."},
    {"id": "shares_growth_yoy", "formel": "number_Of_Shares[T]/number_Of_Shares[T-52v]-1",
     "hypotes": "Aktieutspädning eller återköp."},
    {"id": "dividend_yield_ttm", "formel": "UTESLUTEN: per-aktie/prisbasis inte generellt QA-verifierad",
     "status": "UTESLUTEN", "hypotes": "Direktavkastning."},
    {"id": "fcf_yield_ttm", "formel": "UTESLUTEN: pris×aktieantal ger inte verifierat PIT-börsvärde",
     "status": "UTESLUTEN", "hypotes": "Fritt kassaflöde relativt börsvärde — värderingsfaktor."},
    {"id": "return_since_last_report_ttm", "formel": "adj[T]/adj[vid report_date]-1",
     "hypotes": "Post-earnings-announcement drift (PEAD), robust ersättning för legacyns "
               "trasiga attention_gap-formel."},
    {"id": "fundamenta_days_since", "formel": "T-report_date", "ej_feature": True,
     "hypotes": "Provenance/staleness."},
    {"id": "has_fundamenta", "formel": "bool", "ej_feature": True,
     "hypotes": "Obligatorisk provenance-flagga."},
]
for f in FUND_REGISTRY:
    f["lager"] = "FUNDAMENTA"
    f["kalla"] = ("B-extra KPI R12 + R12 (Spår B)" if f["id"] == "ebitda_margin_ttm"
                  else "R12 (Spår B)") + (", adj (Spår A)" if "adj" in f["formel"] else "")
    f.setdefault("missing", "null om has_fundamenta=False, om nämnare=0/saknas, eller "
                "(för marginal-/tillväxtmått) om materialitetsgrinden ej uppfylls")
FEATURE_IDS = [f["id"] for f in FUND_REGISTRY if not f.get("ej_feature")]


def bygg_asof_index(r12: list) -> dict:
    idx = {}
    for r in r12:
        idx.setdefault(r["kod"], []).append(r)
    for kod in idx:
        idx[kod].sort(key=lambda r: r["report_date"])
    return idx


def slå_upp(idx_kod: list, datumnycklar: list, panel_date: str):
    i = bisect.bisect_right(datumnycklar, panel_date) - 1
    return idx_kod[i] if i >= 0 else None


def materiell(bas, assets) -> bool:
    """Materialitetsregel: |bas| >= 1% av total_Assets samma period."""
    if bas is None or assets is None or assets <= 0:
        return False
    return abs(bas) >= MATERIALITET_TROSKEL * assets


def main() -> None:  # noqa: C901
    r12 = json.loads(R12.read_text(encoding="utf-8"))
    extra = json.loads(KPI_EXTRA.read_text(encoding="utf-8"))
    ebitda = {(r["kod"], r["year"], r["period"], r["report_date"]): r["value_sek"]
              for r in extra if r["kpi"] == "EBITDA" and r["report_type"] == "r12"}
    for r in r12:
        r["ebitda_extra_sek"] = ebitda.get((r["kod"], r["year"], r["period"], r["report_date"]))
    core = json.loads(CORE_PANEL.read_text(encoding="utf-8"))
    priser = json.loads(PRICES.read_text(encoding="utf-8"))
    r12_hash = hashlib.sha256(R12.read_bytes()).hexdigest()
    core_hash = hashlib.sha256(CORE_PANEL.read_bytes()).hexdigest()

    idx = bygg_asof_index(r12)
    datumnycklar = {kod: [r["report_date"] for r in rader] for kod, rader in idx.items()}
    adj_by_kod = {kod: {r["d"]: r["adj"] for r in rader} for kod, rader in priser.items()}
    close_by_kod = {kod: {r["d"]: r["close"] for r in rader} for kod, rader in priser.items()}

    def föregående_år(pdate: str) -> str:
        y, m, dd = map(int, pdate.split("-"))
        try:
            return date(y - 1, m, dd).isoformat()
        except ValueError:
            return date(y - 1, m, dd - 1).isoformat()

    def tom_rad(ny: dict) -> dict:
        ny.update({"has_fundamenta": False, "fundamenta_report_date": None,
                  "fundamenta_days_since": None})
        for fid in FEATURE_IDS:
            ny[fid] = None
        return ny

    n_materialitet_stoppad = {"gross_margin_ttm": 0, "operating_margin_ttm": 0,
                              "ebitda_margin_ttm": 0, "net_margin_ttm": 0, "fcf_margin_ttm": 0, "ocf_margin_ttm": 0,
                              "revenue_growth_yoy": 0, "eps_growth_yoy": 0}

    ut = []
    n_med_fund = n_utan_fund = 0
    for rad in core:
        kod, pdate = rad["kod"], rad["panel_date"]
        ny = dict(rad)
        idx_kod = idx.get(kod)
        if idx_kod is None:
            ut.append(tom_rad(ny))
            n_utan_fund += 1
            continue
        träff = slå_upp(idx_kod, datumnycklar[kod], pdate)
        if träff is None:
            ut.append(tom_rad(ny))
            n_utan_fund += 1
            continue

        n_med_fund += 1
        rd = träff["report_date"]
        ny["has_fundamenta"] = True
        ny["fundamenta_report_date"] = rd
        ny["fundamenta_days_since"] = (date.fromisoformat(pdate) - date.fromisoformat(rd)).days

        def get(f):
            return träff.get(f)

        eq, ass = get("total_Equity"), get("total_Assets")
        rev = get("revenues")
        pte = get("profit_To_Equity_Holders")
        nd = get("net_Debt")
        oi = get("operating_Income")
        ebitda_value = get("ebitda_extra_sek")
        gi = get("gross_Income")
        fcf = get("free_Cash_Flow")
        ocf = get("cash_Flow_From_Operating_Activities")
        ca, cl = get("current_Assets"), get("current_Liabilities")
        n_sh = get("number_Of_Shares")

        ny["roe_ttm"] = (pte / eq) if (pte is not None and eq) else None
        ny["roa_ttm"] = (pte / ass) if (pte is not None and ass) else None
        invk = (eq or 0) + (nd or 0) if (eq is not None and nd is not None) else None
        ny["roic_proxy_ttm"] = (oi / invk) if (oi is not None and invk and invk > 0) else None

        rev_materiell = materiell(rev, ass)
        for namn, täljare in (("gross_margin_ttm", gi), ("operating_margin_ttm", oi),
                              ("ebitda_margin_ttm", ebitda_value),
                              ("net_margin_ttm", pte), ("fcf_margin_ttm", fcf),
                              ("ocf_margin_ttm", ocf)):
            if täljare is not None and rev and rev_materiell:
                ny[namn] = täljare / rev
            else:
                ny[namn] = None
                if täljare is not None and rev and not rev_materiell:
                    n_materialitet_stoppad[namn] += 1

        ny["accruals_ttm"] = ((pte - ocf) / ass) if (pte is not None and ocf is not None
                                                     and ass) else None
        ny["net_debt_to_equity"] = (nd / eq) if (nd is not None and eq) else None
        ny["equity_ratio_ttm"] = (eq / ass) if (eq is not None and ass) else None
        ny["current_ratio"] = (ca / cl) if (ca is not None and cl) else None
        ny["asset_turnover_ttm"] = (rev / ass) if (rev is not None and ass) else None

        # YoY-tillväxt med materialitetsgrind på BÅDA punkterna
        föreg_datum = föregående_år(pdate)
        träff_föreg = slå_upp(idx_kod, datumnycklar[kod], föreg_datum)
        if träff_föreg is not None:
            r0, a0_ass = träff_föreg.get("revenues"), träff_föreg.get("total_Assets")
            r1 = rev
            if (r0 is not None and materiell(r0, a0_ass) and r1 is not None and
                    rev_materiell and r0 != 0):
                ny["revenue_growth_yoy"] = r1 / r0 - 1
            else:
                ny["revenue_growth_yoy"] = None
                if r0 is not None and r1 is not None and \
                        not (materiell(r0, a0_ass) and rev_materiell):
                    n_materialitet_stoppad["revenue_growth_yoy"] += 1

            e0 = träff_föreg.get("earnings_Per_Share")
            e1 = get("earnings_Per_Share")
            p0 = träff_föreg.get("profit_To_Equity_Holders")
            p0_materiell = materiell(p0, a0_ass)
            p1_materiell = materiell(pte, ass)
            if (e0 is not None and e1 is not None and e0 != 0 and (e0 > 0) == (e1 > 0)
                    and p0_materiell and p1_materiell):
                ny["eps_growth_yoy"] = e1 / e0 - 1
            else:
                ny["eps_growth_yoy"] = None
                if e0 is not None and e1 is not None and not (p0_materiell and p1_materiell):
                    n_materialitet_stoppad["eps_growth_yoy"] += 1

            n0 = träff_föreg.get("number_Of_Shares")
            ny["shares_growth_yoy"] = (n_sh / n0 - 1) if (n0 and n_sh is not None) else None
        else:
            ny["revenue_growth_yoy"] = ny["eps_growth_yoy"] = ny["shares_growth_yoy"] = None

        div = get("dividend")
        a0 = adj_by_kod.get(kod, {}).get(rad["price_date"])
        close0 = close_by_kod.get(kod, {}).get(rad["price_date"])
        # Samtida prisnivå/mcap måste använda faktiskt handlad ojusterad close.
        # Adjusted close används endast för return_since_last_report.
        # Excluded until a point-in-time market-cap/per-share price basis is
        # independently validated. FLERIE proves that current EODHD close and
        # Börsdata's report share basis can differ by orders of magnitude.
        ny["dividend_yield_ttm"] = None
        ny["fcf_yield_ttm"] = None

        a_report = adj_by_kod.get(kod, {}).get(rd)
        if a_report is None and kod in adj_by_kod:
            datum_lista = sorted(adj_by_kod[kod])
            i2 = bisect.bisect_right(datum_lista, rd) - 1
            if i2 >= 0:
                a_report = adj_by_kod[kod][datum_lista[i2]]
        ny["return_since_last_report_ttm"] = (a0 / a_report - 1) if (a0 and a_report) else None

        ut.append(ny)

    OUT_PANEL.write_text(json.dumps(ut, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    kanon = json.dumps(sorted(ut, key=lambda r: (r["kod"], r["panel_date"])),
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    panelhash = hashlib.sha256(kanon.encode()).hexdigest()

    print(f"[fundamenta v2] {len(ut)} rader")
    print(f"  has_fundamenta=True:  {n_med_fund} ({100*n_med_fund/len(ut):.1f} %)")
    print(f"  has_fundamenta=False: {n_utan_fund} ({100*n_utan_fund/len(ut):.1f} %)")
    print(f"  materialitetsregel stoppade (satte null i stället för extremvärde):")
    for k, v in n_materialitet_stoppad.items():
        print(f"    {k:22s} {v:>5d} rader")
    print(f"  core_fundamenta_panel_sha256: {panelhash}")

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    reg["registry_version"] = "1.2.0"
    reg["FUNDAMENTA"] = FUND_REGISTRY
    REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[fundamenta v2] registry: {len(FUND_REGISTRY)} fält")

    (V2 / "docs/probes/fundamenta_panel_build_v2.json").write_text(json.dumps({
        "kalla_r12_sha256": r12_hash,
        "kalla_b_extra_sha256": hashlib.sha256(KPI_EXTRA.read_bytes()).hexdigest(),
        "kalla_core_panel_sha256": core_hash,
        "n_rader": len(ut), "n_med_fundamenta": n_med_fund, "n_utan_fundamenta": n_utan_fund,
        "materialitetstroskel": MATERIALITET_TROSKEL,
        "materialitetsregel_stoppade": n_materialitet_stoppad,
        "core_fundamenta_panel_sha256": panelhash,
    }, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
