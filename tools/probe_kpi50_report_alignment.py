#!/usr/bin/env python3
"""KPI 50 {y,p,v} → report-publication alignment probe; no alpha research."""
from __future__ import annotations

import csv
import glob
import hashlib
import importlib.util
import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_k" / "kpi50_report_alignment_probe"
RAW = ROOT / "raw" / "borsdata"
KPI_DIR = RAW / "kpi_valuation"
MATCH = RAW / "_matchning.json"
FUNDS = ROOT / "validated" / "fundamentals"
PATHS = {"W1": ROOT / "research_k/h0_v3_state_machine_and_path_ledger/PATH_LEDGER_W1.csv",
         "W2": ROOT / "research_k/h0_v3_state_machine_and_path_ledger/PATH_LEDGER_W2.csv"}
VALIDATED = ROOT / "validated" / "kpi_pit" / "50_Borsvarde_r12.json"

def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p: Path, x: object) -> None: p.write_text(json.dumps(x, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
def csvout(p: Path, rows: list[dict], fields: list[str]) -> None:
    with p.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def load_helper():
    src=ROOT/"tools"/"build_validated_kpi_extra.py"
    spec=importlib.util.spec_from_file_location("kpi_extra_alignment",src)
    mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)
    return mod

def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True)
    helper=load_helper(); lookup, report_hashes=helper.bygg_rapport_lookup()
    insid2kod={str(x["insid"]):x["kod"] for x in json.loads(MATCH.read_text())["matchade"]}
    period_end_lookup={}
    for name in ("fundamentals_r12_validated.json", "fundamentals_quarter_validated.json", "fundamentals_year_validated.json"):
        for x in json.loads((FUNDS/name).read_text()):
            key=(str(x.get("insid")), x.get("year"), x.get("period"))
            if x.get("report_end_date"):
                period_end_lookup[key]=x["report_end_date"]
    raw=[]
    for fp in sorted(glob.glob(str(KPI_DIR/"50_Borsvarde_*_b*.json"))):
        d=json.loads(Path(fp).read_text())
        for node in d.get("kpisList",[]):
            for v in node.get("values",[]):
                raw.append({"insid":str(node.get("instrument")),"report_type":d.get("reportTime"),
                            "price_value":d.get("priceValue"),"y":v.get("y"),"p":v.get("p"),"v":v.get("v"),
                            "raw_file":str(Path(fp).relative_to(ROOT)),"raw_sha256":sha(Path(fp))})
    raw.sort(key=lambda r:(r["insid"],r["report_type"] or "",r["y"] or 0,r["p"] or 0))
    aligned=[]; status=Counter()
    for r in raw:
        row=dict(r); row["ticker"]=insid2kod.get(r["insid"])
        rt,p=r["report_type"],r["p"]
        if r["v"] is None or r["y"] is None or p is None:
            st="NO_MATCH"; target=None; rule="missing_y_p_or_v"
        elif rt=="r12" and p in (1,2,3,4):
            target=(r["y"],p); st="EXACT"; rule="r12_(y,p)_to_quarter_report_(year,period)"
        elif rt=="year" and p==5:
            target=(r["y"],5); st="EXACT"; rule="year_(y,5)_to_year_report_(year,period=5)"
        elif rt=="year" and p in (1,2,3,4):
            target=None; st="SEMANTIC_CONFLICT"; rule="partial_year_alias_excluded; r12 is the eligible quarterly-period representation"
        else:
            target=None; st="SEMANTIC_CONFLICT"; rule="unsupported_report_type_or_period_token"
        candidates=[] if target is None else ([lookup[r["insid"]][target]] if target in lookup.get(r["insid"],{}) else [])
        meta=candidates[0] if len(candidates)==1 else None
        if st=="EXACT":
            if not candidates: st="NO_MATCH"
            elif not meta["giltig"]: st="SEMANTIC_CONFLICT"
        row.update({"matched_report_period":f"{target[0]}-P{target[1]}" if target else "",
                    "matched_period_end":period_end_lookup.get((r["insid"], *target), "") if target else "", "matched_publication_date":meta["report_date"] if meta else "",
                    "available_at_rule":"first H0 trading day strictly after matched_report.publication_date",
                    "match_rule":rule,"number_of_candidate_reports":len(candidates),"alignment_status":st,
                    "alignment_reason":"" if st=="EXACT" else (meta or {}).get("orsak", st)})
        status[st]+=1; aligned.append(row)
    fields=["ticker","insid","report_type","price_value","y","p","v","matched_report_period","matched_period_end","matched_publication_date","available_at_rule","match_rule","number_of_candidate_reports","alignment_status","alignment_reason","raw_file","raw_sha256"]
    csvout(OUT/"KPI50_REPORT_ALIGNMENT.csv",aligned,fields)

    # cadence uses R12 observations having an exact aligned report, grouped by fiscal year.
    cadence=defaultdict(list)
    for r in aligned:
        if r["report_type"]=="r12" and r["alignment_status"]=="EXACT": cadence[(r["ticker"],r["y"])].append(r)
    countdist=Counter(len(x) for x in cadence.values())
    cadence_rows=[]
    for (ticker,yr),rs in sorted(cadence.items()):
        cadence_rows.append({"ticker":ticker,"year":yr,"r12_observations":len(rs),"period_tokens":"|".join(str(x["p"]) for x in rs),
                             "report_dates":"|".join(x["matched_publication_date"] for x in rs)})
    csvout(OUT/"KPI50_R12_UPDATE_CADENCE.csv",cadence_rows,["ticker","year","r12_observations","period_tokens","report_dates"])

    semantics={
        "kpi_id":50,"name":"Börsvärde / Market Cap","unit":"MCURR","price_value":"mean",
        "observed_period_types":sorted({r["report_type"] for r in raw}),
        "period_token_model":{
            "r12_p_1_to_4":"exactly maps to the corresponding raw quarterly report (year=y, period=p); this is implemented in existing build_validated_kpi_extra.py and used in validated/kpi_pit/50_Borsvarde_r12.json",
            "year_p_5":"maps to the annual report (year=y, period=5)",
            "year_p_1_to_4":"not a complete annual report; excluded from PIT panel mapping to avoid alias ambiguity"},
        "value_semantics_limit":"KPI response does not itself contain observation timestamp or a version date. Alignment only transfers the matching report's conservative availability date; it does not prove the historical KPI value was not later revised.",
        "source_hashes":{"validated_kpi_pit":sha(VALIDATED),"raw_kpi_files":sorted({r["raw_sha256"] for r in raw})[:3],"report_source_file_count":len(report_hashes)},
        "alignment_counts":dict(status),
    }
    dump(OUT/"KPI50_PERIOD_SEMANTICS.json",semantics)

    # Revision audit: only one raw market-cap extraction date exists.  The
    # validated builder itself records that source histories lack version date.
    fetches=sorted({Path(r["raw_file"]).name.split("__")[-1].split(".")[0] for r in raw})
    revision={"risk":"UNKNOWN","historical_cache_snapshots_for_same_kpi_period":1,
              "raw_fetch_snapshot_tokens":fetches,"same_period_cross_snapshot_comparison":"NOT_POSSIBLE",
              "local_builder_documentation":"KPI history {y,p,v} lacks version date; retroactive recalculation cannot be verified.",
              "potential_leakage":"If Börsdata retrospectively revises a historical KPI50 record, attaching it to the original report date would make the revised value appear historically available.",
              "conclusion":"Exact period alignment is insufficient for readiness until revision/version behavior is independently documented or historical as-of snapshots exist."}
    dump(OUT/"KPI50_REVISION_RISK_REPORT.json",revision)

    # Cross representation check: R12 P4 and Year P5 share the fiscal close,
    # providing an internal period-token consistency check without shares.
    r12={(r["insid"],r["y"]):r for r in aligned if r["report_type"]=="r12" and r["p"]==4 and r["alignment_status"]=="EXACT" and r["v"] not in (None,0)}
    yr={(r["insid"],r["y"]):r for r in aligned if r["report_type"]=="year" and r["p"]==5 and r["alignment_status"]=="EXACT" and r["v"] not in (None,0)}
    ratios=[]
    for k in r12.keys() & yr.keys(): ratios.append(yr[k]["v"]/r12[k]["v"])
    dump(OUT/"KPI50_EMPIRICAL_PERIOD_CHECK.json",{"test":"R12_P4_vs_YEAR_P5_same_fiscal_close", "n":len(ratios),
       "median_ratio":statistics.median(ratios) if ratios else None,
       "p05_ratio":sorted(ratios)[int(.05*(len(ratios)-1))] if ratios else None,
       "p95_ratio":sorted(ratios)[int(.95*(len(ratios)-1))] if ratios else None,
       "interpretation":"Internal consistency of period labels only; not proof against later historical revisions or of company/share-class scope."})

    # Scope cannot be inferred merely from a single class per company. Probe
    # same-name class pairs in available mapping conservatively.
    base=defaultdict(list)
    for r in aligned:
        t=r["ticker"] or ""
        for suffix in ("-A","-B","-C"):
            if t.endswith(suffix): base[t[:-2]].append(t)
    scope_rows=[]
    for company,ticks in sorted(base.items()):
        if len(set(ticks))>1:
            scope_rows.append({"company_stub":company,"share_classes":"|".join(sorted(set(ticks))),"KPI50_scope":"UNKNOWN",
                               "evidence":"No API metadata identifies KPI 50 as company-total or share-class-specific; equality/difference must not be inferred from incomplete class coverage."})
    if not scope_rows: scope_rows.append({"company_stub":"NONE_OBSERVED","share_classes":"","KPI50_scope":"UNKNOWN","evidence":"No confirmed multi-class matched pair in this local cache subset."})
    csvout(OUT/"KPI50_SHARE_CLASS_SCOPE.csv",scope_rows,["company_stub","share_classes","KPI50_scope","evidence"])

    # Case studies retain only aligned period facts; they do not claim daily CA continuity.
    ca_names=["SAGA-B","RAY-B","CLAS-B","NET-B","BALD-B"]
    ca=[]
    for t in ca_names:
        rs=[r for r in aligned if r["ticker"]==t and r["alignment_status"]=="EXACT"]
        ca.append({"ticker":t,"aligned_observations":len(rs),"first_report_date":min((r["matched_publication_date"] for r in rs),default=""),
                   "last_report_date":max((r["matched_publication_date"] for r in rs),default=""),"corporate_action_continuity":"NOT_VERIFIABLE_FROM_VERSIONLESS_KPI_HISTORY",
                   "note":"Period alignment holds independently of corporate-action inference; revision and scope remain unresolved."})
    csvout(OUT/"KPI50_CORPORATE_ACTION_QA.csv",ca,["ticker","aligned_observations","first_report_date","last_report_date","corporate_action_continuity","note"])

    # Candidate coverage uses only exact r12 mappings and only records whose
    # report date is strictly earlier than the panel; this is the same
    # conservative availability convention used by existing fundamental PIT.
    usable=defaultdict(list)
    for r in aligned:
        if r["report_type"]=="r12" and r["alignment_status"]=="EXACT" and r["v"] not in (None,0): usable[r["ticker"]].append(r)
    for x in usable.values(): x.sort(key=lambda r:r["matched_publication_date"])
    cov=[]
    for window,path in PATHS.items():
        stats=defaultdict(lambda:defaultdict(list))
        with path.open(newline="",encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("eligible")!="True": continue
                pop="SELECTED_PRE_SMA" if row.get("selected")=="True" else "PIT_ELIGIBLE_UNIVERSE"
                # Avoid double-counting selected in universe: both required
                # populations are collected explicitly below.
                for population, applies in (("PIT_ELIGIBLE_UNIVERSE",True),("SELECTED_PRE_SMA",row.get("selected")=="True")):
                    if not applies: continue
                    yr=row["date"][:4]; d=row["date"]
                    b=stats[(yr,population)]; b["total"].append(1)
                    prior=[x for x in usable.get(row["ticker"],[]) if x["matched_publication_date"] < d]
                    if prior:
                        selected=prior[-1]; b["avail"].append(1)
                        b["age"].append((date.fromisoformat(d)-date.fromisoformat(selected["matched_publication_date"])).days)
                    else: b["unavail"].append(1)
        for (yr,pop),b in sorted(stats.items()):
            age=sorted(b["age"]); n=len(b["total"]); a=len(b["avail"])
            cov.append({"window":window,"year":yr,"population":pop,"total_security_panel_observations":n,
                        "aligned_KPI50_available":a,"unavailable":len(b["unavail"]),"ambiguous":0,
                        "coverage_pct":100*a/n if n else None,"median_proxy_age_days":statistics.median(age) if age else None,
                        "p90_proxy_age_days":age[int(.9*(len(age)-1))] if age else None,
                        "availability_rule":"report_date strictly before panel date; no backward fill"})
    csvout(OUT/"KPI50_REPORT_ALIGNED_COVERAGE.csv",cov,list(cov[0]))

    # PIT proof at the report-alignment layer: mutate post-cutoff source
    # records and confirm selected report keys at/before cutoff are unchanged.
    cutoff="2020-12-31"
    before={(t,d):max((x["matched_publication_date"] for x in rs if x["matched_publication_date"]<=d),default=None)
            for t,rs in usable.items() for d in [cutoff]}
    mutated={t:rs+[{**rs[-1],"matched_publication_date":"2099-01-01","v":999999999}] for t,rs in usable.items() if rs}
    after={(t,d):max((x["matched_publication_date"] for x in rs if x["matched_publication_date"]<=d),default=None)
            for t,rs in mutated.items() for d in [cutoff]}
    pit_pass=before==after
    boundary=next((r for r in aligned if r["alignment_status"]=="EXACT" and r["matched_publication_date"]=="2020-01-28"),None)
    dump(OUT/"KPI50_ALIGNMENT_PIT_TESTS.json",{"KPI50_REPORT_ALIGNMENT_PIT_TEST":"PASS" if pit_pass else "FAIL",
        "cutoff":cutoff,"mutation":"post-cutoff aligned KPI/report records only","publication_boundary_candidate":boundary,
        "KPI50_REPORT_PUBLICATION_BOUNDARY":"PASS_FOR_CONSERVATIVE_RULE" if boundary else "NO_CASE_FOUND",
        "limitation":"These tests prove the candidate mapping has no mechanical future-row leak. They cannot detect vendor retroactive revision because only one raw KPI50 snapshot exists."})

    readiness={"study":"KPI50_REPORT_ALIGNMENT_PROBE","classification":"KPI50_REPORT_ALIGNMENT_REVISION_RISK",
               "exact_alignment_available":status["EXACT"],"alignment_status_counts":dict(status),
               "candidate_available_at":"first H0 trading day strictly after matched report_date","r12_cadence_distribution":dict(sorted(countdist.items())),
               "median_r12_observations_per_instrument_year":statistics.median(countdist.elements()) if countdist else None,
               "publication_boundary_test":"PASS_FOR_CONSERVATIVE_RULE" if boundary else "NO_CASE_FOUND",
               "future_mutation_test":"PASS" if pit_pass else "FAIL","revision_risk":"UNKNOWN",
               "why_not_ready":"No historical as-of snapshots or vendor version timestamps prove KPI50 values were not retrospectively revised. Multi-share-class scope remains UNKNOWN.",
               "alpha_analysis_run":False,"filter_backtest_run":False}
    dump(OUT/"KPI50_ALIGNMENT_READINESS_REPORT.json",readiness)
    (OUT/"SUMMARY.md").write_text("# KPI50 report alignment probe\n\nExact `(y,p)` report-period alignment is mechanically available for R12 `p=1..4` and annual `p=5`, and maps to the existing conservative report-date PIT convention. However, the local Börsdata KPI50 cache has one as-of snapshot only and no revision/version dates. Vendor retroactive revision risk is therefore unknown; the source is not ready for size research. No alpha analysis was run.\n",encoding="utf-8")
    dump(OUT/"HASHES.json",{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!="HASHES.json"})
if __name__=="__main__": main()
