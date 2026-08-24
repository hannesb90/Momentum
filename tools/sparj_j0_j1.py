#!/usr/bin/env python3
"""Track J J0 inventory plus J1 standalone OHLC extension. Never reads targets/models."""
from __future__ import annotations
import argparse,collections,gzip,hashlib,json,math,os,re
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];J=ROOT/'trackj';EOD=Path('/home/hannesb/momentum_prod_work/momentum_ml/cache/eodhd_archive/ST');MFN=Path('/home/hannesb/momentum_prod_work/momentum_ml/cache/mfn');FI=Path('/home/hannesb/momentum_prod_work/momentum_ml/cache/fi_insyn');BD=Path('/home/hannesb/momentum_prod_work/momentum_ml/cache/borsdata')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def gzread(p):
 with gzip.open(p,'rt',encoding='utf-8') as f:return json.load(f)
def gzwrite(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);raw=json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
 with p.open('wb') as fo:
  with gzip.GzipFile(filename='',mode='wb',fileobj=fo,mtime=0) as z:z.write(raw)
def catalog():
 out={}
 for group in ('active','delisted'):
  for r in json.loads((EOD/f'{group}_catalogue.json').read_text()):out[r['Code']]={**r,'group':group}
 return out
def v2_identity():
 master=json.loads((ROOT/'docs/probes/instrument_master.json').read_text());by_code={};by_isin=collections.defaultdict(set)
 for r in master:
  e=r.get('eodhd') or {};c=e.get('code');i=(e.get('isin') or '').upper()
  if c:by_code.setdefault(c,[]).append(r)
  if i and c:by_isin[i].add(c)
 return by_code,by_isin
def inspect_mfn(v2codes,terminal):
 files=[p for p in MFN.glob('*.json') if not p.name.startswith('_')];items=[];file_codes=set();bad=0
 for p in files:
  try:x=json.loads(p.read_text());z=x.get('items') or []
  except Exception:bad+=1;continue
  c=p.stem.removesuffix('.ST');file_codes.add(c);items.extend((c,r) for r in z)
 pubs=[r.get('published') for _,r in items if r.get('published')];reports=[];keys=('delårsrapport','bokslutskommuniké','kvartalsrapport','årsredovisning','interim report','year-end report','quarterly report','annual report')
 for c,r in items:
  if any(k in str(r.get('title','')).lower() for k in keys):reports.append((c,r))
 return {'source':'local legacy-normalized MFN cache; not verbatim feed RAW','files':len(files),'parse_failures':bad,'items':len(items),'unique_item_ids':len({r.get('id') for _,r in items if r.get('id')}),'published_range':[min(pubs) if pubs else None,max(pubs) if pubs else None],'items_with_structured_isin':sum(bool(r.get('isins')) for _,r in items),'items_with_structured_ticker':sum(bool(r.get('tickers')) for _,r in items),'report_like_events':len(reports),'v2_instruments_with_cache':len(v2codes&file_codes),'v2_terminal_instruments_with_cache':len(terminal&file_codes),'v2_terminal_instruments_with_report_event':len(terminal&{c for c,_ in reports}),'reproducibility':'Cache bytes can be hashed, but original HTTP response bytes, request timestamps/headers and append-only source manifest are absent. Must not be treated as verbatim RAW.','identity':'Structured MFN author tickers/ISIN exist per item, but cache file selection was query/name based and requires revalidation.'}
def inspect_fi(v2codes,terminal,by_isin):
 files=list(FI.glob('*.json'));rows=[];caps=0;empty=0
 for p in files:
  try:x=json.loads(p.read_text())
  except Exception:continue
  if not x:empty+=1
  if len(x)==80:caps+=1
  rows.extend(x)
 pubs=[r.get('publish_date') for r in rows if r.get('publish_date')];isins={(r.get('isin') or '').upper() for r in rows if r.get('isin')};codes=set().union(*(by_isin.get(i,set()) for i in isins)) if isins else set();canon={json.dumps(r,sort_keys=True,ensure_ascii=False) for r in rows}
 return {'source':'local legacy-normalized FI issuer-query cache; official portal was source','files':len(files),'empty_files':empty,'files_exactly_80_rows':caps,'rows':len(rows),'exact_duplicate_rows':len(rows)-len(canon),'publish_date_range':[min(pubs) if pubs else None,max(pubs) if pubs else None],'unique_isin':len(isins),'mapped_v2_instruments_by_isin':len(codes),'mapped_terminal_instruments_by_isin':len(codes&terminal),'rows_with_transaction_date':sum(bool(r.get('transaction_date')) for r in rows),'rows_with_publish_date':sum(bool(r.get('publish_date')) for r in rows),'timestamp_granularity':'date only; no publication clock time','corrections_fields_present':sorted({k for r in rows for k in r if any(q in k.lower() for q in ('correct','cancel','makul','rätt'))}),'reproducibility':'Parsed rows only; source HTML, request parameters/timestamps and immutable raw manifest absent. Files may be capped/truncated and were name-query keyed.'}
