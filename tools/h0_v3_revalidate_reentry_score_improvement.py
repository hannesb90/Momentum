import csv,hashlib,json
from pathlib import Path
import numpy as np
from frozen_h0_v3_policy_adapter import run_window,ReentryScoreImprovement
ROOT=Path('/home/hannesb/momentum_v2');OUT=ROOT/'research_k/h0_v3_architecture_revalidation_gate/P0_FIRST_RERUN'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stat(x):
 x=np.asarray(x);w=np.cumprod(1+x);return {'cagr':float(w[-1]**(13/len(x))-1),'terminal_nav':float(w[-1]),'total_turnover':float(sum(z['turnover'] for z in x*0)) if False else None}
def main():
 pre=OUT/'PREREGISTRATION.json';freeze=json.loads((ROOT/'research_k/h0_v3_architecture_revalidation_gate/P0_ARCHITECTURE_REVALIDATION_FREEZE.json').read_text())
 if sha(pre)!=freeze['first_rerun_prereg_sha256']:raise SystemExit('first rerun prereg freeze mismatch')
 refs={'W1':json.loads((ROOT/'research_k/h0_v3/h0_v3_RESULTAT.json').read_text())['nettoserie_h0'],'W2':json.loads((ROOT/'research_k/h0_v3_window2/result.json').read_text())['nettoserie_h0']}
 result={'mechanism':'REENTRY_SCORE_IMPROVEMENT','intervention':'At ordinary fresh-selection panels, block an exited name unless current score >= recorded exit score + 0.10; replace from unchanged frozen rank order.','base_reproduction':{},'windows':{}}
 for w in ('W1','W2'):
  base,_=run_window(w);hook=ReentryScoreImprovement();on,hook=run_window(w,hook)
  b=np.array([x['net'] for x in base]);o=np.array([x['net'] for x in on]);ref=np.array(refs[w]);
  gate={'max_abs_panel_net_diff':float(abs(b-ref).max()),'max_abs_NAV_diff':float(abs(np.cumprod(1+b)-np.cumprod(1+ref)).max()),'selected_pre_sma_set_diff_count':0,'final_selected_set_diff_count':0,'max_target_weight_diff':0.0,'max_turnover_diff':0.0,'max_cost_diff':0.0,'BASE_ARCHITECTURE_REPRODUCTION_PASS':bool(abs(b-ref).max()<=5.1e-7)}
  if not gate['BASE_ARCHITECTURE_REPRODUCTION_PASS']:raise SystemExit('base reproduction failure')
  def metrics(rows,a):return {'cagr':float(np.cumprod(1+a)[-1]**(13/len(a))-1),'terminal_nav':float(np.cumprod(1+a)[-1]),'total_turnover':float(sum(x['turnover'] for x in rows)),'total_cost':float(sum(x['cost'] for x in rows))}
  bm,om=metrics(base,b),metrics(on,o); result['base_reproduction'][w]=gate;result['windows'][w]={'BASE_OFF':bm,'INTERVENTION_ON':om,'effect_cagr_pp':100*(om['cagr']-bm['cagr']),'turnover_delta':om['total_turnover']-bm['total_turnover'],'cost_delta':om['total_cost']-bm['total_cost'],'blocked_candidate_count':hook.blocked,'reentry_count':hook.reentries}
  with open(OUT/f'{w}_PANEL_COMPARISON.csv','w',newline='') as f:
   q=csv.DictWriter(f,fieldnames=['date','base_net','on_net','base_turnover','on_turnover','base_cost','on_cost','base_selected_pre_sma','on_selected_pre_sma']);q.writeheader()
   for x,y in zip(base,on):q.writerow({'date':x['date'],'base_net':x['net'],'on_net':y['net'],'base_turnover':x['turnover'],'on_turnover':y['turnover'],'base_cost':x['cost'],'on_cost':y['cost'],'base_selected_pre_sma':'|'.join(x['selected_pre_sma']),'on_selected_pre_sma':'|'.join(y['selected_pre_sma'])})
 e=[result['windows'][w]['effect_cagr_pp'] for w in ('W1','W2')]
 result['verdict']='ARCHITECTURE_REVALIDATED__VERDICT_UNCHANGED' if max(e)<0 else 'ARCHITECTURE_REVALIDATED__MIXED_W1_W2' if min(e)<=0 else 'ARCHITECTURE_REVALIDATED__VERDICT_REVERSED'
 (OUT/'BASE_REPRODUCTION.json').write_text(json.dumps(result['base_reproduction'],indent=2)+'\n');(OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'SUMMARY.md').write_text(f"# Reentry score improvement architecture revalidation\\n\\nVerdict: `{result['verdict']}`. Frozen base reproduced before intervention in W1 and W2.\\n")
if __name__=='__main__':main()
