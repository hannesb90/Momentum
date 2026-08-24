"""Single exploratory TOP3_PNL_CARRIER_CASHFLOW_FIRST mechanism test.

Frozen selection/returns/costs remain untouched.  Only funding order changes:
eligible realised episode-P&L carriers are the final source of trim funding.
"""
import csv,json,math,sys
from collections import defaultdict
from datetime import date
from pathlib import Path
ROOT=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(ROOT/'tools'))
import rebalance_cadence_4w_vs_8w_audit as H
TOPN=int(sys.argv[1]) if len(sys.argv)>1 else 3
OUT=ROOT/f'research_k/h0_v3_top{TOPN}_pnl_carrier_cashflow_first_audit';OUT.mkdir(parents=True,exist_ok=True)
def st(xs,dates):
 nav=1.;ns=[]
 for x in xs:nav*=1+x;ns.append(nav)
 yrs=(date.fromisoformat(str(dates[-1]))-date.fromisoformat(str(dates[0]))).days/365.25
 peak=1;dd=0
 for x in ns:peak=max(peak,x);dd=min(dd,x/peak-1)
 mu=sum(xs)/len(xs);sd=(sum((x-mu)**2 for x in xs)/(len(xs)-1))**.5
 return {'net_cagr':nav**(1/yrs)-1,'terminal_nav':nav,'max_drawdown':dd,'volatility':sd,'sharpe':mu/sd*math.sqrt(365.25/28) if sd else None}
def cost(vals,cash,x):
 if x<=cash:return vals,cash-x
 rem=x-cash; total=sum(vals.values()); f=1-rem/total if total else 1
 return {k:v*f for k,v in vals.items()},0.
def run(w):
 c=H.run_window(w)['internal_context']; rows=c['base'];ret=c['returns']
 # State: values/cash plus uninterrupted holding-episode realised data.
 arms={'BASE':({'v':{},'cash':1.,'ep':{}}),'TOP3':({'v':{},'cash':1.,'ep':{}})}; panel=[]; secur=[]; protlog=[]
 for r in rows:
  target=r['weights'];sel=set(target); rowres={}
  for arm,s in arms.items():
   old=s['v'];nav=sum(old.values())+s['cash']; cont={k:v for k,v in old.items() if k in sel}; exits={k:v for k,v in old.items() if k not in sel}; cashpool=s['cash']+sum(exits.values()); desired={k:target[k]*nav for k in target}; buys={k:max(0,desired[k]-cont.get(k,0)) for k in target}; need=sum(buys.values()); excess={k:max(0,cont.get(k,0)-desired[k]) for k in target};base_trim=sum(excess.values())
   protected=[]
   if arm=='TOP3':
    elig=[]
    for k,x in excess.items():
     e=s['ep'].get(k)
     if x>0 and e and e['pnl']>0 and e['stockprod']>1:elig.append((e['pnl'],k))
    protected=[k for _,k in sorted(elig,key=lambda z:(-z[0],z[1]))[:TOPN]]
   shortage=max(0,need-cashpool); non=[k for k in excess if k not in protected]; nsum=sum(excess[k] for k in non); pneed=max(0,shortage-nsum); psum=sum(excess[k] for k in protected)
   # BASE treats all excess equally; TOP3 trims nonprotected first then protected only if essential.
   if arm=='BASE':
    trimby={k:excess[k] for k in excess}
    values=dict(desired); cashafter=nav-sum(values.values())
   else:
    # Selective variant: nonprotected excess follows baseline trimming in full.
    # Only protected carriers may retain excess, and only after all other
    # baseline trim funding has been used.
    protected_shortage=max(0., need-cashpool-nsum)
    trimby={k:(excess[k] if k in non else (min(excess[k], protected_shortage*excess[k]/psum) if psum else 0.)) for k in excess}
    freed=sum(trimby.values()); values=dict(cont)
    for k,x in trimby.items():
     if k in values:values[k]-=x
    avail=cashpool+freed; scale=min(1,avail/need) if need else 1
    for k,x in buys.items():values[k]=values.get(k,0)+x*scale
    cashafter=nav-sum(values.values())
   assert abs(sum(values.values())+cashafter-nav)<1e-8
   pre=dict(values); # update realised episode P&L only after actual next return
   values={k:v*(1+ret.get((k,r['date']),0)) for k,v in values.items()}; values,cashafter=cost(values,cashafter,r['cost']*nav); post=sum(values.values())+cashafter; net=post/nav-1
   # Full exits end episodes; all selected new names enter exactly at this decision.
   for k in list(s['ep']):
    if k not in sel:del s['ep'][k]
   for k in sel:
    if k not in s['ep']:s['ep'][k]={'entry':str(r['date']),'pnl':0.,'stockprod':1.}
    sr=ret.get((k,r['date']),0.);s['ep'][k]['pnl']+=pre.get(k,0)/nav*sr;s['ep'][k]['stockprod']*=1+sr
   rowres[arm]={'net':net,'nav':post,'pre':pre,'cash':cashafter,'trim':sum(trimby.values()),'base_trim':base_trim,'protected':protected,'trimby':trimby,'maxw':max((x/nav for x in pre.values()),default=0),'effn':1/sum((x/nav)**2 for x in pre.values()) if pre else 0}
   s['v']=values;s['cash']=cashafter
  assert abs(rowres['BASE']['net']-r['net'])<1e-10
  b,t=rowres['BASE'],rowres['TOP3'];panel.append({'window':w,'date':r['date'],'baseline_net':b['net'],'top3_net':t['net'],'baseline_trim':b['trim'],'top3_trim':t['trim'],'avoided_winner_trim':sum(b['trimby'].get(k,0)-t['trimby'].get(k,0) for k in t['protected']),'protected_count':len(t['protected']),'base_cash':b['cash'],'top3_cash':t['cash'],'base_max_weight':b['maxw'],'top3_max_weight':t['maxw'],'base_effn':b['effn'],'top3_effn':t['effn'],'turnover':r['turnover'],'cost':r['cost']})
  for k in t['protected']:
   retained=t['pre'].get(k,0)/max(1e-18,sum(t['pre'].values())+t['cash'])-b['pre'].get(k,0)/max(1e-18,sum(b['pre'].values())+b['cash']); sr=ret.get((k,r['date']),0)
   e=arms['TOP3']['ep'][k];protlog.append({'window':w,'date':r['date'],'ticker':k,'episode_entry':e['entry'],'episode_pnl_contribution_before_return':e['pnl']-t['pre'].get(k,0)/max(1e-18,sum(t['pre'].values())+t['cash'])*sr,'episode_return_before_return':e['stockprod']/(1+sr)-1,'baseline_weight':b['pre'].get(k,0)/max(1e-18,sum(b['pre'].values())+b['cash']),'variant_weight':t['pre'].get(k,0)/max(1e-18,sum(t['pre'].values())+t['cash']),'retained_capital_weight':retained,'next_panel_return':sr,'incremental_pnl':retained*sr,'baseline_trim':b['trimby'].get(k,0),'variant_trim':t['trimby'].get(k,0)})
 return panel,protlog
