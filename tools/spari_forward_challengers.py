#!/usr/bin/env python3
"""Append-only forward sealing for Research-I H1/H2; never touches Track H/H0."""
from __future__ import annotations
import argparse,datetime as dt,fcntl,hashlib,json,math,os,statistics
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'research_i/forward_challengers';FIRST=dt.date(2026,9,4);STEP=dt.timedelta(days=28);N=30
SPECS={
 'H1':('H1_DRAW_RESILIENCE','drawdown_resilience'),
 'H2':('H2_TREND_STRENGTH','trend_strength'),
}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);b=(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
 with os.fdopen(fd,'wb') as f:f.write(b)
 return sha(p)
def pct(v):
 ok=sorted((x,i) for i,x in enumerate(v) if x is not None and math.isfinite(x));z=[None]*len(v);j=0
 while j<len(ok):
  k=j+1
  while k<len(ok) and ok[k][0]==ok[j][0]:k+=1
  q=((j+1)+k)/2/len(ok)
  for _,i in ok[j:k]:z[i]=q
  j=k
 return z
def med(v):
 x=sorted(q for q in v if q is not None and math.isfinite(q));return statistics.median(x) if x else None
def last(rs,b):
 x=[r for r in rs if r['d']<=b];return x[-1] if x else None
def mom(rs,panel,days):
 a=last(rs,panel);goal=(dt.date.fromisoformat(panel)-dt.timedelta(days=days)).isoformat();b=last(rs,goal)
 if not a or not b or b['adj']<=0 or (dt.date.fromisoformat(goal)-dt.date.fromisoformat(b['d'])).days>10:return None
 return a['adj']/b['adj']-1
def window(rs,panel,days=364):
 lo=(dt.date.fromisoformat(panel)-dt.timedelta(days=days)).isoformat();return [r for r in rs if lo<=r['d']<=panel and r.get('adj') is not None and r['adj']>0]
def factor(rs,panel,kind):
 w=window(rs,panel)
 if kind=='drawdown_resilience':
  if len(w)<200:return None
  peak=w[0]['adj'];m=0.0
  for r in w:peak=max(peak,r['adj']);m=min(m,r['adj']/peak-1)
  return -abs(m)
 if len(w)<200:return None
 y=np.log(np.array([r['adj'] for r in w],float));x=np.arange(len(y),dtype=float);X=np.column_stack([np.ones(len(x)),x]);beta=np.linalg.lstsq(X,y,rcond=None)[0];res=y-X@beta;s2=float(res@res)/(len(x)-2);se=math.sqrt(s2*np.linalg.inv(X.T@X)[1,1])
 return float(beta[1]/se) if se>0 else None
def paths(ch):
 name,kind=SPECS[ch];d=BASE/name;return d,kind,d/'LOCK.json',d/'journal/INDEX.jsonl'
def lock_verify(ch):
 d,kind,lp,idx=paths(ch);l=json.loads(lp.read_text());assert sha(ROOT/'trackh/H0_LOCK.json')==l['h0_lock_sha256'];assert sha(ROOT/'research_i/FREEZE_MANIFEST_BATCH1.json')==l['batch1_freeze_sha256']
 for x in l['locked_files']:
  p=ROOT/x['path'];assert p.is_file() and sha(p)==x['sha256'] and p.stat().st_size==x['bytes'],x['path']
 return l
def records(idx):return [json.loads(x) for x in idx.read_text().splitlines() if x.strip()]
def verify_journal(idx):
 prev='0'*64
 for i,r in enumerate(records(idx),1):
  assert r['seq']==i and r['prev_chain_hash']==prev;z={k:v for k,v in r.items() if k!='chain_hash'};assert hashlib.sha256(json.dumps(z,sort_keys=True,separators=(',',':')).encode()).hexdigest()==r['chain_hash'];p=ROOT/r['path'];assert sha(p)==r['artifact_sha256'];prev=r['chain_hash']
 return i if 'i' in locals() else 0
def append(idx,event,panel,path,h):
 with idx.open('a+',encoding='utf-8') as f:
  fcntl.flock(f,fcntl.LOCK_EX);f.seek(0);rs=[json.loads(x) for x in f if x.strip()];prev=rs[-1]['chain_hash'] if rs else '0'*64;b={'seq':len(rs)+1,'event':event,'panel_date':panel,'path':str(path.relative_to(ROOT)),'artifact_sha256':h,'prev_chain_hash':prev};b['chain_hash']=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest();f.seek(0,2);f.write(json.dumps(b,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno());fcntl.flock(f,fcntl.LOCK_UN)
def validate(d,panel):
 b=d/'inbox'/panel;m=json.loads((b/'input_manifest.json').read_text());assert m['panel_date']==panel;decision=dt.datetime.fromisoformat(m['decision_timestamp']);assert decision.date().isoformat()==panel and dt.datetime.fromisoformat(m['data_as_of_timestamp'])<=decision
 role={}
 for x in m['files']:
  p=b/x['path'];assert p.is_file() and sha(p)==x['sha256'];role[x['role']]=p
 prices=json.loads(role['prices'].read_text());u=json.loads(role['universe'].read_text());assert all(all(r['d']<=panel for r in rs) for rs in prices.values());assert not any('target' in str(k).lower() or 'future' in str(k).lower() for r in u for k in r)
 return m,prices,u
def seal(ch,panel):
 d,kind,lp,idx=paths(ch);l=lock_verify(ch);verify_journal(idx);day=dt.date.fromisoformat(panel);assert day>=FIRST and (day-FIRST).days%28==0;out=d/'sealed'/panel/'prediction';assert not out.exists();m,prices,u=validate(d,panel);rows=[]
 for x in u:
  if not x['investable']:continue
  rs=sorted(prices.get(x['kod'],[]),key=lambda z:z['d']);rows.append({**x,'mom_12m':mom(rs,panel,364),'mom_18m':mom(rs,panel,546),'factor':factor(rs,panel,kind)})
 a=pct([r['mom_12m'] for r in rows]);b=pct([r['mom_18m'] for r in rows]);c=[(x+y)/2 if x is not None and y is not None else None for x,y in zip(a,b)];cm=med(c);c=[cm if x is None else x for x in c];f=pct([r['factor'] for r in rows]);fm=med(f);f=[fm if x is None else x for x in f]
 scored=[{**r,'score_h0':x,'factor_rank':y,'score_challenger':(x+y)/2} for r,x,y in zip(rows,c,f)];ranked=sorted(scored,key=lambda r:(r['score_challenger'],r['kod']),reverse=True);ranking=[{'rank':i+1,'kod':r['kod'],'score':r['score_challenger'],'score_h0':r['score_h0'],'factor':r['factor'],'factor_rank':r['factor_rank']} for i,r in enumerate(ranked)];reb=((day-FIRST).days//28)%2==0;prior=[r for r in records(idx) if r['event']=='PREDICTION'];old=[]
 if prior:old=[x['kod'] for x in json.loads((ROOT/prior[-1]['path']).parent.joinpath('planned_holdings.json').read_text())['holdings']]
 hold=[r['kod'] for r in ranked[:N]] if reb else old
 if not reb and not old:raise SystemExit('non-rebalance without prior holdings')
 objs={'decision_universe.json':scored,'ranking.json':ranking,'top30.json':ranking[:N],'planned_holdings.json':{'rebalance':reb,'holdings':[{'kod':k,'weight':1/N} for k in hold]},'planned_trades.json':{'buys':sorted(set(hold)-set(old)) if reb else [],'sells':sorted(set(old)-set(hold)) if reb else [],'planned_execution_date':m['next_scheduled_trading_date'],'execution_rule':'FIRST_OBSERVED_CLOSE_STRICTLY_AFTER_DECISION'},'input_provenance.json':m}
 out.mkdir(parents=True);files=[]
 for name,obj in objs.items():p=out/name;h=write_new(p,obj);files.append({'path':name,'sha256':h,'bytes':p.stat().st_size,'rows':len(obj) if isinstance(obj,list) else None})
 man={'event':'PREDICTION','challenger':ch,'panel_date':panel,'sealed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'lock_sha256':sha(lp),'files':files,'immutable':True};mp=out/'manifest.json';h=write_new(mp,man);append(idx,'PREDICTION',panel,mp,h);print(json.dumps({'status':'SEALED','challenger':ch,'panel':panel,'sha256':h}))
def verify(ch):
 d,kind,lp,idx=paths(ch);l=lock_verify(ch);n=verify_journal(idx);print(json.dumps({'status':'PASS','challenger':ch,'lock_sha256':sha(lp),'journal_records':n,'first_eligible':l['first_forward_eligible_panel']},indent=2))
def status(ch):
 d,kind,lp,idx=paths(ch);lock_verify(ch);n=verify_journal(idx);today=dt.date.today();due=[];x=FIRST
 while x<=today:due.append(x.isoformat());x+=STEP
 sealed=[r['panel_date'] for r in records(idx) if r['event']=='PREDICTION'];print(json.dumps({'status':'READY' if not due else 'ACTION_REQUIRED','challenger':ch,'eligible_to_date':due,'sealed':sealed,'unsealed':sorted(set(due)-set(sealed)),'journal_records':n},indent=2))
def main():
 p=argparse.ArgumentParser();p.add_argument('challenger',choices=SPECS);p.add_argument('command',choices=['verify','status','seal-panel']);p.add_argument('panel',nargs='?');a=p.parse_args();{'verify':verify,'status':status}.get(a.command,lambda c:seal(c,a.panel))(a.challenger)
if __name__=='__main__':main()
