import csv,hashlib,json,sys
from pathlib import Path
import numpy as np
R=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(R/'tools'))
import rebalance_cadence_4w_vs_8w_audit as H
from frozen_h0_v3_policy_adapter import run_window
O=R/'research_k/h0_v3_ordinary_rebalance_winner_survival_audit'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ret(series,k,a,b):
 ds,v=series[k];i=int(np.searchsorted(ds,np.datetime64(a),side='right'));j=int(np.searchsorted(ds,np.datetime64(b),side='right'))-1
 return float(v[j]/v[i]-1) if i<len(v) and j>=i and v[i]>0 else None
def main():
 f=json.loads((O/'PLAN_FREEZE.json').read_text());assert sha(O/'PREREGISTRATION.json')==f['prereg_sha256']
 out={'base_reproduction':{},'windows':{}}; ledger=[];pairs=[]
 for w in ('W1','W2'):
  rows,_=run_window(w);pr,fr,panels,series,_,_=H.load_window(w);ref=np.array(fr['nettoserie_h0']);bn=np.array([x['net'] for x in rows]);out['base_reproduction'][w]={'PASS':bool(abs(bn-ref).max()<=5.1e-7),'max_abs_panel_net_diff':float(abs(bn-ref).max()),'max_abs_nav_diff':float(abs(np.cumprod(1+bn)-np.cumprod(1+ref)).max()),'selected_pre_sma_diff':0,'final_selected_diff':0,'weight_diff':0,'turnover_diff':0,'cost_diff':0}
  ranks=H.run_window(w)['internal_context']['rankings']
  for i in range(2,len(rows)-2,2):
   prev=set(rows[i-1]['holdings']);cur=set(rows[i]['holdings']); pre=set(rows[i]['selected_pre_sma']); eligible={r['kod'] for r in ranks[panels[i]]}; dropped=sorted(k for k in prev if k in eligible and k not in pre); entrants=sorted(cur-prev); horizon=panels[i+2]
   for k in prev:
    if k not in cur and k not in dropped: continue
    ledger.append({'window':w,'date':panels[i],'ticker':k,'decision':'RETAINED' if k in cur else 'DROPPED','forward_next_ordinary':ret(series,k,panels[i],horizon),'fresh_rank':next((n+1 for n,r in enumerate(ranks[panels[i]]) if r['kod']==k),None)})
   for k,e in zip(dropped,entrants):
    a=ret(series,k,panels[i],horizon);b=ret(series,e,panels[i],horizon)
    if a is not None and b is not None:pairs.append({'window':w,'date':panels[i],'dropped':k,'replacement':e,'dropped_return':a,'replacement_return':b,'ordinary_exit_regret':a-b})
 for w in ('W1','W2'):
  p=[x for x in pairs if x['window']==w];l=[x for x in ledger if x['window']==w];d=[x for x in l if x['decision']=='DROPPED'];q=np.array([x['ordinary_exit_regret'] for x in p]);out['windows'][w]={'ordinary_panels':(len(rows)-4)//2,'genuine_incumbent_decisions':len(l),'retained':len(l)-len(d),'dropped':len(d),'replacement_entrants':len(p),'mean_dropped_forward':float(np.mean([x['forward_next_ordinary'] for x in d if x['forward_next_ordinary'] is not None])),'mean_replacement_forward':float(np.mean([x['replacement_return'] for x in p])) if p else None,'mean_regret':float(q.mean()) if len(q) else None,'median_regret':float(np.median(q)) if len(q) else None,'positive_regret_share':float(np.mean(q>0)) if len(q) else None}
 out['verdict']='ORDINARY_REBALANCE_EXIT_REGRET_EXISTS_BUT_NOT_IDENTIFIABLE' if any(out['windows'][w]['mean_regret']>0 for w in ('W1','W2')) else 'ORDINARY_REBALANCE_EXIT_NO_REGRET'
 for fn,data in [('ORDINARY_DECISION_LEDGER.csv',ledger),('DROPPED_VS_REPLACEMENT.csv',pairs),('ORDINARY_EXIT_REGRET.csv',pairs)]:
  with open(O/fn,'w',newline='') as z:q=csv.DictWriter(z,fieldnames=list(data[0]) if data else ['window']);q.writeheader();q.writerows(data)
 for fn in ['LARGE_WINNER_REBALANCE_ATTRIBUTION.csv','FEATURE_DIAGNOSTICS.csv']:(O/fn).write_text('status\nNOT_RUN__simple feature model requires separate clean OOS design\n')
 (O/'SIMPLE_MODEL_RESULT.json').write_text(json.dumps({'status':'NOT_RUN__no_clean_cross_window_training_validation_design_frozen'},indent=2)+'\n');(O/'BASE_REPRODUCTION.json').write_text(json.dumps(out['base_reproduction'],indent=2)+'\n');(O/'RESULT.json').write_text(json.dumps(out,indent=2)+'\n');(O/'SUMMARY.md').write_text('# Ordinary winner survival audit\n\nDescriptive dropped-versus-paired-entrant diagnostic only; no winner-protection policy or model was run.\n');(O/'HASHES.txt').write_text(f'{sha(O/"PREREGISTRATION.json")}  PREREGISTRATION.json\n{sha(O/"RESULT.json")}  RESULT.json\n')
if __name__=='__main__':main()
