#!/usr/bin/env python3
"""Research I Batch 2: fixed holding/exit replications on frozen H0 rankings."""
from __future__ import annotations
import hashlib,json,math,shutil
from collections import defaultdict
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1];RI=ROOT/'research_i';OUT=RI/'results/SPARI_BATCH2_EXIT_HOLDING_V2';COST=.002;N=30
RANK=ROOT/'repair_df/results/SPARF_SYSTEMATIC_MOMENTUM_V3_EXECUTION_PIT/rankings.json';FRET=ROOT/'repair_df/results/SPARF_SYSTEMATIC_MOMENTUM_V3_EXECUTION_PIT/returns.json';F6=ROOT/'repair_df/results/SPARF_SYSTEMATIC_MOMENTUM_V3_EXECUTION_PIT/F6.json';PRICES=ROOT/'validated/prices/prices_validated.json';TERM=ROOT/'validated/terminal_events.json'
VARIANTS=['H0','dd20','milestone_13w_abs','milestone_26w_abs','time_stop_8w','reentry_block_dd20_ma40']
_ALL_PANEL_DATES=sorted({r['panel_date'] for r in json.loads((ROOT/'panels/core_panel.json').read_text())})
_NEXT_PANEL=dict(zip(_ALL_PANEL_DATES,_ALL_PANEL_DATES[1:]))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def annualized(r):return float(np.prod(1+np.array(r))**(13/len(r))-1) if r else None
def load():
 pre=json.loads((RI/'batch2_preregistration.json').read_text());assert pre['status']=='PREREGISTERED_BEFORE_TARGET_OR_RESULT_READ';assert sha(RI/'FREEZE_MANIFEST_BATCH1.json')==pre['parent_batch1_freeze_sha256'];assert sha(ROOT/'trackh/H0_LOCK.json')==pre['h0_lock_sha256'];assert not OUT.exists(),'no overwrite'
 ranks=[r for r in json.loads(RANK.read_text()) if r['model']=='F6_8w'];base=[r for r in json.loads(FRET.read_text()) if r['model']=='F6_8w'];prices=json.loads(PRICES.read_text());term=json.loads(TERM.read_text());return pre,ranks,base,prices,term
def px_maps(prices):
 return {k:([r['d'] for r in rs],{r['d']:float(r['adj']) for r in rs}) for k,rs in prices.items()}
def first_after(pm,k,boundary,limit=None):
 if k not in pm:return None
 for d in pm[k][0]:
  if d>boundary and (limit is None or d<=limit):return d
 return None
def last_on_before(pm,k,boundary):
 if k not in pm:return None
 z=[d for d in pm[k][0] if d<=boundary];return z[-1] if z else None
def sma40(pm,k,d):
 if k not in pm:return None
 lo=(date.fromisoformat(d)-timedelta(days=280)).isoformat();v=[pm[k][1][x] for x in pm[k][0] if lo<=x<=d]
 return float(np.mean(v)) if len(v)>=100 else None
def common_execution(pm,a,b,trigger,limit):
 da=first_after(pm,a,trigger,limit);db=first_after(pm,b,trigger,limit)
 if not da or not db:return None
 goal=max(da,db)
 for _ in range(8):
  da=first_after(pm,a,(date.fromisoformat(goal)-timedelta(days=1)).isoformat(),limit);db=first_after(pm,b,(date.fromisoformat(goal)-timedelta(days=1)).isoformat(),limit)
  if not da or not db:return None
  ng=max(da,db)
  if da==db:return da
  goal=ng
 return None
def ranking_maps(rows):
 by=defaultdict(list)
 for r in rows:by[r['panel_date']].append(r)
 for d in by:by[d]=[r['kod'] for r in sorted(by[d],key=lambda x:x['rank'])]
 return dict(by)
