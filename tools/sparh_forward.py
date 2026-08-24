#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,fcntl,hashlib,json,os,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];H=ROOT/'trackh';LOCK=H/'H0_LOCK.json';INDEX=H/'journal/INDEX.jsonl'
FIRST=dt.date(2026,9,4);INTERVAL=dt.timedelta(days=28);N=30
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 data=(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
 with os.fdopen(fd,'wb') as f:f.write(data)
 return sha(p)
def parse_ts(x):return dt.datetime.fromisoformat(x)
def scheduled(d):
 delta=(d-FIRST).days
 return d>=FIRST and delta%28==0
def phase(d):return ((d-FIRST).days//28)%2==0
def pct_rank(vals):
 ok=sorted((v,i) for i,v in enumerate(vals) if v is not None);out=[None]*len(vals);j=0;n=len(ok)
 while j<n:
  z=j+1
  while z<n and ok[z][0]==ok[j][0]:z+=1
  avg=((j+1)+z)/2/n
  for _,i in ok[j:z]:out[i]=avg
  j=z
 return out
def median(v):
 x=sorted(z for z in v if z is not None);return statistics.median(x) if x else None
def latest_at_or_before(rs,boundary):
 x=[r for r in rs if r['d']<=boundary];return x[-1] if x else None
def momentum_detail(rs,panel,days):
 now=latest_at_or_before(rs,panel);goal=(dt.date.fromisoformat(panel)-dt.timedelta(days=days)).isoformat();old=latest_at_or_before(rs,goal)
 if not now or not old:return None,{'goal_date':goal,'current':now,'lookback':old,'valid':False}
 lag=(dt.date.fromisoformat(goal)-dt.date.fromisoformat(old['d'])).days
 valid=lag<=10 and old['adj']>0
 return (now['adj']/old['adj']-1 if valid else None),{'goal_date':goal,'current':now,'lookback':old,'lookback_lag_days':lag,'valid':valid}
def json_counts(p):
 if p.suffix!='.json':return {}
 x=json.loads(p.read_text())
 if isinstance(x,list):return {'json_type':'list','row_count':len(x)}
 if isinstance(x,dict):
  out={'json_type':'object','top_level_count':len(x)};nested=sum(len(v) for v in x.values() if isinstance(v,list))
  if nested:out['nested_row_count']=nested
  return out
 return {'json_type':type(x).__name__}
def verify_v4_freeze(p):
 m=json.loads(p.read_text());bad=[]
 items=[m['generator'],*m['inputs'],*m['controls']]
 for result in m['outputs'].values():items.extend(result['files'])
 for x in items:
  q=ROOT/x['path']
  actual={'bytes':q.stat().st_size,'sha256':sha(q),**json_counts(q)} if q.is_file() else {}
  for k in ('bytes','sha256','json_type','row_count','top_level_count','nested_row_count'):
   if k in x and actual.get(k)!=x[k]:bad.append([x['path'],k,x[k],actual.get(k)]);break
 if bad:raise SystemExit('FAIL V4 freeze '+json.dumps(bad))
 return len(items)
def verify_abc():
 def load(p):return json.loads((ROOT/p).read_text())
 a,b,bx,c=(load(p) for p in ('validated/manifest_sparA.json','validated/manifest_sparB.json','validated/manifest_sparB_extra.json','validated/manifest_sparC.json'))
 assert sha(ROOT/'validated/prices/prices_validated.json')==a['dataset_sha256']
 for key in ('ar','kvartal','r12'):
  x=b['tabeller'][key];assert sha(ROOT/'validated/fundamentals'/x['fil'])==x['file_sha256']
 for x in bx['artefakter'].values():assert sha(ROOT/x['fil'])==x['sha256']
 for x in c['paneler'].values():assert sha(ROOT/x['fil'])==x['sha256']
 for x in c['auxiliary_artifacts'].values():assert sha(ROOT/x['fil'])==x['sha256']
 assert sha(ROOT/'docs/probes/feature_registry.json')==c['feature_registry']['sha256']
 from build_external_dependencies_manifest import verify_external_source
 verify_external_source();return 13
def lock_verify():
 if not LOCK.is_file():raise SystemExit('FAIL H0 lock missing')
 l=json.loads(LOCK.read_text());bad=[]
 for x in l['locked_files']:
  p=ROOT/x['path']
  if not p.is_file():bad.append([x['path'],'MISSING'])
  elif sha(p)!=x['sha256']:bad.append([x['path'],'HASH',x['sha256'],sha(p)])
 if bad:raise SystemExit('FAIL H0 '+json.dumps(bad))
 freeze=ROOT/l['freeze_manifest_path'];assert sha(freeze)==l['freeze_manifest_sha256'];l['verified_v4_files']=verify_v4_freeze(freeze);l['verified_abc_artifacts']=verify_abc()
 return l
def records():return [json.loads(x) for x in INDEX.read_text().splitlines() if x.strip()]
def append_event(event,panel,path,artifact_sha):
 with INDEX.open('a+',encoding='utf-8') as f:
  fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);rs=[json.loads(x) for x in f if x.strip()]
  prev=rs[-1]['chain_hash'] if rs else '0'*64;base={'seq':len(rs)+1,'event':event,'panel_date':panel,'path':str(Path(path).relative_to(ROOT)),'artifact_sha256':artifact_sha,'prev_chain_hash':prev};base['chain_hash']=hashlib.sha256(json.dumps(base,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  f.seek(0,os.SEEK_END);f.write(json.dumps(base,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno());fcntl.flock(f,fcntl.LOCK_UN)
 return base
def verify_manifest(mp):
 m=json.loads(mp.read_text())
 if m.get('event')=='PREDICTION':
  for x in m['files']:
   p=mp.parent/x['path']
   if not p.is_file() or sha(p)!=x['sha256'] or p.stat().st_size!=x['bytes']:raise SystemExit('FAIL prediction artifact '+str(p))
   if x.get('rows') is not None and len(json.loads(p.read_text()))!=x['rows']:raise SystemExit('FAIL prediction row count '+str(p))
def verify_index():
 prev='0'*64
 for i,r in enumerate(records(),1):
  if r['seq']!=i or r['prev_chain_hash']!=prev:raise SystemExit('FAIL journal chain')
  z={k:v for k,v in r.items() if k!='chain_hash'};want=hashlib.sha256(json.dumps(z,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if want!=r['chain_hash']:raise SystemExit('FAIL journal hash')
  p=ROOT/r['path']
  if not p.is_file() or sha(p)!=r['artifact_sha256']:raise SystemExit('FAIL journal artifact '+r['path'])
  if r['event']=='PREDICTION':verify_manifest(p)
  prev=r['chain_hash']
 return len(records())
def validate_inbox(panel):
 b=H/'inbox'/panel;m=json.loads((b/'input_manifest.json').read_text());assert m['panel_date']==panel
 decision=parse_ts(m['decision_timestamp']);asof=parse_ts(m['data_as_of_timestamp']);assert decision.date().isoformat()==panel and asof<=decision
 assert m['next_scheduled_trading_date']>panel
 roles={}
 for x in m['files']:
  p=b/x['path'];assert p.is_file() and sha(p)==x['sha256'];roles[x['role']]=p
 assert {'prices','universe'}<=set(roles)
 for x in m.get('upstream_manifests',[]):
  p=Path(x['path']);p=p if p.is_absolute() else ROOT/p;assert p.is_file() and sha(p)==x['sha256'] and parse_ts(x['as_of'])<=decision
 prices=json.loads(roles['prices'].read_text());universe=json.loads(roles['universe'].read_text());assert len({r['kod'] for r in universe})==len(universe)
 forbidden=('target','forward_return','future_return','terminal_outcome','delisting_outcome')
 assert not any(any(z in str(k).lower() for z in forbidden) for r in universe for k in r)
 assert all(all(x['d']<=panel for x in rs) for rs in prices.values())
 assert all(parse_ts(r['known_at'])<=decision for r in universe)
 return b,m,prices,universe
def seal(panel):
 lock_verify();verify_index();d=dt.date.fromisoformat(panel)
 if not scheduled(d):raise SystemExit('FAIL not ordinary forward panel')
 out=H/'sealed'/panel/'prediction'
 if out.exists():raise SystemExit('FAIL prediction already sealed')
 b,m,prices,universe=validate_inbox(panel);rows=[];signal_inputs=[]
 for u in universe:
  if not u['investable']:continue
  rs=sorted(prices.get(u['kod'],[]),key=lambda x:x['d']);mom12,d12=momentum_detail(rs,panel,364);mom18,d18=momentum_detail(rs,panel,546)
  rows.append({**u,'mom_12m':mom12,'mom_18m':mom18});signal_inputs.append({'kod':u['kod'],'mom_12m':d12,'mom_18m':d18})
 r12=pct_rank([r['mom_12m'] for r in rows]);r18=pct_rank([r['mom_18m'] for r in rows])
 combined=[(a+b)/2 if a is not None and b is not None else None for a,b in zip(r12,r18)];cm=median(combined);m12=median([r['mom_12m'] for r in rows])
 scores=[]
 for r,a,b,c in zip(rows,r12,r18,combined):scores.append({**r,'rank_mom12_pct':a,'rank_mom18_pct':b,'score_champion':cm if c is None else c,'score_12m':m12 if r['mom_12m'] is None else r['mom_12m']})
 champion=sorted(scores,key=lambda r:(r['score_champion'],r['kod']),reverse=True);baseline=sorted(scores,key=lambda r:(r['score_12m'],r['kod']),reverse=True)
 ranking=[{'rank':i+1,'kod':r['kod'],'score':r['score_champion']} for i,r in enumerate(champion)];ranking12=[{'rank':i+1,'kod':r['kod'],'score':r['score_12m']} for i,r in enumerate(baseline)]
 reb=phase(d);top=[r['kod'] for r in champion[:N]];prior=[x for x in records() if x['event']=='PREDICTION'];prior_path=ROOT/prior[-1]['path'] if prior else None;previous=[]
 if prior_path:previous=[x['kod'] for x in json.loads((prior_path.parent/'planned_holdings.json').read_text())['holdings']]
 if reb:hold=top
 else:
  if not prior_path:raise SystemExit('FAIL non-rebalance panel without prior sealed holdings')
  hold=previous
 trades={'buys':sorted(set(hold)-set(previous)) if reb else [],'sells':sorted(set(previous)-set(hold)) if reb else [],'initial_cash':bool(reb and not prior),'planned_execution_date':m['next_scheduled_trading_date'],'execution_rule':'FIRST_OBSERVED_CLOSE_STRICTLY_AFTER_DECISION'}
 files={'source_prices_snapshot.json':prices,'source_universe_snapshot.json':universe,'signal_inputs.json':signal_inputs,'decision_universe.json':scores,'ranking_champion.json':ranking,'ranking_12m.json':ranking12,'top30_champion.json':ranking[:N],'top30_12m.json':ranking12[:N],'planned_holdings.json':{'rebalance':reb,'holdings':[{'kod':k,'weight':1/N} for k in hold]},'planned_trades.json':trades,'benchmark_universe.json':[r['kod'] for r in champion],'input_provenance.json':m}
 out.mkdir(parents=True);des=[]
 for name,obj in files.items():p=out/name;p.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n');os.chmod(p,0o444);des.append({'path':name,'sha256':sha(p),'bytes':p.stat().st_size,'rows':len(obj) if isinstance(obj,list) else None})
 manifest={'event':'PREDICTION','panel_date':panel,'sealed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'H0_lock_sha256':sha(LOCK),'freeze_manifest_sha256':json.loads(LOCK.read_text())['freeze_manifest_sha256'],'code_sha256':sha(ROOT/'tools/sparh_forward.py'),'files':des,'immutable':True}
 mp=out/'manifest.json';mh=write_new(mp,manifest);append_event('PREDICTION',panel,mp,mh);print(json.dumps({'status':'SEALED','panel':panel,'manifest_sha256':mh,'rebalance':reb},indent=2))
def immutable_event(kind,panel,input_path):
 lock_verify();verify_index();pred=H/'sealed'/panel/'prediction/manifest.json'
 if not pred.is_file():raise SystemExit('FAIL prediction not sealed')
 src=Path(input_path);obj=json.loads(src.read_text());out=H/'sealed'/panel/kind
 if kind=='correction':
  cid=obj.get('correction_id')
  if not cid or not all(c.isalnum() or c in '-_' for c in cid):raise SystemExit('FAIL correction_id')
  out=out/cid
 if out.exists():raise SystemExit('FAIL event already sealed')
 # Execution must remain strictly post-decision and use the frozen rule.
 if kind=='execution':
  assert obj.get('execution_rule')=='FIRST_OBSERVED_CLOSE_STRICTLY_AFTER_DECISION'
  planned=json.loads((pred.parent/'planned_trades.json').read_text())['planned_execution_date']
  assert all(r['execution_price_date']>panel and r['execution_price_date']==planned for r in obj['trades'] if r.get('execution_price_date'))
 elif kind=='portfolio_outcome':
  assert {'champion_return','baseline_12m_return','benchmark_return','turnover','costs','ticker_contributions'}<=set(obj)
 elif kind=='target_outcome':
  assert {'target_definition','ic52_champion','top30_ic52','ic52_12m'}<=set(obj)
 data={'event':kind.upper(),'panel_date':panel,'prediction_manifest_sha256':sha(pred),'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),'payload':obj}
 out.mkdir(parents=True);p=out/'record.json';h=write_new(p,data);append_event(kind.upper(),panel,p,h);print(json.dumps({'status':'SEALED','event':kind,'sha256':h},indent=2))
def verify():
 l=lock_verify();n=verify_index();print(json.dumps({'status':'PASS','H0_lock_sha256':sha(LOCK),'freeze':l['freeze_manifest_sha256'],'v4_files':l['verified_v4_files'],'abc_artifacts':l['verified_abc_artifacts'],'journal_records':n},indent=2))
def status():
 lock_verify();n=verify_index();today=dt.date.today();eligible=[];d=FIRST
 while d<=today:eligible.append(d.isoformat());d+=INTERVAL
 rs=records();sealed=[x['panel_date'] for x in rs if x['event']=='PREDICTION'];portfolio=len([x for x in rs if x['event']=='PORTFOLIO_OUTCOME']);targets=len([x for x in rs if x['event']=='TARGET_OUTCOME'])
 print(json.dumps({'status':'READY' if not eligible else 'ACTION_REQUIRED','today':today.isoformat(),'first_forward_eligible':FIRST.isoformat(),'next_8w_rebalance':FIRST.isoformat(),'eligible_to_date':eligible,'sealed_predictions':sealed,'unsealed_eligible':sorted(set(eligible)-set(sealed)),'journal_records':n,'checkpoint_progress':{'completed_8w_periods':portfolio,'next_portfolio_checkpoint':next((x for x in [3,6,12] if x>portfolio),None),'matured_ic52_panels':targets,'next_ic52_checkpoint':next((x for x in [5,10,20] if x>targets),None)}},indent=2))
def run_due():
 lock_verify();verify_index();today=dt.date.today();sealed={x['panel_date'] for x in records() if x['event']=='PREDICTION'};d=FIRST;due=[]
 while d<=today:
  if d.isoformat() not in sealed:due.append(d.isoformat())
  d+=INTERVAL
 if not due:print(json.dumps({'status':'NO_DUE_PANELS','today':today.isoformat()}));return
 for panel in due:
  if not (H/'inbox'/panel/'input_manifest.json').is_file():raise SystemExit('FAIL due panel inbox missing '+panel)
  seal(panel)
def main():
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
 sub.add_parser('verify');sub.add_parser('status');sub.add_parser('run-due');s=sub.add_parser('seal-panel');s.add_argument('panel')
 for c in ['record-execution','mature-portfolio','mature-target','record-correction']:
  s=sub.add_parser(c);s.add_argument('panel');s.add_argument('input')
 a=ap.parse_args()
 if a.cmd=='verify':verify()
 elif a.cmd=='status':status()
 elif a.cmd=='run-due':run_due()
 elif a.cmd=='seal-panel':seal(a.panel)
 else:immutable_event({'record-execution':'execution','mature-portfolio':'portfolio_outcome','mature-target':'target_outcome','record-correction':'correction'}[a.cmd],a.panel,a.input)
if __name__=='__main__':main()
