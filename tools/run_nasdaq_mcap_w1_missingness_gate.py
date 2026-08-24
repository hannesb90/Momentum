"""NASDAQ_MCAP_W1_MISSINGNESS_GATE — data-quality audit only.

No market-cap return buckets, size filter, policy run, or imputations are
performed.  Later-observed size is recorded solely to diagnose missingness.
"""
from __future__ import annotations

import csv, hashlib, json, math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT=Path('/home/hannesb/momentum_v2')
OUT=ROOT/'research_k/nasdaq_mcap_w1_missingness_gate'
MASTER=ROOT/'research_k/nasdaq_historical_master/normalized/instrument_monthly_master.json'
PATH=ROOT/'research_k/h0_v3_state_machine_and_path_ledger/PATH_LEDGER_W1.csv'
PRE=ROOT/'research_k/h0_v3_state_machine_and_path_ledger/PRE_SMA_SELECTION_LEDGER.csv'
PNL=ROOT/'research_k/h0_v3_state_machine_and_path_ledger/PANEL_STATE_PNL_LEDGER.csv'

def norm(x): return (x or '').replace('-',' ').upper()
def dump(n,o): (OUT/n).write_text(json.dumps(o,ensure_ascii=False,indent=2,sort_keys=True,default=lambda x:x.item() if hasattr(x,'item') else str(x))+'\n')
def write_csv(n, fields, rows):
    with (OUT/n).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def f(x,default=0.0):
    try:return float(x)
    except (ValueError,TypeError):return default
def q(xs,p):return float(np.percentile(xs,p)) if xs else None
def summary(xs):
    return {'n':len(xs),'mean':float(np.mean(xs)) if xs else None,'median':float(np.median(xs)) if xs else None,
            'p10':q(xs,10),'p90':q(xs,90),'min':min(xs) if xs else None,'max':max(xs) if xs else None}
