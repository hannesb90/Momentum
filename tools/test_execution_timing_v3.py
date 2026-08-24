#!/usr/bin/env python3
import json
from pathlib import Path
import pandas as pd
from decision_portfolio_v2 import V2,load_decision
from decision_portfolio_v3_execution import execution_returns,build_portfolio

def scores():
 d=load_decision('core_panel.json',['mom_52w']);d=d[(d.panel_date>='2024-01-01')&(d.panel_date<='2025-12-31')].copy();d['score']=d.mom_52w.fillna(d.groupby('panel_date').mom_52w.transform('median'));return d[['kod','panel_date','score']]
def test_all_executions_strictly_after_decision():
 _,a=build_portfolio(scores(),n=30,every=2,model='test')
 executed=[r for r in a['trades'] if r['execution_price_date']]
 assert executed and all(r['execution_price_date']>r['decision_date'] for r in executed),(len(executed),[r for r in executed if r['execution_price_date']<=r['decision_date']][:3])
def test_closed_market_panel_cases_use_future_trade_date():
 _,a=build_portfolio(scores(),n=30,every=2,model='test');h=[r for r in a['holdings'] if r['panel_date'] in {'2025-04-18','2025-12-26'}]
 assert len(h)==60
 assert all(r['period_start_execution_date']>r['panel_date'] for r in h)
 assert {r['panel_date'] for r in h}=={'2025-04-18','2025-12-26'}
def test_target_availability_cannot_change_decision():
 s=scores();_,a=build_portfolio(s,n=30,every=2,model='test');target=json.loads((V2/'panels/target_table.json').read_text());
 for rs in target.values():
  for r in rs:r['target_fwd52w']=None
 _,b=build_portfolio(s,n=30,every=2,model='test');assert a['rankings']==b['rankings'] and [(r['panel_date'],r['kod']) for r in a['holdings']]==[(r['panel_date'],r['kod']) for r in b['holdings']]
def test_last_oos_panel_uses_next_frozen_panel_boundary():
 _,a=build_portfolio(scores(),n=30,every=2,model='test');assert any(r['panel_date']=='2025-12-26' for r in a['rankings']);assert any(r['panel_date']=='2025-12-26' for r in a['holdings']);assert any(r['panel_date']=='2025-12-26' for r in a['returns'])

if __name__=='__main__':
 for n,f in sorted(globals().items()):
  if n.startswith('test_'):f();print('PASS',n)
