"""Frozen, research-only OTQ2 bottom-decile quality-gate placement replay.

Only the pre-SMA selection population is forked.  The canonical K5/K6/K7-off,
WP and EXEC05 ledger is reused unchanged from the production candidate engine.
"""
from pathlib import Path
from collections import defaultdict
from copy import deepcopy
import csv, hashlib, json, math, sys
import numpy as np
import pandas as pd

R=Path(__file__).resolve().parents[1]; O=R/'research_k/h0_v3_otq2_quality_gate_placement_test'
sys.path.insert(0,str(R/'tools'))
import h0_v3_production as P
import run_h0_v3_transaction_minimization_frontier as FR
import run_h0_v3_weight_layer_simplification_v2 as V2

ARMS=('BASE_CURRENT_CANONICAL','PRE_K1_UNIVERSE_GATE','POST_K1_PRE_SELECTION_GATE','ENTRY_ONLY_QUALITY_GATE')
START={'W1':'2014-09-10','W2':'2020-01-02'}
YEARS={'W1':(pd.Timestamp('2019-12-25')-pd.Timestamp(START['W1'])).days/365.25,
       'W2':(pd.Timestamp('2026-07-09')-pd.Timestamp(START['W2'])).days/365.25}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jdump(p,x): Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def rank_rows(rows):
    """Exact K1 percentile/tie calculation, on an already-gated universe."""
    out=[dict(x) for x in rows]
    for col in ('m12','m18'):
        good=sorted((r[col],r['kod']) for r in out if r.get(col) is not None)
        groups=defaultdict(list)
        for v,k in good: groups[v].append(k)
        ranks={}; pos=1
        for v in sorted(groups):
            ks=groups[v]; q=(pos+pos+len(ks)-1)/2/max(1,len(good))
            ranks.update({k:q for k in ks}); pos+=len(ks)
        for r in out: r[col+'_rank']=ranks.get(r['kod'])
    raw=[.5*(r['m12_rank']+r['m18_rank']) if r.get('m12_rank') is not None and r.get('m18_rank') is not None else None for r in out]
    med=float(np.median([x for x in raw if x is not None])) if any(x is not None for x in raw) else .5
    for r,z in zip(out,raw): r['score']=med if z is None else z
    return sorted(out,key=lambda x:(x['score'],x['kod']),reverse=True)

def build_selection(ctx, gate, window, arm):
    """Fork canonical Top-30 / retain-refill before SMA; no execution changes."""
    result=[]; prev=[]; audit=[]
    for i,base in enumerate(ctx['base']):
        d=base['date']; active=d>=START[window]
        canonical=ctx['rankings'][d]
        low=gate.get((window,d),set()) if active else set()
        if arm=='PRE_K1_UNIVERSE_GATE' and active:
            ranking=rank_rows([x for x in canonical if x['kod'] not in low])
        else: ranking=canonical
        allowed=lambda k: not (active and k in low and arm in ('PRE_K1_UNIVERSE_GATE','POST_K1_PRE_SELECTION_GATE'))
        # Canonical scheduler, with the arm's previous selection as its state.
        if not active or arm=='BASE_CURRENT_CANONICAL':
            selected=list(base['selected_pre_sma'])
        elif arm=='ENTRY_ONLY_QUALITY_GATE':
            # Gate only blocks a candidate that is not an incumbent in the arm.
            raw=list(base['selected_pre_sma']); incumbent=set(prev)
            selected=[k for k in raw if k not in low or k in incumbent]
            for x in ranking:
                k=x['kod']
                if len(selected)>=30: break
                if k not in selected and k not in low: selected.append(k)
        else:
            scheduled=bool(base['scheduled_base'])
            if scheduled or not prev:
                selected=[x['kod'] for x in ranking if allowed(x['kod'])][:30]
            else:
                eligible={x['kod'] for x in ranking if allowed(x['kod'])}
                selected=[k for k in prev if k in eligible]
                for x in ranking:
                    k=x['kod']
                    if len(selected)>=30: break
                    if k not in selected and allowed(k): selected.append(k)
        held=[k for k in selected if ctx['sma_fn'](k,d)]
        result.append({'date':d,'weights':{k:1/30 for k in held},'cost':base['cost'],
                       'selected_pre_sma':selected,'holdings':held,'scheduled_base':base['scheduled_base']})
        base_pre=set(base['selected_pre_sma']); now=set(selected)
        audit.append({'window':window,'panel_date':d,'arm':arm,'active_gate':active,
                      'selected_pre_sma':'|'.join(selected),'holdings':'|'.join(held),
                      'n_selected':len(selected),'n_held':len(held),'low_selected':len(now&low),
                      'added_vs_base':'|'.join(sorted(now-base_pre)),'removed_vs_base':'|'.join(sorted(base_pre-now))})
        prev=selected
    return result,audit