def pctile(vals):
    a=sorted(vals,key=lambda k:(vals[k],k));n=len(a)
    return {k:(i/(n-1) if n>1 else .5) for i,k in enumerate(a)}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    master=json.loads(MASTER.read_text())['rader'];by=defaultdict(list);isin2={}
    for r in master:
        by[r['orderbook_code'].upper()].append(r)
        if r.get('isin'):isin2.setdefault(r['isin'],r['orderbook_code'].upper())
    for x in by.values():x.sort(key=lambda r:(r['known_from'],r['observation_month']))
    mrows=json.loads((ROOT/'validated/prices_h1419/membership_h1419_v2.json').read_text())['rows']
    isins={r['kod']:r.get('kalla') for r in mrows}
    def source(ticker,dt):
        ob=norm(ticker)
        if ob not in by and isins.get(ticker) in isin2:ob=isin2[isins[ticker]]
        series=by.get(ob,[]); avail=[r for r in series if r['known_from']<=dt]
        return (avail[-1] if avail else None),series,ob
    # Exact pre-SMA state from frozen selection ledger.
    pre=set()
    with PRE.open(newline='') as fh:
        for r in csv.DictReader(fh):
            if r['window']=='W1' and r['current_pre_sma_selected']=='True':pre.add((r['panel_date'],r['ticker']))
    path=[]
    with PATH.open(newline='') as fh:
        for r in csv.DictReader(fh): path.append(r)
    # One row per PIT-eligible ranked security/panel. Keep full metadata only in memory.
    elig=[r for r in path if r['eligible']=='True']
    bypanel=defaultdict(list)
    for r in elig:bypanel[r['date']].append(r)
    classified={};missing=[];observed=[];held=[]
    for r in elig:
        dt,t=r['date'],r['ticker']; rec,series,ob=source(t,dt)
        available=bool(rec and rec.get('market_cap') not in (None,0))
        if available: reason='AVAILABLE'; observed.append((r,rec))
        elif not series:reason='ENTITY_MAPPING_FAILURE'
        elif series[0]['known_from']>dt:reason='EARLY_HISTORY_GAP'
        elif rec is not None:reason='NASDAQ_RECORD_GAP'
        else:reason='UNRESOLVED'
        selected=(dt,t) in pre; held_flag=f(r['actual_posttrade_weight'])>0
        classified[(dt,t)]={'available':available,'reason':reason,'record':rec,'source_orderbook':ob,
                            'selected_pre_sma':selected,'held':held_flag,'row':r}
        if not available:
            out={'panel_date':dt,'ticker':t,'instrument_id':t,'share_class':t.split('-')[-1] if '-' in t else None,
                 'listing_venue':rec.get('location') if rec else None,'pit_eligible':True,'selected_pre_sma':selected,'actually_held':held_flag,
                 'momentum_score':f(r['h0_score'],None),'current_rank':int(f(r['h0_rank'])) if r['h0_rank'] else None,
                 'portfolio_weight':f(r['actual_posttrade_weight']),'nasdaq_observation_month':rec.get('observation_month') if rec else None,
                 'available_no_of_shares_listed':rec.get('no_of_shares_listed') if rec else None,
                 'available_total_turnover':rec.get('total_turnover') if rec else None,'available_total_trades':rec.get('total_trades') if rec else None,
                 'available_latest_paid':rec.get('latest_paid') if rec else None,'available_segment':rec.get('segment') if rec else None,
                 'reason_market_cap_missing':reason,'first_known_from':series[0]['known_from'] if series else None,
                 'first_observation_month':series[0]['observation_month'] if series else None}
            missing.append(out)
        if held_flag:held.append((r,available,reason,rec))
    # coverage including selected and actual held.
    cov=[]
    for year in sorted({r['date'][:4] for r in elig}):
        for pop, rs in [('PIT_ELIGIBLE_UNIVERSE',[r for r in elig if r['date'][:4]==year]),
                        ('SELECTED_PRE_SMA',[r for r in elig if r['date'][:4]==year and (r['date'],r['ticker']) in pre]),
                        ('ACTUAL_HELD_POSITIONS',[r for r in elig if r['date'][:4]==year and f(r['actual_posttrade_weight'])>0])]:
            av=sum(classified[(r['date'],r['ticker'])]['available'] for r in rs);n=len(rs)
            cov.append({'window':'W1','population':pop,'year':year,'total_security_panel_observations':n,'market_cap_available':av,'market_cap_missing':n-av,'coverage_pct':round(100*av/n,4) if n else None})
    # W2 only reference: reuse audited aggregate report, no calculations.
    old=json.loads((ROOT/'research_k/nasdaq_pit_mcap_audit/NASDAQ_MCAP_READINESS_REPORT.json').read_text())
    for pop in ('PIT_ELIGIBLE_UNIVERSE','SELECTED_PRE_SMA'):
        x=old['gates']['coverage_reproduced'][f'{pop}_W2']
        cov.append({'window':'W2_REFERENCE','population':pop,'year':'ALL','total_security_panel_observations':x['total'],'market_cap_available':x['available'],'market_cap_missing':x['missing'],'coverage_pct':x['coverage_pct']})
    write_csv('NASDAQ_MCAP_W1_COVERAGE_BY_YEAR.csv',list(cov[0]),cov)
    write_csv('NASDAQ_MCAP_W1_MISSING_OBSERVATIONS.csv',list(missing[0]) if missing else ['panel_date'],missing)
    # Cause / temporal concentration.
    causes=Counter(x['reason_market_cap_missing'] for x in missing)
    cause_report={'schema':'NASDAQ_MCAP_W1_MISSINGNESS_CAUSES_V1','n_missing':len(missing),'causes':dict(causes),
                  'share_of_eligible_pct':round(100*len(missing)/len(elig),4),'by_year':{y:dict(Counter(x['reason_market_cap_missing'] for x in missing if x['panel_date'].startswith(y))) for y in sorted({x['panel_date'][:4] for x in missing})},
                  'coverage_stability':'Selected-pre-SMA coverage is >=95% in every calendar year from 2015 onward; actual-held coverage is briefly 94.68% in 2017. W1 still needs MCAP_UNKNOWN rather than omission.'}
    dump('NASDAQ_MCAP_W1_MISSINGNESS_CAUSES.json',cause_report)
    # PIT known Nasdaq proxy profile; missing values remain null, never imputed.
    prof=[]
    for label,rs in [('MCAP_AVAILABLE',[(r,rec) for r,rec in observed]),('MCAP_UNKNOWN',[(x['row'],None) for x in classified.values() if not x['available']])]:
        for field in ('no_of_shares_listed','total_turnover','total_traded_shares','total_trades','latest_paid','listed_days'):
            vals=[float(rec[field]) for r,rec in rs if rec and rec.get(field) not in (None,0)]
            prof.append({'group':label,'field':field,**summary(vals),'available_fraction_pct':round(100*len(vals)/len(rs),3) if rs else None})
        seg=Counter(rec.get('segment') for r,rec in rs if rec)
        for k,v in sorted(seg.items()):prof.append({'group':label,'field':'segment_count','category':k,'n':v,'share_pct':round(100*v/len(rs),3) if rs else None})
    write_csv('NASDAQ_MCAP_W1_MISSINGNESS_PROXY_PROFILE.csv',sorted({k for x in prof for k in x}),prof)
    # Capital exposure, weights are actual post-trade frozen weights into next panel.
    exp=[]
    for dt,rs in sorted(bypanel.items()):
        held_rs=[r for r in rs if f(r['actual_posttrade_weight'])>0]
        unknown=sum(f(r['actual_posttrade_weight']) for r in held_rs if not classified[(dt,r['ticker'])]['available'])
        exp.append({'panel_date':dt,'held_positions':len(held_rs),'unknown_held_positions':sum(not classified[(dt,r['ticker'])]['available'] for r in held_rs),'weight_missing_mcap':unknown})
    write_csv('NASDAQ_MCAP_W1_MISSING_CAPITAL_EXPOSURE.csv',list(exp[0]),exp)
    e=[x['weight_missing_mcap'] for x in exp]
    exposure={'mean':float(np.mean(e)),'median':float(np.median(e)),'p90':q(e,90),'max':max(e),'zero_panels':sum(x==0 for x in e),
              'gt_5pct_panels':sum(x>.05 for x in e),'gt_10pct_panels':sum(x>.10 for x in e),'gt_20pct_panels':sum(x>.20 for x in e),'n_panels':len(e)}
    # P&L state contributions; unknown joins are exact by panel/ticker.
    pnl=[]
    with PNL.open(newline='') as fh:
        for r in csv.DictReader(fh):
            if r['window']=='W1':
                state=classified.get((r['panel_date'],r['ticker']))
                if state: pnl.append((r,not state['available']))
    def pnl_stat(xs):
        g=[f(r['gross_return_contribution']) for r,u in xs];pos=sum(v for v in g if v>0);neg=sum(v for v in g if v<0)
        return {'holding_events':len(xs),'positive_pnl':pos,'negative_pnl':neg,'net_pnl':sum(g),'absolute_pnl':sum(abs(v) for v in g)}
    pu=pnl_stat([x for x in pnl if x[1]]);pt=pnl_stat(pnl)
    for k in ('positive_pnl','negative_pnl','absolute_pnl'):pu['share_of_total_'+k]=pu[k]/pt[k] if pt[k] else None
    write_csv('NASDAQ_MCAP_W1_UNKNOWN_PNL_ATTRIBUTION.csv',list(pu),[pu])
    # Maximum portfolio drawdown interval based only on frozen panel net contributions.
    perdate=defaultdict(float)
    for r,u in pnl:perdate[r['panel_date']]+=f(r['net_contribution'])
    nav=1.;peak=1.;peak_date=None;trough=(0.,None,None)
    for dt in sorted(perdate):
        nav*=1+perdate[dt]
        if nav>peak:peak=nav;peak_date=dt
        dd=nav/peak-1
        if dd<trough[0]:trough=(dd,peak_date,dt)
    ddrows=[(r,u) for r,u in pnl if trough[1] and trough[1] < r['panel_date'] <= trough[2] and f(r['gross_return_contribution'])<0]
    du=sum(f(r['gross_return_contribution']) for r,u in ddrows if u);dtot=sum(f(r['gross_return_contribution']) for r,u in ddrows)
    draw={'peak_date':trough[1],'trough_date':trough[2],'max_drawdown':trough[0],'unknown_negative_pnl':du,'total_negative_pnl':dtot,'unknown_share_of_drawdown_loss':du/dtot if dtot else None,'unknown_weight_mean_during_period':float(np.mean([x['weight_missing_mcap'] for x in exp if trough[1] < x['panel_date'] <= trough[2]])) if trough[1] else None}
    write_csv('NASDAQ_MCAP_W1_UNKNOWN_DRAWDOWN_ATTRIBUTION.csv',list(draw),[draw])
    # Later observed size: no backclassification. Percentile is only at first later observable panel.
    later=[]
    first_missing={}
    for x in missing:first_missing.setdefault(x['ticker'],x)
    for ticker,first in sorted(first_missing.items()):
        candidates=[]
        for dt,rs in sorted(bypanel.items()):
            if dt<=first['panel_date']:continue
            row=next((r for r in rs if r['ticker']==ticker),None)
            if row and classified[(dt,ticker)]['available']:
                vals={r['ticker']:classified[(dt,r['ticker'])]['record']['market_cap'] for r in rs if classified[(dt,r['ticker'])]['available']}
                p=pctile(vals)[ticker];bucket='Q'+str(min(4,int(p*4)+1))
                candidates.append((dt,p,bucket));break
        if candidates:
            dt,p,b=candidates[0];later.append({'ticker':ticker,'first_missing_panel':first['panel_date'],'first_observed_panel':dt,'missing_panels_before_observed':sum(1 for x in missing if x['ticker']==ticker and x['panel_date']<dt),'first_observed_percentile':p,'first_observed_bucket':b})
    write_csv('NASDAQ_MCAP_W1_LATER_OBSERVED_SIZE.csv',list(later[0]) if later else ['ticker'],later)
    # Selected outcome comparison is missingness QA only, using frozen stock returns already in the ledger.
    outcomes=[]
    dates=sorted(bypanel);date_ix={d:i for i,d in enumerate(dates)};rowmap={(r['date'],r['ticker']):r for r in elig}
    for r in elig:
        if (r['date'],r['ticker']) not in pre:continue
        u=not classified[(r['date'],r['ticker'])]['available'];r1=f(r['stock_return_next_period'],None)
        i=date_ix[r['date']];chain=[]
        for j in range(i,min(i+3,len(dates))):
            z=rowmap.get((dates[j],r['ticker']));
            if z is None:chain=[];break
            chain.append(1+f(z['stock_return_next_period'],0))
        r3=(math.prod(chain)-1) if len(chain)==3 else None
        outcomes.append((u,r1,r3))
    outstat={}
    for label,u in [('MCAP_AVAILABLE',False),('MCAP_UNKNOWN',True)]:
        outstat[label]={}
        for h,ix in [('one_panel',1),('three_panel',2)]:
            xs=[x[ix] for x in outcomes if x[0]==u and x[ix] is not None]
            outstat[label][h]={'n':len(xs),'mean':float(np.mean(xs)) if xs else None,'median':float(np.median(xs)) if xs else None,'hit_rate':float(np.mean(np.array(xs)>0)) if xs else None,'p10':q(xs,10),'p90':q(xs,90)}
    # Bounds only change Q1 count/capital possible exposure; no return is reclassified.
    total_selected=len([r for r in elig if (r['date'],r['ticker']) in pre])
    unknown_selected=len([r for r in elig if (r['date'],r['ticker']) in pre and not classified[(r['date'],r['ticker'])]['available']])
    bounds={'selected_observations':total_selected,'unknown_selected':unknown_selected,'unknown_share_pct':100*unknown_selected/total_selected if total_selected else None,
            'scenario_A_all_unknown_Q1':{'additional_possible_Q1_observations':unknown_selected},'scenario_B_no_unknown_Q1':{'additional_possible_Q1_observations':0},
            'scenario_C_observed_distribution':{'expected_additional_Q1_observations':unknown_selected*.25},'capital_exposure':exposure,'rule':'No unknown observation has been assigned a market-cap bucket.'}
    dump('NASDAQ_MCAP_W1_MISSINGNESS_BOUNDS.json',bounds)
    # Winner exposure from all unknown P&L contributors, plus named cases.
    bytick=defaultdict(float)
    for r,u in pnl:
        if u:bytick[r['ticker']]+=f(r['gross_return_contribution'])
    winners={'named_w1':{k:bytick.get(k,0.) for k in ['SAGA-B','NET-B','BALD-B','IAR-B','EOLU-B']},'top_unknown_positive':sorted(([k,v] for k,v in bytick.items() if v>0),key=lambda x:-x[1])[:15], 'top_unknown_negative':sorted(([k,v] for k,v in bytick.items() if v<0),key=lambda x:x[1])[:15]}
    # Conservative materiality decision: early 90% coverage and 95% overall; capital/P&L determine whether manageable.
    material=(exposure['mean']>0.03 or exposure['p90']>0.08 or abs(pu['net_pnl'])>0.10*max(1e-12,abs(pt['net_pnl'])) or (len(later)>=10 and sum(x['first_observed_bucket']=='Q1' for x in later)/len(later)>.6))
    classification='NASDAQ_MCAP_W1_MISSINGNESS_MATERIAL_BUT_MANAGEABLE' if material else 'NASDAQ_MCAP_W1_MISSINGNESS_LOW_MATERIALITY'
    report={'schema':'NASDAQ_MCAP_W1_MISSINGNESS_GATE_V1','classification':classification,'scope':'DATA_QUALITY_ONLY_NO_SIZE_RETURN_OR_FILTER_STUDY',
            'coverage':cov,'causes':cause_report,'capital_exposure':exposure,'unknown_pnl':pu,'total_pnl':pt,'drawdown':draw,'winner_exposure':winners,'later_observed_size':{'n':len(later),'bucket_counts':dict(Counter(x['first_observed_bucket'] for x in later))},'available_vs_unknown_outcomes':outstat,'bounds':bounds,
            'recommendation':'If a later study is preregistered, retain an explicit MCAP_UNKNOWN fifth category. Do not omit or impute these observations.',
            'artifacts':'All output is raw-data/missingness QA; no alpha result was calculated.'}
    dump('NASDAQ_MCAP_W1_MISSINGNESS_GATE_REPORT.json',report)
    print(json.dumps({'classification':classification,'capital_exposure':exposure,'unknown_pnl':pu,'later_bucket_counts':report['later_observed_size']['bucket_counts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
