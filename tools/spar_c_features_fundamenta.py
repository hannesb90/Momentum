"""Spar C, steg 2b: feature registry (FUNDAMENTA) + CORE+FUNDAMENTA-panelbygge.

Anvander Spar B:s R12-tabell (rullande 12 manader) som enda fundamentakalla:
den ger bade TTM-floden och balansrakningssnapshots i en enda, kvartalsvis
uppdaterad rad, och redan verifierad 100% identisk med arsdatan vid Q4
(FUNDAMENTAL_QA.md steg 9). Ingen blandning ar/kvartal - EN kalla, en
uppdateringstakt.

PIT-koppling: for varje (instrument, panel_date) tas den SENASTE R12-raden
vars report_date <= panel_date. En rapport blir synlig i panelen forst DEN
DAG den faktiskt publicerades - aldrig tidigare. Tillvaxtmatt jamfor tva
sadana as-of-uppslag ~52v isar (bada oberoende PIT-korrekta).

PROVENANCE PA VARJE RAD (obligatoriskt per instruktion):
  has_fundamenta        bool - fanns NAGON rapport tillganglig vid T?
  fundamenta_report_date  det anvanda rapportens publiceringsdatum
  fundamenta_days_since   T - report_date (staleness)
  fundamenta_quality_class  alltid "A" har (Spar B:s Track B bidrog noll)

SURVIVORSHIP-VARNING: 67 av 68 avnoterade Nasdaq Stockholm-bolag 2020-2026
saknar HELT fundamentadata (FUNDAMENTAL_QA.md). has_fundamenta=False for ALLA
rader for dessa (och for ovriga 71-67=4 CORE-instrument som av andra skal
aldrig matchade Bors data). CORE+FUNDAMENTA-panelen ar DARFOR INTE
survivorship-saker for fundamentafalten, aven om CORE-delen och target ar
det. Detta far ALDRIG doljas - se manifest_sparC.json.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from pathlib import Path

V2 = Path("/home/hannesb/momentum_v2")
R12 = V2 / "validated/fundamentals/fundamentals_r12_validated.json"
CORE_PANEL = V2 / "panels/core_panel.json"
PRICES = V2 / "validated/prices/prices_validated.json"
REGISTRY = V2 / "docs/probes/feature_registry.json"
OUT_PANEL = V2 / "panels/core_fundamenta_panel.json"

FUND_REGISTRY = [
    {"id": "roe_ttm", "lager": "FUNDAMENTA", "kalla": "R12: profit_To_Equity_Holders/total_Equity",
     "formel": "profit_To_Equity_Holders / total_Equity (senast tillgängliga R12)",
     "hypotes": "Lönsamhet på eget kapital — kvalitetsfaktor.",
     "missing": "null om total_Equity=0/saknas eller ingen rapport tillgänglig (has_fundamenta=False)."},
    {"id": "roa_ttm", "lager": "FUNDAMENTA", "kalla": "R12: profit_To_Equity_Holders/total_Assets",
     "formel": "profit_To_Equity_Holders / total_Assets",
     "hypotes": "Lönsamhet på totalt kapital, mindre känslig för belåningsgrad än ROE.",
     "missing": "null om total_Assets saknas/0 eller ingen rapport."},
    {"id": "gross_margin_ttm", "lager": "FUNDAMENTA", "kalla": "R12: gross_Income/revenues",
     "formel": "gross_Income / revenues",
     "hypotes": "Prissättningsmakt/kostnadsstruktur.",
     "missing": "null om revenues=0/saknas."},
    {"id": "operating_margin_ttm", "lager": "FUNDAMENTA", "kalla": "R12: operating_Income/revenues",
     "formel": "operating_Income / revenues",
     "hypotes": "Rörelselönsamhet, kvalitetsfaktor.",
     "missing": "null om revenues=0/saknas."},
    {"id": "net_margin_ttm", "lager": "FUNDAMENTA", "kalla": "R12: profit_To_Equity_Holders/revenues",
     "formel": "profit_To_Equity_Holders / revenues",
     "hypotes": "Nettolönsamhet efter alla poster.",
     "missing": "null om revenues=0/saknas."},
    {"id": "fcf_margin_ttm", "lager": "FUNDAMENTA", "kalla": "R12: free_Cash_Flow/revenues",
     "formel": "free_Cash_Flow / revenues",
     "hypotes": "Kassaflödeskvalitet — skiljer redovisad vinst från verkligt kassaflöde.",
     "missing": "null om revenues=0/saknas."},
    {"id": "net_debt_to_equity", "lager": "FUNDAMENTA", "kalla": "R12: net_Debt/total_Equity",
     "formel": "net_Debt / total_Equity",
     "hypotes": "Finansiell risk/belåningsgrad.",
     "missing": "null om total_Equity=0/saknas. Negativt värde = nettokassa (giltigt, inte fel)."},
    {"id": "current_ratio", "lager": "FUNDAMENTA", "kalla": "R12: current_Assets/current_Liabilities",
     "formel": "current_Assets / current_Liabilities",
     "hypotes": "Kortsiktig likviditet/finansiell stabilitet.",
     "missing": "null om current_Liabilities=0/saknas."},
    {"id": "revenue_growth_yoy", "lager": "FUNDAMENTA", "kalla": "R12: revenues, två as-of-punkter ~52v isär",
     "formel": "revenues[senaste R12 as-of T] / revenues[senaste R12 as-of T-52v] - 1",
     "hypotes": "Organisk/total omsättningstillväxt, TTM mot TTM undviker säsongseffekter.",
     "missing": "null om endera as-of-punkten saknar rapport eller nämnaren är 0."},
    {"id": "eps_growth_yoy", "lager": "FUNDAMENTA", "kalla": "R12: earnings_Per_Share, två as-of-punkter",
     "formel": "EPS[T] / EPS[T-52v] - 1 (endast om samma tecken, se missing)",
     "hypotes": "Resultattillväxt per aktie, splitverifierad källa (FUNDAMENTAL_QA.md §7b).",
     "missing": "null om endera punkten saknas, ELLER om täljare/nämnare har olika tecken "
               "(en tillväxtkvot mellan förlust och vinst är inte tolkningsbar som en kvot)."},
    {"id": "dividend_yield_ttm", "lager": "FUNDAMENTA", "kalla": "R12 dividend (DPS) / CORE adj (pris)",
     "formel": "dividend_TTM / adj[T]", "beroende_av_core": True,
     "hypotes": "Direktavkastning — standardfaktor, kombinerar fundamenta och pris.",
     "missing": "null om ingen rapport tillgänglig; 0 är ett GILTIGT värde (bolag delar inte ut)."},
    {"id": "fundamenta_days_since", "lager": "FUNDAMENTA (provenance)", "kalla": "R12 report_date",
     "formel": "T - report_date för den använda rapporten", "ej_feature": True,
     "hypotes": "Provenance/staleness, inte en alfakandidat i sig.",
     "missing": "null endast om has_fundamenta=False."},
    {"id": "has_fundamenta", "lager": "FUNDAMENTA (provenance)", "kalla": "R12-tillgänglighet",
     "formel": "bool: fanns ≥1 R12-rapport med report_date <= T", "ej_feature": True,
     "hypotes": "Obligatorisk provenance-flagga — se survivorship-varningen i manifestet.",
     "missing": "aldrig null, alltid True/False."},
]


def bygg_asof_index(r12: list) -> dict:
    """kod -> sorterad lista av (report_date, rad) for snabb as-of-uppslag."""
    idx = {}
    for r in r12:
        idx.setdefault(r["kod"], []).append(r)
    for kod in idx:
        idx[kod].sort(key=lambda r: r["report_date"])
    return idx


def slå_upp(idx_kod: list, datumnycklar: list, panel_date: str):
    """Senaste raden med report_date <= panel_date (aldrig senare -> ingen läckage)."""
    i = bisect.bisect_right(datumnycklar, panel_date) - 1
    return idx_kod[i] if i >= 0 else None


def main() -> None:  # noqa: C901
    r12 = json.loads(R12.read_text(encoding="utf-8"))
    core = json.loads(CORE_PANEL.read_text(encoding="utf-8"))
    priser = json.loads(PRICES.read_text(encoding="utf-8"))
    r12_hash = hashlib.sha256(R12.read_bytes()).hexdigest()
    core_hash = hashlib.sha256(CORE_PANEL.read_bytes()).hexdigest()

    idx = bygg_asof_index(r12)
    datumnycklar = {kod: [r["report_date"] for r in rader] for kod, rader in idx.items()}
    adj_by_kod = {kod: {r["d"]: r["adj"] for r in rader} for kod, rader in priser.items()}

    from datetime import date, timedelta

    def föregående_år(pdate: str) -> str:
        y, m, dd = map(int, pdate.split("-"))
        try:
            return date(y - 1, m, dd).isoformat()
        except ValueError:
            return (date(y - 1, m, dd - 1)).isoformat()

    FEATURE_IDS = [f["id"] for f in FUND_REGISTRY if not f.get("ej_feature")]

    def tom_rad(ny: dict) -> dict:
        ny.update({"has_fundamenta": False, "fundamenta_report_date": None,
                  "fundamenta_days_since": None})
        for fid in FEATURE_IDS:
            ny[fid] = None
        return ny

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
        days = (date.fromisoformat(pdate) - date.fromisoformat(rd)).days
        ny["has_fundamenta"] = True
        ny["fundamenta_report_date"] = rd
        ny["fundamenta_days_since"] = days

        def get(f):
            v = träff.get(f)
            return v if v is not None else None

        eq, ass = get("total_Equity"), get("total_Assets")
        rev = get("revenues")
        pte = get("profit_To_Equity_Holders")
        ny["roe_ttm"] = (pte / eq) if (pte is not None and eq) else None
        ny["roa_ttm"] = (pte / ass) if (pte is not None and ass) else None
        gi, oi = get("gross_Income"), get("operating_Income")
        ny["gross_margin_ttm"] = (gi / rev) if (gi is not None and rev) else None
        ny["operating_margin_ttm"] = (oi / rev) if (oi is not None and rev) else None
        ny["net_margin_ttm"] = (pte / rev) if (pte is not None and rev) else None
        fcf = get("free_Cash_Flow")
        ny["fcf_margin_ttm"] = (fcf / rev) if (fcf is not None and rev) else None
        nd = get("net_Debt")
        ny["net_debt_to_equity"] = (nd / eq) if (nd is not None and eq) else None
        ca, cl = get("current_Assets"), get("current_Liabilities")
        ny["current_ratio"] = (ca / cl) if (ca is not None and cl) else None

        # YoY-tillväxt: en oberoende as-of-punkt ~52v tidigare
        föreg_datum = föregående_år(pdate)
        träff_föreg = slå_upp(idx_kod, datumnycklar[kod], föreg_datum)
        if träff_föreg is not None:
            r0, r1 = träff_föreg.get("revenues"), rev
            ny["revenue_growth_yoy"] = (r1 / r0 - 1) if (r0 and r1 is not None and r0 > 0) else None
            e0, e1 = träff_föreg.get("earnings_Per_Share"), get("earnings_Per_Share")
            if e0 is not None and e1 is not None and e0 != 0 and \
                    (e0 > 0) == (e1 > 0):
                ny["eps_growth_yoy"] = e1 / e0 - 1
            else:
                ny["eps_growth_yoy"] = None
        else:
            ny["revenue_growth_yoy"] = ny["eps_growth_yoy"] = None

        div = get("dividend")
        a0 = adj_by_kod.get(kod, {}).get(rad["price_date"])
        ny["dividend_yield_ttm"] = (div / a0) if (div is not None and a0 and a0 > 0) else None

        ut.append(ny)

    OUT_PANEL.write_text(json.dumps(ut, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    kanon = json.dumps(sorted(ut, key=lambda r: (r["kod"], r["panel_date"])),
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    panelhash = hashlib.sha256(kanon.encode()).hexdigest()

    print(f"[fundamenta] {len(ut)} rader")
    print(f"  has_fundamenta=True:  {n_med_fund} ({100*n_med_fund/len(ut):.1f} %)")
    print(f"  has_fundamenta=False: {n_utan_fund} ({100*n_utan_fund/len(ut):.1f} %)")
    print(f"  core_fundamenta_panel_sha256: {panelhash}")

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    reg["FUNDAMENTA"] = FUND_REGISTRY
    REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[fundamenta] registry uppdaterat: +{len(FUND_REGISTRY)} fält -> {REGISTRY}")

    (V2 / "docs/probes/fundamenta_panel_build.json").write_text(json.dumps({
        "kalla_r12_sha256": r12_hash, "kalla_core_panel_sha256": core_hash,
        "n_rader": len(ut), "n_med_fundamenta": n_med_fund, "n_utan_fundamenta": n_utan_fund,
        "core_fundamenta_panel_sha256": panelhash,
    }, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
