"""Run only frozen Q0/Q8/Q15/Q20 constraints on H0 V3's existing 8W panels."""
from __future__ import annotations
import csv, hashlib, json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
V2=Path('/home/hannesb/momentum_v2'); OUT=V2/'research_k/index_quota_portfolio_audit_v2'; sys.path.insert(0,str(V2/'tools'))
from rebalance_cadence_4w_vs_8w_audit import run_window,stat,paired_boot,N,COST
SRC=Path('/home/hannesb/momentum_prod_work/momentum_ml/data/omx30_membership_pit.csv')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(x):return ''.join(c for c in x.upper() if c.isalnum())
ALIAS={'LUNE':'LUPE','NOKIASEK':'NOKIA'}
def members(rows,dt):
 return {z for r in rows if r['member_from']<=dt<=r['member_to'] for z in (norm(r['ticker']),norm(r['nasdaq_symbol']))}
def ismember(k,active):return ALIAS.get(norm(k),norm(k)) in active
def sim(ctx,minimum,memberrows):
 rankings,ret,panels=ctx['rankings'],ctx['returns'],ctx['panels'];sma,vol,conf=ctx['sma_fn'],ctx['vol_fn'],ctx['confirmed_fn']
 prev=[];out=[]; forced=[]
 for a,dt in enumerate(panels):
  raw=rankings[dt]; eligible=[r['kod'] for r in raw]; active=members(memberrows,dt)
  if a%2==0 or not prev:
   base=eligible[:N]; inside=[k for k in base if ismember(k,active)]
   need=max(0,minimum-len(inside)); outside=[k for k in eligible[N:] if ismember(k,active)]
   displaced=[k for k in reversed(base) if not ismember(k,active)][:need]
   if len(outside)<need or len(displaced)<need: raise RuntimeError(f'quota infeasible {dt}: {minimum}')
   sel0=[k for k in base if k not in displaced]+outside[:need]
   # Preserve frozen rank order of kept positions, then append forced names in rank order.
   forced += [dict(date=dt,minimum=minimum,forced_in=k,displaced=d,forced_in_rank=eligible.index(k)+1,displaced_rank=eligible.index(d)+1) for k,d in zip(outside[:need],displaced)]
  else:
   sel0=[k for k in prev if k in set(eligible)]
   sel0 += [k for k in eligible if k not in sel0][:N-len(sel0)]
  turnover=0 if not prev else 1-len(set(sel0)&set(prev))/max(1,len(sel0)); held=[k for k in sel0 if sma(k,dt)]; n=len(held)
  if n:
   iv=1/(np.maximum(np.array([vol(k,dt) for k in held]),.05)**1.5); w=iv/iv.sum()*(n/N);w*=np.array([1 if conf(k,dt) else .75 for k in held]);w=np.clip(w,.01,.06);w=w/w.sum()*(n/N);weights=dict(zip(held,map(float,w)));gross=float(sum(weights[k]*ret[k,dt] for k in held))
  else:weights={};gross=0.
  out.append(dict(panel=a,date=dt,selected_pre_sma=sel0,holdings=held,weights=weights,gross=gross,turnover=turnover,cost=COST*turnover,net=gross-COST*turnover,natural_members=len(inside),member_count=len([k for k in sel0 if ismember(k,active)]),eligible_members=len([k for k in eligible if ismember(k,active)])))
  prev=sel0
 return out,forced
def arm(rows):
 net=np.array([r['net'] for r in rows]); gross=np.array([r['gross'] for r in rows]); years=len(rows)/13
 return {**stat(net),'gross_cagr':stat(gross)['cagr'],'annual_turnover':float(sum(r['turnover'] for r in rows)/years),'annual_cost':float(sum(r['cost'] for r in rows)/years),'mean_holdings':float(np.mean([len(r['holdings']) for r in rows])),'net_series':net.tolist()}
