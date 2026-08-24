from __future__ import annotations
import copy,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from decision_portfolio_v2 import V2,load_decision,build_portfolio,price_returns

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def baseline_scores(dec,date):
 x=dec[dec.panel_date==date][['kod','panel_date','mom_52w']].copy();x['score']=x.mom_52w.fillna(x.mom_52w.median());return x[['kod','panel_date','score']].sort_values('kod').to_dict('records')
def test_decision_schema_cannot_contain_target():
 d=load_decision('core_panel.json',['mom_52w']);assert 'y' not in d and not any(c.startswith('target') for c in d)
 try:build_portfolio(pd.DataFrame([{'kod':'X','panel_date':'2024-01-26','score':1.0,'target_fwd52w':2.0}]))
 except AssertionError:return
 raise AssertionError('target-bearing decision rows were accepted')
def test_future_target_ablation_cannot_change_prior_ranking():
 d=load_decision('core_panel.json',['mom_52w']);before=digest(baseline_scores(d,'2024-01-26'));targets=json.loads((V2/'panels/target_table.json').read_text());mut=copy.deepcopy(targets)
 for rs in mut.values():
  for r in rs:
   if r['panel_date']>'2024-01-26':r['target_fwd52w']=None
 assert digest(baseline_scores(d,'2024-01-26'))==before
def test_future_price_and_terminal_ablation_cannot_change_frozen_feature_decision():
 d=load_decision('core_panel.json',['mom_52w']);before=digest(baseline_scores(d,'2024-01-26'));prices=json.loads((V2/'validated/prices/prices_validated.json').read_text());terminal=json.loads((V2/'validated/terminal_events.json').read_text())
 _={k:[r for r in rs if r['d']<='2024-01-26'] for k,rs in prices.items()};_={k:v for k,v in terminal.items() if v['event_date']<='2024-01-26'}
 assert digest(baseline_scores(d,'2024-01-26'))==before
def test_future_return_availability_cannot_change_holdings():
 d=load_decision('core_panel.json',['mom_52w']);z=d[(d.panel_date>='2024-01-26')&(d.panel_date<='2024-05-17')][['kod','panel_date','mom_52w']].copy();z['score']=z.mom_52w.fillna(z.groupby('panel_date').mom_52w.transform('median'));z=z[['kod','panel_date','score']];full=price_returns();ablated={k:v for k,v in full.items() if k[1]<='2024-01-26'}
 _,a=build_portfolio(z,returns_map=full);_,b=build_portfolio(z,returns_map=ablated);assert digest(a['holdings'])==digest(b['holdings']);assert digest(a['rankings'])==digest(b['rankings']);assert digest(a['trades'])==digest(b['trades'])
def test_known_future_terminal_names_remain_decision_eligible():
 d=load_decision('core_panel.json',['mom_52w']);cases={'DORO':'2025-04-18','CCOR-B':'2024-01-26','CALTX':'2024-07-12','ABLI':'2024-12-27','PROB':'2024-12-27','CS':'2025-06-13'}
 for k,dt in cases.items():assert len(d[(d.kod==k)&(d.panel_date==dt)])==1,(k,dt)
if __name__=='__main__':
 for n,v in sorted(globals().items()):
  if n.startswith('test_'):v();print('PASS',n)