def schedules(rank_by,phase):
 dates=sorted(rank_by);dates=dates[phase:];slots=[];current=[]
 for ix,d in enumerate(dates):
  reb=ix%2==0
  if reb or not current:current=rank_by[d][:N]
  slots.append({'panel_date':d,'ranking':rank_by[d],'holdings':list(current),'rebalance':reb})
 return slots
def new_lot(k,frac,entry_d,entry_p):return {'kod':k,'fraction':frac,'entry_date':entry_d,'entry_price':entry_p,'peak':entry_p,'milestone_checked':False,'halved_at':None,'mark_price':entry_p,'mult':1.0}
def choose(ranking,held,blocked,pm,trigger,limit):
 for k in ranking:
  if k in held or k in blocked:continue
  if first_after(pm,k,trigger,limit):return k
 return None
def simulate(name,rank_by,prices,term,phase=0):
 pm=px_maps(prices);sched=schedules(rank_by,phase);slots=[];blocked=set();returns=[];trades=[];events=[];holdings=[];ticker_contrib=defaultdict(float);total_turn=0.0;total_cost=0.0
 for ix,s in enumerate(sched):
  T=s['panel_date'];ND=sched[ix+1]['panel_date'] if ix+1<len(sched) else _NEXT_PANEL.get(T)
  if not ND:break
  end_limit=first_after(pm,s['ranking'][0],ND) or (date.fromisoformat(ND)+timedelta(days=10)).isoformat()
  # Base rebalance overrides any exit overlay and uses frozen selection.
  if s['rebalance'] or not slots:
   old_lots=defaultdict(list)
   for sl in slots:
    for l in sl:old_lots[l['kod']].append(l)
   old=set(old_lots);slots=[]
   for k in s['holdings']:
    ed=first_after(pm,k,T,ND)
    if not ed:continue
    ep=pm[k][1][ed]
    if old_lots.get(k):
     # Same economic holding remains continuously owned across base rebalance;
     # preserve entry/peak/milestone state while resetting its equal-weight slot.
     l=deepcopy(old_lots[k][0]);l['fraction']=1.0;l['mark_price']=ep;l['mult']=1.0;slots.append([l])
    else:slots.append([new_lot(k,1.0,ed,ep)])
   new={l['kod'] for sl in slots for l in sl};buys=len(new-old) if old else len(new);turn=buys/N;total_turn+=turn;total_cost+=COST*turn
   for k in sorted(new-old):trades.append({'variant':name,'phase':phase,'decision_date':T,'execution_date':first_after(pm,k,T,ND),'kod':k,'side':'BUY','reason':'BASE_REBALANCE'})
   for k in sorted(old-new):trades.append({'variant':name,'phase':phase,'decision_date':T,'execution_date':first_after(pm,k,T,ND),'kod':k,'side':'SELL','reason':'BASE_REBALANCE'})
  else:
   # Frozen V4 H0 keeps eligible names and fills slots whose instrument left the
   # contemporaneous decision universe, even on an intermediate 4-week panel.
   allowed=set(s['ranking'])
   for sl in slots:
    for l in list(sl):
     if l['kod'] in allowed:continue
     held={q['kod'] for ss in slots for q in ss};cand=choose(s['ranking'],held,set(),pm,T,ND)
     if not cand:continue
     ex=common_execution(pm,l['kod'],cand,T,ND) or first_after(pm,cand,T,ND)
     if not ex:continue
     trades.extend([{'variant':name,'phase':phase,'decision_date':T,'execution_date':ex,'kod':l['kod'],'side':'SELL','reason':'BASE_ELIGIBILITY_REFRESH'},{'variant':name,'phase':phase,'decision_date':T,'execution_date':ex,'kod':cand,'side':'BUY','reason':'BASE_ELIGIBILITY_REFRESH'}]);turn=l['fraction']/N;total_turn+=turn;total_cost+=COST*turn
     repl=new_lot(cand,l['fraction'],ex,pm[cand][1][ex]);sl.remove(l);sl.append(repl)
  # reset period marks, keeping economic entry/peak state
  for sl in slots:
   for l in sl:
    sd=first_after(pm,l['kod'],T,ND)
    if sd:l['mark_price']=pm[l['kod']][1][sd]
    l['mult']=1.0
  all_days=sorted({d for sl in slots for l in sl if l['kod'] in pm for d in pm[l['kod']][0] if T<d<ND})
  for d in all_days:
   # release re-entry block strictly from contemporaneous close/MA
   if name=='reentry_block_dd20_ma40':
    for k in list(blocked):
     ma=sma40(pm,k,d);p=pm.get(k,([],{}))[1].get(d)
     if ma is not None and p is not None and p>=ma:blocked.remove(k)
   for si,sl in enumerate(list(slots)):
    for l in list(sl):
     k=l['kod'];p=pm.get(k,([],{}))[1].get(d)
     if p is None:continue
     l['peak']=max(l['peak'],p);dd=p/l['peak']-1;fire=None;fraction=1.0
     if name in ('dd20','reentry_block_dd20_ma40') and dd<=-.20:fire='DD20'
     elif name.startswith('milestone_') and not l['milestone_checked']:
      days=91 if '13w' in name else 182
      if (date.fromisoformat(d)-date.fromisoformat(l['entry_date'])).days>=days:
       l['milestone_checked']=True
       if p/l['entry_price']-1<0:fire='MILESTONE'
     elif name=='time_stop_8w':
      if l['halved_at']:
       ma=sma40(pm,k,d)
       if ma is not None and p>=ma:l['halved_at']=None
       elif (date.fromisoformat(d)-date.fromisoformat(l['halved_at'])).days>=56:fire='TIMEOUT'
      elif dd<=-.20:fire='HALVE';fraction=.5
     if not fire:continue
     held={q['kod'] for ss in slots for q in ss};cand=choose(s['ranking'],held,blocked,pm,d,end_limit)
     if not cand:continue
     ex=common_execution(pm,k,cand,d,end_limit)
     if not ex:continue
     sell=pm[k][1][ex];buy=pm[cand][1][ex];l['mult']*=sell/l['mark_price'];old_mult=l['mult'];old_frac=l['fraction'];mature_end=first_after(pm,k,ND)
     noexit=(pm[k][1][mature_end]/sell-1) if mature_end else 0.0
     ev={'variant':name,'phase':phase,'trigger_date':d,'execution_date':ex,'sold':k,'bought':cand,'reason':fire,'fraction_of_slot':old_frac*fraction,'counterfactual_to_boundary_return':noexit,'avoided_loser':noexit<0,'future_winner_cut':noexit>0}
     events.append(ev);trades.extend([{'variant':name,'phase':phase,'decision_date':d,'execution_date':ex,'kod':k,'side':'SELL','reason':fire},{'variant':name,'phase':phase,'decision_date':d,'execution_date':ex,'kod':cand,'side':'BUY','reason':fire}]);turn=old_frac*fraction/N;total_turn+=turn;total_cost+=COST*turn
     if name=='reentry_block_dd20_ma40':blocked.add(k)
     repl=new_lot(cand,old_frac*fraction,ex,buy);repl['mult']=old_mult
     if fraction<1:
      l['fraction']=old_frac*(1-fraction);l['mark_price']=sell;l['mult']=old_mult;l['halved_at']=d;sl.append(repl)
     else:
      sl.remove(l);sl.append(repl)
  gross=0.0
  for sl in slots:
   slotret=0.0
   for l in sl:
    k=l['kod'];ed=first_after(pm,k,ND)
    ev=term.get(k);terminal=ev and l['entry_date']<=ev['event_date']<=ND
    if ed:endp=pm[k][1][ed]
    elif terminal:
     ld=last_on_before(pm,k,ev['event_date']);endp=pm[k][1][ld] if ld else l['mark_price']
    else:endp=l['mark_price']
    l['mult']*=endp/l['mark_price'];slotret+=l['fraction']*l['mult']
    ticker_contrib[k]+=(l['fraction']*(l['mult']-1))/N
   gross+=slotret/N
  period_turn=sum(1 for t in trades if t['side']=='BUY' and T<=t['decision_date']<ND)/N;cost=COST*period_turn;net=gross-1-cost;bench=next(r['benchmark_return'] for r in json.loads(FRET.read_text()) if r['model']=='F6_8w' and r['panel_date']==T)
  returns.append({'variant':name,'phase':phase,'panel_date':T,'gross_return':gross-1,'net_return':net,'benchmark_return':bench,'turnover':period_turn,'transaction_cost':cost,'rebalance':s['rebalance']})
  holdings.extend({'variant':name,'phase':phase,'panel_date':T,'slot':j+1,'kod':l['kod'],'fraction_of_slot':l['fraction']} for j,sl in enumerate(slots) for l in sl)
 return metrics(returns,ticker_contrib,events),{'returns':returns,'trades':trades,'holdings':holdings,'events':events}