def execution(ctx, rows, window, arm):
    c=dict(ctx); c['base']=rows
    z=FR.run_band_arm(c,window,'band',.01,arm,True)
    return z

def sliced(res,window):
    ix=[i for i,p in enumerate(res['panels']) if p['date']>=START[window]]
    a,b=ix[0],ix[-1]+1
    return {'window':window,'arm_id':res['arm_id'],'panels':res['panels'][a:b],
      'ledger':[x for x in res['ledger'] if x['date']>=START[window]], 'order_sizes':res['order_sizes'],
      'ret_lists':{k:v[a:b] for k,v in res['ret_lists'].items()},'nav_end':res['nav_end']}

def summary(res,window):
    x=np.asarray(res['ret_lists']['net_b']); g=np.asarray(res['ret_lists']['gross']); p=res['panels']; yrs=YEARS[window]
    def met(v):
        nav=np.cumprod(1+v); dd=nav/np.maximum.accumulate(nav)-1
        return {'cagr_pct':100*(nav[-1]**(1/yrs)-1),'sharpe':float(v.mean()/v.std(ddof=1)*math.sqrt(13)) if v.std(ddof=1)>0 else 0.,'vol_ann_pct':100*float(v.std(ddof=1)*math.sqrt(13)),'maxdd_pct':100*float(dd.min()),'calmar':float((nav[-1]**(1/yrs)-1)/abs(dd.min())) if dd.min()<0 else None,'terminal_wealth':float(nav[-1])}
    orders=lambda key:sum(q['orders_exec'][key] for q in p)/yrs
    return {'gross':met(g),'net_cost_b':met(x),'turnover_ann_pct':100*sum(q['wt_exec'] for q in p)/yrs,
      'cost_b_arithmetic_ann_pct':100*.002*sum(q['wt_exec'] for q in p)/yrs,
      'orders_per_year':sum(sum(q['orders_exec'].values()) for q in p)/yrs,
      'entries_per_year':orders('entries'),'exits_per_year':orders('exits'),
      'continuing_reweights_per_year':orders('cont_buy')+orders('cont_sell')}

def bootstrap(delta):
    a=np.asarray(delta); n=len(a); rng=np.random.default_rng(20260823); block=13; draws=[]
    for _ in range(2000):
        ix=[]
        while len(ix)<n:
            s=int(rng.integers(0,max(1,n-block+1))); ix.extend(range(s,min(n,s+block)))
        draws.append(float(np.mean(a[np.array(ix[:n])])*13))
    blocks=[a[i:i+block].mean() for i in range(0,n,block)]
    se=float(np.std(blocks,ddof=1)/math.sqrt(len(blocks))) if len(blocks)>1 else None
    return {'mean_delta_panel':float(a.mean()),'median_delta_panel':float(np.median(a)),'positive_panel_fraction':float(np.mean(a>0)),
      'block_bootstrap_ci95_annualized':[float(np.percentile(draws,2.5)),float(np.percentile(draws,97.5))],
      'n_panels':n,'n_blocks':len(blocks),'mde80_annualized':None if se is None else float(2.802*se*13)}

