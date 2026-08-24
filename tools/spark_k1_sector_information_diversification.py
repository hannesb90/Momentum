#!/usr/bin/env python3
"""Run preregistered K1 sector information and diversification tests."""
from pathlib import Path
from collections import defaultdict
import argparse,hashlib,json,math
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from decision_portfolio_v2 import V2, annualized, dump, manifest, target_map
from decision_portfolio_v3_execution import build_portfolio, execution_returns

R=V2; RK=R/'research_k'; OUT=RK/'results/K1_SECTOR_INFORMATION_DIVERSIFICATION_V2'
PRE=RK/'k1_sector_information_diversification_preregistration.json'; PREHASH='bcf7868ffefd654d4694b712d66509aeef78feb88af950c94db4b0d6731c2319'
G=R/'sparg/results/SPARG_V4_EXECUTABLE_CHAMPION_FALSIFICATION_V3'
S=RK/'sector_classification_v1'; MANUAL={'AGRO','ETX','JOSE','MIC-SDB','SMF','TETY'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fin(x):
 try:return math.isfinite(float(x))
 except:return False

def ic_summary(scores, tm):
 x=scores.merge(tm,on=['kod','panel_date'],how='inner'); per=[]
 for d,g in x.groupby('panel_date',sort=True):
  if len(g)<5:continue
  top=g.nlargest(min(30,len(g)),['score'])
  per.append({'panel_date':d,'n':len(g),'ic52':float(spearmanr(g.score,g.y).statistic),'top30_ic52':float(spearmanr(top.score,top.y).statistic) if len(top)>2 else None})
 v=np.array([z['ic52'] for z in per]); tv=np.array([z['top30_ic52'] for z in per if fin(z['top30_ic52'])])
 return {'panel_dates':len(per),'observations':len(x),'mean_ic52':float(v.mean()),'median_ic52':float(np.median(v)),'mean_top30_ic52':float(tv.mean()),'positive_ic_share':float((v>0).mean()),'per_date':per}

def info_test(base,feat,tm):
 z=base.merge(feat,on=['kod','panel_date'],validate='one_to_one'); z=z[z.feature.map(fin)].copy()
 z=z.sort_values(['panel_date','score','kod'],ascending=[True,False,True]).groupby('panel_date').head(90)
 z['hr']=z.groupby('panel_date').score.rank(pct=True);z['fr']=z.groupby('panel_date').feature.rank(pct=True);z['blend']=.5*z.hr+.5*z.fr
 b=ic_summary(z[['kod','panel_date','score']],tm);c=ic_summary(z[['kod','panel_date','blend']].rename(columns={'blend':'score'}),tm)
 ds=sorted(set(x['panel_date'] for x in b['per_date'])); halves=[set(ds[:len(ds)//2]),set(ds[len(ds)//2:])]; blocks=[]
 for ix,h in enumerate(halves,1):
  bv=np.mean([x['ic52'] for x in b['per_date'] if x['panel_date'] in h]);cv=np.mean([x['ic52'] for x in c['per_date'] if x['panel_date'] in h]);blocks.append({'block':ix,'delta_mean_ic52':float(cv-bv)})
 d={'mean_ic52':c['mean_ic52']-b['mean_ic52'],'median_ic52':c['median_ic52']-b['median_ic52'],'top30_ic52':c['mean_top30_ic52']-b['mean_top30_ic52'],'positive_ic_share':c['positive_ic_share']-b['positive_ic_share']}
 cls='STÖD' if d['mean_ic52']>=.01 and d['median_ic52']>=0 and d['top30_ic52']>=0 and d['positive_ic_share']>=0 and all(x['delta_mean_ic52']>0 for x in blocks) else ('SVAGT STÖD' if d['mean_ic52']>0 else 'INGET STÖD')
 return {'classification':cls,'coverage':{'rows':len(z),'instruments':z.kod.nunique(),'panel_dates':z.panel_date.nunique()},'h0_conditional':b,'blend':c,'delta':d,'chronological_halves':blocks}

def metrics(rows):
 nr=np.array([x['net_return'] for x in rows]);br=np.array([x['benchmark_return'] for x in rows]); w=np.cumprod(1+nr);dd=w/np.maximum.accumulate(w)-1
 ex=nr-br
 return {'periods':len(rows),'cagr':annualized(nr.tolist()),'benchmark_cagr':annualized(br.tolist()),'excess_cagr':annualized(nr.tolist())-annualized(br.tolist()),'sharpe_excess':float(ex.mean()/ex.std(ddof=1)*math.sqrt(13)),'max_drawdown':float(dd.min()),'turnover':float(np.mean([x['turnover'] for x in rows])),'costs':float(sum(x['transaction_cost'] for x in rows))}

def ticker_ablation(holdings,returns,pret):
 by=defaultdict(list)
 for h in holdings:by[h['panel_date']].append(h)
 contrib=defaultdict(float)
 for r in returns:
  for h in by[r['panel_date']]:contrib[h['kod']]+=h['weight']*pret.get((h['kod'],r['panel_date']),0.0)
 order=[k for k,_ in sorted(contrib.items(),key=lambda x:x[1],reverse=True)]
 out={'top_tickers':order[:10],'contribution':dict(sorted(contrib.items(),key=lambda x:x[1],reverse=True))}
 for n in (3,5):
  drop=set(order[:n]); rr=[]
  for r in returns:
   hs=[h for h in by[r['panel_date']] if h['kod'] not in drop]; sw=sum(h['weight'] for h in hs)
   gross=sum(h['weight']*pret.get((h['kod'],r['panel_date']),0.0) for h in hs)/sw if sw else 0
   rr.append({**r,'net_return':gross-r['transaction_cost']})
  out[f'leave_top_{n}']=metrics(rr)
 return out

def concentration(holdings, sectors):
 out=[]
 for d,g in pd.DataFrame(holdings).groupby('panel_date'):
  if not bool(g.rebalance.iloc[0]):continue
  shares=g.groupby(g.kod.map(sectors)).weight.sum().sort_values(ascending=False); h=float((shares**2).sum())
  out.append({'panel_date':d,'sector_count':len(shares),'largest_sector_share':float(shares.iloc[0]),'top2_sector_share':float(shares.iloc[:2].sum()),'hhi':h,'effective_sectors':1/h,'shares':{str(k):float(v) for k,v in shares.items()}})
 return {'per_rebalance':out,'mean_sector_count':float(np.mean([x['sector_count'] for x in out])),'mean_largest_sector_share':float(np.mean([x['largest_sector_share'] for x in out])),'mean_top2_sector_share':float(np.mean([x['top2_sector_share'] for x in out])),'mean_hhi':float(np.mean([x['hhi'] for x in out])),'mean_effective_sectors':float(np.mean([x['effective_sectors'] for x in out]))}

def diversify(df,sectors):
 rows=[]; subs=[]
 for d,g in df.groupby('panel_date',sort=True):
  rem=g.sort_values(['score','kod'],ascending=[False,True]).to_dict('records'); chosen=[]; counts=defaultdict(int)
  while rem and len(chosen)<30:
   pool=rem[:3]; pick=min(pool,key=lambda x:(counts[sectors[x['kod']]],-x['score'],x['kod'])); orig=rem[0]
   if pick['kod']!=orig['kod']:subs.append({'panel_date':d,'selected':pick['kod'],'instead_of':orig['kod'],'selected_h0_rank':pick['rank'],'best_remaining_h0_rank':orig['rank'],'rank_displacement':pick['rank']-orig['rank'],'score_sacrificed':orig['score']-pick['score']})
   chosen.append(pick);counts[sectors[pick['kod']]]+=1;rem.remove(pick)
  chosen_ids={x['kod'] for x in chosen}
  for x in g.to_dict('records'): rows.append({'kod':x['kod'],'panel_date':d,'score':(1000-x['rank']) if x['kod'] in chosen_ids else -1e12})
 return pd.DataFrame(rows),subs

def run_variant(rankings,sector_rows,exclude_manual,tm,pret,emeta):
 allowed=sector_rows[~sector_rows.instrument_id.isin(MANUAL)] if exclude_manual else sector_rows
 sectors=dict(zip(allowed.instrument_id,allowed.canonical_sector)); z=rankings[rankings.kod.isin(sectors)].copy()
 core=pd.DataFrame(json.load(open(R/'panels/core_panel.json')))[['kod','panel_date','mom_52w']]
 z=z.merge(core,on=['kod','panel_date'],how='left',validate='one_to_one')
 z['sector']=z.kod.map(sectors); z['sector_momentum']=z.groupby(['panel_date','sector']).score.transform('mean');z['sector_relative']=z.score-z.sector_momentum
 z['positive']=z.mom_52w>0;z['sector_breadth']=z.groupby(['panel_date','sector']).positive.transform('mean')
 res={}
 for n,c in [('sector_momentum','sector_momentum'),('sector_relative_momentum','sector_relative'),('sector_breadth','sector_breadth')]:res[n]=info_test(z[['kod','panel_date','score']],z[['kod','panel_date',c]].rename(columns={c:'feature'}),tm)
 h0m,h0a=build_portfolio(z[['kod','panel_date','score']],n=30,every=2,cost=.002,model='K1_H0',returns_map=pret,execution_meta=emeta)
 dz,subs=diversify(z[['kod','panel_date','score','rank']],sectors);dm,da=build_portfolio(dz,n=30,every=2,cost=.002,model='K1_DIVERSIFIED',returns_map=pret,execution_meta=emeta)
 hc=concentration(h0a['holdings'],sectors);dc=concentration(da['holdings'],sectors); hm=metrics(h0a['returns']);dmm=metrics(da['returns'])
 ds=sorted(set(x['panel_date'] for x in h0a['returns'])); halves=[set(ds[:len(ds)//2]),set(ds[len(ds)//2:])]; blocks=[]
 for i,h in enumerate(halves,1):blocks.append({'block':i,'h0':metrics([x for x in h0a['returns'] if x['panel_date'] in h]),'diversified':metrics([x for x in da['returns'] if x['panel_date'] in h])})
 support=dc['mean_hhi']<=.95*hc['mean_hhi'] and dc['mean_effective_sectors']>hc['mean_effective_sectors'] and dmm['cagr']>=hm['cagr']-.01 and dmm['sharpe_excess']>=hm['sharpe_excess']-.05 and dmm['turnover']<=hm['turnover']*1.25
 worst=min(h0a['returns'],key=lambda x:x['net_return']); wh=[x for x in h0a['holdings'] if x['panel_date']==worst['panel_date']]; sector_contrib=defaultdict(float)
 for h in wh:sector_contrib[sectors[h['kod']]]+=h['weight']*pret.get((h['kod'],worst['panel_date']),0.0)
 res['h0_concentration']={**hc,'worst_period':worst,'worst_period_sector_contribution':dict(sorted(sector_contrib.items(),key=lambda x:x[1]))}
 res['diversification']={'classification':'STÖD' if support else 'INGET STÖD','h0_metrics':hm,'diversified_metrics':dmm,'h0_concentration':hc,'diversified_concentration':dc,'h0_ticker_ablation':ticker_ablation(h0a['holdings'],h0a['returns'],pret),'diversified_ticker_ablation':ticker_ablation(da['holdings'],da['returns'],pret),'substitutions':{'count':len(subs),'mean_rank_displacement_global':float(np.mean([x['rank_displacement'] for x in subs])) if subs else 0,'max_choice_window_positions':2,'mean_score_sacrificed':float(np.mean([x['score_sacrificed'] for x in subs])) if subs else 0,'rows':subs},'time_blocks':blocks}
 terminal=set(json.load(open(R/'validated/terminal_events.json')));res['terminal_participation']={'ranked':sorted(set(z.kod)&terminal),'ranked_count':len(set(z.kod)&terminal),'h0_held':sorted({x['kod'] for x in h0a['holdings']} & terminal),'diversified_held':sorted({x['kod'] for x in da['holdings']} & terminal)}
 return res,{'rankings':da['rankings'],'holdings':da['holdings'],'trades':da['trades'],'returns':da['returns']}

def main():
 global OUT
 ap=argparse.ArgumentParser();ap.add_argument('--output-dir');args=ap.parse_args()
 if args.output_dir:OUT=Path(args.output_dir)
 assert sha(PRE)==PREHASH; assert not OUT.exists()
 sec=pd.DataFrame(json.load(open(S/'validated/sector_classification_intervals.json')));rank=pd.DataFrame(json.load(open(G/'rankings.json')))[['kod','panel_date','score','rank']]
 tm0=target_map();tm=pd.DataFrame([{'kod':k,'panel_date':d,'y':v} for (k,d),v in tm0.items() if v is not None]);pret,emeta=execution_returns()
 full,fa=run_variant(rank,sec,False,tm,pret,emeta);sens,sa=run_variant(rank,sec,True,tm,pret,emeta)
 for family in ['sector_momentum','sector_relative_momentum','sector_breadth']:
  full[family]['sensitivity_classification']=sens[family]['classification'];full[family]['strong_conclusion_stable']=full[family]['classification']==sens[family]['classification']
 full['diversification']['sensitivity_classification']=sens['diversification']['classification'];full['diversification']['strong_conclusion_stable']=full['diversification']['classification']==sens['diversification']['classification']
 OUT.mkdir(parents=True);dump(OUT/'results_full_mapping.json',full);dump(OUT/'results_excluding_manual_six.json',sens)
 for k,v in fa.items():dump(OUT/f'diversified_{k}.json',v)
 prov={'version':'K1_SECTOR_INFORMATION_DIVERSIFICATION_V2','preregistration_sha256':PREHASH,'sector_manifest_sha256':sha(S/'manifest.json'),'h0_rankings_sha256':sha(G/'rankings.json'),'target_used_only_for_evaluation':True,'selection_target_free':True,'K1G':'SKIPPED','manual_exclusion_codes':sorted(MANUAL),'v1_status':'SUPERSEDED_BEFORE_FINAL_REPORT_BY_CORRECT_EXCESS_SHARPE_AND_REQUIRED_ABLATION_DIAGNOSTICS'};dump(OUT/'run_provenance.json',prov);dump(OUT/'manifest.json',manifest(OUT))
 print(json.dumps({'full':{k:(v.get('classification') if isinstance(v,dict) else None) for k,v in full.items()},'sensitivity':{k:(v.get('classification') if isinstance(v,dict) else None) for k,v in sens.items()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
