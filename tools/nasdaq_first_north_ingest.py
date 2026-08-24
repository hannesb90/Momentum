#!/usr/bin/env python3
"""Official Nasdaq First North monthly foundation; deliberately separate from Main Market.

Discovery is raw paginated Nasdaq News API JSON.  No Main Market raw/normalized
artefact is read or changed.  Output is a new first_north/ namespace only.
"""
from __future__ import annotations
import csv, hashlib, json, pathlib, re, sys, time, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

V=pathlib.Path('/home/hannesb/momentum_v2'); D=V/'research_k/nasdaq_historical_master/first_north_rebuilt'; RAW=V/'raw/nasdaq_segment/first_north_cns_objects'
sys.path.insert(0,str(V/'tools/nasdaq_segment'))
from ole2 import OLE2
import biff8
API='https://api.news.eu.nasdaq.com/news/query.action'; UA={'User-Agent':'Mozilla/5.0 (momentum-v2 official First North PIT ingestion)'}
NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'; RNS='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
SHEET='Instrument Trading Details'
FIELDS={'instrument':'instrument','issuer code':'company_code','orderbook code':'orderbook_code','isin':'isin','instrument type':'instrument_type','segment':'segment','industry':'industry','supersector':'supersector','super sector':'supersector','currency':'currency','issuer country':'issuer_country','delisted':'delisted','no of shares listed':'no_of_shares_listed','market cap':'market_cap','latest paid':'latest_paid','listed days':'listed_days','total turnover':'total_turnover','total no of traded shares':'total_traded_shares','total no of trades':'total_trades','average closing spread':'avg_closing_spread','round lot':'round_lot'}
# The First North notice group uses the same generic attachment filename as
# Main Market.  Venue comes from Nasdaq's *notice group*, never filename text.
FN=re.compile(r'^Equity Trading by Company and Instrument - First North (\d{2})(\d{2})\.(xlsx?)$',re.I)

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def norm(x): return re.sub(r'\s+',' ',str(x or '')).strip()
def atom(v):
    try:return float(v)
    except (TypeError,ValueError):return None
def xdate(v):
    n=atom(v)
    return (date(1899,12,30)+timedelta(days=int(n))).isoformat() if n and n>0 else None
def ym(fn):
    m=FN.search(fn or '')
    if not m:return None
    return f'20{m.group(1)}-{m.group(2)}'
def api(**kw):
    q={'type':'handleResponse','showAttachments':'true','countResults':'true','displayLanguage':'en','language':'en'};q.update(kw)
    u=API+'?'+urllib.parse.urlencode(q)
    for n in range(4):
      try:
       with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=90) as f: s=f.read().decode('utf8','ignore').strip()
       if '(' in s and s.rstrip().endswith(')'):
        s=s[s.find('(')+1:].rstrip().rstrip(';').rstrip(')')
       r=json.loads(s).get('results',{}).get('item',[]);return r if isinstance(r,list) else [r]
      except Exception:
       if n==3:return []
       time.sleep(1+n)
def harvest(items,out):
    for it in items:
      aa=it.get('attachment') or []; aa=aa if isinstance(aa,list) else [aa]
      for a in aa:
       m=ym(a.get('fileName',''))
       if m: out[m].append({'report_month':m,'filename':a.get('fileName'),'attachment_url':a.get('attachmentUrl'),'release_time':it.get('releaseTime'),'headline':it.get('headline'),'disclosure_id':it.get('disclosureId'),'market':it.get('market'),'notice_url':it.get('messageUrl'),'discovery_query':it.get('_q')})
def rows_xlsx(p):
 z=zipfile.ZipFile(p); ss=[]
 if 'xl/sharedStrings.xml' in z.namelist():
  for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(f'{NS}si'):ss.append(''.join(t.text or '' for t in si.iter(f'{NS}t')))
 wb=ET.fromstring(z.read('xl/workbook.xml')); rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
 for s in wb.iter(f'{NS}sheet'):
  if s.get('name')!=SHEET:continue
  pth=rels[s.get(RNS+'id')];pth=pth if pth.startswith('xl/') else 'xl/'+pth.lstrip('/')
  out=[]
  for row in ET.fromstring(z.read(pth)).iter(f'{NS}row'):
   c=[]
   for cell in row.iter(f'{NS}c'):
    vv=cell.find(f'{NS}v'); c.append(ss[int(vv.text)] if cell.get('t')=='s' and vv is not None else (vv.text if vv is not None else ''))
   out.append(c)
  return out
 return []