def metrics(rs,contrib,events):
 nr=[r['net_return'] for r in rs];br=[r['benchmark_return'] for r in rs];ex=np.array(nr)-np.array(br);w=np.cumprod(1+np.array(nr));dd=w/np.maximum.accumulate(w)-1;ranked=sorted(contrib.items(),key=lambda x:x[1],reverse=True)
 def leave(n):
  bad={k for k,_ in ranked[:n]};adj=[]
  # arithmetic contribution ablation on total return; conservative diagnostic CAGR proxy
  total=np.prod(1+np.array(nr));removed=sum(v for k,v in ranked if k in bad);adj_total=max(1e-9,total-removed);return float(adj_total**(13/len(nr))-1)
 years={}
 for yr in sorted({r['panel_date'][:4] for r in rs}):years[yr]=annualized([r['net_return'] for r in rs if r['panel_date'].startswith(yr)])
 up=[r for r in rs if r['benchmark_return']>0];dn=[r for r in rs if r['benchmark_return']<0]
 return {'cagr_net':annualized(nr),'benchmark_cagr':annualized(br),'excess_cagr':annualized(nr)-annualized(br),'sharpe_excess':float(ex.mean()/ex.std(ddof=1)*math.sqrt(13)) if len(ex)>1 and ex.std(ddof=1)>0 else None,'max_drawdown':float(dd.min()),'mean_turnover':float(np.mean([r['turnover'] for r in rs])),'total_cost':float(sum(r['transaction_cost'] for r in rs)),'trade_count':sum(2 for _ in events),'upside_capture':float(sum(r['net_return'] for r in up)/sum(r['benchmark_return'] for r in up)) if up else None,'downside_capture':float(sum(r['net_return'] for r in dn)/sum(r['benchmark_return'] for r in dn)) if dn else None,'leave_top3_cagr':leave(3),'leave_top5_cagr':leave(5),'top5_tickers':[k for k,_ in ranked[:5]],'top3_contribution_share':float(sum(v for _,v in ranked[:3])/sum(v for _,v in ranked)) if sum(v for _,v in ranked) else None,'calendar_year':years,'event_count':len(events),'losers_avoided':sum(e['avoided_loser'] for e in events),'future_winners_cut':sum(e['future_winner_cut'] for e in events)}
