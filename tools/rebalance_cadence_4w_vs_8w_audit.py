"""Strict, separate H0 V3 cadence audit.  Only selection cadence differs."""
from __future__ import annotations
import csv, hashlib, json, math, sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
import numpy as np

ROOT = Path("/home/hannesb/momentum_v2")
OUT = ROOT / "research_k/rebalance_cadence_4w_vs_8w_audit"
sys.path.insert(0, str(ROOT / "tools"))
from h0_v3_eligibility import medlem, kallmanad

PPY, COST, BLOCK, DRAWS, SEED, N = 13.0, .002, 13, 2000, 20260815, 30

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mean(xs): return float(np.mean(xs)) if xs else None
def pct(xs, q): return float(np.percentile(xs, q)) if xs else None

def isin_w1():
    rows=json.loads((ROOT/"validated/prices_h1419/membership_h1419_v2.json").read_text())["rows"]
    return {r["kod"]: (r.get("kalla") if isinstance(r.get("kalla"),str) and len(r["kalla"])==12 and r["kalla"][:2].isalpha() else None) for r in rows}
def isin_w2():
    out={}
    for e in json.loads((ROOT/"research_k/canonical_identity/CANONICAL_IDENTITY_MAP.json").read_text())["entries"]:
        a=[x["isin"] for x in e.get("isin_aliases",[]) if x.get("isin") and len(x["isin"])==12 and x["isin"][:2].isalpha()]
        if a: out[e["instrument_id"]]=a[0]
    return out

def stat(x):
    x=np.asarray(x); nav=np.cumprod(1+x); dd=nav/np.maximum.accumulate(nav)-1
    c=float(nav[-1]**(PPY/len(x))-1); v=float(x.std(ddof=1)*math.sqrt(PPY))
    return {"cagr":c,"vol":v,"maxdd":float(dd.min()),"sharpe":(c-.0224)/v if v else 0.,"calmar":c/abs(float(dd.min())) if dd.min() else None,"nav_end":float(nav[-1])}

def paired_boot(a,b):
    """Existing block length/seed; resample aligned arm panels, preserving pairing."""
    a=np.asarray(a); b=np.asarray(b); rng=np.random.default_rng(SEED); n=len(a); nb=math.ceil(n/BLOCK); ds=[]
    for _ in range(DRAWS):
        ind=[]
        for __ in range(nb):
            s=int(rng.integers(0,n-BLOCK+1)); ind += list(range(s,s+BLOCK))
        ind=np.array(ind[:n]); ds.append(float(np.prod(1+a[ind])**(PPY/n)-np.prod(1+b[ind])**(PPY/n)))
    # conservative effective sample size from non-overlapping calendar blocks
    blocks=[(a[i:min(i+BLOCK,n)]-b[i:min(i+BLOCK,n)]).mean() for i in range(0,n,BLOCK)]
    se=np.std(blocks,ddof=1)/math.sqrt(len(blocks)) if len(blocks)>1 else float("nan")
    mde=2.802*se*PPY if np.isfinite(se) else None
    return {"method":"paired moving-block bootstrap, 13 panels, 2000 draws, seed 20260815","ci95_cagr_diff":[float(np.percentile(ds,2.5)),float(np.percentile(ds,97.5))],"bootstrap_positive_share":float(np.mean(np.array(ds)>0)),"cluster_count":len(blocks),"mde80_pp_per_year":mde,"cluster_mean_diff_pp_per_year":float(np.mean(blocks)*PPY)}

def load_window(tag):
    if tag=="W1":
        pr=ROOT/"research_k/h1419_exakt_h0_preregistration_v2.json"; prices=ROOT/"validated/prices_h1419/prices_h1419_universum_v2.json"; frozen=ROOT/"research_k/h0_v3/h0_v3_RESULTAT.json"; ins=isin_w1()
    else:
        pr=ROOT/"research_k/h0_v3_window2/preregistration.json"; prices=ROOT/"validated/prices/prices_validated.json"; frozen=ROOT/"research_k/h0_v3_window2/result.json"; ins=isin_w2()
    p=json.loads(pr.read_text()); f=json.loads(frozen.read_text()); start=date.fromisoformat(p["fonster"]["test_start"]); end=date.fromisoformat(p["fonster"]["test_slut"])
    panels=[]; d=start
    while d<=end: panels.append(d.isoformat()); d+=timedelta(days=28)
    assert len(panels)==p["fonster"]["n_paneler"]
    raw=json.loads(prices.read_text())
    series={k:(np.array([np.datetime64(x["d"]) for x in rs]),np.array([x["adj"] for x in rs],float)) for k,rs in raw.items()}
    return p,f,panels,series,ins,prices

