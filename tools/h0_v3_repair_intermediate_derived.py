"""Repair only derived intermediate diagnostics from authoritative pre-SMA selection."""
import pandas as pd
from pathlib import Path
R=Path('/home/hannesb/momentum_v2/research_k/h0_v3_state_machine_and_path_ledger')
def b(x): return str(x).lower()=='true'
def main():
 pre=pd.read_csv(R/'PRE_SMA_SELECTION_LEDGER.csv'); pre['panel_date']=pd.to_datetime(pre.panel_date)
 led=[]
 for w in ['W1','W2']:
  x=pd.read_csv(R/f'PATH_LEDGER_{w}.csv');x['date']=pd.to_datetime(x.date);x['window']=w;led.append(x)
 led=pd.concat(led); led['selected_b']=led.selected.map(b); led['previous_b']=led.previous_selected.map(b)
 ps=[]; ref=[]; ret=[]
 for w in ['W1','W2']:
  panels=pre[pre.window==w].groupby('panel_date')
  dates=sorted(panels.groups)
  for ix,d in enumerate(dates):
   g=panels.get_group(d)
   if g.panel_type.iloc[0]!='INTERMEDIATE_PANEL': continue
   previous=len(panels.get_group(dates[ix-1])) if ix else 0
   cur=led[(led.window==w)&(led.date==d)].set_index('ticker')
   retained=g[g.selection_source=='INTERMEDIATE_RETAINED']; refill=g[g.selection_source=='INTERMEDIATE_REFILL']
   pre_n=len(g); sma_removed=int((~g.sma_pass_after_selection.map(b)).sum()); final=int(g.final_selected_after_sma.map(b).sum())
   ps.append({'window':w,'panel_date':d.date(),'previous_selected_n':previous,'retained_n':len(retained),'eligibility_removed_n':previous-len(retained),'vacancy_count':previous-len(retained),'refill_n':len(refill),'pre_sma_selected_n':pre_n,'sma_removed_n':sma_removed,'final_selected_n':final,'retention_identity_pass':previous==len(retained)+(previous-len(retained)),'refill_identity_pass':pre_n==len(retained)+len(refill),'sma_identity_pass':final==pre_n-sma_removed})
   for _,r in retained.iterrows():
    z=cur.loc[r.ticker] if r.ticker in cur.index else None
    ret.append({'window':w,'panel_date':d.date(),'ticker':r.ticker,'previous_selected':True,'still_pit_eligible':True,'fresh_h0_rank':r.fresh_rank,'fresh_h0_score':r.score,'fresh_rank_bucket':('1_10' if r.fresh_rank<=10 else '11_20' if r.fresh_rank<=20 else '21_30' if r.fresh_rank<=30 else '31_40' if r.fresh_rank<=40 else '41_50' if r.fresh_rank<=50 else '51_plus'),'would_not_be_fresh_top30':r.fresh_rank>30,'mom52':z.mom12 if z is not None else None,'mom78':z.mom18 if z is not None else None,'pct52':z.pct_mom12 if z is not None else None,'pct78':z.pct_mom18 if z is not None else None,'sma_pass':b(r.sma_pass_after_selection),'pretrade_weight':z.actual_pretrade_weight if z is not None else None,'target_weight':z.target_weight if z is not None else None,'next_panel_return':z.stock_return_next_period if z is not None else None,'portfolio_contribution_next_interval':(float(z.target_weight)*float(z.stock_return_next_period) if z is not None and b(z.selected) else None)})
   for i,(_,r) in enumerate(refill.iterrows(),1):
    z=cur.loc[r.ticker] if r.ticker in cur.index else None
    ref.append({'window':w,'panel_date':d.date(),'ticker':r.ticker,'vacancy_number':i,'fresh_rank':r.fresh_rank,'fresh_score':r.score,'mom52':z.mom12 if z is not None else None,'mom78':z.mom18 if z is not None else None,'sma_pass':b(r.sma_pass_after_selection),'target_weight':z.target_weight if z is not None else None,'posttrade_weight':z.actual_posttrade_weight if z is not None else None,'next_panel_return':z.stock_return_next_period if z is not None else None,'portfolio_contribution_next_interval':(float(z.target_weight)*float(z.stock_return_next_period) if z is not None and b(z.selected) else None)})
 pd.DataFrame(ps).to_csv(R/'INTERMEDIATE_PANEL_SUMMARY.csv',index=False)
 pd.DataFrame(ret).to_csv(R/'INTERMEDIATE_RETAINED_LEDGER.csv',index=False)
 pd.DataFrame(ref).to_csv(R/'INTERMEDIATE_REFILL_LEDGER.csv',index=False)
if __name__=='__main__':main()
