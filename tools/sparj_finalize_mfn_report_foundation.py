#!/usr/bin/env python3
"""Finalize immutable MFN report-event foundation; never reads target/features/results."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,re,datetime
R=Path(__file__).resolve().parents[1];SRC=R/'trackj/validated_mfn_events_v1';RAW=R/'trackj/mfn/MFN_V2_AUTHOR_20260809T140000Z';OUT=R/'trackj/validated_mfn_report_events_v1'
UPD=re.compile(r'\b(rättelse|korrigering|correction|corrected|uppdatering|updated)\b',re.I)
PRIMARY={'Q1','Q2','Q3','Q4','YEAR_END'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def main():
 assert not OUT.exists();terminal=json.load(open(R/'validated/terminal_events.json'));universe=json.load(open(R/'research_k/sector_classification_v1/validated/sector_classification_intervals.json'));allcodes={x['instrument_id'] for x in universe};assert len(allcodes)==420
 # Verify raw received bytes against immutable page manifest.
 rawrows=[json.loads(x) for x in (RAW/'manifest.jsonl').read_text().splitlines() if x.strip()];bad=[]
 for x in rawrows:
  p=R/x['path']
  if not p.is_file() or p.stat().st_size!=x['response_bytes'] or sha(p)!=x['response_sha256']:bad.append(x['path'])
 assert not bad,bad[:5]
 src_manifest=json.load(open(SRC/'manifest.json'));vf=R/src_manifest['files'][0]['path'];assert sha(vf)==src_manifest['files'][0]['sha256']
 rows=[];excluded=Counter();seen=set();raw_report=0
 for line in vf.open():
  x=json.loads(line)
  if 'REPORT' not in x['derived_event_families']:continue
  raw_report+=1
  if x['instrument_id'] not in allcodes:excluded['NOT_V2_UNIVERSE']+=1;continue
  if not x['published_at'].endswith('Z') or x['market_known_time']!=x['published_at']:excluded['INVALID_PIT_TIMESTAMP']+=1;continue
  if x['mapping_status']!='VERIFIED_EXACT_ISIN_TO_MFN_ENTITY':excluded['IDENTITY_NOT_EXACT']+=1;continue
  if x['event_id'] in seen:excluded['DUPLICATE_EVENT_ID']+=1;continue
  seen.add(x['event_id']);td=terminal.get(x['instrument_id'],{}).get('event_date')
  preterminal=not td or x['published_at'][:10]<=td
  if not preterminal:excluded['AFTER_TERMINAL_DATE']+=1;continue
  typ=x['report_subtype'] or 'OTHER_RESULT_RELATED';basis=x['report_classification_basis'];provider=basis=='MFN_PROVIDER_TAG'
  row={k:x.get(k) for k in ['instrument_id','isin','event_id','group_id','published_at','market_known_time','market_known_time_basis','provider_event_type','provider_tags','headline','source','source_reference','retrieved_at','mapping_status','raw_path','raw_sha256']}
  row.update({'event_type':typ,'classification_basis':basis,'provider_report_tag':provider,'primary_earnings_release_eligible':provider and typ in PRIMARY,'is_correction_or_update':bool(UPD.search(x['headline'])),'terminal_date':td,'pre_terminal_event':preterminal,'timezone':'UTC','deduplication_key':x['event_id']})
  rows.append(row)
 # Deterministic same-day primary: earliest eligible publication; later same-day releases remain immutable updates.
 groups=defaultdict(list)
 for i,x in enumerate(rows):
  if x['primary_earnings_release_eligible']:groups[(x['instrument_id'],x['published_at'][:10])].append(i)
 for inds in groups.values():
  first=min(inds,key=lambda i:(rows[i]['published_at'],rows[i]['event_id']))
  for i in inds:rows[i]['primary_event_for_instrument_day']=(i==first)
 for x in rows:x.setdefault('primary_event_for_instrument_day',False)
 rows.sort(key=lambda x:(x['published_at'],x['instrument_id'],x['event_id']));OUT.mkdir(parents=True)
 out=OUT/'validated_mfn_report_events.jsonl';out.write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in rows))
 current=allcodes-set(terminal);cov={};
 for label,pred in [('ALL_REPORT',lambda x:True),('PROVIDER_REPORT',lambda x:x['provider_report_tag']),('PRIMARY_EARNINGS_RELEASE',lambda x:x['primary_event_for_instrument_day'])]:
  z=[x for x in rows if pred(x)];codes={x['instrument_id'] for x in z};cy={}
  for y in range(2020,2027):
   yz=[x for x in z if x['published_at'].startswith(str(y))];cy[str(y)]={'events':len(yz),'instruments':len({x['instrument_id'] for x in yz}),'terminal_instruments':len({x['instrument_id'] for x in yz}&set(terminal))}
  cov[label]={'events':len(z),'instruments':len(codes),'current_instruments':len(codes&current),'terminal_instruments':len(codes&set(terminal)),'missing_current':sorted(current-codes),'missing_terminal':sorted(set(terminal)-codes),'per_year':cy}
 qa={'version':'VALIDATED_MFN_REPORT_EVENTS_V1','status':'PASS_MED_BEGRAENSNING','universe':{'total':420,'current':352,'terminal':68},'raw_pages_verified':len(rawrows),'raw_bytes_verified':sum(x['response_bytes'] for x in rawrows),'raw_report_candidates':raw_report,'included_rows':len(rows),'excluded':dict(excluded),'event_type_counts':dict(Counter(x['event_type'] for x in rows)),'classification_basis':dict(Counter(str(x['classification_basis']) for x in rows)),'correction_update_rows':sum(x['is_correction_or_update'] for x in rows),'same_day_extra_releases_retained_not_primary':sum(x['primary_earnings_release_eligible'] and not x['primary_event_for_instrument_day'] for x in rows),'coverage':cov,'pit':{'published_at_explicit_utc':all(x['published_at'].endswith('Z') for x in rows),'market_known_equals_published':all(x['market_known_time']==x['published_at'] for x in rows),'filemtime_used':False,'report_period_used_as_known_time':False},'identity':{'exact_only':True,'fuzzy_used':False},'survivorship':'Terminal coverage reported explicitly; after-terminal events excluded, never silently converted to survivor-only population.','target_feature_result_data_read':False}
 dump(OUT/'qa_summary.json',qa)
 manifest={'version_id':'MFN_REPORT_EVENTS_V1_IMMUTABLE_2026-08-09','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs':[{'path':str((RAW/'manifest.jsonl').relative_to(R)),'sha256':sha(RAW/'manifest.jsonl')},{'path':str(vf.relative_to(R)),'sha256':sha(vf)},{'path':'validated/terminal_events.json','sha256':sha(R/'validated/terminal_events.json')}],'outputs':[{'path':str(out.relative_to(R)),'sha256':sha(out),'bytes':out.stat().st_size,'rows':len(rows)},{'path':str((OUT/'qa_summary.json').relative_to(R)),'sha256':sha(OUT/'qa_summary.json'),'bytes':(OUT/'qa_summary.json').stat().st_size}]}
 dump(OUT/'manifest.json',manifest);(OUT/'manifest.sha256').write_text(sha(OUT/'manifest.json')+'  manifest.json\n');print(json.dumps(qa,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
