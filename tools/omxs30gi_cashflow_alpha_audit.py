from __future__ import annotations
import csv, hashlib, json, sys
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from monthly_cash_and_selective_4w_audit import xirr, deposits
ROOT=Path('/home/hannesb/momentum_v2'); OUT=ROOT/'research_k/omxs30gi_cashflow_alpha_audit'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def series():
 rows=[]
 for line in (OUT/'NASDAQOMXS30GI_raw.csv').read_text().splitlines()[1:]:
  d,v=line.split(',')
  if v not in ('.',''): rows.append((date.fromisoformat(d),float(v)))
 return rows
def px(s,d,side='after'):
 z=[x for x in s if x[0]>=d] if side=='after' else [x for x in s if x[0]<=d]
 return (z[0] if side=='after' else z[-1])
def bench(s,start,end):
 p0=px(s,start,'after')[1]; units=100000/p0; flows=[(start,-100000.)]; ledger=[]
 for d in deposits(start,end):
  ex,p=px(s,d,'after'); u=7000/p; units+=u;flows.append((d,-7000.));ledger.append({'deposit_date':d.isoformat(),'execution_date':ex.isoformat(),'amount':7000,'index_level':p,'units':u})
 pe=px(s,end,'before')[1]; terminal=units*pe;flows.append((end,terminal)); years=(end-start).days/365.25
 return {'terminal_wealth':terminal,'twr_cagr':(pe/p0)**(1/years)-1,'xirr_mwr':xirr(flows),'contributions':100000+7000*len(ledger),'end_index_level':pe,'cashflow_ledger':ledger}
def main():
 s=series(); model=json.loads((ROOT/'research_k/monthly_cash_early_topup_vs_next_rebalance_audit/RESULT.json').read_text()); out={'benchmark':'OMXS30GI / FRED NASDAQOMXS30GI / gross total return SEK','raw_sha256':sha(OUT/'NASDAQOMXS30GI_raw.csv'),'plan_sha256':sha(OUT/'PREREGISTRATION.md'),'windows':{}}
 allrows=[]
 for w in ('W1','W2'):
  start,end=(date(2014,1,1),date(2019,12,25)) if w=='W1' else (date(2020,1,2),date(2026,7,9)); b=bench(s,start,end); m=model['windows'][w]['full_portfolio_EARLY_TOPUP'];
  out['windows'][w]={'model_early_topup':{'terminal_wealth':m['terminal_wealth'],'twr_cagr':m['twr_cagr'],'xirr_mwr':m['xirr_mwr']},'omxs30gi':b,'alpha_twr_cagr_pp':m['twr_cagr']-b['twr_cagr'],'alpha_xirr_pp':m['xirr_mwr']-b['xirr_mwr']};allrows += [dict(window=w,**z) for z in b.pop('cashflow_ledger')]
 with open(OUT/'benchmark_cashflow_ledger.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
 (OUT/'RESULT.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));h=sha(OUT/'RESULT.json');(OUT/'RESULT_SHA256.txt').write_text(h+'  RESULT.json\n')
 lines=['# OMXS30GI cashflow alpha audit','','| Window | Model TWR | OMXS30GI TWR | TWR alpha | Model XIRR | OMXS30GI XIRR | XIRR alpha |','|---|---:|---:|---:|---:|---:|---:|']
 for w,x in out['windows'].items():m=x['model_early_topup'];b=x['omxs30gi'];lines.append(f"| {w} | {m['twr_cagr']:.2%} | {b['twr_cagr']:.2%} | {x['alpha_twr_cagr_pp']:+.2%} | {m['xirr_mwr']:.2%} | {b['xirr_mwr']:.2%} | {x['alpha_xirr_pp']:+.2%} |")
 lines += ['',f'Result SHA256: `{h}`'];(OUT/'SUMMARY.md').write_text('\n'.join(lines)+'\n');print(json.dumps({w:out['windows'][w]['alpha_twr_cagr_pp'] for w in out['windows']}))
if __name__=='__main__':main()
