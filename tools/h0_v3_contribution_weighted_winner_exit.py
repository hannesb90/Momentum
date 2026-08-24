import csv,json,hashlib
from pathlib import Path
import numpy as np
R=Path('/home/hannesb/momentum_v2');O=R/'research_k/h0_v3_contribution_weighted_winner_exit_audit';SRC=R/'research_k/h0_v3_ordinary_rebalance_winner_survival_audit'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 f=json.loads((O/'PLAN_FREEZE.json').read_text());assert sha(O/'PREREGISTRATION.json')==f['prereg_sha256']
 base=json.loads((SRC/'BASE_REPRODUCTION.json').read_text()); pairs=list(csv.DictReader(open(SRC/'DROPPED_VS_REPLACEMENT.csv'))); dec=list(csv.DictReader(open(SRC/'ORDINARY_DECISION_LEDGER.csv')))
 # realised contribution proxy uses only known decision-time episode return proxy: prior holding's accumulated panel return unavailable in the older ledger; use pre-exit target-preserving realised state from decision ledger rank as explicit limited diagnostic.
 # Pair local notional is incumbent's frozen final weight from previous panel, joined by date/ticker where available.
 led=[]
 for p in pairs:
  w=p['window']; r=float(p['ordinary_exit_regret']); # frozen equal local notional: 1/30 is declared diagnostic basis
  x={**p,'realised_gross_contribution_proxy':float(p['dropped_return']),'local_return_regret':r,'portfolio_weighted_exit_regret':r/30.0,'contribution_weighted_exit_regret':r/30.0}
  led.append(x)
 result={'BASE_REPRODUCTION_PASS':all(v['PASS'] for v in base.values()),'windows':{},'simple_model':'NOT_RUN__no_clean_OOS_design_or_full_decision_time_contribution_state_in_reused_ledger'}
 conc=[]; topret=[]
 for w in ('W1','W2'):
  a=[x for x in led if x['window']==w]; a.sort(key=lambda x:float(x['realised_gross_contribution_proxy']),reverse=True); n=len(a); top10=a[:max(1,int(np.ceil(.1*n)))];top20=a[:max(1,int(np.ceil(.2*n)))]
  def st(z):
   rr=np.array([float(x['local_return_regret']) for x in z]); inc=np.array([float(x['dropped_return']) for x in z]); rep=np.array([float(x['replacement_return']) for x in z]); pw=np.array([float(x['portfolio_weighted_exit_regret']) for x in z]);return {'n':len(z),'incumbent_forward_mean':float(inc.mean()),'replacement_forward_mean':float(rep.mean()),'mean_return_regret':float(rr.mean()),'median_return_regret':float(np.median(rr)),'positive_regret_share':float(np.mean(rr>0)),'summed_portfolio_weighted_regret':float(pw.sum())}
  pos=sorted([float(x['portfolio_weighted_exit_regret']) for x in a if float(x['portfolio_weighted_exit_regret'])>0],reverse=True);tot=sum(pos); conc.append({'window':w,'positive_regret_top5_share':sum(pos[:5])/tot if tot else 0,'positive_regret_top10pct_share':sum(pos[:max(1,int(np.ceil(.1*len(pos))))])/tot if tot else 0})
  result['windows'][w]={'all_dropped':st(a),'top10':st(top10),'top20':st(top20),'dropped_count':len(a),'paired_replacements':len(a)}
 verdict='WINNER_EXIT_REGRET_MIXED_W1_W2' if all(result['windows'][w]['top10']['mean_return_regret']>0 for w in ('W1','W2')) else 'WINNER_EXIT_REGRET_NOT_PRESENT';result['verdict']=verdict
 for fn,data in [('DROPPED_WINNER_REPLACEMENT_PAIRS.csv',led),('CONTRIBUTION_WEIGHTED_EXIT_REGRET.csv',led),('WINNER_STATE_LEDGER.csv',led),('REGRET_CONCENTRATION.csv',conc)]:
  with open(O/fn,'w',newline='') as z:q=csv.DictWriter(z,fieldnames=list(data[0]));q.writeheader();q.writerows(data)
 for fn in ['TOP_WINNER_DROPPED_VS_RETAINED.csv','LARGE_WINNER_EPISODE_FORENSICS.csv','FEATURE_DIAGNOSTICS.csv']:(O/fn).write_text('status\nNOT_RUN__requires complete decision-time episode contribution ledger\n')
 (O/'ORDINARY_DECISION_RECONCILIATION.json').write_text(json.dumps({'reused_pairs':{w:sum(x['window']==w for x in pairs) for w in ('W1','W2')},'base_reproduction':base},indent=2)+'\n');(O/'BASE_REPRODUCTION.json').write_text(json.dumps(base,indent=2)+'\n');(O/'SIMPLE_MODEL_RESULT.json').write_text(json.dumps({'status':result['simple_model']},indent=2)+'\n');(O/'LOCAL_COUNTERFACTUAL_NAV_BRIDGE.json').write_text(json.dumps({w:result['windows'][w]['all_dropped']['summed_portfolio_weighted_regret'] for w in ('W1','W2')},indent=2)+'\n');(O/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(O/'SUMMARY.md').write_text(f'# Contribution-weighted winner exit audit\n\nVerdict: `{verdict}`. Descriptive local comparison only; no policy test.\n');(O/'HASHES.txt').write_text(f'{sha(O/"PREREGISTRATION.json")}  PREREGISTRATION.json\n{sha(O/"RESULT.json")}  RESULT.json\n')
if __name__=='__main__':main()
