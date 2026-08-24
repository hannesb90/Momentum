"""ABSOLUTE_H0_PERFORMANCE_BY_MCAP — frozen-ledger diagnostic, no policy run.

Uses direct Nasdaq monthly market cap, release-lag PIT join, Q1..Q4 inside
the full frozen PIT-eligible universe, and an explicit MCAP_UNKNOWN category.
"""
from __future__ import annotations
import csv, hashlib, json, math
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

ROOT=Path('/home/hannesb/momentum_v2'); OUT=ROOT/'research_k/absolute_h0_performance_by_mcap'
MASTER=ROOT/'research_k/nasdaq_historical_master/normalized/instrument_monthly_master.json'
STATE=ROOT/'research_k/h0_v3_state_machine_and_path_ledger'
BUCKETS=['Q1','Q2','Q3','Q4','MCAP_UNKNOWN']
def f(x,d=0.0):
    try:return float(x)
    except (TypeError,ValueError):return d
def norm(x):return (x or '').replace('-',' ').upper()
def dump(p,x): (OUT/p).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True,default=lambda z:z.item() if hasattr(z,'item') else str(z))+'\n')
def writecsv(p,rows):
    fields=sorted({k for r in rows for k in r}) if rows else ['empty']
    with (OUT/p).open('w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def stats(x):
    a=np.asarray([v for v in x if v is not None and np.isfinite(v)],float)
    if not len(a):return {'n':0}
    n=len(a);k=max(1,int(math.ceil(.1*n)));k5=max(1,int(math.ceil(.05*n)))
    return {'n':int(n),'mean':float(a.mean()),'median':float(np.median(a)),'se_iid':float(a.std(ddof=1)/math.sqrt(n)) if n>1 else None,
            'hit_rate':float(np.mean(a>0)),'p5':float(np.percentile(a,5)),'p10':float(np.percentile(a,10)),'p25':float(np.percentile(a,25)),
            'p75':float(np.percentile(a,75)),'p90':float(np.percentile(a,90)),'p95':float(np.percentile(a,95)),
            'worst_5_mean':float(np.sort(a)[:k5].mean()),'worst_10_mean':float(np.sort(a)[:k].mean()),'best_10_mean':float(np.sort(a)[-k:].mean()),'best_5_mean':float(np.sort(a)[-k5:].mean()),
            'min':float(a.min()),'max':float(a.max()),'skewness':float(((a-a.mean())**3).mean()/(a.std()**3)) if a.std()>0 else None}
def qbucket(p):return 'Q1' if p<.25 else 'Q2' if p<.5 else 'Q3' if p<.75 else 'Q4'
def percentile(d):
    order=sorted(d,key=lambda k:(d[k],k));n=len(order)
    return {k:(i/(n-1) if n>1 else .5) for i,k in enumerate(order)}
def cluster_contrast(records,h):
    # equal-weighted panel differences: robust to within-panel dependence.
    by=defaultdict(lambda:{'q1':[],'rest':[]})
    for r in records:
        x=r.get(h)
        if x is None:continue
        if r['bucket']=='Q1':by[r['date']]['q1'].append(x)
        elif r['bucket'] in ('Q2','Q3','Q4'):by[r['date']]['rest'].append(x)
    ds=[np.mean(z['q1'])-np.mean(z['rest']) for z in by.values() if z['q1'] and z['rest']]
    if not ds:return {'n_panels':0}
    se=float(np.std(ds,ddof=1)/math.sqrt(len(ds))) if len(ds)>1 else None;m=float(np.mean(ds))
    return {'n_panels':len(ds),'mean_difference':m,'panel_cluster_se':se,'ci95_lo':m-1.96*se if se else None,'ci95_hi':m+1.96*se if se else None,'t':m/se if se else None}
def demean_reg(rows,yfield,xfields):
    # panel fixed effects, numeric covariates, HC-like cluster not needed for descriptive support; panel-cluster sandwich.
    groups=defaultdict(list)
    for r in rows:
        if r[yfield] is not None and all(r.get(x) is not None and np.isfinite(r[x]) for x in xfields):groups[r['date']].append(r)
    Y=[];X=[];gid=[]
    for g,rs in groups.items():
        yy=np.array([r[yfield] for r in rs]);xx=np.array([[r[x] for x in xfields] for r in rs])
        Y.extend(yy-yy.mean());X.extend(xx-xx.mean(axis=0));gid += [g]*len(rs)
    if len(Y)<=len(xfields)+2:return {'n':len(Y)}
    Y=np.asarray(Y);X=np.asarray(X);beta=np.linalg.lstsq(X,Y,rcond=None)[0];res=Y-X@beta;xxi=np.linalg.pinv(X.T@X);meat=np.zeros((len(xfields),len(xfields)))
    for g in sorted(set(gid)):
        ind=np.array([z==g for z in gid]);s=X[ind].T@res[ind];meat+=np.outer(s,s)
    vc=xxi@meat@xxi;se=np.sqrt(np.maximum(np.diag(vc),0));r2=1-float((res@res)/(((Y-Y.mean())@(Y-Y.mean())) or 1))
    return {'n':len(Y),'n_panels':len(groups),'variables':xfields,'coefficient':{x:float(beta[i]) for i,x in enumerate(xfields)},'cluster_se':{x:float(se[i]) for i,x in enumerate(xfields)},'t':{x:float(beta[i]/se[i]) if se[i] else None for i,x in enumerate(xfields)},'within_panel_r2':r2}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    master=json.loads(MASTER.read_text())['rader'];by=defaultdict(list);isin2={}
    for r in master:
        by[r['orderbook_code'].upper()].append(r)
        if r.get('isin'):isin2.setdefault(r['isin'],r['orderbook_code'].upper())
    for rs in by.values():rs.sort(key=lambda r:(r['known_from'],r['observation_month']))
    isins={}
    for r in json.loads((ROOT/'validated/prices_h1419/membership_h1419_v2.json').read_text())['rows']:isins[('W1',r['kod'])]=r.get('kalla')
    for r in json.loads((ROOT/'research_k/canonical_identity/CANONICAL_IDENTITY_MAP.json').read_text())['entries']:
        a=[x.get('isin') for x in r.get('isin_aliases',[]) if x.get('isin')]
        if a:isins[('W2',r['instrument_id'])]=a[0]
    def pick(w,t,d,source=by):
        ob=norm(t);isi=isins.get((w,t))
        if ob not in source and isi:ob=isin2.get(isi,'')
        rr=source.get(ob,[]);a=[x for x in rr if x['known_from']<=d]
        return (a[-1] if a else None),ob
    pre=defaultdict(set)
    with (STATE/'PRE_SMA_SELECTION_LEDGER.csv').open(newline='') as fh:
        for r in csv.DictReader(fh):
            if r['current_pre_sma_selected']=='True':pre[r['window']].add((r['panel_date'],r['ticker']))
    paths={}
    for w in ('W1','W2'):
        with (STATE/f'PATH_LEDGER_{w}.csv').open(newline='') as fh:paths[w]=[r for r in csv.DictReader(fh) if r['eligible']=='True']
    def assign(w,source=by):
        rows=paths[w];bp=defaultdict(list)
        for r in rows:bp[r['date']].append(r)
        out=[]
        for d,rs in sorted(bp.items()):
            mc={}
            for r in rs:
                z,_=pick(w,r['ticker'],d,source)
                if z and z.get('market_cap') not in (None,0):mc[r['ticker']]=float(z['market_cap'])
            pc=percentile(mc)
            for r in rs:
                z,ob=pick(w,r['ticker'],d,source);p=pc.get(r['ticker']);b=qbucket(p) if p is not None else 'MCAP_UNKNOWN'
                out.append({'window':w,'date':d,'ticker':r['ticker'],'bucket':b,'percentile':p,'market_cap':mc.get(r['ticker']),
                            'known_from':z.get('known_from') if z else None,'source_orderbook':ob,'selected_pre_sma':(d,r['ticker']) in pre[w],
                            'held':f(r['actual_posttrade_weight'])>0,'weight':f(r['actual_posttrade_weight']),
                            'score':f(r['h0_score'],None),'rank':f(r['h0_rank'],None),'return_1p':f(r['stock_return_next_period'],None)})
        # horizons are compounds of frozen panel returns, only outcomes after t.
        dates=sorted(bp);ix={d:i for i,d in enumerate(dates)};lookup={(r['date'],r['ticker']):r for r in out}
        for r in out:
            for h in (2,3,6):
                chain=[]
                for j in range(ix[r['date']],min(ix[r['date']]+h,len(dates))):
                    z=lookup.get((dates[j],r['ticker']));
                    if not z:chain=[];break
                    chain.append(1+z['return_1p'])
                r[f'return_{h}p']=math.prod(chain)-1 if len(chain)==h else None
            r['log_market_cap']=math.log(r['market_cap']) if r['market_cap'] else None
        return out,bp
    assignments={};panels={}
    for w in ('W1','W2'):assignments[w],panels[w]=assign(w)
    # exact adversarial future-data test at representative actual panels.
    pit=[]
    for w in ('W1','W2'):
        ds=sorted(panels[w]);d=ds[len(ds)//2];base=[r for r in assignments[w] if r['date']==d]
        trunc={k:[r for r in v if r['known_from']<=d] for k,v in by.items()};mut,_=assign(w,trunc);mut=[r for r in mut if r['date']==d]
        key=lambda rs:[{k:r[k] for k in ('ticker','market_cap','percentile','bucket','selected_pre_sma','held')} for r in rs]
        pit.append({'window':w,'panel_date':d,'baseline_digest':hashlib.sha256(canon(key(base)).encode()).hexdigest(),'mutated_digest':hashlib.sha256(canon(key(mut)).encode()).hexdigest(),'identical':key(base)==key(mut)})
    # Deterministic re-assignment / attribution digest rerun.
    det=[]
    for w in ('W1','W2'):
        second,_=assign(w);key=[{k:r[k] for k in ('date','ticker','bucket','percentile','market_cap','selected_pre_sma','held','weight')} for r in assignments[w]]
        key2=[{k:r[k] for k in ('date','ticker','bucket','percentile','market_cap','selected_pre_sma','held','weight')} for r in second]
        det.append({'window':w,'digest_1':hashlib.sha256(canon(key).encode()).hexdigest(),'digest_2':hashlib.sha256(canon(key2).encode()).hexdigest(),'identical':key==key2})
    # Coverage, distributions, forward tables, contrast and selection edge.
    coverage=[];forward=[];contrasts=[];edge=[];reg=[];stability=[];regime=[]
    for w,rows in assignments.items():
        dates=sorted({r['date'] for r in rows});mid=dates[len(dates)//2]
        for yr in sorted({r['date'][:4] for r in rows}):
            for pop,rs in [('PIT_ELIGIBLE_UNIVERSE',[r for r in rows if r['date'][:4]==yr]),('SELECTED_PRE_SMA',[r for r in rows if r['date'][:4]==yr and r['selected_pre_sma']]),('ACTUAL_HELD_POSITIONS',[r for r in rows if r['date'][:4]==yr and r['held']])]:
                coverage.append({'window':w,'year':yr,'population':pop,'n':len(rs),**{b:sum(r['bucket']==b for r in rs) for b in BUCKETS},'coverage_pct':100*sum(r['bucket']!='MCAP_UNKNOWN' for r in rs)/len(rs) if rs else None})
        selected=[r for r in rows if r['selected_pre_sma']]
        for b in BUCKETS:
            rs=[r for r in selected if r['bucket']==b]
            for h in (1,2,3,6):forward.append({'window':w,'population':'SELECTED_PRE_SMA','bucket':b,'horizon_panels':h,**stats([r[f'return_{h}p'] for r in rs])})
        for h in (1,2,3,6):
            contrasts.append({'window':w,'contrast':'Q1_MINUS_Q234','horizon_panels':h,**cluster_contrast(selected,f'return_{h}p')})
            # secondary Q1-Q4 via same panel contrast.
            q14=[{**r,'bucket':('Q1' if r['bucket']=='Q1' else 'Q2' if r['bucket']=='Q4' else 'X')} for r in selected if r['bucket'] in ('Q1','Q4')]
            c=cluster_contrast(q14,f'return_{h}p');contrasts.append({'window':w,'contrast':'Q1_MINUS_Q4','horizon_panels':h,**c})
        for b in ('Q1','Q2','Q3','Q4'):
            for h in (1,3):
                s=[r[f'return_{h}p'] for r in selected if r['bucket']==b];u=[r[f'return_{h}p'] for r in rows if r['bucket']==b]
                edge.append({'window':w,'bucket':b,'horizon_panels':h,'selected_mean':stats(s).get('mean'),'universe_mean':stats(u).get('mean'),'h0_selection_edge':(stats(s).get('mean')-stats(u).get('mean')) if s and u else None,'selected_n':len([x for x in selected if x['bucket']==b]),'universe_n':len([x for x in rows if x['bucket']==b])})
        for h in (1,3,6):reg.append({'window':w,'model':f'future_{h}p ~ score + log_mcap + panel_FE',**demean_reg(selected,f'return_{h}p',['score','log_market_cap'])})
        for h in (1,3):reg.append({'window':w,'model':f'future_{h}p ~ rank + log_mcap + panel_FE',**demean_reg(selected,f'return_{h}p',['rank','log_market_cap'])})
        for half,rs in [('FIRST_HALF',[r for r in selected if r['date']<mid]),('SECOND_HALF',[r for r in selected if r['date']>=mid])]:
            for h in (1,3):stability.append({'window':w,'half':half,'horizon_panels':h,**cluster_contrast(rs,f'return_{h}p')})
        for b in ('Q1','Q4'):
            for h in (1,3):regime.append({'window':w,'bucket':b,'horizon_panels':h,'universe_mean_return':stats([r[f'return_{h}p'] for r in rows if r['bucket']==b]).get('mean'),'n':sum(r['bucket']==b for r in rows)})
    # P&L / capital with exact frozen panel state contributions.
    pmap={(r['window'],r['date'],r['ticker']):r for w in assignments.values() for r in w};pnls=[];pnl_total=Counter();pnl_unmatched=[];pnl_non_security=Counter()
    with (STATE/'PANEL_STATE_PNL_LEDGER.csv').open(newline='') as fh:
        for r in csv.DictReader(fh):
            if r['ticker']=='PANEL_LEVEL_TURNOVER_COST':
                pnl_non_security[r['window']]+=1
                continue
            pnl_total[r['window']]+=1
            z=pmap.get((r['window'],r['panel_date'],r['ticker']))
            if z:pnls.append({**r,'bucket':z['bucket'],'weight':z['weight'],'stock_return':z['return_1p']})
            else:pnl_unmatched.append({'window':r['window'],'panel_date':r['panel_date'],'ticker':r['ticker'],'gross_return_contribution':r['gross_return_contribution']})
    pnl_join=[]
    for w in ('W1','W2'):
        bad=[r for r in pnl_unmatched if r['window']==w]
        pnl_join.append({'window':w,'security_panel_pnl_rows':pnl_total[w],'joined_security_rows':pnl_total[w]-len(bad),'unmatched_security_rows':len(bad),'non_security_cost_rows_excluded':pnl_non_security[w],'join_coverage_pct':100*(pnl_total[w]-len(bad))/pnl_total[w] if pnl_total[w] else None})
    attribution=[];draw=[];winner=[];loser=[];important=[]
    for w in ('W1','W2'):
        ps=[r for r in pnls if r['window']==w];total_pos=sum(f(r['gross_return_contribution']) for r in ps if f(r['gross_return_contribution'])>0);total_neg=sum(f(r['gross_return_contribution']) for r in ps if f(r['gross_return_contribution'])<0);absall=sum(abs(f(r['gross_return_contribution'])) for r in ps);cap=sum(r['weight'] for r in ps)
        for b in BUCKETS:
            rs=[r for r in ps if r['bucket']==b];pos=sum(f(r['gross_return_contribution']) for r in rs if f(r['gross_return_contribution'])>0);neg=sum(f(r['gross_return_contribution']) for r in rs if f(r['gross_return_contribution'])<0);cw=sum(r['weight'] for r in rs)
            cs=cw/cap if cap else None;attribution.append({'window':w,'bucket':b,'holding_intervals':len(rs),'mean_capital_weight':cw/len({r['panel_date'] for r in ps}) if ps else None,'total_capital_exposure':cw,'capital_share':cs,'positive_pnl':pos,'negative_pnl':neg,'net_pnl':pos+neg,'absolute_pnl':sum(abs(f(r['gross_return_contribution'])) for r in rs),'positive_pnl_share':pos/total_pos if total_pos else None,'negative_pnl_share':neg/total_neg if total_neg else None,'absolute_pnl_share':sum(abs(f(r['gross_return_contribution'])) for r in rs)/absall if absall else None,'positive_per_capital':(pos/total_pos)/cs if cs and total_pos else None,'negative_per_capital':(neg/total_neg)/cs if cs and total_neg else None})
        # max drawdown exact from panel frozen net PnL.
        pr=defaultdict(float)
        for r in ps:pr[r['panel_date']]+=f(r['net_contribution'])
        nav=peak=1.;pd=None;dd=(0.,None,None)
        for d in sorted(pr):
            nav*=1+pr[d]
            if nav>peak:peak=nav;pd=d
            if nav/peak-1<dd[0]:dd=(nav/peak-1,pd,d)
        dr=[r for r in ps if dd[1] and dd[1]<r['panel_date']<=dd[2] and f(r['gross_return_contribution'])<0]
        for b in BUCKETS:draw.append({'window':w,'peak_date':dd[1],'trough_date':dd[2],'maxdd':dd[0],'bucket':b,'negative_contribution':sum(f(r['gross_return_contribution']) for r in dr if r['bucket']==b),'capital_exposure':sum(r['weight'] for r in ps if dd[1]<r['panel_date']<=dd[2] and r['bucket']==b)})
        agg=defaultdict(lambda:{'pnl':0.,'weight':0.,'ret':[],'b':Counter()})
        for r in ps:
            a=agg[r['ticker']];a['pnl']+=f(r['gross_return_contribution']);a['weight']+=r['weight'];a['ret'].append(r['stock_return']);a['b'][r['bucket']]+=1
        ordered=sorted(agg.items(),key=lambda x:x[1]['pnl'])
        for kind,seq in [('LOSER',ordered[:15]),('WINNER',ordered[-15:][::-1])]:
            for t,a in seq:(winner if kind=='WINNER' else loser).append({'window':w,'type':kind,'ticker':t,'gross_pnl':a['pnl'],'mean_weight':a['weight']/len(a['ret']),'mean_stock_return':float(np.mean(a['ret'])),'modal_bucket':a['b'].most_common(1)[0][0],'bucket_counts':dict(a['b'])})
        names={'W1':{'SAGA-B','NET-B','BALD-B','IAR-B','EOLU-B'},'W2':{'VOLO','VBG-B','CLAS-B','RAY-B','HTRO','IPCO'}}[w]
        for t in sorted(names):
            a=agg.get(t)
            if a:important.append({'window':w,'ticker':t,'gross_pnl':a['pnl'],'mean_weight':a['weight']/len(a['ret']),'mean_stock_return':float(np.mean(a['ret'])),'modal_bucket':a['b'].most_common(1)[0][0],'bucket_counts':dict(a['b']),'holding_intervals':len(a['ret'])})
    # output tables and report.
    writecsv('ASSIGNMENTS.csv',[r for w in ('W1','W2') for r in assignments[w]]);writecsv('COVERAGE_BY_YEAR.csv',coverage);writecsv('FORWARD_RETURNS_BY_BUCKET.csv',forward);writecsv('CONTRASTS.csv',contrasts);writecsv('SELECTION_EDGE_BY_BUCKET.csv',edge);writecsv('REGRESSION_CONTROLS.csv',reg);writecsv('TIME_STABILITY.csv',stability);writecsv('UNIVERSE_SIZE_REGIME.csv',regime);writecsv('PORTFOLIO_PNL_ATTRIBUTION.csv',attribution);writecsv('DRAWDOWN_ATTRIBUTION.csv',draw);writecsv('TOP_WINNERS_BY_BUCKET.csv',winner);writecsv('TOP_LOSERS_BY_BUCKET.csv',loser);writecsv('IMPORTANT_WINNER_SIZE_ATTRIBUTION.csv',important);writecsv('UNMATCHED_PNL_ROWS.csv',pnl_unmatched);dump('PNL_JOIN_COVERAGE.json',pnl_join)
    # frozen baseline confirmation; no execution was changed.
    base=json.loads((STATE/'BASE_REPRODUCTION.json').read_text())
    verdict='ABS_H0_MCAP_NO_ROBUST_SIZE_EFFECT'
    # The classification is mechanical only in the weak sense: requires same Q1-Q234 sign in W1/W2 for 1p and 3p and no winner-tail dominance. Otherwise mixed.
    pc={(r['window'],r['horizon_panels']):r for r in contrasts if r['contrast']=='Q1_MINUS_Q234'}
    a,b=pc[('W1',1)]['mean_difference'],pc[('W2',1)]['mean_difference'];a3,b3=pc[('W1',3)]['mean_difference'],pc[('W2',3)]['mean_difference']
    q1attr={(r['window']):r for r in attribution if r['bucket']=='Q1'}
    if (a<0 and b<0 and a3<0 and b3<0):
        verdict='ABS_H0_MCAP_MIXED' if any(q1attr[w]['positive_per_capital'] and q1attr[w]['positive_per_capital']>=1 for w in ('W1','W2')) else 'ABS_H0_MCAP_Q1_EXCLUSION_CANDIDATE'
    elif any(x<0 for x in (a,b,a3,b3)) and any(x>0 for x in (a,b,a3,b3)):verdict='ABS_H0_MCAP_MIXED'
    report={'study':'ABSOLUTE_H0_PERFORMANCE_BY_MCAP','scope':'EXPLORATORY_DIAGNOSTIC_ONLY_NO_FILTER_BACKTEST','baseline_reproduction':base,'market_cap_source':'direct Nasdaq monthly Market Cap; latest known_from <= panel; percentile tie-break=(market_cap,ticker)','pit_adversarial_test':{'status':'PASS' if all(x['identical'] for x in pit) else 'FAIL','tests':pit},'determinism':{'status':'PASS' if all(x['identical'] for x in det) else 'FAIL','tests':det},'pnl_join_coverage':pnl_join,'coverage':coverage,'primary_contrasts':[r for r in contrasts if r['contrast']=='Q1_MINUS_Q234'],'secondary_contrasts':[r for r in contrasts if r['contrast']=='Q1_MINUS_Q4'],'unknown_policy':'MCAP_UNKNOWN is retained and never assigned to a quartile or excluded.','classification':verdict,'candidate_recommendation':'NONE' if verdict!='ABS_H0_MCAP_Q1_EXCLUSION_CANDIDATE' else 'EXCLUDE_BOTTOM_MCAP_QUARTILE requires a separate preregistered policy test.'}
    dump('RESULT.json',report)
    print(json.dumps({'classification':verdict,'pit':report['pit_adversarial_test']['status'],'determinism':report['determinism']['status'],'primary':report['primary_contrasts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
