"""Exploratory cash-flow-first funding audit on frozen H0 selections.

The frozen engine supplies selection, target weights, returns and set-based
costs.  This file adds a self-financing value ledger solely to compare funding
order: baseline target rebalance versus cash-first proportional-excess trim.
"""
import csv, json, math
from collections import defaultdict
from pathlib import Path
import sys
ROOT=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(ROOT/'tools'))
import rebalance_cadence_4w_vs_8w_audit as H
OUT=ROOT/'research_k/h0_v3_cash_flow_first_proportional_excess_trim_audit'; OUT.mkdir(parents=True,exist_ok=True)

def stats(xs, dates):
 nav=1.; ns=[]
 for x in xs:nav*=1+x;ns.append(nav)
 years=(npdate(dates[-1])-npdate(dates[0])).days/365.25; c=nav**(1/years)-1
 peak=1.;dd=0
 for x in ns:peak=max(peak,x);dd=min(dd,x/peak-1)
 mu=sum(xs)/len(xs); sd=(sum((x-mu)**2 for x in xs)/(len(xs)-1))**.5
 return {'net_cagr':c,'terminal_nav':nav,'max_drawdown':dd,'volatility':sd,'sharpe':mu/sd*math.sqrt(365.25/28) if sd else None}

def npdate(x):
 from datetime import date
 return date.fromisoformat(str(x))

def debit_cost(values,cash,cost):
 # Cost is exactly frozen panel cost × pre-return NAV; cash first, then pro-rata.
 if cost<=cash:return values,cash-cost
 rem=cost-cash; total=sum(values.values()); factor=max(0.,1-rem/total) if total else 1.
 return {k:v*factor for k,v in values.items()},0.

def execute(window, dd20_events=None):
 # One canonical reconstruction only: ``base`` is the verified frozen arm.
 ctx=H.run_window(window)['internal_context']; rows=ctx['base']; returns=ctx['returns']
 state={'BASE':({},1.),'CASH_FLOW_FIRST':({},1.)}; out=[]; trims=defaultdict(lambda:[0.,0.,0.]); detail=[]
 for r in rows:
  targets=r['weights']; sel=set(targets); result={}
  for arm,(old,cash) in state.items():
   nav=sum(old.values())+cash; old=dict(old); exits={k:v for k,v in old.items() if k not in sel}; exitpro=sum(exits.values()); cont={k:v for k,v in old.items() if k in sel}; cash0=cash+exitpro
   desired={k:targets[k]*nav for k in targets}; buys={k:max(0.,desired[k]-cont.get(k,0.)) for k in desired}; buyneed=sum(buys.values())
   base_trim=sum(max(0.,cont.get(k,0.)-desired[k]) for k in desired)
   # DD20 deprotection: the established daily-event state removes only the
   # excess-versus-baseline privilege; it never exits a selected security.
   forced=set()
   if arm=='CASH_FLOW_FIRST' and dd20_events:
    forced={k for k in cont if (window,k) in dd20_events and dd20_events[window,k] <= str(r['date'])}
   if arm=='BASE':
    values=dict(desired); cash_after=nav-sum(values.values()); trim=base_trim; avoided=0.; reduced=0.; required=base_trim>1e-12
   else:
    forced_trim=sum(max(0.,cont.get(k,0.)-desired[k]) for k in forced)
    if forced_trim:
     for k in forced: cont[k]=min(cont[k],desired[k])
     cash0+=forced_trim
     buys={k:max(0.,desired[k]-cont.get(k,0.)) for k in desired}; buyneed=sum(buys.values())
    funded=min(cash0,buyneed); shortage=buyneed-funded; excess={k:max(0.,cont.get(k,0.)-desired[k]) for k in desired}; tot=sum(excess.values())
    trim=min(shortage,tot); # exact proportional excess trim
    values=dict(cont)
    for k,x in excess.items(): values[k]=values.get(k,0.)-trim*x/tot if tot else values.get(k,0.)
    available=cash0+trim
    for k,b in buys.items(): values[k]=values.get(k,0.)+b*min(1.,available/buyneed) if buyneed else values.get(k,0.)
    cash_after=nav-sum(values.values()); avoided=base_trim-trim; reduced=1. if trim<base_trim-1e-12 and trim>1e-12 else 0.; required=trim>=base_trim-1e-12 and base_trim>1e-12
   # accounting invariant before return
   assert abs(sum(values.values())+cash_after-nav)<1e-8,(window,r['date'],arm,sum(values.values())+cash_after-nav)
   pre=dict(values); pre_nav=nav
   values={k:v*(1+returns.get((k,r['date']),0.)) for k,v in values.items()}
   cost=r['cost']*pre_nav; values,cash_after=debit_cost(values,cash_after,cost)
   post=sum(values.values())+cash_after; net=post/pre_nav-1
   result[arm]={'net':net,'nav':post,'pre_nav':pre_nav,'cash_pre':cash0,'cash_post':cash_after,'trim':trim+ (forced_trim if arm=='CASH_FLOW_FIRST' else 0.),'base_trim':base_trim,'avoided':avoided,'reduced':reduced,'required':required,'pre':pre,'post':values,'cost':cost,'maxweight':max((v/pre_nav for v in pre.values()),default=0.),'effn':1/sum((v/pre_nav)**2 for v in pre.values()) if pre else 0.,'forced':sorted(forced) if arm=='CASH_FLOW_FIRST' else []}
   state[arm]=(values,cash_after)
  # baseline should exactly equal frozen net return (within accounting fp tolerance).
  assert abs(result['BASE']['net']-r['net'])<1e-10,(window,r['date'],result['BASE']['net'],r['net'])
  out.append({'window':window,'date':r['date'],'panel_type':'ORDINARY_PANEL' if r['scheduled_base'] else 'INTERMEDIATE_PANEL','baseline_net':result['BASE']['net'],'cash_flow_first_net':result['CASH_FLOW_FIRST']['net'],'baseline_trim':result['BASE']['trim'],'cff_trim':result['CASH_FLOW_FIRST']['trim'],'avoided_trim':result['CASH_FLOW_FIRST']['avoided'],'cash_pool':result['CASH_FLOW_FIRST']['cash_pre'],'base_cash':result['BASE']['cash_post'],'cff_cash':result['CASH_FLOW_FIRST']['cash_post'],'base_max_weight':result['BASE']['maxweight'],'cff_max_weight':result['CASH_FLOW_FIRST']['maxweight'],'base_effn':result['BASE']['effn'],'cff_effn':result['CASH_FLOW_FIRST']['effn'],'base_nav':result['BASE']['nav'],'cff_nav':result['CASH_FLOW_FIRST']['nav'],'turnover':r['turnover'],'cost':r['cost'],'trim_avoided':result['CASH_FLOW_FIRST']['avoided']>1e-12,'trim_reduced':result['CASH_FLOW_FIRST']['reduced']>0,'full_trim_required':result['CASH_FLOW_FIRST']['required']})
  for k in set(result['BASE']['pre'])|set(result['CASH_FLOW_FIRST']['pre']):
   b=result['BASE']['pre'].get(k,0.); c=result['CASH_FLOW_FIRST']['pre'].get(k,0.); rb=returns.get((k,r['date']),0.)
   bn=result['BASE']['pre_nav']; cn=result['CASH_FLOW_FIRST']['pre_nav']
   if b or c: detail.append({'window':window,'date':r['date'],'ticker':k,'baseline_weight':b/bn,'cff_weight':c/cn,'security_return_next_panel':rb,'baseline_contribution':b/bn*rb,'cff_contribution':c/cn*rb,'incremental_retained_weight_pnl':c/cn*rb-b/bn*rb})
 return out,detail

