"""H0_V2_MEMBERSHIP_CORRECTED_AUDIT_ONLY.
Samma signal, parametrar, rebalans, viktning och kostnad. ENDAST eligibility andras.
Ingen parameter retunas. Ingen size-information anvands. ERSATTER INTE H0 V2."""
from __future__ import annotations
import hashlib, json, math, pathlib, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
import numpy as np
V2=pathlib.Path("/home/hannesb/momentum_v2"); D=V2/"research_k/h0_membership_audit"
sys.path.insert(0,str(V2/"tools"))
import stack_h_motor as S
NOW=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
COST,PPY,N=0.002,13,30

snap=json.load(open(V2/"research_k/nasdaq_segment_foundation/monthly_size_snapshots.json"))["rader"]
manader=sorted({x["report_month"] for x in snap})
by_kod_m={(x["orderbook_code"].upper(),x["report_month"]) for x in snap}
by_isin_m={(x["isin"],x["report_month"]) for x in snap}
isin2kod={}
for x in snap: isin2kod.setdefault(x["isin"],x["orderbook_code"].upper())
def norm(k): return k.replace("-"," ").upper()
def medlem(kod,isin,panel):
    pm=panel[:7]; kand=[m for m in manader if m<pm]
    if not kand: return False
    m=kand[-1]
    if (norm(kod),m) in by_kod_m: return True
    k2=isin2kod.get(isin)
    if k2 and (k2,m) in by_kod_m: return True
    return bool(isin and (isin,m) in by_isin_m)

def kor(F,univ,filtrera):
    dts,ret,schedf=F["eval_dates"],F["returns_map"],F["sched_fn"]
    w={};nets=[];turns=[];top=[]
    for pi,dt in enumerate(dts):
        raw=F["rankings"][dt]
        if filtrera: raw=[r for r in raw if medlem(r["kod"],univ.get(r["kod"]),dt)]
        if schedf(pi,dt) or not w:
            sel=[r["kod"] for r in raw][:N]
            mal={k:1.0/len(sel) for k in sel} if sel else {}
            turn=sum(abs(mal.get(k,0.0)-w.get(k,0.0)) for k in set(mal)|set(w))/2.0
        else:
            mal=dict(w); turn=0.0; sel=sorted(mal)
        top.append((dt,tuple(sorted(k for k in mal))))
        r={k:ret.get((k,dt),0.0) for k in mal}
        nets.append(float(sum(mal[k]*r[k] for k in mal))-COST*turn); turns.append(turn)
        ny={k:mal[k]*(1+r[k]) for k in mal}; s_=sum(ny.values())
        w={k:v/s_ for k,v in ny.items()} if s_>0 else {}
    return np.array(nets),np.array(turns),top

mem={r["kod"]:r.get("kalla") for r in json.load(
     open(V2/"validated/prices_h1419/membership_h1419_v2.json"))["rows"]}
qa=json.load(open(V2/"research_k/avanza_sector_recovery_probe/qa_identity_sector_evidence.json"))
u26={x["instrument_id"]:x.get("expected_isin") for x in qa}
ut={}
for namn,F,univ in (("2014_2019",S.F19,mem),("2020_2026",S.F26,u26)):
    nb,tb,topb=kor(F,univ,False)      # baslinje = fryst eligibility (pris inom 30 dagar)
    nc,tc,topc=kor(F,univ,True)       # audit-only = PIT-verifierat medlemskap
    sb,sc=S.stat(nb),S.stat(nc)
    andr=[(a[0],len(set(a[1])^set(b[1]))//1) for a,b in zip(topb,topc)]
    bytt=[x for x in andr if x[1]>0]
    ov=[len(set(a[1])&set(b[1]))/max(1,len(set(a[1])|set(b[1]))) for a,b in zip(topb,topc)]
    ut[namn]={"baslinje_fryst_eligibility":sb,"audit_only_pit_membership":sc,
      "delta":{"cagr":round(sc["cagr"]-sb["cagr"],4),"vol":round(sc["vol"]-sb["vol"],4),
               "maxdd":round(sc["maxdd"]-sb["maxdd"],4),"sharpe":round((sc["sharpe"] or 0)-(sb["sharpe"] or 0),3)},
      "oms_ar":{"baslinje":round(float(tb.mean())*PPY,4),"audit":round(float(tc.mean())*PPY,4)},
      "top30_paneler_andrade":len(bytt),"antal_paneler":len(andr),
      "medel_antal_andrade_namn":round(float(np.mean([x[1] for x in andr])),2),
      "max_antal_andrade_namn":int(max(x[1] for x in andr)),
      "jaccard_overlap_medel":round(float(np.mean(ov)),4),
      "avkastningskorrelation":round(float(np.corrcoef(nb,nc)[0,1]),4)}
    u=ut[namn]
    print(f"=== {namn} ===")
    print(f"  fryst eligibility : CAGR {sb['cagr']:+.2%} vol {sb['vol']:.2%} maxDD {sb['maxdd']:.2%} Sharpe {sb['sharpe']}")
    print(f"  PIT-medlemskap    : CAGR {sc['cagr']:+.2%} vol {sc['vol']:.2%} maxDD {sc['maxdd']:.2%} Sharpe {sc['sharpe']}")
    print(f"  delta CAGR {u['delta']['cagr']:+.2%}  maxDD {u['delta']['maxdd']:+.2%}")
    print(f"  top30 andrade paneler {u['top30_paneler_andrade']}/{u['antal_paneler']}  "
          f"medel {u['medel_antal_andrade_namn']} namn (max {u['max_antal_andrade_namn']})  "
          f"jaccard {u['jaccard_overlap_medel']:.3f}  retkorr {u['avkastningskorrelation']:.4f}")
json.dump({"schema":"H0_V2_MEMBERSHIP_CORRECTED_AUDIT_ONLY_V1","created_utc":NOW,
  "VIKTIGT":"AUDIT ONLY. Ersatter INTE H0 V2. Ar INTE V3. Baslinjearmen ar den frysta "
    "eligibility-logiken (pris inom 30 dagar) kord i SAMMA harness som auditarmen, sa att "
    "differensen isolerar ENBART eligibility. Absoluta nivaer skiljer sig darfor fran "
    "h1419_exakt_h0_RESULTAT_V2.json, som anvander sin egen fullstandiga motor.",
  "enda_andring":"eligibility: instrumentet maste vara PIT-verifierat STO Main Market Stock "
    "enligt Nasdaq-manadsserien vid senaste rapportmanad STRIKT FORE panelen",
  "fonster":ut},open(D/"h0_v2_vs_membership_corrected_comparison.json","w"),
  ensure_ascii=False,indent=1)
print("\nskrivet: h0_v2_vs_membership_corrected_comparison.json")
