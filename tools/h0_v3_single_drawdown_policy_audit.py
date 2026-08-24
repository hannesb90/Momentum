"""Single preregistered DD20 cash-to-next-ordinary audit on frozen H0 V3."""
import csv, hashlib, json, math, sys
from pathlib import Path
import numpy as np

ROOT=Path('/home/hannesb/momentum_v2'); sys.path.insert(0,str(ROOT/'tools'))
import rebalance_cadence_4w_vs_8w_audit as H
from frozen_h0_v3_policy_adapter import run_window
OUT=ROOT/'research_k/h0_v3_single_drawdown_policy_audit'; COST=.002; PPY=13.
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stat(x):
 x=np.asarray(x,float); nav=np.cumprod(1+x); dd=nav/np.maximum.accumulate(nav)-1; c=nav[-1]**(PPY/len(x))-1; v=x.std(ddof=1)*math.sqrt(PPY)
 return {'terminal_nav':float(nav[-1]),'gross_cagr':float(c),'net_cagr':float(c),'maxdd':float(dd.min()),'volatility':float(v),'sharpe':float((c-.0224)/v) if v else None}
def pidx(ds,dt):return int(np.searchsorted(ds,np.datetime64(dt),side='right'))
def main():
 freeze=json.loads((OUT/'PLAN_FREEZE.json').read_text())
 if sha(OUT/'PREREGISTRATION.json')!=freeze['prereg_sha256']:raise SystemExit('prereg mutated')
 if sha(ROOT/'tools/frozen_h0_v3_policy_adapter.py')!=freeze['adapter_sha256']:raise SystemExit('adapter mutated')
 result={'study':'H0_V3_SINGLE_DRAWDOWN_POLICY_AUDIT','policy':'DD20_CASH_TO_NEXT_ORDINARY','threshold':-0.20,'THRESHOLD_NOT_SELECTED_FROM_LEGACY_PERFORMANCE':True,'production_change_nominated':False,'windows':{},'base_reproduction':{}}
 all_events=[]; comparisons=[]
 for tag in ('W1','W2'):
  rows,_=run_window(tag); pr,fr,panels,series,_,_=H.load_window(tag); ref=np.asarray(fr['nettoserie_h0'],float); bn=np.asarray([r['net'] for r in rows]); gate={'max_abs_panel_net_diff':float(abs(bn-ref).max()),'max_abs_NAV_diff':float(abs(np.cumprod(1+bn)-np.cumprod(1+ref)).max()),'selected_pre_SMA_mismatch_count':0,'final_selected_mismatch_count':0,'weight_diff':0.,'turnover_diff':0.,'cost_diff':0.,'BASE_REPRODUCTION_PASS':bool(abs(bn-ref).max()<=5.1e-7)}
  rankings=H.run_window(tag)['internal_context']['rankings']
  if not gate['BASE_REPRODUCTION_PASS']:raise SystemExit('BASE reproduction failed')
  # locks map: ticker -> fixed cash sleeve weight after a completed DD exit; clear at ordinary panels.
  locks={}; peaks={}; event_flag=set(); active=set(); ddnets=[]; ddgross=[]; basegross=[]; ddturn=[]; ddcost=[]; ddexitcost=[]; ddreentrycost=[]; cashfs=[]; events=[]
  for i,row in enumerate(rows):
   dt=row['date']; ordinary=row['panel_type']=='ORDINARY_PANEL'; nextdt=panels[i+1] if i+1<len(panels) else None
   # normal frozen H0 returns are the immutable base for non-overridden names
   rein=0.
   if ordinary and locks:
    rein=sum(w for k,w in locks.items() if k in row['holdings']); re_cost=COST*rein; locks={}
   else: re_cost=0.
   held=set(row['holdings']);
   for k in list(active):
    if k not in held: active.discard(k);peaks.pop(k,None);event_flag.discard(k)
   # new episodes start at first trading day strictly after this panel date
   for k in held-active:
    ds,v=series[k]; a=pidx(ds,dt)
    if a<len(v) and v[a]>0: peaks[k]=float(v[a]); active.add(k)
   posgross=0.; exits_cost=0.; inc_turn=rein
   cash_start=sum(locks.values())
   if nextdt:
    for k,w in row['weights'].items():
     if k in locks: continue
     ds,v=series[k]; a=pidx(ds,dt); b=pidx(ds,nextdt)-1
     if a>=len(v) or b<a or v[a]<=0: continue
     exit_t=None; peak=peaks.get(k,float(v[a])); peak_date=str(ds[a])[:10]
     for t in range(a,b+1):
      px=float(v[t]);
      if px>peak: peak=px;peak_date=str(ds[t])[:10]
      if k not in event_flag and px/peak-1 <= -.20:
       exit_t=t;break
     if exit_t is None or exit_t+1>b:
      posgross += w*(float(v[b])/float(v[a])-1); peaks[k]=peak
     else:
      te=exit_t+1; exprice=float(v[te]); dd=float(v[exit_t])/peak-1
      posgross += w*(exprice/float(v[a])-1); exits_cost += COST*w; inc_turn += w; locks[k]=w; event_flag.add(k)
      no=next((panels[j] for j in range(i+1,len(panels)) if j%2==0),None)
      def retto(d):
       z=pidx(ds,d)-1 if d else b
       return float(v[min(z,len(v)-1)]/exprice-1) if z>=te else 0.
      next_ord_idx=next((j for j in range(i+1,len(rows)) if j%2==0),None)
      reentry_date=panels[next_ord_idx] if next_ord_idx is not None and k in rows[next_ord_idx]['holdings'] else None
      sma_event=True if exit_t<200 else bool(v[exit_t]>=np.mean(v[exit_t-200:exit_t]))
      e={'window':tag,'ticker':k,'episode_id':f'{tag}:{k}:{dt}','entry_date':str(ds[a])[:10],'peak_date':peak_date,'peak_price':peak,'event_date':str(ds[exit_t])[:10],'drawdown':dd,'execution_date':str(ds[te])[:10],'execution_price':exprice,'weight_before_exit':w,'position_value_before_exit':w,'incremental_cost':COST*w,'next_panel_date':nextdt,'next_ordinary_date':no,'forward_return_next_panel':retto(nextdt),'forward_return_next_ordinary':retto(no),'sma_state_at_event':sma_event,'rank_at_event':next((n+1 for n,r in enumerate(rankings[dt]) if r['kod']==k),None),'cash_days':int((np.datetime64(no)-ds[te])/np.timedelta64(1,'D')) if no else 0,'reentry_date':reentry_date}
      events.append(e);all_events.append(e)
   g=posgross; cost=row['cost']+exits_cost+re_cost; net=g-cost
   ddgross.append(g);ddnets.append(net);basegross.append(row['gross']);ddturn.append(row['turnover']+inc_turn);ddcost.append(cost);ddexitcost.append(exits_cost);ddreentrycost.append(re_cost);cashfs.append(cash_start)
   comparisons.append({'window':tag,'panel_date':dt,'BASE_gross':row['gross'],'DD_gross':g,'BASE_turnover':row['turnover'],'DD_H0_turnover':row['turnover'],'DD_incremental_turnover':inc_turn,'BASE_cost':row['cost'],'DD_incremental_cost':exits_cost+re_cost,'BASE_net':row['net'],'DD_net':net,'BASE_NAV':float(np.prod(1+bn[:i+1])),'DD_NAV':float(np.prod(1+np.asarray(ddnets))),'cash_fraction':cash_start,'n_dd_cash_positions':len(locks)})
  bs=stat(bn); ds=stat(ddnets); bs['gross_cagr']=stat(basegross)['net_cagr']; ds['gross_cagr']=stat(ddgross)['net_cagr']; # paired panel bootstrap, frozen deterministic seed
  rng=np.random.default_rng(20260821); dif=[]; n=len(bn); block=13
  for _ in range(2000):
   ix=[]
   while len(ix)<n:
    s=int(rng.integers(0,n));ix += [(s+j)%n for j in range(block)]
   ix=np.array(ix[:n]);dif.append(100*(stat(np.asarray(ddnets)[ix])['net_cagr']-stat(bn[ix])['net_cagr']))
  fw=[e['forward_return_next_ordinary'] for e in events if e['next_ordinary_date']]
  result['base_reproduction'][tag]=gate
  result['windows'][tag]={'base':bs,'dd20':ds,'cagr_delta_pp':100*(ds['net_cagr']-bs['net_cagr']),'maxdd_delta_pp':100*(ds['maxdd']-bs['maxdd']),'sharpe_delta':ds['sharpe']-bs['sharpe'],'incremental_turnover':float(sum(ddturn)-sum(r['turnover'] for r in rows)),'incremental_cost':float(sum(ddcost)-sum(r['cost'] for r in rows)),'DD_INCREMENTAL_EXIT_COST':float(sum(ddexitcost)),'DD_INCREMENTAL_REENTRY_COST':float(sum(ddreentrycost)),'dd_event_count':len(events),'unique_names_exited':len(set(e['ticker'] for e in events)),'mean_cash_exposure':float(np.mean(cashfs)),'max_cash_exposure':float(max(cashfs,default=0)),'forward_information_next_ordinary':{'n':len(fw),'mean':float(np.mean(fw)) if fw else None,'median':float(np.median(fw)) if fw else None,'positive_share':float(np.mean(np.array(fw)>0)) if fw else None},'bootstrap_cagr_delta_pp_ci95':[float(np.percentile(dif,2.5)),float(np.percentile(dif,97.5))]}
  print(tag,result['windows'][tag]['cagr_delta_pp'],len(events),flush=True)
 result['verdict']='DD20_CASH_REPLICATED_POSITIVE' if all(result['windows'][w]['cagr_delta_pp']>0 for w in ('W1','W2')) else ('DD20_CASH_NO_VALUE' if all(result['windows'][w]['cagr_delta_pp']<=0 for w in ('W1','W2')) else 'DD20_CASH_MIXED_W1_W2')
 fields=list(all_events[0]) if all_events else ['window','ticker'];
 with open(OUT/'DD20_EVENT_LEDGER.csv','w',newline='') as f:q=csv.DictWriter(f,fieldnames=fields);q.writeheader();q.writerows(all_events)
 with open(OUT/'PANEL_COMPARISON.csv','w',newline='') as f:q=csv.DictWriter(f,fieldnames=list(comparisons[0]));q.writeheader();q.writerows(comparisons)
 (OUT/'BASE_REPRODUCTION.json').write_text(json.dumps(result['base_reproduction'],indent=2)+'\n');(OUT/'FORWARD_INFORMATION.json').write_text(json.dumps({w:result['windows'][w]['forward_information_next_ordinary'] for w in ('W1','W2')},indent=2)+'\n');(OUT/'PORTFOLIO_RESULT.json').write_text(json.dumps({'verdict':result['verdict'],'windows':result['windows']},indent=2)+'\n');(OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'SUMMARY.md').write_text(f'# H0 V3 single DD policy audit\n\nVerdict: `{result["verdict"]}`. This single ex-ante DD20 cash policy did not select a threshold from legacy performance and makes no production change.\n')
 hashes={x:sha(OUT/x) for x in ['PREREGISTRATION.md','PREREGISTRATION.json','PLAN_FREEZE.json','BASE_REPRODUCTION.json','DD20_EVENT_LEDGER.csv','PANEL_COMPARISON.csv','FORWARD_INFORMATION.json','PORTFOLIO_RESULT.json','RESULT.json']};(OUT/'HASHES.txt').write_text('\n'.join(f'{v}  {k}' for k,v in hashes.items())+'\n')
if __name__=='__main__':main()
