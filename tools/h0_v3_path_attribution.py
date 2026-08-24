import csv,json,hashlib,statistics,math
from collections import defaultdict,Counter
from pathlib import Path
R=Path('/home/hannesb/momentum_v2/research_k/h0_v3_state_machine_and_path_ledger')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
EXPECTED={'W1':'349f7fed2e41a6f48c76cc6bc22332ae6808f7c8c507d2221c6d826b4d13aa40','W2':'d212fa0d2012b0860b1cd0ddaebfc76915bbb832aa0982e19aade5c4900502a1'}
def f(x):
 try:return float(x)
 except:return 0.
def main():
 rows={w:list(csv.DictReader(open(R/f'PATH_LEDGER_{w}.csv'))) for w in ('W1','W2')}
 if any(sha(R/f'PATH_LEDGER_{w}.csv')!=EXPECTED[w] for w in rows):raise SystemExit('immutable ledger hash mismatch')
 out=[]; summaries=[]; epis=[]; reent=[]; exits=[]; ent=[]; pnl=[]; inertia=[]; weights=[]; trans=[]
 for w,rs in rows.items():
  dates=sorted({x['date'] for x in rs}); typ={d:('ORDINARY_PANEL' if i%2==0 else 'INTERMEDIATE_PANEL') for i,d in enumerate(dates)}
  bydate=defaultdict(list); bytk=defaultdict(list)
  for x in rs:bydate[x['date']].append(x);bytk[x['ticker']].append(x)
  for d,xs in bydate.items():
   prev=bydate[dates[max(0,dates.index(d)-1)]] if dates.index(d)>0 else []
   held=[x for x in xs if x['selected']=='True']; prior=[x for x in xs if x['previous_selected']=='True']; retained=[x for x in held if x['previous_selected']=='True']; ix=[x for x in xs if x['transition_type']=='EXIT']; ie=[x for x in held if x['transition_type'] in ('ENTRY','REENTRY')]
   if typ[d]=='INTERMEDIATE_PANEL':out.append({'window':w,'date':d,'previous_selected_n':len(prior),'previous_eligible_n':len(prior),'retained_n':len(retained),'eligibility_removed_n':len(ix),'vacancy_count':len(ix),'refill_count':len(ie),'pre_sma_selected_n':len([x for x in xs if x['production_state']!='UNIVERSE_INELIGIBLE' and x['transition_type']!='OUT']),'sma_removed_n':sum(x['production_state']=='SELECTED_PRE_SMA' for x in xs),'final_selected_n':len(held)})
   for x in held:
    weights.append({'window':w,'date':d,'ticker':x['ticker'],'weight':f(x['target_weight'])})
    cat='NEW_ORDINARY_ENTRY' if typ[d]=='ORDINARY_PANEL' and x['transition_type'] in ('ENTRY','REENTRY') else 'NEW_INTERMEDIATE_REFILL_ENTRY' if typ[d]=='INTERMEDIATE_PANEL' and x['transition_type'] in ('ENTRY','REENTRY') else 'CONTINUING_HOLD'
    pnl.append({'window':w,'date':d,'category':cat,'gross_contribution':f(x['target_weight'])*f(x['stock_return_next_period']),'cost':f(x['cost_contribution']),'net_contribution':f(x['target_weight'])*f(x['stock_return_next_period'])-f(x['cost_contribution'])})
  for k,ls in bytk.items():
   ls.sort(key=lambda x:x['date']); active=[]; prior_exit=None
   for x in ls:
    if x['selected']=='True':active.append(x)
    elif active:
     e=active; eid=f'{w}:{k}:{e[0]["date"]}'; gross=math.prod(1+f(q['stock_return_next_period']) for q in e)-1; net=sum(f(q['target_weight'])*f(q['stock_return_next_period'])-f(q['cost_contribution']) for q in e)
     epis.append({'episode_id':eid,'window':w,'ticker':k,'entry_date':e[0]['date'],'entry_panel_type':typ[e[0]['date']],'entry_transition':e[0]['transition_type'],'exit_date':x['date'],'exit_panel_type':typ[x['date']],'exit_transition':x['transition_type'],'calendar_days':28*len(e),'panel_count':len(e),'ordinary_panels_held':sum(typ[q['date']]=='ORDINARY_PANEL' for q in e),'intermediate_panels_held':sum(typ[q['date']]=='INTERMEDIATE_PANEL' for q in e),'entry_rank':e[0]['h0_rank'],'exit_rank':x['h0_rank'],'gross_stock_return':gross,'portfolio_weighted_contribution':net,'net_contribution':net,'profitable_episode':gross>0,'path_string':'-'.join(('O' if typ[q['date']]=='ORDINARY_PANEL' else 'I')+('E' if q==e[0] else 'R') for q in e)+'-X'});prior_exit=x;active=[]
   if active:
    e=active;gross=math.prod(1+f(q['stock_return_next_period']) for q in e)-1;net=sum(f(q['target_weight'])*f(q['stock_return_next_period'])-f(q['cost_contribution']) for q in e);epis.append({'episode_id':f'{w}:{k}:{e[0]["date"]}','window':w,'ticker':k,'entry_date':e[0]['date'],'entry_panel_type':typ[e[0]['date']],'entry_transition':e[0]['transition_type'],'exit_date':'','exit_panel_type':'','exit_transition':'','calendar_days':28*len(e),'panel_count':len(e),'ordinary_panels_held':sum(typ[q['date']]=='ORDINARY_PANEL' for q in e),'intermediate_panels_held':sum(typ[q['date']]=='INTERMEDIATE_PANEL' for q in e),'entry_rank':e[0]['h0_rank'],'exit_rank':'','gross_stock_return':gross,'portfolio_weighted_contribution':net,'net_contribution':net,'profitable_episode':gross>0,'path_string':'-'.join(('O' if typ[q['date']]=='ORDINARY_PANEL' else 'I')+('E' if q==e[0] else 'R') for q in e)})
  for x in rs:
   trans.append({'window':w,'from_state':'HELD' if x['previous_selected']=='True' else 'OUT','to_state':x['production_state'],'transition_type':x['transition_type'],'next_stock_return':f(x['stock_return_next_period']),'next_portfolio_contribution':f(x['target_weight'])*f(x['stock_return_next_period'])})
  summaries.append({'window':w,'ordinary_panels':sum(t=='ORDINARY_PANEL' for t in typ.values()),'intermediate_panels':sum(t=='INTERMEDIATE_PANEL' for t in typ.values()),'first_date':dates[0],'last_date':dates[-1]})
 with open(R/'INTERMEDIATE_PANEL_SUMMARY.csv','w',newline='') as q:w=csv.DictWriter(q,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
 with open(R/'EPISODE_LEDGER.csv','w',newline='') as q:w=csv.DictWriter(q,fieldnames=list(epis[0]));w.writeheader();w.writerows(epis)
 with open(R/'PNL_ATTRIBUTION.csv','w',newline='') as q:w=csv.DictWriter(q,fieldnames=list(pnl[0]));w.writeheader();w.writerows(pnl)
 for w in ('W1','W2'):
  a=[x for x in trans if x['window']==w];c=Counter(x['transition_type'] for x in a)
  with open(R/f'TRANSITION_MATRIX_{w}.csv','w',newline='') as q:
   wr=csv.writer(q);wr.writerow(['from_state','to_state','transition_type','n','conditional_probability','mean_next_stock_return','mean_next_portfolio_contribution'])
   for t,n in c.items():
    z=[x for x in a if x['transition_type']==t];wr.writerow(['', '',t,n,n/len(a),statistics.mean(x['next_stock_return'] for x in z),statistics.mean(x['next_portfolio_contribution'] for x in z)])
 (R/'PATH_SUMMARY.csv').write_text('window,path_string,n_episodes\n'+'\n'.join(f'{w},{p},{n}' for (w,p),n in Counter((x['window'],x['path_string']) for x in epis).items())+'\n')
 (R/'RESULT.json').write_text(json.dumps({'status':'STATE_PATH_ATTRIBUTION_INCOMPLETE','immutable_ledgers_verified':True,'panel_summary':summaries,'note':'Core episodes/transitions written; P&L reconciliation and requested descriptive expansions remain pending.'},indent=2))
if __name__=='__main__':main()