def inspect_dividends(v2codes,terminal,cat):
 events=[];missing=[]
 for c in sorted(v2codes):
  g=cat.get(c,{}).get('group');p=EOD/g/'div'/f'{c}.json.gz' if g else None
  if not p or not p.exists():missing.append(c);continue
  for r in gzread(p):
   if str(r.get('date',''))>='2020-01-01':events.append((c,r))
 years=collections.Counter(str(r.get('date',''))[:4] for _,r in events);codes={c for c,_ in events};decl=[r.get('declarationDate') for _,r in events if r.get('declarationDate')]
 return {'source':'immutable manifested EODHD dividend snapshot','events_since_2020':len(events),'instruments_with_event':len(codes),'terminal_instruments_with_event':len(codes&terminal),'active_instruments_with_event':len(codes-terminal),'year_rows':dict(sorted(years.items())),'declarationDate_nonnull':len(decl),'declarationDate_coverage':len(decl)/len(events) if events else 0,'recordDate_nonnull':sum(bool(r.get('recordDate')) for _,r in events),'paymentDate_nonnull':sum(bool(r.get('paymentDate')) for _,r in events),'ex_date_present':sum(bool(r.get('date')) for _,r in events),'period_values':dict(collections.Counter(str(r.get('period')) for _,r in events)),'missing_dividend_file':len(missing),'pit_assessment':'Ex-date/payment data are historical facts. Dividend-gap remains blocked where declarationDate is absent; ex-date must never backfill announcement knowledge.'}
def inspect_borsdata_dividend(by_isin):
 files=list(BD.glob('dividend_calendar_*.json'));events=[];ids=set()
 for p in files:
  try:x=json.loads(p.read_text())
  except Exception:continue
  for block in x.get('list') or []:
   ids.add(block.get('insId'));events.extend(block.get('values') or [])
 return {'source':'unmanifested legacy-normalized Börsdata cache','files':len(files),'insIds':len(ids),'events':len(events),'events_since_2020':sum(str(r.get('excludingDate',''))[:4]>='2020' for r in events),'fields':sorted({k for r in events for k in r}),'announcement_timestamp_present':False,'pit_assessment':'Contains ex-date and paid amount/type, not announcement time. Cannot establish when dividend change became public; zero amounts also require QA.'}