def main():
 OUT.mkdir(parents=True,exist_ok=True); pre=OUT/'preregistration.json'; plan=json.loads(pre.read_text()); memberrows=list(csv.DictReader(SRC.open())); result={'study':'INDEX_QUOTA_PORTFOLIO_AUDIT_V2','run_utc':datetime.now(timezone.utc).isoformat(),'prereg_sha256':sha(pre),'membership_source_sha256':sha(SRC),'arms':{},'windows':{}}
 allpanel=[];allforced=[]
 for tag in ('W1','W2'):
  x=run_window(tag); ctx=x['internal_context']; base=ctx['base']; base_net=np.array([r['net'] for r in base]); wd={'base_reproduction':x['base_reproduction'],'arms':{}}
  for armid,q in [('BASE_Q0',0),('INDEX_Q8',8),('INDEX_Q15',15),('INDEX_Q20',20)]:
   rows,forced=sim(ctx,q,memberrows); a=arm(rows); diff=np.array(a['net_series'])-base_net; a['vs_base']={'net_cagr_pp':a['cagr']-stat(base_net)['cagr'],'gross_cagr_pp':a['gross_cagr']-arm(base)['gross_cagr'],'incremental_annual_turnover':a['annual_turnover']-arm(base)['annual_turnover'],'incremental_annual_cost':a['annual_cost']-arm(base)['annual_cost'],'bootstrap':paired_boot(np.array(a['net_series']),base_net)}; wd['arms'][armid]=a
   for r in rows:allpanel.append({'window':tag,'arm':armid,**{k:r[k] for k in ('panel','date','natural_members','member_count','eligible_members','gross','turnover','cost','net')}})
   for r in forced:allforced.append({'window':tag,'arm':armid,**r})
  result['windows'][tag]=wd
 verdicts={}
 for armid in ('INDEX_Q8','INDEX_Q15','INDEX_Q20'):
  a=result['windows']['W1']['arms'][armid]['vs_base']['net_cagr_pp']; b=result['windows']['W2']['arms'][armid]['vs_base']['net_cagr_pp']
  verdicts[armid]='REPLICATED_POSITIVE' if a>0 and b>0 else ('REPLICATED_NEGATIVE' if a<0 and b<0 else 'MIXED_W1_W2')
 result['arm_verdicts']=verdicts
 result['final_verdict']='NO_INDEX_QUOTA_VALUE__NO_ARM_REPLICATED_POSITIVE'
 result['production_change_nominated']=False
 (OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 for name,rows in [('panel_level_comparison.csv',allpanel),('forced_substitutions.csv',allforced)]:
  with (OUT/name).open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['empty']);w.writeheader();w.writerows(rows)
 (OUT/'RESULT_SHA256.txt').write_text(sha(OUT/'RESULT.json')+'  RESULT.json\n');print(json.dumps({w:{a:round(z['vs_base']['net_cagr_pp']*100,3) for a,z in v['arms'].items()} for w,v in result['windows'].items()},ensure_ascii=False))
 lines=['# INDEX_QUOTA_PORTFOLIO_AUDIT_V2','',f"Final verdict: **{result['final_verdict']}**. BASE_Q0 reproduces the frozen H0 V3 series in W1 and W2.",'','| Arm | W1 net CAGR delta | W2 net CAGR delta | status |','|---|---:|---:|---|']
 for armid in ('INDEX_Q8','INDEX_Q15','INDEX_Q20'):
  a=result['windows']['W1']['arms'][armid]['vs_base']['net_cagr_pp'];b=result['windows']['W2']['arms'][armid]['vs_base']['net_cagr_pp'];lines.append(f'| {armid} | {a:+.2%} | {b:+.2%} | {verdicts[armid]} |')
 lines += ['', 'The predeclared arms are minimum quotas.  No quota is selected post hoc and no production change is nominated.', '', f'Preregregistration SHA256: `{sha(pre)}`', f'Result SHA256: `{sha(OUT / "RESULT.json")}`']
 (OUT/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()