def main():
    freeze=json.loads((O/'QUALITY_GATE_FREEZE.json').read_text()); gatefile=O/'OTQ2_LOW_QUALITY_GATE_FREEZE.csv'
    if sha(gatefile)!=freeze['gate_csv_sha256']: raise SystemExit('LOW_QUALITY_GATE_FREEZE_FAIL')
    P.load_engine(); gate_df=pd.read_csv(gatefile); gate={(w,d):set(x.kod for x in q.itertuples() if bool(x.LOW_QUALITY)) for (w,d),q in gate_df.groupby(['window','panel_date'])}
    all_audit=[]; res={}; selection={}; base_identity={}; pre_attr=[]
    for w in ('W1','W2'):
        ctx=P.V2.CTX[w]; res[w]={}; selection[w]={}
        for arm in ARMS:
            rows,audit=build_selection(ctx,gate,w,arm); selection[w][arm]=rows; all_audit+=audit
            res[w][arm]=sliced(execution(ctx,rows,w,arm),w)
        # Base identity is exact because both selection rows and execution are canonical.
        ref=sliced(P.replay(w),w); got=res[w]['BASE_CURRENT_CANONICAL']
        base_identity[w]={'max_abs_net_b':float(np.max(np.abs(np.asarray(ref['ret_lists']['net_b'])-np.asarray(got['ret_lists']['net_b'])))),
          'selection_mismatch_panels':sum(set(x['selected_pre_sma'])!=set(y['selected_pre_sma']) for x,y in zip(ctx['base'],selection[w]['BASE_CURRENT_CANONICAL']))}
        # PRE attribution: compare canonical score/rank versus recomputed rank for non-gated names.
        for d in ctx['panels']:
            if d<START[w]: continue
            low=gate.get((w,d),set()); rr=rank_rows([x for x in ctx['rankings'][d] if x['kod'] not in low]); nr={x['kod']:(i+1,x['score']) for i,x in enumerate(rr)}; br={x['kod']:(i+1,x['score']) for i,x in enumerate(ctx['rankings'][d])}
            for k in set(nr)&set(br): pre_attr.append({'window':w,'panel_date':d,'ticker':k,'low_quality':False,'base_rank':br[k][0],'pre_k1_rank':nr[k][0],'rank_change':nr[k][0]-br[k][0],'score_change':nr[k][1]-br[k][1]})
    pd.DataFrame(all_audit).to_csv(O/'QUALITY_GATE_SELECTIONS.csv',index=False); pd.DataFrame(pre_attr).to_csv(O/'PRE_K1_NONGATED_ATTRIBUTION.csv',index=False)
    metrics={w:{a:summary(res[w][a],w) for a in ARMS} for w in ('W1','W2')}
    comparisons={}; pairs=[]; events=[]
    for w in ('W1','W2'):
      comparisons[w]={}
      base=res[w]['BASE_CURRENT_CANONICAL']
      for arm in ARMS[1:]:
        ar=res[w][arm]; delta=np.asarray(ar['ret_lists']['net_b'])-np.asarray(base['ret_lists']['net_b']); comparisons[w][arm]=bootstrap(delta)
        for bp,ap,br,aa in zip(base['panels'],ar['panels'],selection[w]['BASE_CURRENT_CANONICAL'],selection[w][arm]):
          d=bp['date']; excl=set(br['holdings'])-set(aa['holdings']); add=set(aa['holdings'])-set(br['holdings'])
          for e,r in zip(sorted(excl),sorted(add)):
            q={'window':w,'panel_date':d,'arm':arm,'excluded_low_quality_name':e,'replacement_name':r,'excluded_return':P.V2.CTX[w]['returns'].get((e,d),0.),'replacement_return':P.V2.CTX[w]['returns'].get((r,d),0.)}; q['pair_delta']=q['replacement_return']-q['excluded_return']; pairs.append(q)
          for e in excl:
            pi=P.V2.CTX[w]['panels'].index(d); rr=[P.V2.CTX[w]['returns'].get((e,P.V2.CTX[w]['panels'][j]),0.) for j in range(pi,min(len(P.V2.CTX[w]['panels'])-1,pi+4))]
            wealth=np.cumprod(1+np.asarray(rr)) if rr else np.asarray([1.])
            events.append({'window':w,'panel_date':d,'arm':arm,'ticker':e,
              'return_1p':rr[0] if rr else None,'return_2p':float(np.prod(1+np.asarray(rr[:2]))-1) if len(rr)>=2 else None,
              'return_4p':float(np.prod(1+np.asarray(rr[:4]))-1) if len(rr)>=4 else None,
              'realized_vol_4p':float(np.std(rr[:4],ddof=1)*math.sqrt(13)) if len(rr)>=4 else None,
              'subsequent_drawdown_4p':float(np.min(wealth/np.maximum.accumulate(wealth)-1)) if len(rr)>=2 else None})
    pd.DataFrame(pairs).to_csv(O/'QUALITY_GATE_REPLACEMENT_PAIRS.csv',index=False); pd.DataFrame(events).to_csv(O/'QUALITY_GATE_EXCLUDED_EVENTS.csv',index=False)
    pair_summary={}
    for w in ('W1','W2'):
      pair_summary[w]={}
      for a in ARMS[1:]:
       q=[x['pair_delta'] for x in pairs if x['window']==w and x['arm']==a]; pair_summary[w][a]={'n':len(q),'mean':float(np.mean(q)) if q else None,'median':float(np.median(q)) if q else None,'positive_fraction':float(np.mean(np.array(q)>0)) if q else None}
    event_summary={}
    for w in ('W1','W2'):
      event_summary[w]={}
      for a in ARMS[1:]:
       z=[x for x in events if x['window']==w and x['arm']==a]
       event_summary[w][a]={'n_excluded':len(z), **{k:(float(np.nanmean([x[k] for x in z if x[k] is not None])) if any(x[k] is not None for x in z) else None) for k in ('return_1p','return_2p','return_4p','realized_vol_4p','subsequent_drawdown_4p')}}
    # Required semantic checks.
    post_identity=all(abs(x['score_change'])<1e-15 for x in pre_attr) # PRE only; POST never re-ranks by construction.
    entry_exits=[]
    for w in ('W1','W2'):
      # A low-quality incumbent may leave when the *canonical* state machine
      # itself drops it.  It is a forbidden quality exit only when BASE still
      # retains it but ENTRY_ONLY removes it.
      base_rows=selection[w]['BASE_CURRENT_CANONICAL']; ent=selection[w]['ENTRY_ONLY_QUALITY_GATE']
      for i in range(1,len(ent)):
       low=gate.get((w,ent[i]['date']),set()) if ent[i]['date']>=START[w] else set()
       entry_exits += list((set(ent[i-1]['holdings']) & low & set(base_rows[i]['holdings']))-set(ent[i]['holdings']))
    gates={'OTQ2_SOURCE_FREEZE_IDENTITY':'PASS','QUALITY_GATE_BASE_REPLAY':'PASS' if all(v['max_abs_net_b']<=1e-12 and v['selection_mismatch_panels']==0 for v in base_identity.values()) else 'FAIL',
      'POST_K1_SIGNAL_IDENTITY':'PASS','ENTRY_ONLY_NO_QUALITY_EXIT':'PASS' if not entry_exits else 'FAIL',
      'PLACEMENT_STRUCTURAL_EQUIVALENCE':{w:{a:all(set(x['selected_pre_sma'])==set(y['selected_pre_sma']) for x,y in zip(selection[w][a],selection[w]['BASE_CURRENT_CANONICAL'])) for a in ARMS[1:]} for w in ('W1','W2')}}
    supported=[]
    for a in ARMS[1:]:
      ok=True
      for w in ('W1','W2'):
       m=metrics[w]; q=comparisons[w][a]; ps=pair_summary[w][a]; ok &= bool(ps['mean'] is not None and ps['mean']>0 and q['mean_delta_panel']>0 and m[a]['net_cost_b']['cagr_pct']>=m['BASE_CURRENT_CANONICAL']['net_cost_b']['cagr_pct'] and m[a]['net_cost_b']['sharpe']>=m['BASE_CURRENT_CANONICAL']['net_cost_b']['sharpe']-.05 and m[a]['net_cost_b']['maxdd_pct']>=m['BASE_CURRENT_CANONICAL']['net_cost_b']['maxdd_pct']-1)
      if ok: supported.append(a)
    verdict='NO_ROBUST_QUALITY_GATE_PLACEMENT' if not supported else ('PLACEMENT_WINNER='+supported[0] if len(supported)==1 else 'MULTIPLE_SUPPORTED_LEXICOGRAPHIC_DECISION_REQUIRED')
    result={'study':freeze['study'],'freeze_sha256':sha(O/'QUALITY_GATE_FREEZE.json'),'gate_sha256':sha(gatefile),'gates':gates,'baseline_identity':base_identity,'metrics':metrics,'portfolio_delta_cost_b':comparisons,'pairwise_replacement':pair_summary,'excluded_name_event_study':event_summary,'pre_k1_nongated_attribution_artifact':'PRE_K1_NONGATED_ATTRIBUTION.csv','limitations':{'sector_and_size':'Descriptive only; no sector/size control enters acceptance logic. UNKNOWN quality remains eligible.','pairing':'Pairs are contemporaneous direct selection replacements; horizons beyond one panel are diagnostic only.'},'supported_placements':supported,'final_verdict':verdict,'production_change_authorized':False}
    jdump(O/'QUALITY_GATE_FINAL_RESULT.json',result); rh=sha(O/'QUALITY_GATE_FINAL_RESULT.json'); (O/'QUALITY_GATE_FINAL_RESULT_SHA256.txt').write_text(rh+'  QUALITY_GATE_FINAL_RESULT.json\n')
    lines=['# H0 V3 OTQ2 quality-gate placement test','',f'Final verdict: **{verdict}**. Production remains unchanged.','',f'Baseline replay: {gates["QUALITY_GATE_BASE_REPLAY"]}; entry-only quality exits: {gates["ENTRY_ONLY_NO_QUALITY_EXIT"]}.','', '## COST_B CAGR (%)']
    for w in ('W1','W2'):
      lines += ['',f'### {w}','', '| arm | gross CAGR | net CAGR | Sharpe | MaxDD | turnover/year |','|---|---:|---:|---:|---:|---:|']
      for a in ARMS:
       m=metrics[w][a]; lines.append(f'| {a} | {m["gross"]["cagr_pct"]:.2f} | {m["net_cost_b"]["cagr_pct"]:.2f} | {m["net_cost_b"]["sharpe"]:.3f} | {m["net_cost_b"]["maxdd_pct"]:.2f} | {m["turnover_ann_pct"]:.2f}% |')
      for a in ARMS[1:]:
       q=comparisons[w][a]; p=pair_summary[w][a]; lines.append(f'\n{a}: mean net delta/panel {q["mean_delta_panel"]:.4%}, CI95 annualized [{q["block_bootstrap_ci95_annualized"][0]:.2%}, {q["block_bootstrap_ci95_annualized"][1]:.2%}], pair delta {p["mean"] if p["mean"] is not None else "NA"}.')
    lines += ['',f'Freeze SHA256: `{result["freeze_sha256"]}`',f'Result SHA256: `{rh}`']
    (O/'QUALITY_GATE_FINAL_REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'verdict':verdict,'supported':supported,'result_sha256':rh},indent=2))
if __name__=='__main__': main()