def ohlc_audit(build=False):
 from build_external_dependencies_manifest import verify_external_source
 verify_external_source();a=json.loads((ROOT/'validated/prices/prices_validated.json').read_text());aman=json.loads((ROOT/'validated/manifest_sparA.json').read_text());cat=catalog();terminal=set(json.loads((ROOT/'validated/terminal_events.json').read_text()));norm={};valid={};q=collections.Counter();year=collections.Counter();extreme=[];factor_jumps=[];source_files=[]
 for c,ars in sorted(a.items()):
  g=cat.get(c,{}).get('group');p=EOD/g/'eod'/f'{c}.json.gz' if g else None
  if not p or not p.exists():q['missing_source_file']+=1;continue
  source_files.append({'code':c,'group':g,'path':str(p.relative_to(EOD)),'sha256':sha(p),'bytes':p.stat().st_size});raw={r.get('date'):r for r in gzread(p)};nr=[];vr=[];prevf=None
  for ar in ars:
   d=ar['d'];r=raw.get(d);q['expected_A_rows']+=1
   if not r:q['missing_raw_date']+=1;continue
   vals={k:r.get(k) for k in ('open','high','low','close','adjusted_close','volume')};row={'d':d,'open':vals['open'],'high':vals['high'],'low':vals['low'],'close':vals['close'],'adjusted_close':vals['adjusted_close'],'volume':vals['volume'],'source_group':g};nr.append(row);year[d[:4]]+=1
   missing=[k for k,v in vals.items() if v is None]
   if missing:q['rows_missing_any_ohlcv']+=1;q.update('missing_'+k for k in missing);continue
   if any(not isinstance(vals[k],(int,float)) or not math.isfinite(vals[k]) for k in vals):q['nonfinite']+=1;continue
   if any(vals[k]<=0 for k in ('open','high','low','close','adjusted_close')):q['nonpositive_price']+=1;continue
   if vals['volume']<0:q['negative_volume']+=1;continue
   if not (vals['low']<=vals['open']<=vals['high'] and vals['low']<=vals['close']<=vals['high']):q['ohlc_identity_violation']+=1;continue
   if vals['close']!=ar['close'] or vals['adjusted_close']!=ar['adj'] or vals['volume']!=ar['v']:q['A_raw_mismatch']+=1;continue
   f=vals['adjusted_close']/vals['close'];row['adjustment_factor']=f;row['adjusted_open']=vals['open']*f;row['adjusted_high']=vals['high']*f;row['adjusted_low']=vals['low']*f
   rng=vals['high']/vals['low'];
   if rng>2:extreme.append({'code':c,'date':d,'high_low_ratio':rng,'open':vals['open'],'high':vals['high'],'low':vals['low'],'close':vals['close']})
   if prevf and (f/prevf>1.5 or f/prevf<2/3):factor_jumps.append({'code':c,'date':d,'factor_ratio':f/prevf})
   prevf=f;vr.append(row);q['validated_rows']+=1
  norm[c]=nr
  if vr:valid[c]=vr
 active=set(valid)-terminal;term=set(valid)&terminal
 qa={'status':'PASS' if q['validated_rows']==q['expected_A_rows'] and not (q['ohlc_identity_violation']+q['A_raw_mismatch']+q['rows_missing_any_ohlcv']) else 'FAIL','counts':dict(q),'instruments':len(valid),'active_instruments':len(active),'terminal_instruments':len(term),'terminal_instrument_coverage':len(term)/len(terminal) if terminal else None,'date_range':[min(r['d'] for rs in valid.values() for r in rs),max(r['d'] for rs in valid.values() for r in rs)],'year_rows':dict(sorted(year.items())),'extreme_high_low_ratio_gt_2_count':len(extreme),'extreme_examples':sorted(extreme,key=lambda x:x['high_low_ratio'],reverse=True)[:50],'adjustment_factor_jump_count':len(factor_jumps),'adjustment_factor_jump_examples':factor_jumps[:100],'semantics':{'open_high_low_close_volume':'unadjusted vendor observations','adjusted_close':'vendor total-return adjusted close','adjustment_factor':'adjusted_close/close','adjusted_open_high_low':'mechanical same-day scaling by adjustment_factor; normalization, not an ATR/ADX feature'},'survivorship':'Selection follows frozen A codes/dates, including terminal instruments; source group retained per row.'}
 if build:
  out=J/'ohlc_v1';assert not out.exists(),'no overwrite';out.mkdir(parents=True);gzwrite(out/'normalized/ohlc_normalized.json.gz',norm);gzwrite(out/'validated/ohlc_validated.json.gz',valid);dump(out/'qa/ohlc_qa.json',qa);dump(out/'raw_reference_manifest.json',{'classification':'IMMUTABLE EXTERNAL RAW SOURCE REFERENCE','source_root':str(EOD),'external_manifest_path':'validated/external_dependencies_manifest.json','external_manifest_sha256':sha(ROOT/'validated/external_dependencies_manifest.json'),'external_aggregate_sha256':json.loads((ROOT/'validated/external_dependencies_manifest.json').read_text())['active_dependencies'][0]['aggregate_sha256'],'sparA_manifest_sha256':sha(ROOT/'validated/manifest_sparA.json'),'sparA_dataset_sha256':aman['dataset_sha256'],'source_files':source_files})
  files=[]
  for p in sorted(out.rglob('*')):
   if p.is_file():files.append({'path':str(p.relative_to(out)),'sha256':sha(p),'bytes':p.stat().st_size})
  agg=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest();dump(out/'manifest.json',{'dataset':'Track J OHLC extension v1','version':'1.0.0','status':'IMMUTABLE_FROZEN' if qa['status']=='PASS' else 'QA_FAILED_NOT_APPROVED','feature_engineering':False,'target_read':False,'model_imports':False,'files':files,'aggregate_sha256':agg});(out/'manifest.sha256').write_text(sha(out/'manifest.json')+'  manifest.json\n')
 return qa
