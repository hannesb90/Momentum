"""Fixed-model mechanism audit; no H0 or parameter search."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
from sklearn.inspection import permutation_importance
import shap
V=Path('/home/hannesb/momentum_v2');sys.path.insert(0,str(V/'tools'))
import h0_extratrees_topn_1419 as T
import h0_validator_model_race_1419 as R
O=V/'research_k/h0_extratrees_mechanism_target_audit_results.json'; RAW=V/'research_k/h0_extratrees_top20_mechanism_audit_raw_events.json'
FAMS={'h0':['h0_score','h0_rank','m12_rank','m18_rank'],'momentum':['mom4','mom13','mom26','mom52','mom12_1','accel13'],'risk':['vol13','vol52','downvol52','maxdd52','skew52','kurt52'],'trend':['trend_t52','trend_consistency52','sma26_gap','sma52_gap','high52_ratio'],'market':['market_median26','market_breadth26']}
def data(): return T.data()
def fit(obs,cut,drop=()):
 idx=[i for i,n in enumerate(R.NAMES) if n not in drop];tr=[r for r in obs if r['y'] is not None and r['date']<=cut];x=np.array([r['x'] for r in tr],float)[:,idx];med=np.nanmedian(x,axis=0);x=np.where(np.isnan(x),med,x);return R.make('extra_trees').fit(x,[r['y'] for r in tr]),med,idx
def imp(d,cut,start,end):
 m,med,idx=fit(d[-1],cut);test=[r for r in d[-1] if r['y'] is not None and start<=r['date']<=end];rng=np.random.default_rng(20260816);test=[test[i] for i in rng.choice(len(test),min(300,len(test)),replace=False)];x=np.array([r['x'] for r in test],float)[:,idx];x=np.where(np.isnan(x),med,x);y=np.array([r['y'] for r in test]);pi=permutation_importance(m,x,y,n_repeats=5,random_state=20260816,scoring='neg_mean_squared_error');sv=shap.TreeExplainer(m).shap_values(x);out=[]
 for j,i in enumerate(idx): out.append({'feature':R.NAMES[i],'permutation_mse':float(pi.importances_mean[j]),'mean_abs_shap':float(np.mean(abs(sv[:,j]))),'shap_direction_corr':float(spearmanr(x[:,j],sv[:,j]).statistic),'native':float(m.feature_importances_[j])})
 return sorted(out,key=lambda z:-z['permutation_mse'])
def main():
 d=data();p=sys.argv[1] if len(sys.argv)>1 else 'all';out=json.loads(O.read_text()) if O.exists() else {'exposed_data':True,'periods':{}}
 if p in ('17','all'):out['periods']['2017']={'importance':imp(d,'2016-12-28','2017-01-25','2017-12-27')}
 if p in ('19','all'):out['periods']['2018_2019']={'importance':imp(d,'2017-12-27','2018-01-24','2019-12-25')}
 O.write_text(json.dumps(out,indent=2));print('wrote',O)
if __name__=='__main__':main()
