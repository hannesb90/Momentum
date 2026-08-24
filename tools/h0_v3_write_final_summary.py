import hashlib,json
from pathlib import Path
import pandas as pd
R=Path('/home/hannesb/momentum_v2/research_k/h0_v3_state_machine_and_path_ledger')
def sha(x): return hashlib.sha256((R/x).read_bytes()).hexdigest()
def main():
 ep=pd.read_csv(R/'EPISODE_LEDGER.csv'); ret=pd.read_csv(R/'INTERMEDIATE_RETAINED_LEDGER.csv'); pnl=pd.read_csv(R/'PNL_ATTRIBUTION.csv'); inertia=pd.read_csv(R/'PORTFOLIO_INERTIA.csv'); sig=pd.read_csv(R/'SIGNAL_INERTIA.csv'); rc=json.loads((R/'PNL_ATTRIBUTION_RECONCILIATION.json').read_text()); result=json.loads((R/'RESULT.json').read_text())
 ticker=[]; retained=[]; duration=[]; entries=[]
 for w in ['W1','W2']:
  g=ep[ep.window==w]; a=g.groupby('ticker').portfolio_weighted_contribution.sum().sort_values(ascending=False); tot=g.portfolio_weighted_contribution.sum()
  ticker.append({'window':w,'largest_single_ticker_gross_share':float(a.iloc[0]/tot),'top_5_ticker_gross_share':float(a.iloc[:5].sum()/tot),'top_10_ticker_gross_share':float(a.iloc[:10].sum()/tot),'top_20_ticker_gross_share':float(a.iloc[:20].sum()/tot)})
  x=ret[(ret.window==w)&(ret.would_not_be_fresh_top30.astype(str).str.lower()=='true')]; y=pd.to_numeric(x.next_panel_return,errors='coerce')
  retained.append({'window':w,'n':len(x),'mean_next_panel_return':float(y.mean()),'median_next_panel_return':float(y.median()),'positive_share':float((y>0).mean()),'gross_contribution':float(pd.to_numeric(x.portfolio_contribution_next_interval,errors='coerce').sum()),'interpretation':'DESCRIPTIVE_ONLY__NO_COUNTERFACTUAL_CAUSAL_INTERPRETATION'})
  for q,label in [(g[g.profitable_episode.astype(str).str.lower()=='true'],'PROFITABLE'),(g[g.profitable_episode.astype(str).str.lower()!='true'],'LOSING')]: duration.append({'window':w,'episode_group':label,'n':len(q),'median_holding_panels':float(q.panel_count.median()),'median_holding_days':float(q.calendar_days.median()),'p75_holding_days':float(q.calendar_days.quantile(.75)),'p90_holding_days':float(q.calendar_days.quantile(.9))})
  for et in ['ORDINARY_PANEL','INTERMEDIATE_PANEL']:
   q=g[g.entry_panel_type==et];entries.append({'window':w,'entry_type':et,'n_episodes':len(q),'mean_episode_return':float(q.gross_stock_return.mean()),'median_episode_return':float(q.gross_stock_return.median()),'positive_share':float(q.profitable_episode.astype(str).str.lower().eq('true').mean()),'median_holding_panels':float(q.panel_count.median()),'median_holding_days':float(q.calendar_days.median()),'gross_contribution':float(q.portfolio_weighted_contribution.sum())})
 pd.DataFrame(ticker).to_csv(R/'TICKER_CONCENTRATION.csv',index=False);pd.DataFrame(retained).to_csv(R/'RETAINED_OUTSIDE_TOP30_DIAGNOSTICS.csv',index=False);pd.DataFrame(duration).to_csv(R/'EPISODE_DURATION_BY_OUTCOME.csv',index=False);pd.DataFrame(entries).to_csv(R/'ENTRY_TYPE_EPISODE_DIAGNOSTICS.csv',index=False)
 # Required artifacts now exist; update result without changing any ledger or accounting output.
 result['ALL_REQUIRED_ARTIFACTS_WRITTEN']=True
 result['future_research_hypotheses']=[]
 (R/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=['# H0 V3 state machine and path ledger','',f"Final status: `{result['status']}`.",'','## Integrity and accounting','', '- Immutable W1/W2 ledgers verified against the frozen SHA256 values.', '- Pre-SMA identities, frozen set-based turnover, 20 bp costs, panel-level P&L and window-level P&L all reconcile exactly.', '- Turnover cost remains a panel-level accounting bucket; no artificial ticker cost allocation was made.','','## Frozen mechanics','', '- Ordinary panels rebuild from current rank; intermediate panels retain PIT-eligible pre-SMA names and refill vacancies from current rank.', '- SMA200 is applied after pre-SMA selection, without refill after SMA removal.', '- Sizing is inverse-volatility^1.5 × confirmation (1.00/0.75), one clip to 1–6%, then normalization.','','## Descriptive scope','', 'All path, return, concentration and retained-outside-Top30 figures are descriptive attribution only. They are not counterfactual evidence for a new exit, cadence, entry or holding policy.','','## Future research hypotheses','', 'None nominated here. The observed intermediate retain/refill states are already the frozen cadence architecture; testing alternatives would require a separate preregistered counterfactual and canonical same-estimand review.','','## Key artifacts','']
 for x in ['PANEL_STATE_PNL_LEDGER.csv','PANEL_PNL_RECONCILIATION.csv','PNL_ATTRIBUTION.csv','PNL_ATTRIBUTION_RECONCILIATION.json','PORTFOLIO_INERTIA.csv','SIGNAL_INERTIA.csv','EPISODE_LEDGER.csv','PATH_SUMMARY.csv','TRANSITION_MATRIX_W1.csv','TRANSITION_MATRIX_W2.csv'] : lines.append(f'- `{x}` — `{sha(x)}`')
 (R/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()