def inventory(build=False):
 cat=catalog();a=json.loads((ROOT/'validated/prices/prices_validated.json').read_text());v2codes=set(a);terminal=set(json.loads((ROOT/'validated/terminal_events.json').read_text()));by_code,by_isin=v2_identity();ohlc=ohlc_audit(build);mfn=inspect_mfn(v2codes,terminal);fi=inspect_fi(v2codes,terminal,by_isin);div=inspect_dividends(v2codes,terminal,cat);bddiv=inspect_borsdata_dividend(by_isin)
 families={
 'ATR_high_low':{'hypothesis':'Intraday range and true range may improve risk measurement/exits without using future prices.','required':['PIT O/H/L/C/adjusted close/volume','split/corporate-action semantics','stable instrument identity'],'resolution':'daily','pit_timestamp':'exchange close for same-day bar; usable only after close','already':'Immutable EODHD contains full fields; A retained close/adjusted close/volume only','missing':'Nothing material for a standalone OHLC extension; feature definition remains deliberately absent','local_sources':['manifested EODHD eod/splits files'],'external_candidates':['same EODHD endpoint only for future append snapshots'],'coverage':ohlc,'classification':'DATA REDAN TILLGÄNGLIG — BYGG QA' if not build else ('DATA REDAN TILLGÄNGLIG — QA FRYST' if ohlc['status']=='PASS' else 'KRÄVER ÅTGÄRD')},
 'Report_Attention_PEAD':{'hypothesis':'Report publication, initial reaction/attention and subsequent drift contain information distinct from long momentum.','required':['verbatim report event','publication timestamp+timezone','report type','stable ISIN/issuer','pre/post price and volume','optional expectations only from genuine consensus source'],'resolution':'event timestamp plus daily/intraday execution boundary','pit_timestamp':'actual public release timestamp; period end/report_Date alone is insufficient','already':{'MFN':mfn,'V2_report_date':'date-level as-of field exists but is not exact publication time'},'missing':['verbatim MFN raw responses and request manifests','event classification QA','complete identity and terminal coverage','consensus/expectations source for true surprise'],'classification':'DELVIS BYGGBAR'},
 'Dividend_gap':{'hypothesis':'A publicly announced dividend change with weak initial reaction may drift.','required':['announcement timestamp','amount/current and prior comparable dividend','ordinary/special','ex/record/payment dates','currency','split adjustment','stable ISIN'],'resolution':'event timestamp plus daily prices','pit_timestamp':'announcement publication, not ex-date','already':{'EODHD':div,'Borsdata':bddiv},'missing':['announcement timestamp for most events','ordinary/special definition reconciliation','PIT comparable prior dividend and correction history'],'classification':'DATA SAKNAS / EJ PIT-FÖRSVARBAR'},
 'Insider_gap':{'hypothesis':'Publicly disclosed discretionary insider buying/selling plus weak initial reaction may predict drift.','required':['person/role/related','issuer/instrument/ISIN','transaction character','buy/sell','volume/price/currency','transaction date','publication/registration timestamp','corrections/cancellations'],'resolution':'event publication time plus daily prices','pit_timestamp':'when FI made filing public, not transaction date','already':fi,'missing':['verbatim FI HTML/API RAW','clock-time or defensible next-day timestamp policy','pagination completeness beyond apparent 80-row caps','correction/cancellation history','issuer request manifest and historical terminal coverage'],'classification':'DELVIS BYGGBAR'} }
 payload={'track':'J0_DATA_GAP_ANALYSIS','research_i_status':'SLUTFÖRT_NO_BATCH4','target_read':False,'model_code_imported':False,'v2_codes':len(v2codes),'terminal_codes':len(terminal),'families':families,'priority_order':['ATR_high_low','Report_Attention_PEAD','Insider_gap','Dividend_gap'],'stop_before_external_fetch':True};dump(J/'J0_DATA_GAP_ANALYSIS.json',payload);return payload
def main():
 p=argparse.ArgumentParser();p.add_argument('--build-ohlc',action='store_true');a=p.parse_args();x=inventory(a.build_ohlc);print(json.dumps({'status':'COMPLETE','classifications':{k:v['classification'] for k,v in x['families'].items()},'ohlc_qa':x['families']['ATR_high_low']['coverage']['status']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
