"""Cash-flow companion audit; imports the verified H0 V3 panel reconstruction."""
from __future__ import annotations
import csv, hashlib, json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import rebalance_cadence_4w_vs_8w_audit as H

ROOT=Path('/home/hannesb/momentum_v2'); OUT=ROOT/'research_k/monthly_cash_and_selective_4w_audit'; COST=.002
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def xirr(flows):
    t0=flows[0][0]
    def f(r): return sum(v/(1+r)**((d-t0).days/365.25) for d,v in flows)
    lo,hi=-.999,10.
    for _ in range(200):
        mid=(lo+hi)/2
        if f(mid)>0: lo=mid
        else: hi=mid
    return (lo+hi)/2
def deposits(start,end):
    y,m=start.year,start.month+1
    if m==13:y,m=y+1,1
    ans=[]
    while date(y,m,1)<=end:
        ans.append(date(y,m,1)); m+=1
        if m==13:y,m=y+1,1
    return ans
def context(tag):
    x=H.run_window(tag); return x['internal_context'], x['base_reproduction']
def simulate(tag,ctx,arm):
    rows,rankings,ret,panels=ctx['base'],ctx['rankings'],ctx['returns'],ctx['panels']
    start,end=date.fromisoformat(panels[0]),date.fromisoformat(panels[-1]); ds=deposits(start,end); di=0
    core,cash,extras=100000.,0.,{}; costs=0.; swaps=[]; bd=[]; topups=[]; cash_ids=[]; twr=1.; period_returns=[]; nav_path=[]; flows=[(start,-100000.)]; same=[]; maxw=[]
    for i,(row,dt) in enumerate(zip(rows,panels)):
        now=date.fromisoformat(dt); dep=0.
        begin=core+cash+sum(extras.values())
        while di<len(ds) and ds[di]<=now:
            cash+=7000.; cash_ids.append((ds[di],7000.)); dep+=7000.; flows.append((ds[di],-7000.)); di+=1
        if row['scheduled_base']:
            core+=cash+sum(extras.values()); cash=0.; cash_ids=[]; extras={}
            c=core*COST*row['turnover']; core-=c; costs+=c
        elif arm=='B' and cash>0:
            owned=set(row['selected_pre_sma']); cand=next((r for r in rankings[dt] if r['kod'] not in owned and r['sma200_ok']),None)
            if cand is not None:
                k=cand['kod']; amt=cash; c=amt*COST; cash=0.; extras[k]=extras.get(k,0)+amt-c; costs+=c
                bd.append({'window':tag,'panel':dt,'cash_use':'new_name','ticker':k,'rank':rankings[dt].index(cand)+1,'score':cand['score'],'mom13':'NOT_H0_FEATURE','mom26':'NOT_H0_FEATURE','mom52':cand['m12'],'mom78':cand['m18'],'next_8w_return':ret.get((k,dt),0.)})
        elif arm=='D' and cash>0:
            owned=[r for r in rankings[dt] if r['kod'] in row['weights']]
            cash_before=cash
            total=core+cash+sum(extras.values()); used=[]
            for r in owned:
                if cash<=1e-9: break
                k=r['kod']; cur=core*row['weights'].get(k,0)+extras.get(k,0); cap=max(0.,.06*total-cur); amt=min(cash,cap)
                if amt>0:
                    c=amt*COST; cash-=amt; extras[k]=extras.get(k,0)+amt-c; costs+=c; used.append((k,amt-c))
                    bd.append({'window':tag,'panel':dt,'cash_use':'existing_winner','ticker':k,'rank':rankings[dt].index(r)+1,'score':r['score'],'mom13':'NOT_H0_FEATURE','mom26':'NOT_H0_FEATURE','mom52':r['m12'],'mom78':r['m18'],'next_8w_return':ret.get((k,dt),0.)})
                    for cf,cfamt in cash_ids:
                        topups.append({'cashflow_id':f'{tag}_{cf.isoformat()}','deposit_date':cf.isoformat(),'amount':cfamt,'deployment_date':dt,'ticker':k,'rank':rankings[dt].index(r)+1,'score':r['score'],'weight_before':cur/total,'weight_after':(cur+amt-c)/total,'cap_spill':len(used)>1,'gross_allocation':amt*cfamt/cash_before,'net_allocation':(amt-c)*cfamt/cash_before,'trading_cost':c*cfamt/cash_before,'next_panel_return':ret.get((k,dt),0.)})
            maxw += [(v/(total or 1)) for _,v in used]
            if used: same.append(used[0][0])
            cash_ids=[]
        elif arm=='C':
            owned=set(row['selected_pre_sma']); cand=next((r for r in rankings[dt] if r['kod'] not in owned and r['sma200_ok'] and rankings[dt].index(r)<30),None)
            weak=next((r for r in reversed(rankings[dt]) if r['kod'] in owned and rankings[dt].index(r)>=30),None)
            if cand and weak:
                w=row['weights'].get(weak['kod'],0.); spread=ret.get((cand['kod'],dt),0)-ret.get((weak['kod'],dt),0); c=core*w*COST; core+=core*w*spread-c; costs+=c
                swaps.append({'window':tag,'panel':dt,'sold':weak['kod'],'bought':cand['kod'],'sold_return':ret.get((weak['kod'],dt),0.),'bought_return':ret.get((cand['kod'],dt),0.),'spread':spread,'cost':c})
        # Base core earns exact frozen panel net.  Sleeves earn constituent panel returns.
        core*=1+row['net']; extras={k:v*(1+ret.get((k,dt),0.)) for k,v in extras.items()}
        endv=core+cash+sum(extras.values());
        if begin>0:
            rr=endv/(begin+dep)-1; twr*=1+rr; period_returns.append(rr); nav_path.append({'date':dt,'nav':endv,'external_deposit':dep,'twr_return':rr})
    terminal=core+cash+sum(extras.values()); flows.append((end,terminal)); years=(end-start).days/365.25
    return {'terminal_wealth':terminal,'contributed_capital':100000+7000*len(ds),'profit_above_contributions':terminal-(100000+7000*len(ds)),'twr_cagr':twr**(1/years)-1,'xirr_mwr':xirr(flows),'cash_final':cash,'transaction_costs':costs,'cash_drag':'embedded: cash earns 0%','period_returns':period_returns,'nav_path':nav_path,'swaps':swaps,'bd':bd,'topup_ledger':topups,'max_temporary_sleeve_weight':max(maxw) if maxw else 0.,'same_winner_longest_run':max([len(list(g)) for _,g in __import__('itertools').groupby(same)] or [0])}