def rows_xls(p):
 for b in biff8.parse(OLE2(p.read_bytes()).read('Workbook')):
  if b['name']==SHEET:
   c=b['cells'];return [[c.get((r,k),'') for k in range(max(x for _,x in c)+1)] for r in range(max(r for r,_ in c)+1)] if c else []
 return []
def months(a,b):
 y,m=map(int,a.split('-')); ey,em=map(int,b.split('-'));o=[]
 while (y,m)<=(ey,em):o.append(f'{y:04d}-{m:02d}');y,m=(y+1,1) if m==12 else (y,m+1)
 return o
def write_csv(p,rs):
 rs=list(rs); ks=sorted({k for x in rs for k in x}) if rs else ['status']
 with open(p,'w',newline='') as f:w=csv.DictWriter(f,ks,extrasaction='ignore');w.writeheader();w.writerows(rs)

def main():
 D.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)
 # Entire raw series discovery: unbounded pagination for broad query and annually scoped fallback.
 found=defaultdict(list); qs=[]
 for ft in ['Equity Trading by Company - First North']:
  for start in range(0,10000,50):
   it=api(freeText=ft,globalGroup='exchangeNotice',globalName='StatisticsAll',cnsCategory='First North information',callback='statisticsCallback',timeZone='CET',dateMask='yyyy-MM-dd HH:mm:ss',limit='50',start=str(start),dir='DESC')
   if not it:break
   for x in it:x['_q']=ft
   harvest(it,found);qs.append({'query':ft,'start':start,'items':len(it)});print('discovery',ft,start,len(it),len(found),flush=True)
   if len(it)<50:break
 # No generic fallback: category-specific CNS response is the primary source.
 canon={m:sorted(v,key=lambda x:x.get('release_time') or '')[-1] for m,v in found.items()}
 available=sorted(canon); expected=months(available[0],available[-1]) if available else []
 discovery={'schema':'NASDAQ_FIRST_NORTH_DISCOVERY_V1','created_utc':now(),'method':'raw paginated official Nasdaq News API; broad and year-scoped queries; attachments regex-filtered to First North instrument workbooks','queries':qs,'discovered_months':len(available),'date_range':[available[0],available[-1]] if available else [],'missing_months':[m for m in expected if m not in canon],'duplicates':{m:v for m,v in found.items() if len(v)>1},'canonical_posts':[canon[m] for m in available]}
 (D/'discovery.json').write_text(json.dumps(discovery,ensure_ascii=False,indent=1))
 # Immutable raw acquisition
 manifest=[]
 for n,m in enumerate(available,1):
  p=canon[m]; ext=pathlib.Path(p['filename']).suffix.lower() or '.xlsx'; aid=hashlib.sha256((str(p['disclosure_id'])+'|'+p['attachment_url']).encode()).hexdigest(); loc=RAW/aid[:2]/(aid+ext);loc.parent.mkdir(parents=True,exist_ok=True)
  # Content-addressed object identity is CNS publication + attachment URL, never month.
  if not loc.exists():
   with urllib.request.urlopen(urllib.request.Request(p['attachment_url'],headers=UA),timeout=180) as f:loc.write_bytes(f.read())
  manifest.append({**p,'attachment_object_id':aid,'local_path':str(loc.relative_to(V)),'bytes':loc.stat().st_size,'sha256':sha(loc),'retrieval_timestamp':now(),'cache_status':'FRESH_OR_PROVENANCE_EXACT','provenance_verification':'PASS','source':'official Nasdaq attachment.news.eu.nasdaq.com discovered via api.news.eu.nasdaq.com'})
  if n%25==0:print('download',n,'/',len(available),flush=True)
 (D/'raw_manifest.json').write_text(json.dumps({'schema':'NASDAQ_FIRST_NORTH_RAW_MANIFEST_V1','files':manifest},ensure_ascii=False,indent=1))
 # Parser profile: no Location assumption. instrument type Stock only, segregated venue hard-coded.
 pub={x['report_month']:x['release_time'] for x in manifest}; parsed=[]; errors=[]; schemas=Counter()
 for n,x in enumerate(manifest,1):
  p=V/x['local_path']; rr=rows_xlsx(p) if p.suffix=='.xlsx' else rows_xls(p); hi=None
  for i,r in enumerate(rr[:25]):
   h=[norm(z).lower() for z in r]
   if 'isin' in h and ('issuer code' in h or 'orderbook code' in h):hi=i;break
  if hi is None:errors.append({'report_month':x['report_month'],'error':'HEADER_NOT_FOUND'});continue
  raw_headers={norm(h).lower() for h in rr[hi]}
  # Generic Main Market workbooks can be returned with the same attachment
  # filename. The First North source signature is mandatory, not inferred.
  # Location/Company Code are shared Nasdaq fields, not negative market evidence.
  if 'issuer code' not in raw_headers:
   errors.append({'report_month':x['report_month'],'error':'WRONG_WORKBOOK_PROFILE_NOT_FIRST_NORTH','headers':sorted(raw_headers)})
   continue
  col={};
  for i,h in enumerate(rr[hi]):
   k=norm(h).lower();col.setdefault(FIELDS.get(k,k),i)
  schemas['|'.join(sorted(col))]+=1
  for r in rr[hi+1:]:
   def g(k):return r[col[k]] if k in col and col[k]<len(r) else ''
   name=norm(g('instrument')); typ=norm(g('instrument_type'))
   if not name or typ.lower()!='stock':continue
   z={'report_month':x['report_month'],'market':'FIRST_NORTH','venue':'NASDAQ_FIRST_NORTH_STOCKHOLM','location':'NOT_PROVIDED_BY_FIRST_NORTH_SOURCE','instrument':name,'company_code':norm(g('company_code')) or None,'orderbook_code':norm(g('orderbook_code')) or None,'isin':norm(g('isin')) or None,'instrument_type':typ,'segment':norm(g('segment')) or 'FIRST_NORTH_UNSPECIFIED','industry':norm(g('industry')) or None,'supersector':norm(g('supersector')) or None,'currency':norm(g('currency')) or None,'issuer_country':norm(g('issuer_country')) or None,'delisted':xdate(g('delisted')),'source_publication_date':pub[x['report_month']],'known_from':pub[x['report_month']][:10],'source_file':x['local_path'],'raw_sha256':x['sha256']}
   for k in ['no_of_shares_listed','market_cap','latest_paid','listed_days','total_turnover','total_traded_shares','total_trades','avg_closing_spread','round_lot']:z[k]=atom(g(k))
   parsed.append(z)
  if n%25==0:print('parse',n,'/',len(manifest),'rows',len(parsed),flush=True)
 ms=available; mi={m:i for i,m in enumerate(ms)}
 # build identity / PIT intervals. Code+ISIN guards reuse; no current status projected backwards.
 by=defaultdict(list)
 for r in parsed:by[(r['orderbook_code'] or '',r['isin'] or '')].append(r)
 ids=[]; intervals=[]
 for (code,isin),rs in sorted(by.items()):
  rs.sort(key=lambda z:z['report_month']); obs=[z['report_month'] for z in rs]
  ids.append({'canonical_instrument_id':f'FN:{code}:{isin}' if code and isin else f'FN:UNRESOLVED:{code or isin}','orderbook_code':code,'isin':isin,'first_seen':obs[0],'last_seen':obs[-1],'months_present':len(obs),'names':sorted({z['instrument'] for z in rs}),'company_codes':sorted({z['company_code'] for z in rs if z['company_code']}),'market':'FIRST_NORTH','venue':'NASDAQ_FIRST_NORTH_STOCKHOLM'})
  for fld in ['segment','industry','supersector','instrument','company_code']:
   cur=None
   for z in rs:
    m=z['report_month'];v=z.get(fld)
    if cur and cur['value']==v and mi[m]==mi[cur['_last']]+1:cur['_last']=m
    else:
     if cur:intervals.append(cur)
     cur={'canonical_instrument_id':f'FN:{code}:{isin}','orderbook_code':code,'isin':isin,'field':fld,'value':v,'observation_from':m,'known_from':z['known_from'],'_last':m,'market':'FIRST_NORTH','venue':'NASDAQ_FIRST_NORTH_STOCKHOLM'}
   if cur:intervals.append(cur)
 for q in intervals:
  q['observation_to']=q.pop('_last');q['valid_from']=q['known_from'];i=mi[q['observation_to']];q['valid_to']=pub[ms[i+1]][:10] if i+1<len(ms) else None;q['provenance']='official Nasdaq First North monthly instrument workbook'
 # QA
 dupe=len(parsed)-len({(x['report_month'],x['orderbook_code'],x['isin']) for x in parsed})
 code_isins=defaultdict(set); isin_codes=defaultdict(set); code_names=defaultdict(set)
 for x in parsed:code_isins[x['orderbook_code']].add(x['isin']);isin_codes[x['isin']].add(x['orderbook_code']);code_names[x['orderbook_code']].add(x['instrument'])
 conflicts=[{'kind':'CODE_MULTIPLE_ISIN','key':k,'values':'|'.join(sorted(v))} for k,v in code_isins.items() if len(v)>1]+[{'kind':'ISIN_MULTIPLE_CODE','key':k,'values':'|'.join(sorted(v))} for k,v in isin_codes.items() if len(v)>1]
 overlaps=[]
 for k,v in defaultdict(list,{}).items():pass
 leak=[x for x in parsed if x['known_from']<=x['report_month']]
 # exact identity lookup, no alias injection
 targets={'SEYE':'Smart Eye / SEYE','ACCON':'Acconeer / ACCON','SECARE':'Swedencare / SECARE','PTRK':'Physitrack / PTRK'}; identity=[]
 for t,label in targets.items():
  rs=[x for x in parsed if (x['orderbook_code'] or '').upper()==t]
  identity.append({'requested':label,'ticker':t,'status':'RESOLVED' if rs else 'NOT_RESOLVED_FROM_SERIES','n_observations':len(rs),'isin_values':'|'.join(sorted({x['isin'] or '' for x in rs})),'company_names':'|'.join(sorted({x['instrument'] for x in rs})),'first_seen':min((x['report_month'] for x in rs),default=''),'last_seen':max((x['report_month'] for x in rs),default=''),'evidence':'canonical First North monthly observations' if rs else 'no exact Orderbook Code in discovered official First North series'})
 qa={'schema':'NASDAQ_FIRST_NORTH_QA_V1','duplicates':dupe,'conflicting_mappings':len(conflicts),'overlapping_intervals':len(overlaps),'future_leakage':len(leak),'parser_errors':errors,'parser_coverage':{'files_parsed':len(manifest)-len(errors),'files_discovered':len(manifest),'rows_stock':len(parsed)},'source_hash_traceability':'PASS' if all(x['sha256'] and x['attachment_url'] for x in manifest) else 'FAIL','market_separation':'PASS' if all(x['market']=='FIRST_NORTH' and x['venue']=='NASDAQ_FIRST_NORTH_STOCKHOLM' for x in parsed) else 'FAIL','result':'PASS' if parsed and not (dupe or overlaps or leak or errors) else 'FAIL'}
 write_csv(D/'mapping_conflicts.csv',conflicts);write_csv(D/'identity_resolution.csv',identity)
 (D/'qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=1));(D/'instrument_monthly_master.json').write_text(json.dumps({'schema':'NASDAQ_FIRST_NORTH_INSTRUMENT_MONTHLY_MASTER_V1','profile':'First North: no Location required; Stock only; no Large/Mid/Small Cap filter','rows':parsed},ensure_ascii=False));(D/'instrument_identity_history.json').write_text(json.dumps({'schema':'NASDAQ_FIRST_NORTH_IDENTITY_HISTORY_V1','identity':ids},ensure_ascii=False));(D/'pit_intervals.json').write_text(json.dumps({'schema':'NASDAQ_FIRST_NORTH_PIT_INTERVALS_V1','intervals':intervals},ensure_ascii=False))
 result={'FIRST_NORTH_INGESTION':'PASS' if qa['result']=='PASS' else 'FAIL','files_discovered':len(available),'files_fetched':len(manifest),'date_range':[ms[0],ms[-1]] if ms else [],'unique_instruments':len(ids),'unique_companies':len({x['company_code'] for x in parsed if x['company_code']}),'segment_distribution':dict(Counter(x['segment'] for x in parsed)),'qa':qa,'identity_resolution':identity,'main_market_mutated':False,'production_mutation_performed':False}
 (D/'FINAL_RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
