"""K9 — periodiseringsgap. Kör den låsta preregistreringen (sha256 8d3d6273...).
Återanvänder K2:s funktioner verbatim så designen inte kan glida isär."""
from __future__ import annotations
import importlib.util, json
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

V2=Path("/home/hannesb/momentum_v2"); PIT=V2/"validated/kpi_pit"
spec=importlib.util.spec_from_file_location("k2",V2/"tools/run_k2_value_within_momentum.py")
k2=importlib.util.module_from_spec(spec); spec.loader.exec_module(k2)

def lk(f):
    rows=json.loads((PIT/f"{f}.json").read_text()); per=defaultdict(list)
    for r in rows: per[r["kod"]].append((r["report_date"],r["v"]))
    for k in per: per[k].sort()
    return {k:([d for d,_ in v],[x for _,x in v]) for k,v in per.items()}

vinst=lk("30_Vinstmarginal_r12"); fcf=lk("24_FCF_Marginal_r12")
class Gap:
    """accrual_gap = vinstmarginal - fcf-marginal, lägre är bättre."""
    def get(self,kod):
        a=vinst.get(kod); b=fcf.get(kod)
        if not a or not b: return None
        ds=sorted(set(a[0])&set(b[0]))
        if not ds: return None
        ma=dict(zip(*a)); mb=dict(zip(*b))
        return (ds,[ma[d]-mb[d] for d in ds])
GAP=Gap()

rankings,tm=k2.h0_and_target()
per=k2.ic_pair(rankings,tm,GAP,-1)      # -1: lägre gap är bättre
s=k2.summarise(per)
bounds=k2.survivorship_bounds(rankings,tm,GAP,-1,s)
cls,bars=k2.classify(s,bounds["flips_sign"])

print("="*74); print("K9 — PERIODISERINGSGAP (vinstmarginal − FCF-marginal, lägre bättre)"); print("="*74)
print(f"  paneldatum {s['panel_dates']}   median n/panel {s['median_n_per_panel']}")
print(f"  mean IC52  H0     {s['mean_ic52_h0']:+.4f}")
print(f"  mean IC52  blend  {s['mean_ic52_blend']:+.4f}")
print(f"  Δ mean IC52       {s['delta_mean_ic52']:+.4f}   (krav >= +0.0100)")
print(f"  Δ median IC52     {s['delta_median_ic52']:+.4f}   (krav > 0)")
print(f"  Δ Top30 IC52      {s['delta_top30_ic52']:+.4f}   (krav >= 0)")
print(f"  positiv andel     {s['positive_ic_share_h0']:.3f} → {s['positive_ic_share_blend']:.3f}")
print(f"  block1 / block2   {s['delta_mean_ic52_block1']:+.4f} / {s['delta_mean_ic52_block2']:+.4f}")
print(f"  survivorship      värsta {bounds.get('varsta_fall',{}).get('delta_mean_ic52',float('nan')):+.4f}"
      f"  spegel {bounds.get('spegel',{}).get('delta_mean_ic52',float('nan')):+.4f}  vänder: {bounds['flips_sign']}")
print(f"\n  KLASSIFICERING: {cls}")
json.dump({"version":"SPARK_K9_RESULT_V1","run_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
 "prereg_sha256":json.loads((V2/"research_k/K9_PREREG_FREEZE.json").read_text())["sha256"],
 "summary":s,"survivorship_bounds":bounds,"classification":cls,"support_bars":bars},
 open(V2/"research_k/k9_accrual_results.json","w"),ensure_ascii=False,indent=2)
print("skrev k9_accrual_results.json")
