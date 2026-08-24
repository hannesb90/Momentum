#!/usr/bin/env python3
"""Exact 46-row difference from the frozen 420-script legacy registry. No targets/results read."""
from __future__ import annotations
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];REG=R/'research_i/legacy_hypothesis_registry.json';OUT=R/'research_i/LEGACY_V2_COVERAGE_MATRIX_PRE_BATCH3.json'
M={
'run_armed_takeprofit_state_machine_stage38.py':('Armed take-profit after sector-relative strength and subsequent drawdown/rank decay','armed exit','KAN INTE TESTAS — DATA SAKNAS','—','No PIT-defensible historical sector state; drawdown/trend/rank exit legs already covered','nej'),
'run_armed_technical_exit_stage41.py':('Sector-armed trend/rank exit','armed exit','KAN INTE TESTAS — DATA SAKNAS','—','PIT sector history is unavailable; unarmed trend/rank exits were answered in F','nej'),
'run_cash_alternative_after_exit_current.py':('Cash versus market replacement after technical exit','post-exit allocation','DUPLIKAT/SAMMA HYPOTES','Spår F / Batch 2','No supported technical exit survived; cash/gate risk control already covered','nej'),
'run_cause_specific_reentry_current.py':('Exit-cause-specific cooldown/re-entry','re-entry','KAN INTE TESTAS — DATA SAKNAS','—','Frozen H0 history lacks a mutually exclusive PIT exit-cause ledger','nej'),
'run_correlation_refill_stage119.py':('Refill correlation-rejected slots with next ranked diversifying candidate','correlation allocation','FORTFARANDE MOTIVERAD ATT TESTA','Batch 3','Distinct diversification mechanism; adjusted-close history is sufficient','ja'),
'run_drawdown_rank_confirmed_exit_current.py':('Exit only when drawdown and rank deterioration agree','combined exit','DUPLIKAT/SAMMA HYPOTES','Spår F / Batch 2','Combination of separately answered drawdown and rank-exit legs; legacy used a parameter grid','nej'),
'run_fundamental_residual_to_roa_current.py':('Profitability quality beyond price momentum','fundamental quality','FORTFARANDE MOTIVERAD ATT TESTA','Batch 3','QA-approved PIT roa_ttm exists; raw ROA is testable without inventing PIT sector neutralization','ja'),
'run_quality_momentum_neutralized_current.py':('Trend quality adds to momentum','momentum quality','BESVARAD BATCH 1','Research I Batch 1','Drawdown resilience, trend strength, weekly consistency and jump diffuseness tested','nej'),
'run_reentry_threshold_canonical_stage116.py':('Require rank recovery before re-entry','re-entry','KAN INTE REPLIKERAS ENTydigt','Batch 2 inventory','Several incompatible 0/5/10pp and MA-unlock definitions; choosing one is new research','nej'),
'run_sizing_decomposition_stage120.py':('Decompose diversification benefit from sizing','sizing','BESVARAD BATCH 1','Research I Batch 1','Inverse-vol sizing and target-vol tested with frozen H0 selection','nej'),
'run_small_sizing_isolation_s11.py':('Volatility-based position sizing','sizing','BESVARAD BATCH 1','Research I Batch 1','Same economic inverse-vol/vol-target family','nej'),
'run_small_sizing_rerun_s19.py':('Volatility-based position sizing rerun','sizing','DUPLIKAT/SAMMA HYPOTES','Research I Batch 1','Rerun of same sizing family','nej'),
'tune_anchor_exit.py':('Expected-return-anchored early exit','model-conditioned exit','KAN INTE TESTAS — DATA SAKNAS','—','Requires legacy calibrated probability/expected-return state not present in frozen H0','nej'),
'tune_asymmetric_exit.py':('SMA trend exit','trend exit','REDAN BESVARAD I V2','Spår F F7','Absolute trend-break exit tested; nearby SMA lengths are parameter variants','nej'),
'tune_attention_gap.py':('Weak attention/initial report reaction predicts drift','report/attention/PEAD','KAN INTE TESTAS — DATA SAKNAS','Batch 1 data gate','No QA-approved event timestamp/reaction/volume chain','nej'),
'tune_combined_exit_2026_08_04.py':('Combine momentum/rank deterioration with drawdown floor','combined exit','DUPLIKAT/SAMMA HYPOTES','Spår F / Batch 2','Combination of answered exit legs, not independent information','nej'),
'tune_combined_exits.py':('Combine trend and ATR exits','combined exit','KAN INTE TESTAS — DATA SAKNAS','—','ATR/high-low chain is not QA-approved; trend leg already answered','nej'),
'tune_correlation_filter_freq.py':('Measure/use pairwise-correlation filtering','correlation allocation','DUPLIKAT/SAMMA HYPOTES','Batch 3 family','Same economic family as correlation refill; one fixed replication only','nej'),
'tune_dd20_hold_kombo_2026_08_05.py':('Combine DD20 with signal-streak holding rule','combined exit','DUPLIKAT/SAMMA HYPOTES','Batch 2','DD20 answered; exact weekly streak is data-blocked; combination forbidden','nej'),
'tune_dd20_robustness_2026_08_04.py':('Individual 20% drawdown exit','drawdown exit','BESVARAD BATCH 2','Research I Batch 2','Exact DD20 legacy replication received INGET STÖD','nej'),
'tune_dispersion_proxy.py':('Price-signal dispersion describes momentum regimes','regime diagnostic','BESVARAD BATCH 1','Research I Batch 1','Tested explicitly as price proxy, not analyst dispersion','nej'),
'tune_exit_2026_08_06.py':('Rank hysteresis and exit candidates','exit grid','DUPLIKAT/SAMMA HYPOTES','Spår F / Batch 2','Grid of nearby rank/trend/drawdown/milestone variants already economically answered','nej'),
'tune_graded_exit_2026_08_04.py':('Graded absolute/relative trend exit','trend exit','DUPLIKAT/SAMMA HYPOTES','Spår F F7 / Batch 2','Same trend-loss and risk-exit information with different staging','nej'),
'tune_hold_forever.py':('Long-horizon persistence of buy signals','holding horizon','KAN INTE TESTAS — DATA SAKNAS','—','Requires new 2–3 year targets/cohorts outside frozen 52w target contract','nej'),
'tune_hold_forever_fundamentals.py':('Fundamentals identify multi-year winners among signals','fundamental long horizon','KAN INTE TESTAS — DATA SAKNAS','—','Requires unfrozen 2–3 year target and has severe fundamental survivorship','nej'),
'tune_hold_streak_2026_08_05.py':('Exit when weekly signal streak breaks','streak','KAN INTE TESTAS — DATA SAKNAS','Batch 2 gate','Exact weekly signal history is absent from frozen 4-week V2 panel','nej'),
'tune_individual_drawdown_floor.py':('Individual drawdown floor','drawdown exit','DUPLIKAT/SAMMA HYPOTES','Research I Batch 2','Same DD-floor hypothesis; threshold difference is not new information','nej'),
'tune_individual_drawdown_floor_rotate.py':('Drawdown exit with immediate ranked replacement','drawdown exit','BESVARAD BATCH 2','Research I Batch 2','DD20 replication used immediate ranked replacement','nej'),
'tune_individual_voltarget_2026_08_04.py':('Individual volatility targeting','risk allocation','DUPLIKAT/SAMMA HYPOTES','Research I Batch 1','Inverse-vol and target-vol covered the risk-allocation hypothesis','nej'),
'tune_ingang_streak_2026_08_05.py':('Require persistent weekly signal before entry','streak','KAN INTE TESTAS — DATA SAKNAS','Batch 2 gate','Exact weekly signal streak cannot be reconstructed without approximation','nej'),
'tune_malexit_2026_08_06.py':('Exit non-delivering position at half horizon','milestone exit','BESVARAD BATCH 2','Research I Batch 2','26-week absolute milestone tested and received INGET STÖD','nej'),
'tune_malexit_placebo_2026_08_06.py':('Placebo validation of milestone exit','milestone exit','DUPLIKAT/SAMMA HYPOTES','Research I Batch 2','Diagnostic of same 26w milestone, not a distinct hypothesis','nej'),
'tune_pead.py':('Post-earnings announcement drift','report/attention/PEAD','KAN INTE TESTAS — DATA SAKNAS','Batch 1 data gate','No QA-approved PIT publication/reaction chain','nej'),
'tune_quality_momentum_interact.py':('Interact momentum with trend quality','momentum quality','BESVARAD BATCH 1','Research I Batch 1','Fixed 50/50 H0 blends with quality factors tested; H1/H2 frozen separately','nej'),
'tune_reentry_threshold_production.py':('Rank-improvement threshold before re-entry','re-entry','KAN INTE REPLIKERAS ENTydigt','Batch 2 inventory','Legacy grid 0/5/10pp and no unique preregistered value','nej'),
'tune_refill_discount.py':('Rebuy exited name after a fixed price discount','re-entry','KAN INTE REPLIKERAS ENTydigt','—','Depends on legacy sellwatch state and a 5/10/15/20% grid; no unique rule','nej'),
'tune_report_crowding.py':('Report crowding/attention changes drift','report/attention/PEAD','KAN INTE TESTAS — DATA SAKNAS','Batch 1 data gate','Required PIT report-event and attention data absent','nej'),
'tune_report_dip_reversal.py':('Report dip followed by reversal/drift','report/attention/PEAD','KAN INTE TESTAS — DATA SAKNAS','Batch 1 data gate','Required event timestamp and initial-reaction window absent','nej'),
'tune_resid_mom_ic.py':('Residual momentum adds stock-specific information','residual momentum','BESVARAD BATCH 1','Research I Batch 1','Solo and fixed H0 blend tested','nej'),
'tune_sizing.py':('Alternative position sizing','sizing','BESVARAD BATCH 1','Research I Batch 1','Inverse-vol sizing tested as risk, not alpha','nej'),
'tune_sizing_korr_2026_08_04.py':('Correlation-aware sizing','sizing/correlation','DUPLIKAT/SAMMA HYPOTES','Batch 1 / Batch 3 family','Sizing answered; remaining correlation-selection question consolidated into one Batch 3 family','nej'),
'tune_sizing_niva2_stage4.py':('Alternative position sizing','sizing','DUPLIKAT/SAMMA HYPOTES','Research I Batch 1','Same economic sizing family','nej'),
'tune_streak_2026_08_04.py':('Persistent candidate signal plus underperforming holding swap','streak','KAN INTE TESTAS — DATA SAKNAS','Batch 2 gate','Requires weekly signal streak unavailable in frozen V2','nej'),
'tune_takeprofit.py':('Take-profit/armed sellwatch gap','take-profit exit','KAN INTE REPLIKERAS ENTydigt','—','Legacy searches 30/40/50/60/80% gaps; no unique fixed economic parameter','nej'),
'tune_voltarget.py':('Portfolio volatility target','risk allocation','BESVARAD BATCH 1','Research I Batch 1','Fixed 10% no-leverage target-vol tested','nej'),
'tune_voltarget_addon_2026_08_04.py':('Volatility-target add-on','risk allocation','DUPLIKAT/SAMMA HYPOTES','Research I Batch 1','Same target-vol economic hypothesis','nej')}
def main():
 x=json.loads(REG.read_text());rows=[r for r in x['rows'] if r['classification']=='REPLIKERA NU'];assert len(rows)==46;assert {r['legacy_script'] for r in rows}==set(M)
 out=[]
 for r in rows:
  hyp,fam,status,where,reason,rem=M[r['legacy_script']]
  out.append({'legacy_test':r['legacy_script'],'ekonomisk_hypotes':hyp,'familj':fam,'V2_status':status,'var_testad':where,'resultat':reason,'återstår_ja_nej':rem,'orsak':reason,'legacy_source_sha256':r['legacy_source_sha256']})
 counts={k:sum(q['V2_status']==k for q in out) for k in sorted({q['V2_status'] for q in out})};payload={'matrix_id':'LEGACY_V2_EXACT_DIFFERENCE_46_PRE_BATCH3','source_registry_sha256':__import__('hashlib').sha256(REG.read_bytes()).hexdigest(),'source_scripts':420,'replicate_now_original':46,'rows':out,'status_counts':counts,'remaining_tests':[q['legacy_test'] for q in out if q['återstår_ja_nej']=='ja'],'legacy_results_used_as_evidence':False}
 OUT.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print(json.dumps({'rows':len(out),'counts':counts,'remaining':payload['remaining_tests']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
