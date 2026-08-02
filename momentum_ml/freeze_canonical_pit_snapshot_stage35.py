"""N3-35: freeze complete feature/price state and its source provenance."""
from __future__ import annotations
import glob,json
from pathlib import Path
import pandas as pd
from niva3_stage_control import freeze_stage,verify_manifest,sha
from tune_publication_missingness_niva3_stage17 import reconstructed_state
from tune_reconstructed_prices_niva3_stage11 import IDS
ROOT=Path(__file__).resolve().parents[1];PARENT=ROOT/'results/niva3_stages/34_sr5_price_state_remediation.json'
PRICE=ROOT/'results/niva3_current_reconstructed_prices_stage34.pkl';FEAT=ROOT/'results/niva3_canonical_features_stage35.pkl';MODEL=ROOT/'results/niva3_canonical_model_state_stage35.pkl'
PROV=ROOT/'results/niva3_canonical_snapshot_provenance.csv';OUT=ROOT/'results/niva3_canonical_snapshot_stage35.json';CACHE=ROOT/'momentum_ml/cache/borsdata'
DOCS=(ROOT/'docs/UTVECKLINGSLOGG.md',ROOT/'docs/niva3_status_handoff.md')
def main():
 p=verify_manifest(PARENT);features,prices,state=reconstructed_state();frozen=pd.read_pickle(PRICE)
 if set(prices)!=set(frozen) or any(not prices[t].equals(frozen[t]) for t in prices):raise RuntimeError('Current reconstructed prices differ from Stage34 frozen candidate')
 pd.to_pickle(features,FEAT);pd.to_pickle(state,MODEL)
 sources=[ROOT/'results/abstention_features.pkl',ROOT/'results/abstention_price_data.pkl',ROOT/'results/abstention_lgbm.pkl',ROOT/'results/niva3_fallback_instrument_events.csv',CACHE/'stocksplits_from2000.json']
 sources += [CACHE/f'stockprices_{iid}_max20.json' for iid in IDS.values()]
 sources += [Path(x) for x in glob.glob(str(CACHE/'dividend_calendar_*.json'))]
 sources=sorted({x.resolve() for x in sources if x.exists()})
 pd.DataFrame([{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size} for x in sources]).to_csv(PROV,index=False)
 bad=[]
 for t,x in frozen.items():
  if 'Close' not in x or not x.index.is_monotonic_increasing or x.index.has_duplicates or (x.Close.dropna()<=0).any():bad.append(t)
 report={'status':'PASS','parent_stage':p['manifest_sha256'],'test':'N3-35-canonical-PIT-snapshot','price_tickers':len(frozen),'price_rows':sum(len(x) for x in frozen.values()),'feature_tickers':len(features),'feature_rows':sum(len(x) for x in features.values()),'source_files':len(sources),'invalid_price_series':bad,'snapshot_gate':'PASS' if not bad else 'FAIL','snapshot_semantics':'immutable current research candidate; no cache resolution permitted downstream','production':False,'holdout_used':False}
 OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
 sec=f"\n## 2026-08-02 – N3-35: kanonisk PIT-snapshot\n\nPrisstate ({len(frozen)} serier), featurestate ({len(features)} bolag), modellstate och {len(sources)} underliggande cache-/corporate-action-filer har hashinventerats. `snapshot_gate={report['snapshot_gate']}`. Efterföljande reträning får endast läsa de frysta picklefilerna, aldrig lösa om cache. Ingen produktion ändrades.\n"
 for d in DOCS:
  with d.open('a',encoding='utf-8') as f:f.write(sec)
 stage=freeze_stage('35_canonical_pit_snapshot',[OUT,PRICE,FEAT,MODEL,PROV,Path(__file__).resolve(),*sources],{'test':'N3-35-canonical-PIT-snapshot','snapshot_gate':report['snapshot_gate'],'production':False},parent=PARENT)
 print(json.dumps(report,indent=2,ensure_ascii=False));print(stage)
if __name__=='__main__':main()