def run_window(tag):
    print(f"[{tag}] loading and reconstructing canonical rankings", flush=True)
    pr,frozen,panels,series,isins,price_path=load_window(tag)
    def idx(k,dt):
        ds,_=series[k]; z=int(np.searchsorted(ds,np.datetime64(dt),side="right"))-1; return z if z>=0 else None
    def tradable(k,dt):
        i=idx(k,dt)
        return i is not None and int((np.datetime64(dt)-series[k][0][i])/np.timedelta64(1,"D"))<=30
    def mom(k,dt,weeks):
        ds,v=series[k]; now=np.datetime64(dt); target=now-np.timedelta64(7*weeks,"D"); i=int(np.searchsorted(ds,now,side="right"))-1; j=int(np.searchsorted(ds,target,side="right"))-1
        if i<0 or j<0 or int((target-ds[j])/np.timedelta64(1,"D"))>10: return None
        return float(v[i]/v[j]-1)
    rankings={}
    for dt in panels:
        rows=[]
        for k in series:
            if tradable(k,dt) and medlem(k,isins.get(k),dt)[0]: rows.append({"kod":k,"m12":mom(k,dt,52),"m18":mom(k,dt,78)})
        for col in ("m12","m18"):
            good=sorted((r[col],r["kod"]) for r in rows if r[col] is not None); groups=defaultdict(list)
            for v,k in good: groups[v].append(k)
            ranks={}; pos=1
            for v in sorted(groups):
                ks=groups[v]; q=(pos+pos+len(ks)-1)/2/max(1,len(good)); ranks.update({k:q for k in ks}); pos+=len(ks)
            for r in rows: r[col+"_rank"]=ranks.get(r["kod"])
        rawscore=[.5*(r["m12_rank"]+r["m18_rank"]) if r["m12_rank"] is not None and r["m18_rank"] is not None else None for r in rows]
        med=float(np.median([x for x in rawscore if x is not None])) if any(x is not None for x in rawscore) else .5
        scored=[{**r,"score":med if z is None else z} for r,z in zip(rows,rawscore)]; scored.sort(key=lambda x:(x["score"],x["kod"]),reverse=True); rankings[dt]=scored
    print(f"[{tag}] rankings complete; constructing canonical panel returns", flush=True)
    ret={}
    for k,(ds,v) in series.items():
        for a,dt in enumerate(panels[:-1]):
            nd=panels[a+1]; i=int(np.searchsorted(ds,np.datetime64(dt),side="right")); j=int(np.searchsorted(ds,np.datetime64(nd),side="right")); ret[k,dt]=float(v[j-1]/v[i]-1) if i<len(ds) and j-1<len(ds) and j-1>i-1 and i<j and v[i]>0 else 0.
        ret[k,panels[-1]]=0.
    def sma(k,dt):
        i=idx(k,dt)
        return True if i is None or i<200 else bool(series[k][1][i]>=np.mean(series[k][1][i-200:i]))
    # Expose the canonical entry gate to the separate cash-deployment audit;
    # it is diagnostic metadata only and is not used by either cadence arm.
    for dt in panels:
        for r in rankings[dt]: r["sma200_ok"]=sma(r["kod"],dt)
    # The frozen engine precomputes this map for every daily index.  The value
    # is read only at panel dates, so compute the *identical* 60-observation
    # formula lazily there; this avoids an enormous transient allocation.
    volm={}
    def vol(k,dt):
        i=idx(k,dt)
        if not i: return .25
        key=(k,i-1)
        if key not in volm:
            v=series[k][1]
            if i-1 >= 60:
                rr=np.diff(v[i-61:i])/v[i-61:i-1]
                volm[key]=float(np.std(rr)*math.sqrt(252))
            else: volm[key]=.25
        return volm[key]
    def confirmed(k,dt):
        i=idx(k,dt)
        if i is None or i<120:return False
        v=series[k][1]; return bool(v[i]>=np.mean(v[i-120:i]) and np.std(np.diff(v[i-60:i+1])/v[i-60:i])*math.sqrt(252)<.35)
    def simulate(every):
        prev=[]; out=[]; durations=defaultdict(int)
        for a,dt in enumerate(panels):
            raw=rankings[dt]; eligible={r["kod"] for r in raw}; scheduled=every or a%2==0
            sel0=[r["kod"] for r in raw[:N]] if scheduled or not prev else [k for k in prev if k in eligible]
            if not scheduled and len(sel0)<N: sel0 += [r["kod"] for r in raw if r["kod"] not in sel0][:N-len(sel0)]
            turnover=0. if not prev else 1-len(set(sel0)&set(prev))/max(1,len(sel0)); sel=[k for k in sel0 if sma(k,dt)]; n=len(sel)
            if not n: gross=0.; weights={}
            else:
                iv=1/(np.maximum(np.array([vol(k,dt) for k in sel]),.05)**1.5); w=iv/iv.sum()*(n/N); w=w*np.array([1 if confirmed(k,dt) else .75 for k in sel]); w=np.clip(w,.01,.06); w=w/w.sum()*(n/N); weights=dict(zip(sel,map(float,w))); gross=float(sum(weights[k]*ret[k,dt] for k in sel))
            for k in sel0: durations[k]+=1
            out.append({"index":a,"date":dt,"scheduled_base":a%2==0,"selected_pre_sma":sel0,"holdings":sel,"weights":weights,"gross":gross,"turnover":turnover,"cost":COST*turnover,"net":gross-COST*turnover,"entries":sorted(set(sel0)-set(prev)),"exits":sorted(set(prev)-set(sel0)),"n":n})
            prev=sel0
        return out,durations
    print(f"[{tag}] simulating BASE_8W", flush=True); base,bdur=simulate(False)
    print(f"[{tag}] simulating CADENCE_4W", flush=True); four,fdur=simulate(True)
    print(f"[{tag}] both cadence arms complete; applying frozen reproduction gate", flush=True)
    # explicit gate against published frozen return series
    ref=np.array(frozen["nettoserie_h0"],float); got=np.array([x["net"] for x in base]); navdiff=float(np.max(np.abs(np.cumprod(1+got)-np.cumprod(1+ref))))
    sm=stat(got); head=frozen["h0"]; metric_ok=all(abs(sm[k]-head[k])<=.000051 for k in ("cagr","vol","maxdd","sharpe")); gate={"max_abs_panel_net_diff":float(np.max(abs(got-ref))),"max_abs_nav_diff":navdiff,"holdings_mismatch_count":"not available in frozen baseline artifact","headline_metrics_match":metric_ok,"pass":bool(np.max(abs(got-ref))<=.00000051 and metric_ok)}
    if not gate["pass"]: raise RuntimeError(f"BASE reproduction failed {tag}: {gate}")
    # panel-level pair; comparison is meaningful particularly at intermediate panels
    panel=[]
    for b,q in zip(base,four):
        bs,qs=set(b["holdings"]),set(q["holdings"]); inter=not b["scheduled_base"]
        panel.append({"window":tag,"panel_index":b["index"],"date":b["date"],"base_rebalance":b["scheduled_base"],"intermediate_panel":inter,"base_n":b["n"],"fourw_n":q["n"],"overlap_count":len(bs&qs),"jaccard":len(bs&qs)/len(bs|qs) if bs|qs else 1.,"only_4w":len(qs-bs),"only_8w":len(bs-qs),"base_gross":b["gross"],"fourw_gross":q["gross"],"base_turnover":b["turnover"],"fourw_turnover":q["turnover"],"base_cost":b["cost"],"fourw_cost":q["cost"],"base_net":b["net"],"fourw_net":q["net"]})
    def arm(a,dur):
        x=np.array([z["net"] for z in a]); gross=np.array([z["gross"] for z in a]); turns=np.array([z["turnover"] for z in a]); ent=sum(len(z["entries"]) for z in a[1:]); ex=sum(len(z["exits"]) for z in a[1:]); years=len(a)/PPY
        return {**stat(x),"gross_cagr":stat(gross)["cagr"],"total_turnover":float(turns.sum()),"annual_turnover":float(turns.sum()/years),"transaction_cost_total":float(sum(z["cost"] for z in a)),"annual_cost_drag_arithmetic":float(sum(z["cost"] for z in a)/years),"mean_holdings":mean([z["n"] for z in a]),"entries":ent,"exits":ex,"entries_per_year":ent/years,"exits_per_year":ex/years,"mean_holding_panels_pre_sma":mean(list(dur.values())),"mean_holding_days_pre_sma":mean(list(dur.values()))*28}
    A,B=arm(base,bdur),arm(four,fdur); bn=np.array([z["net"] for z in base]); fn=np.array([z["net"] for z in four]); bg=np.array([z["gross"] for z in base]); fg=np.array([z["gross"] for z in four]);
    # Secondary, descriptive holdings exposures.  Size comes from the same PIT
    # Nasdaq snapshots used for eligibility; volatility is the engine's own
    # 60-day value.  The available sector interval map starts in 2020, so W1
    # sector exposure is intentionally marked unavailable rather than backfilled.
    snaps=json.loads((ROOT/"research_k/nasdaq_segment_foundation/monthly_size_snapshots.json").read_text())["rader"]
    size={(r["report_month"],r["orderbook_code"].replace("-"," ").upper()):r["segment"] for r in snaps}
    sectors={r["instrument_id"]:r["canonical_sector"] for r in json.loads((ROOT/"research_k/sector_classification_v1/validated/sector_classification_intervals.json").read_text()) if r.get("valid_from","")<="2020-01-02" and (not r.get("valid_to") or r["valid_to"]>="2020-01-02")}
    def exposure(armrows):
        sz=Counter(); vb=Counter(); sec=Counter(); n=0; secn=0
        for row in armrows:
            hs=row["holdings"]; n+=len(hs); m=kallmanad(row["date"])
            for k in hs:
                sz[size.get((m,k.replace("-"," ").upper()),"UNMAPPED")]+=1
            vals=np.array([vol(r["kod"],row["date"]) for r in rankings[row["date"]]])
            q1,q2=np.percentile(vals,[100/3,200/3])
            for k in hs: vb["LOW" if vol(k,row["date"])<=q1 else "MID" if vol(k,row["date"])<=q2 else "HIGH"]+=1
            if tag=="W2":
                for k in hs:
                    sec[sectors.get(k,"UNMAPPED")]+=1; secn+=1
        norm=lambda c,den:{k:v/den for k,v in sorted(c.items())} if den else {}
        return {"size_share":norm(sz,n),"vol_tercile_share":norm(vb,n),"sector_share_W2_only":norm(sec,secn) if tag=="W2" else "NOT_IDENTIFIABLE: PIT sector interval map begins 2020-01-02"}
    diff={"net_cagr_pp":B["cagr"]-A["cagr"],"gross_cagr_pp":B["gross_cagr"]-A["gross_cagr"],"cost_drag_pp_arithmetic":B["annual_cost_drag_arithmetic"]-A["annual_cost_drag_arithmetic"],"sharpe":B["sharpe"]-A["sharpe"],"maxdd":B["maxdd"]-A["maxdd"],"turnover_annual":B["annual_turnover"]-A["annual_turnover"],"incremental_net_per_incremental_turnover":(B["cagr"]-A["cagr"])/(B["annual_turnover"]-A["annual_turnover"]) if B["annual_turnover"]!=A["annual_turnover"] else None}
    # Mechanism: only BASE entries delayed one intermediate panel that 4W owns there.
    latency=[]; timing=[]
    for i in range(2,len(base),2):
        for k in set(base[i]["entries"]):
            if k in set(four[i-1]["selected_pre_sma"]):
                pre=ret.get((k,panels[i-1]),0.); after=ret.get((k,panels[i]),0.); latency.append({"window":tag,"ticker":k,"base_entry":panels[i],"fourw_entry":panels[i-1],"days_earlier":28,"pre_base_entry_return":pre,"post_base_entry_panel_return":after}); timing.append({"kind":"entry_earlier","ticker":k,"panel":panels[i-1],"return_next_panel":pre})
    for i in range(1,len(base),2):
        # At the intermediate panel BASE continues to own these names whereas
        # CADENCE_4W has already removed them: the requested exit-timing set.
        for k in set(base[i]["selected_pre_sma"])-set(four[i]["selected_pre_sma"]):
            timing.append({"kind":"exit_earlier","ticker":k,"panel":panels[i],"return_next_panel":ret.get((k,panels[i]),0.)})
    summary={"n":len(latency),"share_of_base_new_entries":len(latency)/max(1,sum(len(z["entries"]) for z in base[1:])),"mean_days_earlier":mean([x["days_earlier"] for x in latency]),"mean_return_from_4w_to_base":mean([x["pre_base_entry_return"] for x in latency]),"mean_return_after_base_entry":mean([x["post_base_entry_panel_return"] for x in latency])}
    overlap={"all_panels":{"mean_overlap":mean([x["overlap_count"] for x in panel]),"mean_jaccard":mean([x["jaccard"] for x in panel]),"only_4w_mean":mean([x["only_4w"] for x in panel]),"only_8w_mean":mean([x["only_8w"] for x in panel])},"intermediate_only":{"n":sum(x["intermediate_panel"] for x in panel),"mean_overlap":mean([x["overlap_count"] for x in panel if x["intermediate_panel"]]),"mean_jaccard":mean([x["jaccard"] for x in panel if x["intermediate_panel"]]),"jaccard_p25_p50_p75":[pct([x["jaccard"] for x in panel if x["intermediate_panel"]],q) for q in (25,50,75)]}}
    return {"tag":tag,"panel_calendar":panels,"input_hashes":{"prereg":sha(ROOT/("research_k/h1419_exakt_h0_preregistration_v2.json" if tag=="W1" else "research_k/h0_v3_window2/preregistration.json")),"prices":sha(price_path),"h0_v3_engine":sha(ROOT/"tools/h0_v3_kor.py")},"base_reproduction":gate,"base_8w":A,"cadence_4w":B,"difference_4w_minus_8w":diff,"inference":paired_boot(fn,bn),"holdings_difference":overlap,"cadence_latency":summary,"timing_contributions":{"entry_timing_n":sum(x["kind"]=="entry_earlier" for x in timing),"entry_timing_mean_return":mean([x["return_next_panel"] for x in timing if x["kind"]=="entry_earlier"]),"exit_timing_n":sum(x["kind"]=="exit_earlier" for x in timing),"exit_timing_mean_return":mean([x["return_next_panel"] for x in timing if x["kind"]=="exit_earlier"])} ,"secondary_exposure": {"base_8w":exposure(base),"cadence_4w":exposure(four)},"panel_rows":panel,"latency_rows":latency,"internal_context":{"base":base,"rankings":rankings,"returns":ret,"panels":panels,"sma_fn":sma,"vol_fn":vol,"confirmed_fn":confirmed}}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=OUT/"PREREGISTRATION.md"; plan_hash=sha(plan)
    w1,w2=run_window("W1"),run_window("W2")
    # In-memory context supports companion audits; it is deliberately not part
    # of the canonical cadence result artifact.
    w1.pop("internal_context"); w2.pop("internal_context")
    rows=w1.pop("panel_rows")+w2.pop("panel_rows"); lat=w1.pop("latency_rows")+w2.pop("latency_rows")
    with open(OUT/"panel_level_comparison.csv","w",newline="") as f: w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(OUT/"cadence_latency_entries.csv","w",newline="") as f: w=csv.DictWriter(f,fieldnames=["window","ticker","base_entry","fourw_entry","days_earlier","pre_base_entry_return","post_base_entry_panel_return"]); w.writeheader(); w.writerows(lat)
    d1=w1["difference_4w_minus_8w"]["net_cagr_pp"]; d2=w2["difference_4w_minus_8w"]["net_cagr_pp"]
    verdict="REBALANCE_4W_REPLICATED_POSITIVE" if d1>0 and d2>0 else ("REBALANCE_4W_HARMS" if d1<0 and d2<0 else "REBALANCE_4W_MIXED")
    hold={"W1":w1["holdings_difference"],"W2":w2["holdings_difference"]}
    (OUT/"holdings_difference.json").write_text(json.dumps(hold,ensure_ascii=False,indent=2))
    result={"study":"REBALANCE_CADENCE_4W_VS_8W_AUDIT","plan_sha256":plan_hash,"only_cadence_modified":True,"model_changes":{"ranking_model":"NO","features":"NO","universe":"NO","top_n":"NO","K4A":"NO","sizing":"NO","exit_logic":"NO","cost_model":"NO","only_cadence":"YES"},"W1":w1,"W2":w2,"final_verdict":verdict,"production_change_nominated":False,"conditional_next_study_nomination":False,"future_study_if_justified":"Only after a replicated, net-positive result: pre-register one intermediate-panel conditional rule using already-existing structural rank boundaries for both entrant and incumbent, with no new threshold search. Not run here."}
    (OUT/"RESULT.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    rh=sha(OUT/"RESULT.json"); (OUT/"RESULT_SHA256.txt").write_text(rh+"  RESULT.json\n")
    lines=["# REBALANCE_CADENCE_4W_VS_8W_AUDIT",f"\nFinal verdict: **{verdict}**. BASE reproduction passed in both windows; no production change is nominated.","\nThe calendar is the frozen start date plus 28 calendar days (W1: 79 panels, 2014-01-01..2019-12-25; W2: 86 panels, 2020-01-02..2026-07-09). BASE executes at indexes 0,2,4,…; CADENCE executes at every index.","\n| Window | 8W CAGR | 4W CAGR | Net Δ | Gross Δ | Cost drag Δ | Turnover Δ/year |", "|---|---:|---:|---:|---:|---:|---:|"]
    for label,x in (("W1",w1),("W2",w2)):
        a=x["base_8w"]; b=x["cadence_4w"]; z=x["difference_4w_minus_8w"]
        lines.append(f"| {label} | {a['cagr']:.2%} | {b['cagr']:.2%} | {z['net_cagr_pp']:+.2%} | {z['gross_cagr_pp']:+.2%} | {z['cost_drag_pp_arithmetic']:+.2%} | {z['turnover_annual']:+.2f} |")
    for label,x in (("W1",w1),("W2",w2)):
        a=x["base_8w"]; b=x["cadence_4w"]; z=x["difference_4w_minus_8w"]; inf=x["inference"]; h=x["holdings_difference"]["intermediate_only"]; t=x["timing_contributions"]
        lines += [f"\n## {label}",f"\nReproduction PASS: max panel-net difference {x['base_reproduction']['max_abs_panel_net_diff']:.2e}; max NAV difference {x['base_reproduction']['max_abs_nav_diff']:.2e}. Frozen holdings ledger was not published, so a holdings mismatch count cannot be independently computed; published panel NAV and headline metrics reproduce.",f"\n8W / 4W: Sharpe {a['sharpe']:.3f} / {b['sharpe']:.3f}; MaxDD {a['maxdd']:.2%} / {b['maxdd']:.2%}; Calmar {a['calmar']:.3f} / {b['calmar']:.3f}; annual turnover {a['annual_turnover']:.2f} / {b['annual_turnover']:.2f}; entries/year {a['entries_per_year']:.1f} / {b['entries_per_year']:.1f}; holding duration {a['mean_holding_days_pre_sma']:.0f} / {b['mean_holding_days_pre_sma']:.0f} days.",f"\nPaired 13-panel bootstrap: 95% CI for net CAGR difference [{inf['ci95_cagr_diff'][0]:+.2%}, {inf['ci95_cagr_diff'][1]:+.2%}], positive-draw share {inf['bootstrap_positive_share']:.1%}, MDE80 {inf['mde80_pp_per_year']:.2%}/year. Intermediate holdings: mean Jaccard {h['mean_jaccard']:.3f} (P25/P50/P75 {h['jaccard_p25_p50_p75'][0]:.3f}/{h['jaccard_p25_p50_p75'][1]:.3f}/{h['jaccard_p25_p50_p75'][2]:.3f}), overlap {h['mean_overlap']:.1f} names.",f"\nCadence-latency entries bought earlier: {x['cadence_latency']['n']}; mean return from 4W entry to BASE entry {x['cadence_latency']['mean_return_from_4w_to_base']:.2%}, then {x['cadence_latency']['mean_return_after_base_entry']:.2%} over the next panel. Earlier exits: {t['exit_timing_n']}; their next-panel return while BASE would retain them: {t['exit_timing_mean_return']:.2%}."]
    lines += [f"\nPlan SHA256: `{plan_hash}`",f"\nResult SHA256: `{rh}`", "\nThe daily sampling audit is not used for the estimand; this run uses only the pre-existing synchronized 28-day panels."]
    (OUT/"SUMMARY.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"out":str(OUT),"verdict":verdict,"w1":d1,"w2":d2},ensure_ascii=False))
if __name__=="__main__": main()
