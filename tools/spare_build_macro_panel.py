from __future__ import annotations
import csv,hashlib,json,math
from pathlib import Path
import numpy as np
import pandas as pd

V2=Path(__file__).resolve().parents[1]; RAW=V2/"spare/raw_macro_v1"; OUT=V2/"spare/macro_v1"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def riks(name):
 x=json.loads((RAW/name).read_text()); return pd.Series({pd.Timestamp(r["date"]):float(r["value"]) for r in x}).sort_index()
def fred(name,col):
 d=pd.read_csv(RAW/name); d.columns=["date",col]; d["date"]=pd.to_datetime(d.date); d[col]=pd.to_numeric(d[col],errors="coerce"); return d.set_index("date")[col].dropna().sort_index()
def vix():
 d=pd.read_csv(RAW/"cboe_vix.csv"); d["DATE"]=pd.to_datetime(d.DATE,format="%m/%d/%Y"); return pd.Series(pd.to_numeric(d.CLOSE,errors="coerce").values,index=d.DATE,name="vix").dropna().sort_index()
def asof(s,dates): return s.reindex(s.index.union(dates)).sort_index().ffill().reindex(dates)
def past(s,dates,months):
 q=pd.Series(index=dates,dtype=float)
 for d in dates:
  cut=d-pd.DateOffset(months=months); z=s[s.index<=cut]; q.loc[d]=z.iloc[-1] if len(z) else np.nan
 return q
def ret(s,dates,m):
 now=asof(s,dates); old=past(s,dates,m); return now/old-1
def delta(s,dates,m): return asof(s,dates)-past(s,dates,m)
def vol3(s,dates,periods_per_year=252,min_obs=20):
 rr=np.log(s/s.shift(1))
 q=pd.Series(index=dates,dtype=float)
 for d in dates:
  z=rr[(rr.index>d-pd.DateOffset(months=3))&(rr.index<=d)].dropna(); q.loc[d]=z.std()*math.sqrt(periods_per_year) if len(z)>=min_obs else np.nan
 return q
def main():
 raw_manifest=json.loads((RAW/"source_manifest.json").read_text())
 for e in raw_manifest["files"]:
  p=(RAW/e["path"]).resolve() if not e["path"].startswith("../") else (RAW/e["path"]).resolve()
  assert sha(p)==e["sha256"],e["path"]
 core=json.loads((V2/"panels/core_panel.json").read_text()); dates=pd.DatetimeIndex(sorted({pd.Timestamp(r["panel_date"]) for r in core}))
 src={"policy":riks("riksbank_policy.json"),"gov2y":riks("riksbank_gov2y.json"),"gov10y":riks("riksbank_gov10y.json"),"eursek":riks("riksbank_eursek.json"),"usdsek":riks("riksbank_usdsek.json"),"sp500":fred("fred_sp500.csv","sp500"),"hy_oas":fred("fred_hy_oas.csv","hy_oas"),"brent":fred("fred_brent.csv","brent"),"vix":vix()}
 internal=json.loads((V2/"docs/probes/internal_index_series.json").read_text()); se_ret=pd.Series({pd.Timestamp(k):float(v) for k,v in internal.items()}).sort_index(); src["se_market"]=(1+se_ret).cumprod()
 f={}
 for n,pfx in (("policy","policy_rate"),("gov2y","gov2y"),("gov10y","gov10y")):
  f[pfx+"_level"]=asof(src[n],dates)
  for m in (3,6,12): f[pfx+f"_d{m}m"]=delta(src[n],dates,m)
 curve=src["gov10y"].reindex(src["gov10y"].index.union(src["gov2y"].index)).ffill()-src["gov2y"].reindex(src["gov10y"].index.union(src["gov2y"].index)).ffill()
 f["curve_10y_2y"]=asof(curve,dates)
 for m in (3,6,12): f[f"curve_d{m}m"]=delta(curve,dates,m)
 for n in ("eursek","usdsek"):
  f[n+"_level"]=asof(src[n],dates)
  for m in (3,6,12): f[n+f"_ret{m}m"]=ret(src[n],dates,m)
  f[n+"_vol3m"]=vol3(src[n],dates)
 f["vix_level"]=asof(src["vix"],dates)
 for m in (3,6,12): f[f"vix_d{m}m"]=delta(src["vix"],dates,m)
 # Credit is retained as a raw candidate but rejected below when full 2020 coverage fails.
 for n,pfx in (("brent","brent"),("sp500","sp500"),("se_market","se_market")):
  if n=="brent": f["brent_level"]=asof(src[n],dates)
  for m in (3,6,12): f[pfx+f"_ret{m}m"]=ret(src[n],dates,m)
  if n!="brent": f[pfx+"_vol3m"]=vol3(src[n],dates,52,8) if n=="se_market" else vol3(src[n],dates)
 panel=pd.DataFrame(f,index=dates); panel.index.name="panel_date"
 coverage={c:float(panel[c].notna().mean()) for c in panel}
 rows=[]
 for d,r in panel.iterrows(): rows.append({"panel_date":d.strftime("%Y-%m-%d"),**{k:(None if pd.isna(v) else float(v)) for k,v in r.items()}})
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/"macro_panel.json").write_text(json.dumps(rows,ensure_ascii=False,separators=(",",":"))+"\n")
 source_qa={}
 for n,s in src.items():
  cov=float(asof(s,dates).notna().mean()); source_qa[n]={"first":s.index.min().strftime("%Y-%m-%d"),"last":s.index.max().strftime("%Y-%m-%d"),"observations":int(s.notna().sum()),"panel_level_coverage":cov,"status":"GODKÄND" if cov==1 else "KRÄVER ÅTGÄRD"}
 source_qa["hy_oas"]["status"]="UTESLUTEN"; source_qa["hy_oas"]["reason"]="downloaded official snapshot begins after 2023; fails full 2020-2026 coverage gate"
 source_qa["se_market"]["status"]="GODKÄND_MED_INLEDANDE_LAGGAR"; source_qa["se_market"]["reason"]="frozen internal series starts 2020-01-10; transformations remain null until their preregistered lookback exists"
 qa={"status":"GODKÄND","target_accessed":False,"panel_dates":len(dates),"first_panel_date":str(dates.min().date()),"last_panel_date":str(dates.max().date()),"feature_count":len(panel.columns),"all_feature_names":list(panel.columns),"coverage":coverage,"sources":source_qa,"as_of_rule":"observation_date <= panel_date; forward-fill only; never backfill","same_day_semantics":"rebalance after market close; same-day observed market closes are available","raw_manifest_sha256":sha(RAW/"source_manifest.json")}
 (OUT/"qa.json").write_text(json.dumps(qa,indent=2,ensure_ascii=False)+"\n")
 files=[]
 for p in (OUT/"macro_panel.json",OUT/"qa.json"):
  files.append({"path":p.name,"bytes":p.stat().st_size,"sha256":sha(p)})
 manifest={"version":"macro_panel_v1","status":"FROZEN","files":files,"raw_manifest_sha256":sha(RAW/"source_manifest.json"),"preregistration_sha256":sha(V2/"spare/e3_macro_preregistration.json"),"aggregate_sha256":hashlib.sha256("".join(x["path"]+x["sha256"] for x in files).encode()).hexdigest()}
 (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
 print(json.dumps({"panel_dates":len(dates),"features":len(panel.columns),"aggregate_sha256":manifest["aggregate_sha256"]},indent=2))
if __name__=="__main__": main()
