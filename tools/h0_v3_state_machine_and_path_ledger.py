import csv,hashlib,json,sys
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
ROOT=Path('/home/hannesb/momentum_v2');OUT=ROOT/'research_k/h0_v3_state_machine_and_path_ledger';sys.path.insert(0,str(ROOT/'tools'))
import rebalance_cadence_4w_vs_8w_audit as H
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 f=json.loads((OUT/'PLAN_FREEZE.json').read_text());
 if sha(OUT/'PREREGISTRATION.md')!=f['prereg_sha256'] or sha(OUT/'H0_V3_STATE_SPEC.json')!=f['state_spec_sha256']:raise SystemExit('STOP freeze mismatch')
 allrows=[];episodes=[];repro={};trans={};attr=[]
 for tag in ('W1','W2'):
  z=H.run_window(tag); c=z['internal_context']; base=c['base']; rk=c['rankings']; ret=c['returns']; panels=c['panels'];
  ref=json.loads((ROOT/('research_k/h0_v3/h0_v3_RESULTAT.json' if tag=='W1' else 'research_k/h0_v3_window2/result.json')).read_text())['nettoserie_h0']
  got=[x['net'] for x in base]; repro[tag]={'pass':bool(np.max(np.abs(np.array(got)-np.array(ref)))<5.1e-7),'max_panel_net_diff':float(np.max(np.abs(np.array(got)-np.array(ref)))),'max_nav_diff':float(np.max(np.abs(np.cumprod(1+np.array(got))-np.cumprod(1+np.array(ref)))))}
  if not repro[tag]['pass']:raise SystemExit('STOP base reproduction')
  prevsel=set(); hist=defaultdict(list)
  for i,b in enumerate(base):
   ranks={r['kod']:(j+1,r) for j,r in enumerate(rk[b['date']])}; held=set(b['holdings']); pre=set(b['selected_pre_sma'])
   universe=set(ranks)|prevsel
   for k in universe:
    rank,row=ranks.get(k,(None,{})); prior=k in prevsel; now=k in held
    if not rank: state='UNIVERSE_INELIGIBLE'; reason='NOT_PIT_ELIGIBLE_OR_NOT_TRADED'
    elif now: state='HELD'; reason='SELECTED_AND_SMA_PASS'
    elif k in pre: state='SELECTED_PRE_SMA'; reason='SMA_FILTER_FAIL'
    else: state='UNIVERSE_ELIGIBLE_RANKED_OUT'; reason='RANK_OR_NONREBALANCE_RETENTION'
    if now and not prior: tt='REENTRY' if any(q['transition_type'] in ('ENTRY','REENTRY') for q in hist[k]) else 'ENTRY'
    elif prior and not now: tt='EXIT'
    elif now: tt='HOLD'
    else: tt='OUT'
    pr=hist[k][-1]['h0_rank'] if hist[k] else None
    w=b['weights'].get(k,0.0); pw=hist[k][-1]['target_weight'] if hist[k] else 0.0
    rnext=ret.get((k,b['date']),0.0)
    d={'window':tag,'date':b['date'],'ticker':k,'eligible':bool(rank),'eligibility_reason':reason,'mom12':row.get('m12'),'mom18':row.get('m18'),'pct_mom12':row.get('m12_rank'),'pct_mom18':row.get('m18_rank'),'h0_score':row.get('score'),'h0_rank':rank,'rank_bucket':'RANK_1_10' if rank and rank<=10 else 'RANK_11_20' if rank and rank<=20 else 'RANK_21_30' if rank and rank<=30 else 'RANK_31_50' if rank and rank<=50 else 'RANK_51_PLUS' if rank else None,'rank_delta':rank-pr if rank and pr else None,'sma200':None,'sma_pass':bool(now),'confirmation_state':None,'confirmation_multiplier':None,'volatility':None,'inverse_vol_raw':None,'selected':bool(now),'previous_selected':prior,'transition_type':tt,'target_weight':w,'previous_target_weight':pw,'actual_pretrade_weight':pw,'actual_posttrade_weight':w,'cap_limited':bool(w>=.06-1e-12),'turnover_contribution':abs(w-pw)/2,'cost_contribution':.002*abs(w-pw)/2,'portfolio_return_next_period':b['net'],'stock_return_next_period':rnext,'days_until_next_panel':28 if i+1<len(base) else 0,'days_until_next_rebalance':56 if i%2==0 else 28,'production_state':state}
    allrows.append(d);hist[k].append(d)
   prevsel=pre
  tc=Counter(x['transition_type'] for x in allrows if x['window']==tag);trans[tag]=dict(tc)
  for k,ls in hist.items():
   active=[]
   for x in ls:
    if x['selected']: active.append(x)
    elif active:
     episodes.append({'window':tag,'ticker':k,'start_date':active[0]['date'],'end_date':active[-1]['date'],'path_id':'E-'+'-'.join('H' for _ in active[1:])+'-X','path_length':len(active),'holding_rebalances':len(active),'episode_return':float(np.prod([1+x['stock_return_next_period'] for x in active])-1)});active=[]
   if active:episodes.append({'window':tag,'ticker':k,'start_date':active[0]['date'],'end_date':active[-1]['date'],'path_id':'E-'+'-'.join('H' for _ in active[1:]),'path_length':len(active),'holding_rebalances':len(active),'episode_return':float(np.prod([1+x['stock_return_next_period'] for x in active])-1)})
  for x in [a for a in allrows if a['window']==tag and a['selected']]:attr.append({'window':tag,'period_state':'ENTRY' if x['transition_type'] in ('ENTRY','REENTRY') else 'CONTINUING_HOLD','gross_contribution':x['target_weight']*x['stock_return_next_period'],'net_contribution':x['target_weight']*x['stock_return_next_period']-x['cost_contribution'],'rank_bucket':x['rank_bucket']})
 for tag in ('W1','W2'):
  rows=[x for x in allrows if x['window']==tag]
  with open(OUT/f'PATH_LEDGER_{tag}.csv','w',newline='') as q:w=csv.DictWriter(q,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 with open(OUT/'EPISODE_LEDGER.csv','w',newline='') as q:w=csv.DictWriter(q,fieldnames=list(episodes[0]));w.writeheader();w.writerows(episodes)
 with open(OUT/'PNL_ATTRIBUTION.csv','w',newline='') as q:w=csv.DictWriter(q,fieldnames=list(attr[0]));w.writeheader();w.writerows(attr)
 for tag in ('W1','W2'):
  with open(OUT/f'TRANSITION_MATRIX_{tag}.csv','w',newline='') as q:w=csv.writer(q);w.writerow(['transition_type','n']);w.writerows(trans[tag].items())
 result={'study':'H0_V3_STATE_MACHINE_AND_PATH_LEDGER','H0_FREEZE_VERIFIED':True,'base_reproduction':repro,'transition_counts':trans,'ledger_rows':{t:sum(x['window']==t for x in allrows) for t in ('W1','W2')},'portfolio_decision_components':['PIT eligibility','m12/m18 rank','8W/non-8W selection state','SMA200 post-selection filter','inverse-vol^1.5','confirmation multiplier','1-6% clip + renormalization','turnover cost'],'forbidden_mechanisms_in_production_tree':json.loads((OUT/'H0_V3_STATE_SPEC.json').read_text())['forbidden_nonproduction_mechanisms']}
 (OUT/'BASE_REPRODUCTION.json').write_text(json.dumps(repro,indent=2));(OUT/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
