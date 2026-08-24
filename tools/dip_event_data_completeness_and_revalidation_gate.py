"""Data-only gate; intentionally does not compute any forward-return revalidation."""
import csv, hashlib, json
from pathlib import Path

ROOT=Path('/home/hannesb/momentum_v2')
OUT=ROOT/'research_k/dip_event_data_completeness_and_revalidation_gate'
SRC=ROOT/'research_k/momentum_dip_survival_and_opportunistic_entry_audit/dip_event_ledger.csv'
PORT=ROOT/'research_k/opportunistic_dip_buy_portfolio_audit'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    freeze=json.loads((OUT/'PLAN_FREEZE.json').read_text())
    if sha(OUT/'PREREGISTRATION.md')!=freeze['prereg_md_sha256']: raise SystemExit('STOP prereg hash')
    before={p.name:sha(p) for p in (PORT/'PREREGISTRATION.json',PORT/'PLAN_FREEZE.json')}
    sources=[
      ('report_dates','Borsdata/report PEAD artifacts','PARTIAL','NO','PARTIAL','PARTIAL','Entity/date fields exist, but no demonstrated W1/W2 PIT-complete publication-time coverage.'),
      ('profit_warning_guidance','MFN/Borsdata announcements','PARTIAL','NO','PARTIAL','PARTIAL','MFN cache exists, but semantic negative classification and comparable historical coverage are not established.'),
      ('major_announcements','MFN/Nasdaq notices','PARTIAL','NO','PARTIAL','PARTIAL','No complete structured historical Nasdaq corporate announcement series.'),
      ('corporate_actions','Nasdaq corporate_actions_discovery','PARTIAL','NO','PARTIAL','PARTIAL','Discovery explicitly says no structured historical dividend/rights/M&A series.'),
      ('splits_share_changes','Nasdaq monthly share-count snapshots','PARTIAL','PARTIAL','PARTIAL','PARTIAL','Monthly share-count changes can diagnose some splits, not event-date complete.'),
      ('dividends_ex_dates','price adjustment repair / dividend state machine','PARTIAL','PARTIAL','PARTIAL','PARTIAL','Adjustment QA exists; no event-date-complete PIT dividend/ex-date event ledger.'),
      ('delistings','Nasdaq membership and delisting audit','YES','PARTIAL','PARTIAL','YES','Listing/delisting semantics are PIT membership-oriented, not complete announcement attribution.'),
      ('raw_adjusted_prices','prices adjustment repair v4','YES','PARTIAL','PARTIAL','YES','Strong repair provenance, but original dip study used its frozen W1/W2 price inputs, not a per-event v4 corporate-action mapping.')]
    with open(OUT/'DATA_SOURCE_INVENTORY.csv','w',newline='') as f:
      w=csv.writer(f);w.writerow(['category','source','source_available','pit_complete','W1_coverage','W2_coverage','known_gaps']);w.writerows(sources)
    rows=list(csv.DictReader(open(SRC)))
    out=[]
    for r in rows:
      # Conservative classification follows the locked rule: absence of a complete source is incomplete, never clean.
      out.append({'event_id':f"{r['window']}:{r['reference_rebalance_date']}:{r['ticker']}:{r['event_date']}",'window':r['window'],'ticker':r['ticker'],'event_date':r['event_date'],'original_dip_event':'YES','primary_status':'EVENT_DATA_INCOMPLETE','report_event':'NOT_IDENTIFIABLE','known_negative_information':'NOT_IDENTIFIABLE','corporate_action_mechanical':'NOT_IDENTIFIABLE','pit_clean_dip':'NO','price_event_qa':'UNCLEAR','mapping_quality':'PARTIAL','reason':'No PIT-complete, semantically comparable W1/W2 event source for report/profit-warning/announcement/corporate-action attribution.'})
    fields=list(out[0]);
    for name in ('ORIGINAL_DIP_EVENT_RECLASSIFICATION.csv','PRICE_EVENT_QA.csv'):
      with open(OUT/name,'w',newline='') as f: w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
    counts={}
    for win in ('W1_2014_2019','W2_2020_2026'):
      x=[r for r in out if r['window']==win]; n=len(x)
      counts[win]={'total_DIP_10_events':n,'unique_stocks':len(set(r['ticker'] for r in x)),'complete_report_coverage':0,'complete_profit_warning_coverage':0,'complete_corporate_action_coverage':0,'complete_announcement_coverage':0,'complete_price_QA':0,'fully_PIT_classifiable':0,'fully_PIT_classifiable_share':0.0,'known_negative_information':0,'report_events':0,'corporate_action_mechanical':0,'PIT_clean_dips':0,'event_data_incomplete':n,'mapping_ambiguous':0,'price_event_QA_fail':0}
    gate={'study':'DIP_EVENT_DATA_COMPLETENESS_AND_REVALIDATION_GATE','preregistration_sha256':sha(OUT/'PREREGISTRATION.md'),'original_event_source_sha256':sha(SRC),'coverage':counts,'gate':'DIP_EVENT_DATA_GATE_FAIL','exact_blocker':'No locally demonstrated PIT-complete and semantically comparable W1/W2 event series for reports, profit warnings/guidance, major announcements and corporate actions. Nasdaq discovery explicitly lacks structured historical corporate-action coverage; available MFN/Borsdata artifacts do not establish required W1/W2 completeness/timestamps/negative-event semantics.','revalidation_executed':False,'required_data_work':['PIT publication-time report calendar and announcement ledger across W1/W2','Frozen semantic tags for profit warnings/negative guidance without post-hoc NLP','Event-date PIT corporate-action ledger: dividends/ex-dates, splits, rights issues, spin-offs, bids and buybacks','Instrument/entity mapping with name-change and delisting continuity','Per-event mapping from price-repair/adjustment registry to original dip-price inputs'],'portfolio_prereg_status':'PREREGISTERED_NOT_ACTIVATED__MECHANISM_GATE_NOT_PASSED','portfolio_prereg_before':before,'portfolio_prereg_after':{p.name:sha(p) for p in (PORT/'PREREGISTRATION.json',PORT/'PLAN_FREEZE.json')}}
    gate['PORTFOLIO_PREREG_MUTATED']=gate['portfolio_prereg_before']!=gate['portfolio_prereg_after']
    (OUT/'DATA_GATE_RESULT.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2))
    (OUT/'DATA_GATE_RESULT_SHA256.txt').write_text(sha(OUT/'DATA_GATE_RESULT.json')+'  DATA_GATE_RESULT.json\n')
    (OUT/'EVENT_RECLASSIFICATION_SHA256.txt').write_text(sha(OUT/'ORIGINAL_DIP_EVENT_RECLASSIFICATION.csv')+'  ORIGINAL_DIP_EVENT_RECLASSIFICATION.csv\n')
    print(json.dumps({'gate': gate['gate'], 'mutated': gate['PORTFOLIO_PREREG_MUTATED']}, ensure_ascii=False))
if __name__=='__main__': main()
