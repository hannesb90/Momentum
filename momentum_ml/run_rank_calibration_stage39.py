"""N3-39 / SR11: causal rank calibration on the canonical OOF panel."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import ndcg_score
from niva3_stage_control import freeze_stage,verify_manifest
from tune_reconstructed_prices_niva3_stage12_corrected import panel_from
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/38_armed_takeprofit_screen.json'
RAW=ROOT/'results/niva3_canonical_raw_stage36.csv';FEAT=ROOT/'results/niva3_canonical_features_stage35.pkl';PRICE=ROOT/'results/niva3_current_reconstructed_prices_stage34.pkl'
OUT=ROOT/'results/niva3_rank_calibration_stage39.json';DEC=ROOT/'results/niva3_rank_calibration_deciles_stage39.csv';DATES=ROOT/'results/niva3_rank_calibration_dates_stage39.csv';CAL=ROOT/'results/niva3_rank_calibration_oof_isotonic_stage39.csv'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
def main():
 p=verify_manifest(PARENT);raw=pd.read_csv(RAW,parse_dates=['Date']);features=pd.read_pickle(FEAT);prices=pd.read_pickle(PRICE);panel=panel_from(features,prices)[['ticker','ret13']].reset_index()
 x=raw.merge(panel,on=['Date','ticker'],how='inner').sort_values(['Date','ticker']);x['rank_pct']=x.groupby('Date').raw.rank(pct=True);x['excess13']=x.ret13-x.groupby('Date').ret13.transform('mean');x['decile']=np.minimum((x.rank_pct*10).astype(int),9)
 dec=x.groupby('decile').agg(n=('ticker','size'),mean_excess13=('excess13','mean'),median_excess13=('excess13','median'),positive_excess_share=('excess13',lambda z:(z>0).mean()),mean_rank_pct=('rank_pct','mean')).reset_index();dec.to_csv(DEC,index=False)
 date_rows=[]
 for d,g in x.groupby('Date'):
  top=g.nlargest(min(15,len(g)),'rank_pct');rel=(g.excess13-g.excess13.min()).to_numpy()[None,:];score=g.raw.to_numpy()[None,:]
  date_rows.append({'Date':d,'n':len(g),'spearman_ic':g.raw.corr(g.excess13,method='spearman'),'top15_positive_excess_precision':(top.excess13>0).mean(),'top15_mean_excess13':top.excess13.mean(),'ndcg15':ndcg_score(rel,score,k=min(15,len(g)))})
 dm=pd.DataFrame(date_rows);dm.to_csv(DATES,index=False)
 # Expanding OOF calibration: each date may use only earlier OOF outcomes.
 cal=[];dates=sorted(x.Date.unique())
 for i,d in enumerate(dates):
  if i<52:continue
  train=x[x.Date.isin(dates[:i])];test=x[x.Date.eq(d)];iso=IsotonicRegression(out_of_bounds='clip').fit(train.rank_pct,train.excess13)
  pred=iso.predict(test.rank_pct);base=np.full(len(test),train.excess13.mean())
  for j,r in enumerate(test.itertuples()):cal.append({'Date':d,'ticker':r.ticker,'rank_pct':r.rank_pct,'actual_excess13':r.excess13,'isotonic_pred_excess13':pred[j],'expanding_mean_pred':base[j]})
 c=pd.DataFrame(cal);c.to_csv(CAL,index=False);iso_mae=float((c.isotonic_pred_excess13-c.actual_excess13).abs().mean());base_mae=float((c.expanding_mean_pred-c.actual_excess13).abs().mean())
 rho=float(stats.spearmanr(dec.decile,dec.mean_excess13).statistic);years=(dm.assign(year=dm.Date.dt.year).groupby('year').top15_mean_excess13.mean());gate=bool(rho>=.8 and dec.iloc[-1].mean_excess13>0 and (years>0).mean()>=.60)
 report={'status':'PASS','parent_stage':p['manifest_sha256'],'test':'N3-SR11-rank-calibration','rows':len(x),'dates':len(dm),'decile_excess_spearman':rho,'top_decile_mean_excess13':float(dec.iloc[-1].mean_excess13),'mean_date_rank_ic':float(dm.spearman_ic.mean()),'mean_top15_precision_positive_excess':float(dm.top15_positive_excess_precision.mean()),'mean_ndcg15':float(dm.ndcg15.mean()),'expanding_isotonic_dates':int(c.Date.nunique()),'isotonic_mae':iso_mae,'expanding_mean_mae':base_mae,'isotonic_mae_improvement':base_mae-iso_mae,'rank_information_gate':'PASS' if gate else 'FAIL','prob_up_is_probability':False,'decision':'calibration is diagnostic; no sizing/adoption without a separately validated economic backtest','holdout_used':False,'production':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');sec=f"\n## 2026-08-02 – N3-39: SR11 rankkalibrering\n\nRankpercentil kalibrerades mot 13v excessavkastning med strikt expanderande OOF-isotonic. Decilmonotonicitet rho={rho:.3f}, toppdecil excess={dec.iloc[-1].mean_excess13:+.2%}, medel-IC={dm.spearman_ic.mean():+.3f}, `rank_information_gate={'PASS' if gate else 'FAIL'}`. `prob_up` är fortsatt inte en sannolikhet. Ingen holdout eller produktion användes.\n"
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(sec)
 stage=freeze_stage('39_rank_calibration',[OUT,DEC,DATES,CAL,Path(__file__).resolve(),RAW,FEAT,PRICE],{'test':'N3-SR11','rank_information_gate':report['rank_information_gate'],'production':False},parent=PARENT);print(dec.to_string(index=False));print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