def main():
    OUT.mkdir(parents=True,exist_ok=True); plan=OUT/'PREREGISTRATION.md'; result={'plan_sha256':sha(plan),'initial_capital_sek':100000,'monthly_deposit_sek':7000,'arms':{}}
    allbd=[]; allsw=[]
    for tag in ('W1','W2'):
        ctx,gate=context(tag); d={'base_reproduction':gate,'A_BASE_8W':simulate(tag,ctx,'A'),'B_MONTHLY_CASH_NEW_NAME':simulate(tag,ctx,'B'),'C_SELECTIVE_4W_SWAP':simulate(tag,ctx,'C'),'D_MONTHLY_CASH_STRONG_EXISTING':simulate(tag,ctx,'D')}
        a=d['A_BASE_8W']['terminal_wealth']
        for k in ('B_MONTHLY_CASH_NEW_NAME','C_SELECTIVE_4W_SWAP','D_MONTHLY_CASH_STRONG_EXISTING'): d[k]['terminal_wealth_delta_vs_A']=d[k]['terminal_wealth']-a
        result['arms'][tag]=d; allbd += d['B_MONTHLY_CASH_NEW_NAME']['bd']+d['D_MONTHLY_CASH_STRONG_EXISTING']['bd']; allsw += d['C_SELECTIVE_4W_SWAP']['swaps']
    with open(OUT/'new_name_vs_existing_winner.csv','w',newline='') as f: w=csv.DictWriter(f,fieldnames=['window','panel','cash_use','ticker','rank','score','mom13','mom26','mom52','mom78','next_8w_return']);w.writeheader();w.writerows(allbd)
    with open(OUT/'selective_swaps.csv','w',newline='') as f: w=csv.DictWriter(f,fieldnames=['window','panel','sold','bought','sold_return','bought_return','spread','cost']);w.writeheader();w.writerows(allsw)
    # Replication verdicts: terminal wealth direction, separately by window.
    for key,pos,null,harm in [('B_MONTHLY_CASH_NEW_NAME','NEW_NAME_CASH_DEPLOYMENT_POSITIVE','NO_NEW_NAME_CASH_DEPLOYMENT_VALUE','NEW_NAME_CASH_DEPLOYMENT_HARMS'),('C_SELECTIVE_4W_SWAP','SELECTIVE_4W_SWAP_POSITIVE','NO_SELECTIVE_4W_SWAP_VALUE','SELECTIVE_4W_SWAP_HARMS'),('D_MONTHLY_CASH_STRONG_EXISTING','EXISTING_WINNER_TOPUP_POSITIVE','NO_EXISTING_WINNER_TOPUP_VALUE','EXISTING_WINNER_TOPUP_HARMS')]:
        z=[result['arms'][w][key]['terminal_wealth_delta_vs_A'] for w in ('W1','W2')]; result[key+'_verdict']=pos if min(z)>0 else harm if max(z)<0 else null
    (OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)); rh=sha(OUT/'RESULT.json');(OUT/'RESULT_SHA256.txt').write_text(rh+'  RESULT.json\n')
    lines=['# MONTHLY_CASH_AND_SELECTIVE_4W_AUDIT','',f"Plan SHA256: `{result['plan_sha256']}`",f"Result SHA256: `{rh}`",'','| Window | Arm | Terminal wealth | Δ vs A | TWR CAGR | XIRR | Costs |','|---|---|---:|---:|---:|---:|---:|']
    for w in ('W1','W2'):
        for k in ('A_BASE_8W','B_MONTHLY_CASH_NEW_NAME','C_SELECTIVE_4W_SWAP','D_MONTHLY_CASH_STRONG_EXISTING'):
            x=result['arms'][w][k];lines.append(f"| {w} | {k} | {x['terminal_wealth']:.0f} | {x.get('terminal_wealth_delta_vs_A',0):+.0f} | {x['twr_cagr']:.2%} | {x['xirr_mwr']:.2%} | {x['transaction_costs']:.0f} |")
    lines += ['','Verdicts: '+', '.join(f"{k}: {result[k+'_verdict']}" for k in ('B_MONTHLY_CASH_NEW_NAME','C_SELECTIVE_4W_SWAP','D_MONTHLY_CASH_STRONG_EXISTING')),'','`mom13`/`mom26` are explicitly unavailable: they are not H0 features and were not introduced for this study.']
    (OUT/'SUMMARY.md').write_text('\n'.join(lines)+'\n'); print(json.dumps({k:result[k+'_verdict'] for k in ('B_MONTHLY_CASH_NEW_NAME','C_SELECTIVE_4W_SWAP','D_MONTHLY_CASH_STRONG_EXISTING')}))
if __name__=='__main__': main()
