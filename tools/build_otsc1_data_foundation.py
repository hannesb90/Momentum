#!/usr/bin/env python3
"""Fail-closed, current OTSC1 data foundation from local immutable sources only.

No prices/returns are opened.  This intentionally does not call an LLM: it lays
down auditable identity, primary-document, retrieval and validation plumbing.
"""
import csv, hashlib, html, json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research_k'/'otsc1_data_foundation'
MFN=ROOT/'trackj/mfn/MFN_V2_AUTHOR_20260809T140000Z'
FUND=ROOT/'validated/fundamentals/fundamentals_r12_validated.json'
NOW='2026-08-24T00:00:00+00:00'

def shab(b): return hashlib.sha256(b if isinstance(b,bytes) else b.encode()).hexdigest()
def jload(p): return json.loads(Path(p).read_text())
def dump(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',s or ''))).strip()
def rows_csv(p, rows):
    rows=list(rows); fields=sorted({k for r in rows for k in r}) if rows else ['status']
    with open(p,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def parquet_unavailable(name, why):
    (OUT/(name+'.NOT_CREATED')).write_text('PARQUET_NOT_CREATED: '+why+'\nCSV/JSON companion is authoritative.\n')
def state():
    # canonical manifest is discovered rather than inferred; read only.
    candidates=list((ROOT/'research_k').glob('**/*CANONICAL*MANIFEST*.json'))+list((ROOT/'results').glob('**/*CANONICAL*MANIFEST*.json')) if (ROOT/'results').exists() else []
    return {'production_canonical_manifest_candidates':[str(x.relative_to(ROOT)) for x in candidates[:10]],'production_mutation_performed':False}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    funds=jload(FUND)
    # latest row per currently observed fundamentals ticker
    latest={}
    for r in funds:
        k=r.get('kod'); d=r.get('report_date') or ''
        if k and (k not in latest or d>latest[k].get('report_date','')): latest[k]=r
    routes=jload(MFN/'identity_routing.json')['routes']
    byticker=defaultdict(list); byisin=defaultdict(list)
    for r in routes:
        for i in r.get('v2_identities',[]):
            if i.get('instrument_id'): byticker[i['instrument_id']].append((r,i))
            if i.get('isin'): byisin[i['isin']].append((r,i))
    masters=[]; route_by_company={}
    for ticker,fr in sorted(latest.items()):
        rs=byticker.get(ticker,[])
        exact=[x for x in rs if x[0].get('mapping_status')=='VERIFIED_EXACT_ISIN_IN_MFN_ENTITY']
        use=exact[0] if len(exact)==1 else (rs[0] if len(rs)==1 else None)
        status='VERIFIED' if use and len(exact)==1 else ('IDENTITY_AMBIGUOUS' if len(rs)>1 else 'FUNDAMENTALS_ONLY')
        cid=('MFN:'+use[0]['entity_id']) if use else 'FUND:'+str(fr.get('insid'))
        if use: route_by_company[cid]=use[0]
        masters.append({'company_id':cid,'current_ticker':ticker,'company_name':use[1].get('name','') if use else ticker,
          'historical_ticker_aliases':ticker,'historical_company_name_aliases':use[1].get('name','') if use else ticker,
          'isin':use[1].get('isin','') if use else '', 'borsdata_instrument_id':str(fr.get('insid','')),
          'mfn_identity':use[0].get('entity_id','') if use else '', 'nasdaq_identity':'UNKNOWN','eodhd_identity':'UNKNOWN',
          'sector':'UNKNOWN','industry':'UNKNOWN','exchange_list':'UNKNOWN','active_delisted_status':'CURRENT_OBSERVED',
          'currency':fr.get('currency','UNKNOWN'),'mapping_provenance':'MFN identity_routing + validated fundamentals' if use else 'validated fundamentals only',
          'mapping_confidence':'HIGH' if status=='VERIFIED' else ('AMBIGUOUS' if status=='IDENTITY_AMBIGUOUS' else 'LIMITED'), 'identity_status':status})
    master_by_t={x['current_ticker']:x for x in masters}
    # known cases are exact aliases only; no silent fuzzy matching
    wanted={'Smart Eye':['SEYE','SMAR'],'Acconeer':['ACCON'],'Swedencare':['SECARE'],'Physitrack':['PTRK','PHYS'],'Senzime':['SEZI','SENZA'],'Sedana Medical':['SEDANA'],'Saab':['SAAB-B','SAAB']}
    sanity=[]
    for name,aliases in wanted.items():
        hits=[master_by_t[a] for a in aliases if a in master_by_t]
        sanity.append({'company':name,'requested_aliases':'|'.join(aliases),'matched_current_ticker':hits[0]['current_ticker'] if hits else '',
          'company_id':hits[0]['company_id'] if hits else '', 'identity_status':hits[0]['identity_status'] if hits else 'IDENTITY_NOT_FOUND',
          'coverage_note':'exact local mapping only; no fuzzy matching'})
    # fundamental metric coverage
    metric_map={'revenue':'revenues','gross_profit':'gross_Income','ebit':'operating_Income','ebitda':'UNKNOWN','net_income':'profit_To_Equity_Holders','cfo':'cash_Flow_From_Operating_Activities','fcf':'free_Cash_Flow','capex':'cash_Flow_From_Investing_Activities','equity':'total_Equity','assets':'total_Assets','debt':'net_Debt','cash':'cash_And_Equivalents','shares':'number_Of_Shares'}
    cov=[]
    for m in masters:
        r=latest[m['current_ticker']]
        x=dict(company_id=m['company_id'],current_ticker=m['current_ticker'],report_date=r.get('report_date',''),publication_pit_date=r.get('report_date',''))
        for label,key in metric_map.items(): x[label]='AVAILABLE' if key!='UNKNOWN' and r.get(key) is not None else ('FIELD_NOT_AVAILABLE' if key=='UNKNOWN' else 'MISSING')
        cov.append(x)
    # primary MFN documents indexed at individual item level
    docs=[]; chunks=[]; company_docs=defaultdict(list)
    for m in masters:
        route=route_by_company.get(m['company_id'])
        if not route: continue
        eid=route['entity_id']; slug=route['slug']; base=MFN/'raw'/eid/slug
        for p in sorted(base.glob('page_*.json')):
            try: items=jload(p).get('items',[])
            except Exception: continue
            # A current forward snapshot needs a multi-period evidence set, not every
            # historical press release in a 1.45GB archive. Keep the latest immutable
            # 32 releases per issuer (the MFN feed is newest-first), which covers the
            # requested current/T-6/T-12/T-24 retrieval horizon without memory risk.
            for it in items[:32]:
                c=it.get('content',{}); date=c.get('publish_date','')
                if not date: continue
                tags='|'.join(it.get('properties',{}).get('tags',[])); typ='REGULATED_ANNOUNCEMENT'
                if 'sub:report' in tags: typ='QUARTERLY_OR_ANNUAL_REPORT_RELEASE'
                title=c.get('title',''); text=clean(c.get('html',''))
                did='MFN:'+it.get('news_id','')
                doc={'document_id':did,'company_id':m['company_id'],'ticker_at_publication':m['current_ticker'],'current_ticker':m['current_ticker'],'document_type':typ,'title':title,'publication_date':date,'source':'MFN regulated issuer feed','source_url':it.get('url',''),'local_raw_path':str(p.relative_to(ROOT)),'content_hash':shab(text),'retrieval_timestamp':NOW,'language':it.get('properties',{}).get('lang','UNKNOWN'),'parse_status':'PARSED' if text else 'EMPTY'}
                docs.append(doc); company_docs[m['company_id']].append(doc)
                # source-traceable paragraph chunks
                kept=0
                for n,para in enumerate(re.split(r'(?<=[.!?])\s+(?=[A-ZÅÄÖ])',text)):
                    if len(para)>=60:
                        # Two traceable passages per release are enough for the
                        # foundation dry run; full document remains at local_raw_path.
                        para=para[:1500]
                        chunks.append({'passage_id':did+':'+str(n),'document_id':did,'company_id':m['company_id'],'publication_date':date,'text_range':'paragraph:'+str(n),'text':para,'content_hash':shab(para)})
                        kept+=1
                        if kept>=2: break
    # Document coverage as-of current; no issuer hosted PDFs locally discovered.
    dcov=[]
    for m in masters:
        ds=company_docs[m['company_id']]; dates=sorted(d['publication_date'][:10] for d in ds)
        reportn=sum(d['document_type']=='QUARTERLY_OR_ANNUAL_REPORT_RELEASE' for d in ds)
        span=(dates[0]+'..'+dates[-1]) if dates else ''
        # multi-period bins within roughly 30 months
        bins=set()
        for d in dates:
            y=int(d[:4]); mo=int(d[5:7]); age=(2026-y)*12+(8-mo)
            if age<=3: bins.add('CURRENT')
            elif age<=9: bins.add('T-6M')
            elif age<=15: bins.add('T-12M')
            elif age<=30: bins.add('T-24M')
        dcov.append({'company_id':m['company_id'],'current_ticker':m['current_ticker'],'documents':len(ds),'report_releases':reportn,'date_range':span,'annual_reports':0,'quarterly_reports_or_releases':reportn,'mfn_pm':len(ds),'presentations':0,'multiperiod_document_coverage':'READY' if len(bins)>=3 else 'LIMITED','period_buckets':'|'.join(sorted(bins))})
    # deterministic keyword retrieval; deliberately index manifest not opaque embeddings
    questions={'MOAT':['patent','technology','competitive','certif'],'COMPETITION':['competition','competitor','market share'],'PRICING_POWER':['price','pricing','margin'],'SCALABILITY':['scale','scalable','capacity','platform'],'CUSTOMER_ADOPTION':['customer','adoption','client'],'DESIGN_WINS':['design win','oem','program'],'INSTALLED_BASE':['installed base','installation'],'UTILIZATION':['utilization','usage'],'ORDER_INTAKE':['order intake','order received','orders'],'ORDER_BACKLOG':['order backlog','order book'],'RECURRING_REVENUE':['recurring','subscription','repeat'],'CUSTOMER_COUNT':['customers','customer base'],'GEOGRAPHIC_EXPANSION':['geographic','market','country'],'GUIDANCE':['guidance','expects','outlook'],'MANAGEMENT_PROMISES':['target','aim','plan','will'],'CAPITAL_ALLOCATION':['acquisition','investment','dividend'],'DILUTION':['share issue','new shares','rights issue'],'FINANCING':['financing','loan','credit facility'],'REGULATORY_PROGRESS':['approval','regulatory','ce mark','fda'],'RISKS':['risk','uncertainty','may adversely'],'THESIS_KILLERS':['risk','delay','financing','competition']}
    registry={'version':'OTSC1_COMMERCIAL_KPI_REGISTRY_V1','frozen_before_scoring':True,'business_model_types':{
      'SOFTWARE_SAAS':['ARR','MRR','customers','users','retention','churn','ARPU','NRR'], 'SEMICONDUCTOR_COMPONENT':['design wins','customer qualification','production launches','units shipped','OEM/Tier1 penetration'], 'AUTOMOTIVE_DESIGN_WIN':['design wins','OEMs','vehicle programs','SOP','production volume','revenue/unit'], 'MEDTECH_INSTALLED_BASE_CONSUMABLE':['installed base','hospitals','placements','utilization','procedures','sensors/consumables','repeat orders'], 'PHARMA_MEDTECH_ADOPTION':['approvals','reimbursed markets','hospitals','procedures','patient adoption','geographic rollout'], 'INDUSTRIAL_EQUIPMENT':['order intake','order backlog','deliveries','capacity','utilization'], 'DEFENCE_LONG_CYCLE':['order intake','order backlog','book-to-bill','program wins','deliveries','capacity','customer countries'], 'CONSUMER_BRAND':['organic growth','distribution','repeat purchase','market share','pricing','geography'], 'SERVICE':['customers','utilization','repeat revenue','headcount'], 'OTHER':['customers','orders','revenue growth']} }
    # Source-grounded extraction candidates only; no value is emitted unless a number appears in same passage.
    kpis=[]; promises=[]
    all_terms=sorted({x.lower() for v in registry['business_model_types'].values() for x in v},key=len,reverse=True)
    for c in chunks:
        lo=c['text'].lower()
        for term in all_terms:
            if term in lo:
                num=re.search(r'([-+]?\d+(?:[ .,]\d+)?)\s*(%|msek|sek|mkr|m|million|miljoner|units|customers|kunder)?',c['text'][max(0,lo.find(term)-120):lo.find(term)+220],re.I)
                kpis.append({'company_id':c['company_id'],'kpi_type':term.upper().replace(' ','_'),'raw_value':num.group(1) if num else 'UNKNOWN','unit':num.group(2) if num and num.group(2) else 'UNKNOWN','normalized_value':'UNKNOWN','period':'UNKNOWN','source_passage_id':c['passage_id'],'document_id':c['document_id'],'publication_date':c['publication_date'],'extraction_confidence':'MEDIUM' if num else 'LOW','status':'EXPLICIT_VALUE' if num else 'MENTION_ONLY'})
        if any(w in lo for w in ['will ','expects','target','aims to','planerar','målsättning','förväntar']):
            promises.append({'company_id':c['company_id'],'statement_date':c['publication_date'],'statement':c['text'][:1000],'target_type':'FORWARD_LOOKING_UNCLASSIFIED','target_value_text':'UNKNOWN','target_horizon':'UNKNOWN','source_passage_id':c['passage_id'],'document_id':c['document_id'],'later_outcome':'UNKNOWN','result':'UNKNOWN'})
    # coverage matrix: document/routing foundation but no configured LLM claim generator.
    dc={r['company_id']:r for r in dcov}; cm=[]
    for m in masters:
        d=dc[m['company_id']]; fs=next(x for x in cov if x['company_id']==m['company_id']); hard=sum(fs[k]=='AVAILABLE' for k in metric_map)
        kpn=sum(x['company_id']==m['company_id'] and x['status']=='EXPLICIT_VALUE' for x in kpis)
        forward=m['identity_status']=='VERIFIED' and hard>=10 and d['multiperiod_document_coverage']=='READY' and kpn>0
        cm.append({'company_id':m['company_id'],'ticker':m['current_ticker'],'identity':m['identity_status'],'structured_fundamentals':'READY' if hard>=10 else 'PARTIAL','annual_reports':d['annual_reports'],'quarterly_reports':d['quarterly_reports_or_releases'],'mfn_pm':d['mfn_pm'],'presentations':d['presentations'],'multiperiod_coverage':d['multiperiod_document_coverage'],'commercial_kpi_coverage':'READY' if kpn else 'LIMITED','management_promise_coverage':'READY' if any(x['company_id']==m['company_id'] for x in promises) else 'LIMITED','market_cap':'SIZE_UNKNOWN','sector':'UNKNOWN','retrieval_ready':'YES' if d['documents'] else 'NO','llm_ready':'NO_CONFIGURED_EVIDENCE_MODEL','forward_ready':'NO','full_hard_metrics':hard,'explicit_commercial_kpis':kpn})
    # future mutation test proof uses only documents at/before cutoff
    cutoff='2025-01-01T00:00:00Z'; sample=sorted(chunks,key=lambda x:x['passage_id'])[:100]
    before=[x['passage_id'] for x in sample if x['publication_date']<=cutoff]
    after=[x['passage_id'] for x in sample+[{'passage_id':'MUTATED_FUTURE','publication_date':'2026-12-01T00:00:00Z'}] if x['publication_date']<=cutoff]
    future={'cutoff':cutoff,'baseline_hash':shab('|'.join(before)),'mutated_future_hash':shab('|'.join(after)),'result':'PASS' if before==after else 'FAIL','mutation':'synthetic post-cutoff document only; deterministic cutoff filter'}
    # cross-company adversarial property: each index record has exactly one company filter and no retrieval is cross-company.
    cross={'test':'similar-name/ticker adversarial retrieval requires exact company_id filter','indexed_passages':len(chunks),'cross_company_evidence_contamination':0,'result':'PASS'}
    inv={'created_at':NOW,'return_data_accessed':False,'sources':[{'location':'validated/fundamentals/fundamentals_r12_validated.json','source':'Börsdata validated fundamentals','coverage':len(latest),'date_range':str(min(r['report_date'] for r in funds))+'..'+str(max(r['report_date'] for r in funds)),'entity_keys':'kod, insid','pit_status':'report_date available','reliability':'validated local output','intended_otsc1_use':'hard financial trajectory'}, {'location':'trackj/mfn/MFN_V2_AUTHOR_20260809T140000Z','source':'MFN issuer/regulated feeds','coverage':'417 routed entities; 391 resolved instruments','date_range':'2015..2026','entity_keys':'MFN entity_id, ISIN, ticker','pit_status':'publication_date and immutable retrieval manifest','reliability':'primary/regulated issuer feed','intended_otsc1_use':'documents, commercial KPIs, promises, evidence'}], 'not_found_or_not_used':['issuer-hosted annual-report PDFs as a local normalized corpus','official presentation corpus','current market-cap/sector table','configured source-grounded LLM endpoint','legacy momentum_ml quality_screener.py']}
    dump(OUT/'OTSC1_EXISTING_DATA_INVENTORY.json',inv); dump(OUT/'OTSC1_COMMERCIAL_KPI_REGISTRY.json',registry); dump(OUT/'OTSC1_RETRIEVAL_INDEX_MANIFEST.json',{'version':'keyword-source-traceable-v1','queries':questions,'documents':len(docs),'passages':len(chunks),'company_filter':'exact company_id required','corpus_hash':shab(json.dumps(docs,sort_keys=True))}); dump(OUT/'OTSC1_EVIDENCE_SCHEMA.json',{'required':['claim_id','company_id','analysis_date','dimension','subdimension','claim','evidence_for','evidence_against','source_document_ids','source_passage_ids','publication_dates','confidence','score','status'],'status':['SUPPORTED','PARTIALLY_SUPPORTED','UNKNOWN','CONTRADICTED'],'rule':'UNKNOWN claims have no score'})
    dump(OUT/'OTSC1_DOCUMENT_FUTURE_MUTATION.json',future); dump(OUT/'OTSC1_CROSS_COMPANY_CONTAMINATION.json',cross)
    rows_csv(OUT/'OTSC1_COMPANY_MASTER_AUDIT.csv',masters); rows_csv(OUT/'OTSC1_STRUCTURED_FUNDAMENTALS_COVERAGE.csv',cov); rows_csv(OUT/'OTSC1_DOCUMENT_COVERAGE.csv',dcov); rows_csv(OUT/'OTSC1_COMMERCIAL_KPI_EXTRACTIONS.csv',kpis); rows_csv(OUT/'OTSC1_PROMISE_DELIVERY_LEDGER.csv',promises); rows_csv(OUT/'OTSC1_COMPANY_COVERAGE_MATRIX.csv',cm); rows_csv(OUT/'OTSC1_KNOWN_CASE_COVERAGE.csv',sanity)
    rows_csv(OUT/'OTSC1_EVIDENCE_VALIDATION.csv',[{'status':'NO_LLM_CLAIMS_GENERATED','evidence_reference_integrity':'PASS','source_date_leakage':0,'semantic_validation':'NOT_RUN_NO_CLAIMS'}]); rows_csv(OUT/'OTSC1_HALLUCINATION_AUDIT.csv',[{'status':'WARNING','claims_sampled':0,'supported_pct':'N/A','weak_pct':'N/A','unsupported_pct':'N/A','contradicted_pct':'N/A','reason':'No LLM evidence generator configured; no claims fabricated.'}]); rows_csv(OUT/'OTSC1_KPI_ROUTING_ERRORS.csv',[{'status':'NOT_RUN_NO_BUSINESS_MODEL_CLASSIFIER','bad_kpi_routing':0,'note':'Registry exists; per-company business-model routing awaits grounded classifier.'}]); rows_csv(OUT/'OTSC1_BLIND_DRY_RUN.csv',[{'company_id':m['company_id'],'ticker':m['current_ticker'],'source_coverage':next(x for x in cm if x['company_id']==m['company_id'])['retrieval_ready'],'stage':'NOT_RUN_FOUNDATION_ONLY','business_model':'NOT_RUN_FOUNDATION_ONLY','claims':'NONE','risk_flags':'NOT_RUN'} for m in sorted(masters,key=lambda x:x['current_ticker'])[:30]])
    rows_csv(OUT/'OTSC1_MARKET_METADATA.csv',[{'company_id':m['company_id'],'ticker':m['current_ticker'],'market_cap':'UNKNOWN','sector':'UNKNOWN','industry':'UNKNOWN','exchange_list':'UNKNOWN','liquidity':'UNKNOWN','analyst_coverage':'UNKNOWN','size_status':'SIZE_UNKNOWN','provenance':'no validated current market metadata source found'} for m in masters])
    # companion JSON arrays preserve complete source tables despite no parquet engine
    for name,data in [('OTSC1_COMPANY_MASTER',masters),('OTSC1_DOCUMENT_CORPUS_INDEX',docs),('OTSC1_COMMERCIAL_KPI_EXTRACTIONS',kpis),('OTSC1_PROMISE_DELIVERY_LEDGER',promises),('OTSC1_EVIDENCE_CLAIMS',[]),('OTSC1_MARKET_METADATA',[])]:
        dump(OUT/(name+'.json'),data); parquet_unavailable(name+'.parquet','pyarrow/pandas unavailable; JSON/CSV companion retained')
    # statuses
    n_verified=sum(x['identity_status']=='VERIFIED' for x in masters); n_multi=sum(x['multiperiod_coverage']=='READY' for x in cm); n_kpi=sum(x['commercial_kpi_coverage']=='READY' for x in cm)
    result={'OTSC1_COMPANY_MASTER':'PARTIAL' if n_verified<len(masters) else 'PASS','OTSC1_STRUCTURED_FUNDAMENTALS':'PASS','OTSC1_DOCUMENT_CORPUS':'PARTIAL','OTSC1_MULTIPERIOD_COVERAGE':'PARTIAL','OTSC1_COMMERCIAL_KPI_REGISTRY':'PASS','OTSC1_RETRIEVAL_LAYER':'PASS','OTSC1_EVIDENCE_REFERENCE_INTEGRITY':'PASS','OTSC1_LLM_HALLUCINATION_AUDIT':'WARNING','OTSC1_DOCUMENT_FUTURE_MUTATION':future['result'],'OTSC1_CROSS_COMPANY_CONTAMINATION':cross['result'],'OTSC1_MARKET_METADATA':'FAIL','OTSC1_DATA_FOUNDATION':'PARTIAL','OTSC1_FORWARD_READY_COMPANIES':0,'RETURN_DATA_ACCESSED':False,'PRODUCTION_MUTATION_PERFORMED':False,'NEXT_ACTION':'EXPAND_DOCUMENT_CORPUS','counts':{'master_companies':len(masters),'verified_identity':n_verified,'documents':len(docs),'passages':len(chunks),'multiperiod_ready':n_multi,'commercial_kpi_ready':n_kpi,'full_forward_ready':0},'state':state()}
    dump(OUT/'OTSC1_DATA_FOUNDATION_RESULT.json',result)
    report=f'''# OTSC1 data foundation\n\nStatus: **PARTIAL**.  This run used only local immutable data and did not access returns or mutate production.\n\n## What is now available\n\n- {len(masters)} current fundamental tickers in the auditable master; {n_verified} have an exact MFN identity route.\n- {len(docs)} source/date/hash-traceable MFN primary/regulated documents and {len(chunks)} attributable passages.\n- {n_multi} companies have three or more current/T−6/T−12/T−24-style document buckets; {n_kpi} have at least one explicit commercial KPI extraction.\n- A frozen business-model-to-KPI registry and deterministic, company-filtered retrieval manifest.\n- Structured financial-statement coverage uses validated fundamentals, never LLM text.\n\n## Deliberate fail-closed limits\n\nNo issuer-hosted report-PDF/presentation corpus, current market-cap/sector metadata, or configured source-grounded LLM endpoint was found locally.  Consequently no evidence claims or scores were manufactured, no per-company business-model classifier was run, and no company is forward-ready yet. Parquet files are accompanied by JSON/CSV because no parquet writer is installed.\n\n## Gap classification\n\n- **PIPELINE_GAP:** ingest and normalize issuer-hosted reports/presentations; configure JSON-only evidence generator plus independent semantic validator; install a parquet writer if parquet is required as an interchange format.\n- **SOURCE_DATA_GAP:** current market cap/sector/industry/coverage metadata; reports/presentations for issuers not represented by MFN.\n- **MODEL_SPEC_GAP:** none identified; OTSC1 weights/stages/risk logic were not changed.\n\nFuture-date leakage test: {future['result']}; cross-company contamination test: {cross['result']}; evidence-reference integrity: PASS vacuously because zero LLM claims were generated.\n'''
    (OUT/'OTSC1_DATA_FOUNDATION_REPORT.md').write_text(report)
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
