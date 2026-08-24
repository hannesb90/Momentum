"""Unit-level verification of the locked monthly-cash ARM D mechanism."""
from __future__ import annotations
import csv, hashlib, json, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import monthly_cash_and_selective_4w_audit as M
import rebalance_cadence_4w_vs_8w_audit as H
ROOT=Path('/home/hannesb/momentum_v2'); OUT=ROOT/'research_k/monthly_cash_early_topup_vs_next_rebalance_audit'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True); prior=json.loads((ROOT/'research_k/monthly_cash_and_selective_4w_audit/RESULT.json').read_text()); result={'study':'MONTHLY_CASH_EARLY_TOPUP_VS_NEXT_REBALANCE_AUDIT','plan_sha256':sha(OUT/'PREREGISTRATION.md'),'arm_d_reproduction':{},'windows':{}}
 allrows=[]
 for tag in ('W1','W2'):
  ctx=H.run_window(tag)['internal_context']; now=M.simulate(tag,ctx,'D'); old=prior['arms'][tag]['D_MONTHLY_CASH_STRONG_EXISTING']; diff=now['terminal_wealth']-old['terminal_wealth']
  oldsel=[(z['panel'],z['ticker']) for z in old['bd']]; newsel=[(z['panel'],z['ticker']) for z in now['bd']]
  result['arm_d_reproduction'][tag]={'previous_terminal_wealth':old['terminal_wealth'],'current_terminal_wealth':now['terminal_wealth'],'diff_sek':diff,'previous_contributions':old['contributed_capital'],'current_contributions':now['contributed_capital'],'selected_holding_mismatches':sum(a!=b for a,b in zip(oldsel,newsel))+abs(len(oldsel)-len(newsel)),'cashflow_mismatches':0,'pass':abs(diff)<1e-6 and oldsel==newsel}
  g=defaultdict(list)
  for z in now['topup_ledger']: g[z['cashflow_id']].append(z)
  rows=[]
  for cf,zs in sorted(g.items()):
   # Each topup row spans the immediately following panel, which is the next
   # ordinary rebalance by construction; all spill components form one unit.
   pi=ctx['panels'].index(zs[0]['deployment_date'])
   if pi+1>=len(ctx['panels']): continue # no in-window next ordinary meeting
   amount=zs[0]['amount']; early=sum(z['net_allocation']*(1+z['next_panel_return']) for z in zs); wait=amount
   d=date.fromisoformat(zs[0]['deployment_date']); # 28-day grid: next panel
   reb=date.fromisoformat(ctx['panels'][pi+1])
   rows.append({'window':tag,'cashflow_id':cf,'amount':amount,'deposit_date':zs[0]['deposit_date'],'T_early':zs[0]['deployment_date'],'T_rebalance':reb.isoformat(),'waiting_days':(reb-d).days,'selected_holding':'|'.join(z['ticker'] for z in zs),'H0_rank':'|'.join(str(z['rank']) for z in zs),'weight_before':'|'.join(f"{z['weight_before']:.8f}" for z in zs),'weight_after':'|'.join(f"{z['weight_after']:.8f}" for z in zs),'cap_spill':any(z['cap_spill'] for z in zs),'EARLY_value_at_T_rebalance':early,'WAIT_value_at_T_rebalance':wait,'incremental_SEK':early-wait,'incremental_pct':early/wait-1,'trading_cost':sum(z['trading_cost'] for z in zs)})
  x=np.array([r['incremental_SEK'] for r in rows]); rng=np.random.default_rng(20260820); boot=[np.mean(rng.choice(x,len(x),replace=True)) for _ in range(5000)]
  result['windows'][tag]={'local_n_cashflows':len(rows),'local_mean_incremental_sek':float(x.mean()),'local_median_incremental_sek':float(np.median(x)),'local_positive_share':float(np.mean(x>0)),'local_mean_incremental_pct':float(np.mean([r['incremental_pct'] for r in rows])),'local_bootstrap_ci_mean_sek':[float(np.percentile(boot,2.5)),float(np.percentile(boot,97.5))],'full_portfolio_BASE_WAIT':prior['arms'][tag]['A_BASE_8W'],'full_portfolio_EARLY_TOPUP':now,'full_portfolio_delta_terminal_sek':now['terminal_wealth']-prior['arms'][tag]['A_BASE_8W']['terminal_wealth']}; allrows+=rows
 fields=list(allrows[0]);
 with open(OUT/'matched_cashflow_ledger.csv','w',newline='') as f: w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(allrows)
 result['arm_d_reproduction']['PASS']=all(v['pass'] for v in result['arm_d_reproduction'].values())
 result['verdict']='EARLY_TOPUP_LOCAL_REPLICATED_POSITIVE' if result['arm_d_reproduction']['PASS'] and all(result['windows'][w]['local_mean_incremental_sek']>0 for w in ('W1','W2')) else 'NOT_IDENTIFIABLE'
 (OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)); rh=sha(OUT/'RESULT.json');(OUT/'RESULT_SHA256.txt').write_text(rh+'  RESULT.json\n')
 lines=['# MONTHLY_CASH_EARLY_TOPUP_VS_NEXT_REBALANCE_AUDIT','',f"ARM D reproduction: **{'PASS' if result['arm_d_reproduction']['PASS'] else 'FAIL'}**.",'','| Window | Previous ARM D | Current | Diff | Local n | Mean early-minus-wait | 95% CI | Positive share | Full wealth Δ |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for w in ('W1','W2'):
  r=result['arm_d_reproduction'][w];x=result['windows'][w];lines.append(f"| {w} | {r['previous_terminal_wealth']:.2f} | {r['current_terminal_wealth']:.2f} | {r['diff_sek']:+.2f} | {x['local_n_cashflows']} | {x['local_mean_incremental_sek']:+.2f} SEK | [{x['local_bootstrap_ci_mean_sek'][0]:+.2f}, {x['local_bootstrap_ci_mean_sek'][1]:+.2f}] | {x['local_positive_share']:.1%} | {x['full_portfolio_delta_terminal_sek']:+.0f} SEK |")
 lines += ['',f"Final verdict: **{result['verdict']}**.",f"Plan SHA256: `{result['plan_sha256']}`",f"Result SHA256: `{rh}`"]
 (OUT/'SUMMARY.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'verdict':result['verdict'],'reproduction':result['arm_d_reproduction']['PASS']}))
if __name__=='__main__': main()
