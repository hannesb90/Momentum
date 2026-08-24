import hashlib,json,csv
from pathlib import Path
R=Path('/home/hannesb/momentum_v2')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'research_k/h0_v3_size_attribution_audit';o.mkdir(exist_ok=True)
 pre={'study':'H0_V3_SIZE_ATTRIBUTION_AUDIT','status':'BLOCKED_PIT_MARKET_CAP_UNAVAILABLE','primary':'PIT cross-sectional market-cap quintiles','no_size_policy':True}
 (o/'PREREGISTRATION.json').write_text(json.dumps(pre,indent=2)+'\n');(o/'PREREGISTRATION.md').write_text('# Size attribution audit\n\nPIT market-cap quintiles are required. No empirical size attribution is run unless historical PIT market cap is available.\n')
 (o/'BASE_REPRODUCTION.json').write_text(json.dumps({'status':'NOT_RUN__PIT_GATE_FAILED'},indent=2)+'\n')
 (o/'PIT_MARKET_CAP_METHOD.md').write_text('# PIT market-cap gate\n\n`monthly_size_snapshots.json` is PIT segment membership only (Small/Mid/Large); its rows contain no market-cap or shares field. It cannot form cross-sectional market-cap quintiles. Using current market cap or survivorship mappings is prohibited.\n')
 for f,h in [('SIZE_EXPOSURE_BY_PANEL.csv','status\nBLOCKED_PIT_MARKET_CAP_UNAVAILABLE\n'),('SIZE_PNL_ATTRIBUTION.csv','status\nBLOCKED_PIT_MARKET_CAP_UNAVAILABLE\n'),('SIZE_EPISODE_ATTRIBUTION.csv','status\nBLOCKED_PIT_MARKET_CAP_UNAVAILABLE\n'),('W1_W2_SIZE_DECOMPOSITION.csv','status\nBLOCKED_PIT_MARKET_CAP_UNAVAILABLE\n'),('WINNER_SIZE_ATTRIBUTION.csv','status\nBLOCKED_PIT_MARKET_CAP_UNAVAILABLE\n')]:(o/f).write_text(h)
 res={'verdict':'SIZE_ATTRIBUTION_BLOCKED','blocker':'No local source provides PIT market cap/shares aligned to the H0 panel date; available historical snapshots are segment-only.'};(o/'RESULT.json').write_text(json.dumps(res,indent=2)+'\n');(o/'SUMMARY.md').write_text('# Size attribution audit\n\nBlocked before attribution: no PIT market-cap input.\n');(o/'HASHES.txt').write_text(f'{sha(o/"PREREGISTRATION.json")}  PREREGISTRATION.json\n{sha(o/"RESULT.json")}  RESULT.json\n')
if __name__=='__main__':main()
