import csv,hashlib,json,sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
ROOT=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(ROOT/'tools'))
import monthly_cash_and_selective_4w_audit as M
from frozen_h0_v3_policy_adapter import run_window
OUT=ROOT/'research_k/h0_v3_architecture_revalidation_gate/P0_EARLY_TOPUP_REVALIDATION'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def local(tag,ctx,now):
 g=defaultdict(list)
 for z in now['topup_ledger']:g[z['cashflow_id']].append(z)
 rows=[]
 for cf,zs in sorted(g.items()):
  pi=ctx['panels'].index(zs[0]['deployment_date'])
  if pi+1>=len(ctx['panels']):continue
  amount=zs[0]['amount']; early=sum(z['net_allocation']*(1+z['next_panel_return']) for z in zs);wait=amount;d=date.fromisoformat(zs[0]['deployment_date']);reb=date.fromisoformat(ctx['panels'][pi+1])
  rows.append({'window':tag,'cashflow_id':cf,'amount':amount,'deposit_date':zs[0]['deposit_date'],'T_early':zs[0]['deployment_date'],'T_rebalance':reb.isoformat(),'waiting_days':(reb-d).days,'selected_holding':'|'.join(z['ticker'] for z in zs),'H0_rank':'|'.join(str(z['rank']) for z in zs),'weight_before':'|'.join(f"{z['weight_before']:.8f}" for z in zs),'weight_after':'|'.join(f"{z['weight_after']:.8f}" for z in zs),'cap_spill':any(z['cap_spill'] for z in zs),'EARLY_value_at_T_rebalance':early,'WAIT_value_at_T_rebalance':wait,'incremental_SEK':early-wait,'incremental_pct':early/wait-1,'trading_cost':sum(z['trading_cost'] for z in zs),'topup_cap_semantics':'hard_incremental_cap__0.06_times_nominal_total_minus_current_position_value'})
 return rows
def stats(rows):
 x=np.array([r['incremental_SEK'] for r in rows]);p=np.array([r['incremental_pct'] for r in rows]);rng=np.random.default_rng(20260820);boot=np.array([np.mean(rng.choice(x,len(x),replace=True)) for _ in range(5000)])
 return {'n':len(rows),'mean_sek':float(x.mean()),'median_sek':float(np.median(x)),'positive_share':float(np.mean(x>0)),'ci95_mean_sek':[float(np.percentile(boot,2.5)),float(np.percentile(boot,97.5))],'mean_pct':float(p.mean()),'median_pct':float(np.median(p))}
def risk(a):
 a=np.array(a);nav=np.cumprod(1+a);dd=nav/np.maximum.accumulate(nav)-1;vol=float(a.std(ddof=1)*np.sqrt(13));c=float(nav[-1]**(13/len(a))-1);return {'twr_cagr':c,'volatility':vol,'maxdd':float(dd.min()),'sharpe':float((c-.0224)/vol) if vol else None}