def main():
 ps=[];es=[];res={}
 for w in ['W1','W2']:
  a,b=run(w);ps+=a;es+=b;dates=[x['date'] for x in a];B=st([x['baseline_net'] for x in a],dates);T=st([x['top3_net'] for x in a],dates)
  for z in [B,T]:z['turnover']=sum(x['turnover'] for x in a);z['cost']=sum(x['cost'] for x in a)
  B.update({'mean_cash':sum(x['base_cash'] for x in a)/len(a),'max_weight':max(x['base_max_weight'] for x in a),'mean_max_weight':sum(x['base_max_weight'] for x in a)/len(a),'effn':sum(x['base_effn'] for x in a)/len(a)})
  T.update({'mean_cash':sum(x['top3_cash'] for x in a)/len(a),'max_weight':max(x['top3_max_weight'] for x in a),'mean_max_weight':sum(x['top3_max_weight'] for x in a)/len(a),'effn':sum(x['top3_effn'] for x in a)/len(a)})
  res[w]={'baseline':B,'top3_carrier':T,'delta':{k:T[k]-B[k] for k in B},'funding':{'baseline_trim':sum(x['baseline_trim'] for x in a),'variant_trim':sum(x['top3_trim'] for x in a),'avoided_protected_trim':sum(x['avoided_winner_trim'] for x in a),'protected_events':sum(x['protected_count'] for x in a),'protected_trim_required':sum(float(x['baseline_trim']>x['top3_trim'])==False for x in a)}}
 with open(OUT/'PANEL_REBALANCE_LEDGER.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=ps[0].keys());w.writeheader();w.writerows(ps)
 with open(OUT/'PROTECTED_CARRIER_LEDGER.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=['window','date','ticker','episode_entry','episode_pnl_contribution_before_return','episode_return_before_return','baseline_weight','variant_weight','retained_capital_weight','next_panel_return','incremental_pnl','baseline_trim','variant_trim']);w.writeheader();w.writerows(es)
 res['baseline_reproduction_pass']=True;res['mechanism']=f'TOP{TOPN}_PNL_CARRIER_CASHFLOW_FIRST';res['exploratory_posthoc_parameter_variant']=TOPN!=3;d1=res['W1']['delta']['net_cagr'];d2=res['W2']['delta']['net_cagr'];res['verdict']='TOPN_CARRIER_REBALANCE_PROMISING' if d1>0 and d2>0 else ('TOPN_CARRIER_REBALANCE_NO_VALUE' if d1<=0 and d2<=0 else 'TOPN_CARRIER_REBALANCE_MIXED')
 (OUT/'RESULT.json').write_text(json.dumps(res,sort_keys=True,indent=2)+'\n');print(json.dumps(res,indent=2))
if __name__=='__main__':main()
