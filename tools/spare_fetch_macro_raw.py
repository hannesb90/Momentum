from __future__ import annotations
import hashlib,json,urllib.request
from pathlib import Path

V2=Path(__file__).resolve().parents[1]
RAW=V2/"spare/raw_macro_v1"
SOURCES={
 "riksbank_policy.json":"https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF/2018-01-01",
 "riksbank_gov2y.json":"https://api.riksbank.se/swea/v1/Observations/SEGVB2YC/2018-01-01",
 "riksbank_gov10y.json":"https://api.riksbank.se/swea/v1/Observations/SEGVB10YC/2018-01-01",
 "riksbank_eursek.json":"https://api.riksbank.se/swea/v1/Observations/SEKEURPMI/2018-01-01",
 "riksbank_usdsek.json":"https://api.riksbank.se/swea/v1/Observations/SEKUSDPMI/2018-01-01",
 "fred_sp500.csv":"https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500&cosd=2018-01-01",
 "fred_hy_oas.csv":"https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd=2018-01-01",
 "fred_brent.csv":"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU&cosd=2018-01-01",
 "cboe_vix.csv":"https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
}
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 RAW.mkdir(parents=True,exist_ok=True)
 for name,url in SOURCES.items():
  req=urllib.request.Request(url,headers={"User-Agent":"momentum-v2-reproducible-macro-fetch/1.0"})
  with urllib.request.urlopen(req,timeout=120) as r: data=r.read()
  (RAW/name).write_bytes(data)
 internal=V2/"docs/probes/internal_index_series.json"
 entries=[]
 for p in sorted(RAW.iterdir()):
  if p.name=="source_manifest.json": continue
  entries.append({"path":p.name,"bytes":p.stat().st_size,"sha256":h(p),"url":SOURCES[p.name],"classification":"IMMUTABLE_EXTERNAL_RAW_SOURCE"})
 entries.append({"path":"../../docs/probes/internal_index_series.json","bytes":internal.stat().st_size,"sha256":h(internal),"url":None,"classification":"FROZEN_V2_DERIVED_MARKET_SERIES"})
 agg=hashlib.sha256("".join(x["path"]+x["sha256"] for x in entries).encode()).hexdigest()
 manifest={"version":"macro_raw_v1","files":entries,"aggregate_sha256":agg,"fetch_is_explicit_snapshot":True}
 (RAW/"source_manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"files":len(entries),"aggregate_sha256":agg},indent=2))
if __name__=="__main__": main()