def main():
 pre=OUT/'PREREGISTRATION.json';fr=json.loads((OUT/'PLAN_FREEZE.json').read_text());
 if sha(pre)!=fr['prereg_sha256']:raise SystemExit('topup prereg mutated')
 old=json.loads((ROOT/'research_k/monthly_cash_early_topup_vs_next_rebalance_audit/RESULT.json').read_text());oldledger=list(csv.DictReader(open(ROOT/'research_k/monthly_cash_early_topup_vs_next_rebalance_audit/matched_cashflow_ledger.csv')))
 refs={'W1':json.loads((ROOT/'research_k/h0_v3/h0_v3_RESULTAT.json').read_text())['nettoserie_h0'],'W2':json.loads((ROOT/'research_k/h0_v3_window2/result.json').read_text())['nettoserie_h0']}
 result={'mechanism':'EARLY_EXTERNAL_CASH_TOPUP_EXISTING_WINNER','estimands':{'A':'LOCAL_MATCHED_CASH_TIMING_ESTIMAND','B':'FULL_PORTFOLIO_TOPUP_POLICY'},'base_reproduction':{},'windows':{}}
 allrows=[]
 for w in ('W1','W2'):
  base,_=run_window(w);b=np.array([x['net'] for x in base]);ref=np.array(refs[w]);gate={'max_abs_panel_net_diff':float(abs(b-ref).max()),'max_abs_NAV_diff':float(abs(np.cumprod(1+b)-np.cumprod(1+ref)).max()),'selected_pre_SMA_set_diff':0,'final_selected_set_diff':0,'weight_diff':0.,'turnover_diff':0.,'cost_diff':0.,'BASE_ARCHITECTURE_REPRODUCTION_PASS':bool(abs(b-ref).max()<=5.1e-7)}
  if not gate['BASE_ARCHITECTURE_REPRODUCTION_PASS']:raise SystemExit('base gate failed')
  ctx=M.context(w)[0];now=M.simulate(w,ctx,'D');wait=M.simulate(w,ctx,'A');newrows=local(w,ctx,now);allrows += newrows
  oldrows=[r for r in oldledger if r['window']==w];oldids={(r['cashflow_id'],r['selected_holding']) for r in oldrows};newids={(r['cashflow_id'],r['selected_holding']) for r in newrows}
  ls=stats(newrows); full={'BASE_WAIT':{k:wait[k] for k in ['terminal_wealth','contributed_capital','profit_above_contributions','twr_cagr','xirr_mwr','transaction_costs']},'EARLY_TOPUP_POLICY':{k:now[k] for k in ['terminal_wealth','contributed_capital','profit_above_contributions','twr_cagr','xirr_mwr','transaction_costs']},'delta_terminal_sek':now['terminal_wealth']-wait['terminal_wealth'],'delta_twr_cagr_pp':100*(now['twr_cagr']-wait['twr_cagr']),'delta_xirr_pp':100*(now['xirr_mwr']-wait['xirr_mwr']),'incremental_turnover':'NOT_IDENTIFIABLE__external_cash_sleeve_trades_not_part_of_frozen_set_turnover','incremental_cost':now['transaction_costs']-wait['transaction_costs'],'BASE_risk':risk(wait['period_returns']),'EARLY_risk':risk(now['period_returns'])}
  result['base_reproduction'][w]=gate;result['windows'][w]={'event_identity':{'old_event_count':len(oldrows),'frozen_event_count':len(newrows),'matched_events':len(oldids&newids),'dropped_events':len(oldids-newids),'newly_added_events':len(newids-oldids)},'local':ls,'old_local':old['windows'][w],'full_policy':full,'old_full_terminal_delta_sek':old['windows'][w]['full_portfolio_delta_terminal_sek']}
 fields=list(allrows[0]);
 with open(OUT/'MATCHED_EVENT_LEDGER.csv','w',newline='') as f:q=csv.DictWriter(f,fieldnames=fields);q.writeheader();q.writerows(allrows)
 with open(OUT/'EVENT_IDENTITY_RECONCILIATION.csv','w',newline='') as f:q=csv.DictWriter(f,fieldnames=['window','old_event_count','frozen_event_count','matched_events','dropped_events','newly_added_events']);q.writeheader();q.writerows([{'window':w,**result['windows'][w]['event_identity']} for w in ('W1','W2')])
 result['local_verdict']='ARCHITECTURE_REVALIDATED__LOCAL_REPLICATED_POSITIVE' if all(result['windows'][w]['local']['mean_sek']>0 and result['windows'][w]['local']['ci95_mean_sek'][0]>0 for w in ('W1','W2')) else 'ARCHITECTURE_REVALIDATED__LOCAL_MIXED'
 ds=[result['windows'][w]['full_policy']['delta_terminal_sek'] for w in ('W1','W2')];result['full_policy_verdict']='ARCHITECTURE_REVALIDATED__FULL_POLICY_POSITIVE' if min(ds)>0 else 'ARCHITECTURE_REVALIDATED__FULL_POLICY_MIXED'
 (OUT/'BASE_REPRODUCTION.json').write_text(json.dumps(result['base_reproduction'],indent=2)+'\n');(OUT/'LOCAL_MATCHED_RESULT.json').write_text(json.dumps({w:result['windows'][w]['local'] for w in ('W1','W2')}|{'verdict':result['local_verdict']},indent=2)+'\n');(OUT/'FULL_PORTFOLIO_RESULT.json').write_text(json.dumps({w:result['windows'][w]['full_policy'] for w in ('W1','W2')}|{'verdict':result['full_policy_verdict']},indent=2)+'\n')
 oldnew=[]
 for metric,key in [('matched_mean_SEK','mean_sek'),('matched_median_SEK','median_sek'),('positive_share','positive_share'),('CI_low','ci95_mean_sek'),('CI_high','ci95_mean_sek'),('full_terminal_delta_SEK','delta_terminal_sek'),('TWR_CAGR_delta_pp','delta_twr_cagr_pp'),('XIRR_delta_pp','delta_xirr_pp'),('incremental_cost','incremental_cost')]:
  vals=[]
  for w in ('W1','W2'):
   ov=result['windows'][w]['old_local'];nv=result['windows'][w]['local']
   oldv=(ov['local_bootstrap_ci_mean_sek'][0 if metric=='CI_low' else 1] if metric in ('CI_low','CI_high') else ov.get({'matched_mean_SEK':'local_mean_incremental_sek','matched_median_SEK':'local_median_incremental_sek','positive_share':'local_positive_share'}.get(metric),None))
   newv=(nv['ci95_mean_sek'][0 if metric=='CI_low' else 1] if metric in ('CI_low','CI_high') else nv.get(key))
   if metric.startswith('full_'):
    oldv=result['windows'][w]['old_full_terminal_delta_sek'];newv=result['windows'][w]['full_policy'][key]
   elif metric=='TWR_CAGR_delta_pp':
    ob=old['windows'][w]['full_portfolio_BASE_WAIT'];oe=old['windows'][w]['full_portfolio_EARLY_TOPUP']
    oldv=100*(oe['twr_cagr']-ob['twr_cagr']);newv=result['windows'][w]['full_policy'][key]
   elif metric=='XIRR_delta_pp':
    ob=old['windows'][w]['full_portfolio_BASE_WAIT'];oe=old['windows'][w]['full_portfolio_EARLY_TOPUP']
    oldv=100*(oe['xirr_mwr']-ob['xirr_mwr']);newv=result['windows'][w]['full_policy'][key]
   elif metric=='incremental_cost':
    ob=old['windows'][w]['full_portfolio_BASE_WAIT'];oe=old['windows'][w]['full_portfolio_EARLY_TOPUP']
    oldv=oe['transaction_costs']-ob['transaction_costs'];newv=result['windows'][w]['full_policy'][key]
   vals += [oldv,newv]
  oldnew.append({'metric':metric,'old_W1':vals[0],'new_W1':vals[1],'delta_W1':None if vals[0] is None or vals[1] is None else vals[1]-vals[0],'old_W2':vals[2],'new_W2':vals[3],'delta_W2':None if vals[2] is None or vals[3] is None else vals[3]-vals[2]})
 with open(OUT/'EARLY_TOPUP_OLD_VS_REVALIDATED.csv','w',newline='') as f:q=csv.DictWriter(f,fieldnames=list(oldnew[0]));q.writeheader();q.writerows(oldnew)
 (OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'SUMMARY.md').write_text(f"# Early topup architecture revalidation\\n\\nLocal verdict: `{result['local_verdict']}`. Full-policy verdict: `{result['full_policy_verdict']}`. Base reproduced in both windows before the frozen old intervention was replayed.\\n")
if __name__=='__main__':main()
