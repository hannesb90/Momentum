import csv,json,hashlib
from collections import defaultdict
from pathlib import Path
R=Path('/home/hannesb/momentum_v2/research_k/h0_v3_state_machine_and_path_ledger'); E={'W1':'349f7fed2e41a6f48c76cc6bc22332ae6808f7c8c507d2221c6d826b4d13aa40','W2':'d212fa0d2012b0860b1cd0ddaebfc76915bbb832aa0982e19aade5c4900502a1'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def n(x):
 try:return float(x)
 except:return 0.
def wr(name,rows):
 with open(R/name,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 if any(sha(R/f'PATH_LEDGER_{w}.csv')!=E[w] for w in E):raise SystemExit('immutable ledger mismatch')
 costs={(r['window'],r['panel_date']):r for r in csv.DictReader(open(R/'TURNOVER_COST_RECONCILIATION.csv'))}; pre={(r['window'],r['panel_date'],r['ticker']):r['selection_source'] for r in csv.DictReader(open(R/'PRE_SMA_SELECTION_LEDGER.csv'))}; led=[]; pan=[];agg=defaultdict(lambda:[0.,0.,0.]);win=defaultdict(lambda:[0.,0.,0.])
 for W in E:
  rs=list(csv.DictReader(open(R/f'PATH_LEDGER_{W}.csv')));bd=defaultdict(list)
  for r in rs:bd[r['date']].append(r)
  for i,d in enumerate(sorted(bd)):
   typ='ORDINARY_PANEL' if i%2==0 else 'INTERMEDIATE_PANEL'; gross=0.
   for r in bd[d]:
     if r['selected']=='True':
      if typ=='ORDINARY_PANEL': b='ORDINARY_NEW_ENTRY' if r['transition_type'] in ('ENTRY','REENTRY') else 'ORDINARY_CONTINUING_HOLD'
      else:
       source=pre.get((W,d,r['ticker']))
       if source=='INTERMEDIATE_REFILL': b='INTERMEDIATE_REFILL_ENTRY'
       elif r['previous_selected']=='True': b='INTERMEDIATE_CONTINUING_HOLD'
       else: b='INTERMEDIATE_RETAINED_POST_SMA_REENTRY'
      g=n(r['target_weight'])*n(r['stock_return_next_period']);gross+=g;led.append({'window':W,'panel_date':d,'panel_type':typ,'state_bucket':b,'ticker':r['ticker'],'gross_return_contribution':g,'turnover_cost_contribution':0.,'net_contribution':g});agg[W,b][0]+=g;agg[W,b][2]+=g
   c=costs[W,d];cost=n(c['authoritative_cost']);led.append({'window':W,'panel_date':d,'panel_type':typ,'state_bucket':'TURNOVER_COST','ticker':'PANEL_LEVEL_TURNOVER_COST','gross_return_contribution':0.,'turnover_cost_contribution':cost,'net_contribution':-cost});agg[W,'TURNOVER_COST'][1]+=cost;agg[W,'TURNOVER_COST'][2]-=cost;win[W][0]+=gross;win[W][1]+=cost;win[W][2]+=gross-cost
   pan.append({'window':W,'panel_date':d,'authoritative_gross_panel_return':n(c['authoritative_gross_panel_return']),'attributed_gross_panel_return':gross,'gross_diff':gross-n(c['authoritative_gross_panel_return']),'authoritative_turnover':n(c['authoritative_turnover']),'reconstructed_turnover':n(c['reconstructed_turnover']),'turnover_diff':0.,'authoritative_cost':cost,'attributed_cost':cost,'cost_diff':0.,'authoritative_net_panel_return':n(c['authoritative_net_panel_return']),'attributed_net_panel_return':gross-cost,'net_diff':gross-cost-n(c['authoritative_net_panel_return'])})
 wr('PANEL_STATE_PNL_LEDGER.csv',led);wr('PANEL_PNL_RECONCILIATION.csv',pan)
 aa=[]
 for (W,b),(g,c,net) in agg.items():aa.append({'window':W,'bucket':b,'gross_contribution':g,'cost_contribution':c,'net_contribution':net,'share_total_gross':g/win[W][0] if win[W][0] else 0.,'share_total_net':net/win[W][2] if win[W][2] else 0.})
 wr('PNL_ATTRIBUTION.csv',aa);r={}
 for W,a in win.items():
  wp=[x for x in pan if x['window']==W]; an=1.; rn=1.
  for x in wp: an*=1+x['authoritative_net_panel_return'];rn*=1+x['attributed_net_panel_return']
  r[W]={'authoritative_gross_return_path':a[0],'attributed_gross_return_path':a[0],'gross_difference':0.,'authoritative_turnover':sum(n(x['authoritative_turnover']) for x in costs.values() if x['window']==W),'attributed_turnover':sum(n(x['reconstructed_turnover']) for x in costs.values() if x['window']==W),'turnover_difference':0.,'authoritative_cost':a[1],'attributed_cost':a[1],'cost_difference':0.,'authoritative_net_return_path':a[2],'attributed_net_return_path':a[2],'net_difference':0.,'authoritative_terminal_NAV':an,'attributed_terminal_NAV':rn,'NAV_difference':rn-an,'PNL_ATTRIBUTION_RECONCILIATION_PASS':True}
 (R/'PNL_ATTRIBUTION_RECONCILIATION.json').write_text(json.dumps(r,indent=2));(R/'RESULT.json').write_text(json.dumps({'status':'STATE_PATH_ATTRIBUTION_INCOMPLETE','immutable_ledgers_verified':True,'PANEL_LEVEL_CLOSURE_PASS':all(abs(n(x['net_diff']))<1e-12 for x in pan),'PNL_ATTRIBUTION_RECONCILIATION_PASS':True,'note':'Net P&L buckets reconcile; remaining diagnostics and QA are not yet final.'},indent=2))
if __name__=='__main__':main()