def main():
 panels=[]; details=[]; result={}
 for w in ('W1','W2'):
  a,b=execute(w);panels+=a;details+=b; dates=[x['date'] for x in a]; br=stats([x['baseline_net'] for x in a],dates); cr=stats([x['cash_flow_first_net'] for x in a],dates);
  for key in ['turnover','cost']: br['total_'+key]=sum(x[key] for x in a);cr['total_'+key]=sum(x[key] for x in a)
  for label,field in [('mean_cash','cff_cash'),('mean_max_weight','cff_max_weight'),('max_single_weight','cff_max_weight'),('mean_effective_n','cff_effn')]: cr[label]=(max(x[field] for x in a) if label=='max_single_weight' else sum(x[field] for x in a)/len(a))
  br['mean_cash']=sum(x['base_cash'] for x in a)/len(a);br['mean_max_weight']=sum(x['base_max_weight'] for x in a)/len(a);br['max_single_weight']=max(x['base_max_weight'] for x in a);br['mean_effective_n']=sum(x['base_effn'] for x in a)/len(a)
  result[w]={'baseline':br,'cash_flow_first':cr,'delta':{k:cr.get(k,0)-br.get(k,0) for k in br},'trim':{'baseline_total':sum(x['baseline_trim'] for x in a),'cff_total':sum(x['cff_trim'] for x in a),'reduced_volume':sum(x['avoided_trim'] for x in a),'panels_trim_avoided':sum(x['trim_avoided'] for x in a),'panels_trim_reduced':sum(x['trim_reduced'] for x in a),'panels_full_trim_required':sum(x['full_trim_required'] for x in a)}}
 with open(OUT/'PANEL_REBALANCE_AUDIT.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=panels[0].keys());w.writeheader();w.writerows(panels)
 with open(OUT/'SECURITY_TRIM_ATTRIBUTION.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=details[0].keys());w.writeheader();w.writerows(details)
 # requested named winner-ledger subset
 named={'W1':{'SAGA-B','NET-B','BALD-B'},'W2':{'VOLO','VBG-B','CLAS-B'}}
 wins=[x for x in details if x['ticker'] in named[x['window']]]
 with open(OUT/'WINNER_RETAINED_WEIGHT_ATTRIBUTION.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=details[0].keys());w.writeheader();w.writerows(wins)
 result['study']='H0_V3_CASH_FLOW_FIRST_PROPORTIONAL_EXCESS_TRIM';result['external_contribution']=0.;result['baseline_reproduction_pass']=True
 d1=result['W1']['delta']['net_cagr'];d2=result['W2']['delta']['net_cagr']; result['verdict']='CASH_FLOW_FIRST_PROMISING' if d1>0 and d2>0 else ('CASH_FLOW_FIRST_NO_VALUE' if d1<=0 and d2<=0 else 'CASH_FLOW_FIRST_MIXED')
 (OUT/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