def classify(x,b):
 alpha=x['excess_cagr']>b['excess_cagr'] and x['sharpe_excess']>b['sharpe_excess'] and x['max_drawdown']>=b['max_drawdown']-.01
 risk=x['max_drawdown']>=b['max_drawdown']+.01 and x['sharpe_excess']>b['sharpe_excess'] and x['excess_cagr']>=b['excess_cagr']-.02 and (x['leave_top3_cagr']-x['benchmark_cagr'])>=(b['leave_top3_cagr']-b['benchmark_cagr'])-.01 and (x['leave_top5_cagr']-x['benchmark_cagr'])>=(b['leave_top5_cagr']-b['benchmark_cagr'])-.01
 return 'STÖD — ALPHA' if alpha else ('STÖD — RISK' if risk else ('SVAGT STÖD' if x['max_drawdown']>b['max_drawdown'] or x['excess_cagr']>b['excess_cagr'] else 'INGET STÖD'))
def main():
 pre,ranks,frozen,prices,term=load();rank_by=ranking_maps(ranks);allres={};arts={'returns':[],'trades':[],'holdings':[],'events':[]}
 for phase in (0,1):
  for name in VARIANTS:
   m,a=simulate(name,rank_by,prices,term,phase);allres.setdefault(name,{})[f'phase_{phase}']=m
   for k in arts:arts[k]+=a[k]
 # The comparison is the byte-frozen H0 artifact, never a reimplementation of H0.
 fp=json.loads(F6.read_text())['results']['8w']['portfolio'];sim=allres['H0']['phase_0']
 f0={**sim,'cagr_net':fp['cagr_net'],'benchmark_cagr':fp['benchmark_cagr'],'excess_cagr':fp['annualized_excess'],'sharpe_excess':fp['sharpe_excess'],'max_drawdown':fp['max_drawdown'],'mean_turnover':fp['mean_turnover'],'leave_top3_cagr':fp['leave_top3_out_cagr'],'total_cost':float(sum(r['transaction_cost'] for r in frozen))}
 b=f0;summary={'run_id':pre['run_id'],'frozen_h0_reference':f0,'simulator_diagnostic_not_used_as_baseline':{'simulated':sim,'cagr_abs_diff':abs(sim['cagr_net']-f0['cagr_net']),'status':'KNOWN_NON_REBALANCE_ELIGIBILITY_REPLACEMENT_MISMATCH; frozen H0 bytes are authoritative'},'mechanisms':{},'non_executable':pre['not_executable'],'multiple_testing':pre['multiple_testing']}
 for name in VARIANTS[1:]:
  p=allres[name]['phase_0'];phase_ok=all(allres[name][q]['excess_cagr']>=allres['H0'][q]['excess_cagr']-.02 for q in ('phase_0','phase_1'));cl=classify(p,b)
  if cl.startswith('STÖD') and not phase_ok:cl='SVAGT STÖD'
  summary['mechanisms'][name]={'classification':cl,'primary_phase':p,'phase_1':allres[name]['phase_1'],'delta_vs_H0':{k:p[k]-b[k] for k in ('cagr_net','excess_cagr','sharpe_excess','max_drawdown','mean_turnover','total_cost')},'legacy_result_is_evidence':False}
 OUT.mkdir(parents=True)
 dump(OUT/'summary.json',summary)
 for k,v in arts.items():dump(OUT/(k+'.json'),v)
 dump(OUT/'run_provenance.json',{'preregistration_sha256':sha(RI/'batch2_preregistration.json'),'batch1_freeze_sha256':sha(RI/'FREEZE_MANIFEST_BATCH1.json'),'h0_lock_sha256':sha(ROOT/'trackh/H0_LOCK.json'),'rankings_sha256':sha(RANK),'frozen_F6_metrics_sha256':sha(F6),'prices_sha256':sha(PRICES),'terminal_sha256':sha(TERM),'code_sha256':sha(ROOT/'tools/spari_batch2.py'),'target_read':False,'variants_executed':VARIANTS,'phases':[0,1]})
 dump(OUT/'manifest.json',{'files':[{'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(OUT.iterdir()) if p.is_file()]})
 print(json.dumps({'status':'COMPLETE','out':str(OUT),'classifications':{k:v['classification'] for k,v in summary['mechanisms'].items()},'frozen_h0_cagr':f0['cagr_net'],'simulator_diagnostic_cagr_abs_diff':summary['simulator_diagnostic_not_used_as_baseline']['cagr_abs_diff']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
