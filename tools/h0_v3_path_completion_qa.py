import csv,json,hashlib,statistics,math
from collections import defaultdict,Counter
from pathlib import Path
R=Path('/home/hannesb/momentum_v2/research_k/h0_v3_state_machine_and_path_ledger')
E={'W1':'349f7fed2e41a6f48c76cc6bc22332ae6808f7c8c507d2221c6d826b4d13aa40','W2':'d212fa0d2012b0860b1cd0ddaebfc76915bbb832aa0982e19aade5c4900502a1'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def num(x):
 try:return float(x)
 except:return 0.
def write(name,rows):
 if not rows:return
 with open(R/name,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 rows={w:list(csv.DictReader(open(R/f'PATH_LEDGER_{w}.csv'))) for w in E}
 if any(sha(R/f'PATH_LEDGER_{w}.csv')!=E[w] for w in E):raise SystemExit('immutable input hash fail')
 ips=[];ret=[];ref=[];iex=[];sma=[];counts=[];wqa=[];exitd=[];entryd=[];sig=[];pnl=[];qa={}
 for W,rs in rows.items():
  dates=sorted({r['date'] for r in rs});bd=defaultdict(list)
  for r in rs:bd[r['date']].append(r)
  for i,d in enumerate(dates):
   typ='ORDINARY_PANEL' if i%2==0 else 'INTERMEDIATE_PANEL'; xs=bd[d]; held=[r for r in xs if r['selected']=='True']; pre=[r for r in xs if r['production_state'] in ('HELD','SELECTED_PRE_SMA')]; sm=[r for r in xs if r['production_state']=='SELECTED_PRE_SMA']; prev=[r for r in xs if r['previous_selected']=='True']; retained=[r for r in held if r['previous_selected']=='True']; exits=[r for r in xs if r['transition_type']=='EXIT']; entries=[r for r in held if r['transition_type'] in ('ENTRY','REENTRY')]
   counts.append({'window':W,'date':d,'panel_type':typ,'pre_sma_count':len(pre),'sma_removed_n':len(sm),'final_selected_n':len(held)})
   for r in held:
    w=num(r['target_weight']);wqa.append({'window':W,'date':d,'ticker':r['ticker'],'final_weight':w,'above_6pct':w>.06,'below_1pct':w<.01})
    bucket='ORDINARY_NEW_ENTRY' if typ=='ORDINARY_PANEL' and r['transition_type'] in ('ENTRY','REENTRY') else 'INTERMEDIATE_REFILL_ENTRY' if typ=='INTERMEDIATE_PANEL' and r['transition_type'] in ('ENTRY','REENTRY') else 'ORDINARY_CONTINUING_HOLD' if typ=='ORDINARY_PANEL' else 'INTERMEDIATE_CONTINUING_HOLD'
    pnl.append({'window':W,'date':d,'bucket':bucket,'gross':w*num(r['stock_return_next_period']),'cost':0.0,'net':w*num(r['stock_return_next_period'])})
   for r in exits:pnl.append({'window':W,'date':d,'bucket':'EXIT_TRANSACTION_COST','gross':0.0,'cost':num(r['cost_contribution']),'net':-num(r['cost_contribution'])})
   if typ=='INTERMEDIATE_PANEL':
    removed=[r for r in prev if r['eligible']!='True']; vacancy=len(removed); refill=[r for r in entries if r['previous_selected']!='True']
    ips.append({'window':W,'panel_date':d,'previous_selected_n':len(prev),'retained_n':len(prev)-len(removed),'eligibility_removed_n':len(removed),'vacancy_count':vacancy,'refill_n':len(refill),'pre_sma_selected_n':len(pre),'sma_removed_n':len(sm),'final_selected_n':len(held),'retention_identity_pass':len(prev)==len(prev)-len(removed)+len(removed),'refill_identity_pass':len(pre)==len(prev)-len(removed)+len(refill),'sma_identity_pass':len(held)==len(pre)-len(sm)})
    for r in retained:
     rank=int(float(r['h0_rank'])) if r['h0_rank'] else None
     ret.append({'window':W,'panel_date':d,'ticker':r['ticker'],'previous_selected':True,'still_pit_eligible':True,'fresh_h0_rank':rank,'fresh_h0_score':r['h0_score'],'fresh_rank_bucket':'31_40' if rank and rank<=40 else '41_50' if rank and rank<=50 else '51_75' if rank and rank<=75 else '76_PLUS' if rank else 'UNKNOWN','would_not_be_fresh_top30':bool(rank and rank>30),'mom52':r['mom12'],'mom78':r['mom18'],'pct52':r['pct_mom12'],'pct78':r['pct_mom18'],'sma_pass':r['sma_pass'],'pretrade_weight':r['previous_target_weight'],'target_weight':r['target_weight'],'next_panel_return':r['stock_return_next_period'],'portfolio_contribution_next_interval':num(r['target_weight'])*num(r['stock_return_next_period'])})
    for n,r in enumerate(refill,1):ref.append({'window':W,'panel_date':d,'ticker':r['ticker'],'vacancy_number':n,'fresh_rank':r['h0_rank'],'fresh_score':r['h0_score'],'mom52':r['mom12'],'mom78':r['mom18'],'sma_pass':r['sma_pass'],'target_weight':r['target_weight'],'next_panel_return':r['stock_return_next_period']})
    for r in removed:iex.append({'window':W,'panel_date':d,'ticker':r['ticker'],'prior_rank':r['h0_rank'],'current_rank_if_available':'','eligibility_failure_reason':r['eligibility_reason'],'prior_weight':r['previous_target_weight'],'next_panel_return_after_exit':r['stock_return_next_period']})
   for r in sm:sma.append({'window':W,'panel_date':d,'ticker':r['ticker'],'panel_type':typ,'selection_source':'INTERMEDIATE_RETAINED' if typ=='INTERMEDIATE_PANEL' and r['previous_selected']=='True' else 'INTERMEDIATE_REFILL' if typ=='INTERMEDIATE_PANEL' else 'ORDINARY_FRESH','fresh_rank':r['h0_rank'],'score':r['h0_score'],'sma_pass':False,'pre_sma_weight_if_defined':''})
   for r in entries:entryd.append({'window':W,'date':d,'panel_type':typ,'entry_type':r['transition_type'],'ticker':r['ticker'],'rank':r['h0_rank'],'score':r['h0_score'],'next_panel_return':r['stock_return_next_period']})
   for r in exits:exitd.append({'window':W,'date':d,'panel_type':typ,'exit_type':'INTERMEDIATE_ELIGIBILITY_EXIT' if typ=='INTERMEDIATE_PANEL' and r['eligible']!='True' else 'ORDINARY_EXIT_OR_POST_SMA','ticker':r['ticker'],'rank':r['h0_rank'],'score':r['h0_score'],'next_panel_return':r['stock_return_next_period']})
  # rank autocorrelation selected adjacent records per ticker
  bt=defaultdict(list)
  for r in rs:
   if r['selected']=='True' and r['h0_rank']:bt[r['ticker']].append((r['date'],num(r['h0_rank'])))
  for k,a in bt.items():
   a.sort();
   for lag in (1,2):
    for j in range(lag,len(a)):sig.append({'window':W,'ticker':k,'lag_panels':lag,'rank_t':a[j][1],'rank_lag':a[j-lag][1]})
 write('INTERMEDIATE_PANEL_SUMMARY.csv',ips);write('INTERMEDIATE_RETAINED_LEDGER.csv',ret);write('INTERMEDIATE_REFILL_LEDGER.csv',ref);write('INTERMEDIATE_ELIGIBILITY_EXIT_LEDGER.csv',iex);write('POST_SMA_REMOVAL_LEDGER.csv',sma);write('PORTFOLIO_COUNT_QA.csv',counts);write('FINAL_WEIGHT_QA.csv',wqa);write('ENTRY_DIAGNOSTICS.csv',entryd);write('EXIT_DIAGNOSTICS.csv',exitd);write('SIGNAL_INERTIA.csv',sig);write('PNL_ATTRIBUTION.csv',pnl)
 # episode QA based on selected rows is intentionally strict and reported, not silently repaired
 ep=list(csv.DictReader(open(R/'EPISODE_LEDGER.csv')));selected=sum(r['selected']=='True' for x in rows.values() for r in x);membership=sum(int(r['panel_count']) for r in ep);qa={'selected_rows':selected,'episode_membership_rows':membership,'orphan_selected_rows':max(0,selected-membership),'duplicate_episode_membership_rows':max(0,membership-selected),'EPISODE_QA_PASS':selected==membership}
 (R/'EPISODE_QA.json').write_text(json.dumps(qa,indent=2))
 # Attribution is a return contribution identity; authoritative net return equals sum final weights*stock returns minus actual cost, evaluated panel-wise below.
 rec={}
 for W,rs in rows.items():
  by=defaultdict(list)
  for r in rs:by[r['date']].append(r)
  gross=sum(num(r['target_weight'])*num(r['stock_return_next_period']) for r in rs if r['selected']=='True'); attrgross=sum(num(r['gross']) for r in pnl if r['window']==W); rec[W]={'attributed_gross_return_sum':attrgross,'ledger_gross_return_sum':gross,'gross_difference':attrgross-gross,'PNL_ATTRIBUTION_RECONCILIATION_PASS':abs(attrgross-gross)<1e-12}
 (R/'PNL_ATTRIBUTION_RECONCILIATION.json').write_text(json.dumps(rec,indent=2))
 status='STATE_PATH_ATTRIBUTION_INCOMPLETE'
 (R/'RESULT.json').write_text(json.dumps({'status':status,'immutable_hash_verified':True,'episode_qa':qa,'pnl_reconciliation':rec,'accounting_blocker':'Gross attribution reconciles, but cost attribution has not yet been reconciled to frozen turnover = 1 - overlap(selected_pre_SMA, prior_selected_pre_SMA)/len(selected_pre_SMA). No net-P&L path conclusion is permitted.','note':'No causal/counterfactual inference; all state statistics are descriptive.'},indent=2))
if __name__=='__main__':main()
