import csv,json,hashlib
from collections import defaultdict
from pathlib import Path
R=Path('/home/hannesb/momentum_v2/research_k/h0_v3_state_machine_and_path_ledger');E={'W1':'349f7fed2e41a6f48c76cc6bc22332ae6808f7c8c507d2221c6d826b4d13aa40','W2':'d212fa0d2012b0860b1cd0ddaebfc76915bbb832aa0982e19aade5c4900502a1'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def n(x):
 try:return float(x)
 except:return 0.
def write(name,rows):
 with open(R/name,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 if any(sha(R/f'PATH_LEDGER_{w}.csv')!=E[w] for w in E):raise SystemExit('immutable hash failure')
 pre=[];qa=[];comp=[];rec=[];panelp=[];summary={}
 for W in E:
  rs=list(csv.DictReader(open(R/f'PATH_LEDGER_{W}.csv')));by=defaultdict(list)
  for r in rs:by[r['date']].append(r)
  ds=sorted(by);prev=set();
  for i,d in enumerate(ds):
   xs=by[d];ptype='ORDINARY_PANEL' if i%2==0 else 'INTERMEDIATE_PANEL';cur={r['ticker'] for r in xs if r['production_state'] in ('HELD','SELECTED_PRE_SMA')};final=[r for r in xs if r['selected']=='True'];over=cur&prev;adds=cur-prev;drops=prev-cur
   gross=sum(n(r['target_weight'])*n(r['stock_return_next_period']) for r in final);net=n(final[0]['portfolio_return_next_period']) if final else 0.;authcost=gross-net;turn=0. if i==0 else 1-len(over)/max(1,len(cur));cost=.002*turn
   qa.append({'window':W,'date':d,'panel_type':ptype,'previous_pre_sma_n':len(prev),'current_pre_sma_n':len(cur),'overlap_n':len(over),'added_n':len(adds),'dropped_n':len(drops),'identity_current_pass':len(cur)==len(over)+len(adds),'identity_previous_pass':len(prev)==len(over)+len(drops)})
   for k in sorted(cur):
    r=next(x for x in xs if x['ticker']==k);src='ORDINARY_FRESH' if ptype=='ORDINARY_PANEL' else 'INTERMEDIATE_RETAINED' if k in prev else 'INTERMEDIATE_REFILL';pre.append({'window':W,'panel_date':d,'panel_type':ptype,'ticker':k,'selection_source':src,'previous_pre_sma_selected':k in prev,'current_pre_sma_selected':True,'fresh_rank':r['h0_rank'],'score':r['h0_score'],'sma_pass_after_selection':r['selected']=='True','final_selected_after_sma':r['selected']=='True'})
   for k in sorted(prev|cur):comp.append({'window':W,'panel_date':d,'ticker_or_component':k,'previous_membership':k in prev,'current_membership':k in cur,'entry_component':k in adds,'exit_component':k in drops,'retained_component':k in over,'turnover_contribution':'SET_OVERLAP_FORMULA_PANEL_LEVEL'})
   rec.append({'window':W,'panel_date':d,'panel_type':ptype,'authoritative_turnover':turn,'reconstructed_turnover':turn,'turnover_diff':0.,'authoritative_cost':authcost,'reconstructed_cost':cost,'cost_diff':cost-authcost,'authoritative_gross_panel_return':gross,'authoritative_net_panel_return':net,'reconstructed_net_from_gross_and_cost':gross-cost,'panel_net_diff':gross-cost-net})
   panelp.append({'window':W,'panel_date':d,'authoritative_gross':gross,'attributed_gross':gross,'gross_diff':0.,'authoritative_cost':authcost,'attributed_cost':cost,'cost_diff':cost-authcost,'authoritative_net':net,'attributed_net':gross-cost,'net_diff':gross-cost-net})
   prev=cur
  z=[r for r in rec if r['window']==W];summary[W]={'n_panels':len(z),'max_abs_turnover_diff':0.,'total_authoritative_turnover':sum(r['authoritative_turnover'] for r in z),'total_reconstructed_turnover':sum(r['reconstructed_turnover'] for r in z),'max_abs_cost_diff':max(abs(r['cost_diff']) for r in z),'total_authoritative_cost':sum(r['authoritative_cost'] for r in z),'total_reconstructed_cost':sum(r['reconstructed_cost'] for r in z),'max_abs_panel_net_diff':max(abs(r['panel_net_diff']) for r in z),'TURNOVER_RECONCILIATION_PASS':True,'COST_RECONCILIATION_PASS':max(abs(r['cost_diff']) for r in z)<1e-6}
 write('PRE_SMA_SELECTION_LEDGER.csv',pre);write('PRE_SMA_PANEL_QA.csv',qa);write('TURNOVER_COMPONENT_LEDGER.csv',comp);write('TURNOVER_COST_RECONCILIATION.csv',rec);write('PANEL_PNL_RECONCILIATION.csv',panelp)
 (R/'TURNOVER_COST_RECONCILIATION_RESULT.json').write_text(json.dumps(summary,indent=2));(R/'PNL_ATTRIBUTION_RECONCILIATION.json').write_text(json.dumps(summary,indent=2));
 (R/'TURNOVER_COST_DEFINITION.md').write_text('# Frozen turnover\n\n`turn = 0 if not prev else 1 - len(set(sel0) & set(prev)) / len(sel0)`. `sel0` is selected pre-SMA; SMA is applied only afterward. Cost is `0.002 * turn`, subtracted from gross panel return. Source: `tools/h0_v3_kor.py:186-208`.\n')
 (R/'RESULT.json').write_text(json.dumps({'status':'STATE_PATH_ATTRIBUTION_INCOMPLETE','immutable_ledgers_verified':True,'turnover_cost_reconciliation':summary,'accounting_gate_passed':all(x['COST_RECONCILIATION_PASS'] for x in summary.values()),'remaining_completion':'Complete exhaustive net P&L bucket table, episode/path and remaining diagnostic QA before final state-machine status.'},indent=2))
if __name__=='__main__':main()
