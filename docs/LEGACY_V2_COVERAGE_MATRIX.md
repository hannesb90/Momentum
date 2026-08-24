# LEGACY_V2_COVERAGE_MATRIX — slutlig 46/46

Legacyprogrammet är **STOPPAT och komplett**. Batch 3 gav inget stöd för ROA eller korrelationsrefill och skapade ingen ny forward-challenger.

## Summering

| Mått | Antal |
|---|---:|
| ursprungliga_REPLIKERA_NU | 46 |
| redan_besvarade_DG | 1 |
| batch1 | 8 |
| batch2 | 3 |
| data_blockerade | 14 |
| definitions_blockerade | 4 |
| duplicerade | 14 |
| faktiskt_kvarvarande_fore_batch3 | 2 |
| batch3_tester | 2 |
| kvarvarande_efter_batch3 | 0 |
| resultatgranskade_varianter_Research_I | 16 |

## Exakt differens för alla 46

| # | legacy_test | ekonomisk_hypotes | familj | V2_status | var_testad | resultat | återstår | orsak |
|---:|---|---|---|---|---|---|---|---|
| 1 | `run_armed_takeprofit_state_machine_stage38.py` | Armed take-profit after sector-relative strength and subsequent drawdown/rank decay | armed exit | KAN INTE TESTAS — DATA SAKNAS | — | No PIT-defensible historical sector state; drawdown/trend/rank exit legs already covered | nej | No PIT-defensible historical sector state; drawdown/trend/rank exit legs already covered |
| 2 | `run_armed_technical_exit_stage41.py` | Sector-armed trend/rank exit | armed exit | KAN INTE TESTAS — DATA SAKNAS | — | PIT sector history is unavailable; unarmed trend/rank exits were answered in F | nej | PIT sector history is unavailable; unarmed trend/rank exits were answered in F |
| 3 | `run_cash_alternative_after_exit_current.py` | Cash versus market replacement after technical exit | post-exit allocation | DUPLIKAT/SAMMA HYPOTES | Spår F / Batch 2 | No supported technical exit survived; cash/gate risk control already covered | nej | No supported technical exit survived; cash/gate risk control already covered |
| 4 | `run_cause_specific_reentry_current.py` | Exit-cause-specific cooldown/re-entry | re-entry | KAN INTE TESTAS — DATA SAKNAS | — | Frozen H0 history lacks a mutually exclusive PIT exit-cause ledger | nej | Frozen H0 history lacks a mutually exclusive PIT exit-cause ledger |
| 5 | `run_correlation_refill_stage119.py` | Refill correlation-rejected slots with next ranked diversifying candidate | correlation allocation | FORTFARANDE MOTIVERAD ATT TESTA | Research I Batch 3 | TESTAD PÅ V2 BATCH 3 — INGET STÖD | nej | Distinct diversification mechanism; adjusted-close history is sufficient |
| 6 | `run_drawdown_rank_confirmed_exit_current.py` | Exit only when drawdown and rank deterioration agree | combined exit | DUPLIKAT/SAMMA HYPOTES | Spår F / Batch 2 | Combination of separately answered drawdown and rank-exit legs; legacy used a parameter grid | nej | Combination of separately answered drawdown and rank-exit legs; legacy used a parameter grid |
| 7 | `run_fundamental_residual_to_roa_current.py` | Profitability quality beyond price momentum | fundamental quality | FORTFARANDE MOTIVERAD ATT TESTA | Research I Batch 3 | TESTAD PÅ V2 BATCH 3 — INGET STÖD | nej | QA-approved PIT roa_ttm exists; raw ROA is testable without inventing PIT sector neutralization |
| 8 | `run_quality_momentum_neutralized_current.py` | Trend quality adds to momentum | momentum quality | BESVARAD BATCH 1 | Research I Batch 1 | Drawdown resilience, trend strength, weekly consistency and jump diffuseness tested | nej | Drawdown resilience, trend strength, weekly consistency and jump diffuseness tested |
| 9 | `run_reentry_threshold_canonical_stage116.py` | Require rank recovery before re-entry | re-entry | KAN INTE REPLIKERAS ENTydigt | Batch 2 inventory | Several incompatible 0/5/10pp and MA-unlock definitions; choosing one is new research | nej | Several incompatible 0/5/10pp and MA-unlock definitions; choosing one is new research |
| 10 | `run_sizing_decomposition_stage120.py` | Decompose diversification benefit from sizing | sizing | BESVARAD BATCH 1 | Research I Batch 1 | Inverse-vol sizing and target-vol tested with frozen H0 selection | nej | Inverse-vol sizing and target-vol tested with frozen H0 selection |
| 11 | `run_small_sizing_isolation_s11.py` | Volatility-based position sizing | sizing | BESVARAD BATCH 1 | Research I Batch 1 | Same economic inverse-vol/vol-target family | nej | Same economic inverse-vol/vol-target family |
| 12 | `run_small_sizing_rerun_s19.py` | Volatility-based position sizing rerun | sizing | DUPLIKAT/SAMMA HYPOTES | Research I Batch 1 | Rerun of same sizing family | nej | Rerun of same sizing family |
| 13 | `tune_anchor_exit.py` | Expected-return-anchored early exit | model-conditioned exit | KAN INTE TESTAS — DATA SAKNAS | — | Requires legacy calibrated probability/expected-return state not present in frozen H0 | nej | Requires legacy calibrated probability/expected-return state not present in frozen H0 |
| 14 | `tune_asymmetric_exit.py` | SMA trend exit | trend exit | REDAN BESVARAD I V2 | Spår F F7 | Absolute trend-break exit tested; nearby SMA lengths are parameter variants | nej | Absolute trend-break exit tested; nearby SMA lengths are parameter variants |
| 15 | `tune_attention_gap.py` | Weak attention/initial report reaction predicts drift | report/attention/PEAD | KAN INTE TESTAS — DATA SAKNAS | Batch 1 data gate | No QA-approved event timestamp/reaction/volume chain | nej | No QA-approved event timestamp/reaction/volume chain |
| 16 | `tune_combined_exit_2026_08_04.py` | Combine momentum/rank deterioration with drawdown floor | combined exit | DUPLIKAT/SAMMA HYPOTES | Spår F / Batch 2 | Combination of answered exit legs, not independent information | nej | Combination of answered exit legs, not independent information |
| 17 | `tune_combined_exits.py` | Combine trend and ATR exits | combined exit | KAN INTE TESTAS — DATA SAKNAS | — | ATR/high-low chain is not QA-approved; trend leg already answered | nej | ATR/high-low chain is not QA-approved; trend leg already answered |
| 18 | `tune_correlation_filter_freq.py` | Measure/use pairwise-correlation filtering | correlation allocation | DUPLIKAT/SAMMA HYPOTES | Batch 3 family | Same economic family as correlation refill; one fixed replication only | nej | Same economic family as correlation refill; one fixed replication only |
| 19 | `tune_dd20_hold_kombo_2026_08_05.py` | Combine DD20 with signal-streak holding rule | combined exit | DUPLIKAT/SAMMA HYPOTES | Batch 2 | DD20 answered; exact weekly streak is data-blocked; combination forbidden | nej | DD20 answered; exact weekly streak is data-blocked; combination forbidden |
| 20 | `tune_dd20_robustness_2026_08_04.py` | Individual 20% drawdown exit | drawdown exit | BESVARAD BATCH 2 | Research I Batch 2 | Exact DD20 legacy replication received INGET STÖD | nej | Exact DD20 legacy replication received INGET STÖD |
| 21 | `tune_dispersion_proxy.py` | Price-signal dispersion describes momentum regimes | regime diagnostic | BESVARAD BATCH 1 | Research I Batch 1 | Tested explicitly as price proxy, not analyst dispersion | nej | Tested explicitly as price proxy, not analyst dispersion |
| 22 | `tune_exit_2026_08_06.py` | Rank hysteresis and exit candidates | exit grid | DUPLIKAT/SAMMA HYPOTES | Spår F / Batch 2 | Grid of nearby rank/trend/drawdown/milestone variants already economically answered | nej | Grid of nearby rank/trend/drawdown/milestone variants already economically answered |
| 23 | `tune_graded_exit_2026_08_04.py` | Graded absolute/relative trend exit | trend exit | DUPLIKAT/SAMMA HYPOTES | Spår F F7 / Batch 2 | Same trend-loss and risk-exit information with different staging | nej | Same trend-loss and risk-exit information with different staging |
| 24 | `tune_hold_forever.py` | Long-horizon persistence of buy signals | holding horizon | KAN INTE TESTAS — DATA SAKNAS | — | Requires new 2–3 year targets/cohorts outside frozen 52w target contract | nej | Requires new 2–3 year targets/cohorts outside frozen 52w target contract |
| 25 | `tune_hold_forever_fundamentals.py` | Fundamentals identify multi-year winners among signals | fundamental long horizon | KAN INTE TESTAS — DATA SAKNAS | — | Requires unfrozen 2–3 year target and has severe fundamental survivorship | nej | Requires unfrozen 2–3 year target and has severe fundamental survivorship |
| 26 | `tune_hold_streak_2026_08_05.py` | Exit when weekly signal streak breaks | streak | KAN INTE TESTAS — DATA SAKNAS | Batch 2 gate | Exact weekly signal history is absent from frozen 4-week V2 panel | nej | Exact weekly signal history is absent from frozen 4-week V2 panel |
| 27 | `tune_individual_drawdown_floor.py` | Individual drawdown floor | drawdown exit | DUPLIKAT/SAMMA HYPOTES | Research I Batch 2 | Same DD-floor hypothesis; threshold difference is not new information | nej | Same DD-floor hypothesis; threshold difference is not new information |
| 28 | `tune_individual_drawdown_floor_rotate.py` | Drawdown exit with immediate ranked replacement | drawdown exit | BESVARAD BATCH 2 | Research I Batch 2 | DD20 replication used immediate ranked replacement | nej | DD20 replication used immediate ranked replacement |
| 29 | `tune_individual_voltarget_2026_08_04.py` | Individual volatility targeting | risk allocation | DUPLIKAT/SAMMA HYPOTES | Research I Batch 1 | Inverse-vol and target-vol covered the risk-allocation hypothesis | nej | Inverse-vol and target-vol covered the risk-allocation hypothesis |
| 30 | `tune_ingang_streak_2026_08_05.py` | Require persistent weekly signal before entry | streak | KAN INTE TESTAS — DATA SAKNAS | Batch 2 gate | Exact weekly signal streak cannot be reconstructed without approximation | nej | Exact weekly signal streak cannot be reconstructed without approximation |
| 31 | `tune_malexit_2026_08_06.py` | Exit non-delivering position at half horizon | milestone exit | BESVARAD BATCH 2 | Research I Batch 2 | 26-week absolute milestone tested and received INGET STÖD | nej | 26-week absolute milestone tested and received INGET STÖD |
| 32 | `tune_malexit_placebo_2026_08_06.py` | Placebo validation of milestone exit | milestone exit | DUPLIKAT/SAMMA HYPOTES | Research I Batch 2 | Diagnostic of same 26w milestone, not a distinct hypothesis | nej | Diagnostic of same 26w milestone, not a distinct hypothesis |
| 33 | `tune_pead.py` | Post-earnings announcement drift | report/attention/PEAD | KAN INTE TESTAS — DATA SAKNAS | Batch 1 data gate | No QA-approved PIT publication/reaction chain | nej | No QA-approved PIT publication/reaction chain |
| 34 | `tune_quality_momentum_interact.py` | Interact momentum with trend quality | momentum quality | BESVARAD BATCH 1 | Research I Batch 1 | Fixed 50/50 H0 blends with quality factors tested; H1/H2 frozen separately | nej | Fixed 50/50 H0 blends with quality factors tested; H1/H2 frozen separately |
| 35 | `tune_reentry_threshold_production.py` | Rank-improvement threshold before re-entry | re-entry | KAN INTE REPLIKERAS ENTydigt | Batch 2 inventory | Legacy grid 0/5/10pp and no unique preregistered value | nej | Legacy grid 0/5/10pp and no unique preregistered value |
| 36 | `tune_refill_discount.py` | Rebuy exited name after a fixed price discount | re-entry | KAN INTE REPLIKERAS ENTydigt | — | Depends on legacy sellwatch state and a 5/10/15/20% grid; no unique rule | nej | Depends on legacy sellwatch state and a 5/10/15/20% grid; no unique rule |
| 37 | `tune_report_crowding.py` | Report crowding/attention changes drift | report/attention/PEAD | KAN INTE TESTAS — DATA SAKNAS | Batch 1 data gate | Required PIT report-event and attention data absent | nej | Required PIT report-event and attention data absent |
| 38 | `tune_report_dip_reversal.py` | Report dip followed by reversal/drift | report/attention/PEAD | KAN INTE TESTAS — DATA SAKNAS | Batch 1 data gate | Required event timestamp and initial-reaction window absent | nej | Required event timestamp and initial-reaction window absent |
| 39 | `tune_resid_mom_ic.py` | Residual momentum adds stock-specific information | residual momentum | BESVARAD BATCH 1 | Research I Batch 1 | Solo and fixed H0 blend tested | nej | Solo and fixed H0 blend tested |
| 40 | `tune_sizing.py` | Alternative position sizing | sizing | BESVARAD BATCH 1 | Research I Batch 1 | Inverse-vol sizing tested as risk, not alpha | nej | Inverse-vol sizing tested as risk, not alpha |
| 41 | `tune_sizing_korr_2026_08_04.py` | Correlation-aware sizing | sizing/correlation | DUPLIKAT/SAMMA HYPOTES | Batch 1 / Batch 3 family | Sizing answered; remaining correlation-selection question consolidated into one Batch 3 family | nej | Sizing answered; remaining correlation-selection question consolidated into one Batch 3 family |
| 42 | `tune_sizing_niva2_stage4.py` | Alternative position sizing | sizing | DUPLIKAT/SAMMA HYPOTES | Research I Batch 1 | Same economic sizing family | nej | Same economic sizing family |
| 43 | `tune_streak_2026_08_04.py` | Persistent candidate signal plus underperforming holding swap | streak | KAN INTE TESTAS — DATA SAKNAS | Batch 2 gate | Requires weekly signal streak unavailable in frozen V2 | nej | Requires weekly signal streak unavailable in frozen V2 |
| 44 | `tune_takeprofit.py` | Take-profit/armed sellwatch gap | take-profit exit | KAN INTE REPLIKERAS ENTydigt | — | Legacy searches 30/40/50/60/80% gaps; no unique fixed economic parameter | nej | Legacy searches 30/40/50/60/80% gaps; no unique fixed economic parameter |
| 45 | `tune_voltarget.py` | Portfolio volatility target | risk allocation | BESVARAD BATCH 1 | Research I Batch 1 | Fixed 10% no-leverage target-vol tested | nej | Fixed 10% no-leverage target-vol tested |
| 46 | `tune_voltarget_addon_2026_08_04.py` | Volatility-target add-on | risk allocation | DUPLIKAT/SAMMA HYPOTES | Research I Batch 1 | Same target-vol economic hypothesis | nej | Same target-vol economic hypothesis |

## Batch 3

### ROA / profitability quality — INGET STÖD

På exakt ROA-täckningsmatchad population föll mean IC från 0,1525 till 0,1365 (Δ −0,0160), median IC Δ −0,0336 och Top-30 IC Δ −0,0986. Challenger-CAGR var 15,86 % mot 27,01 % för täckningsmatchad H0. Populationen hade 8 584 rader, 340 instrument och **0 terminalinstrument med ROA**. Resultatet är både negativt och kraftigt survivorshipbegränsat.

### Correlation refill 0,85 — INGET STÖD

Regeln var testbar men band inte under OOS: inga Top-30-kandidater överskred 0,85 mot redan valda namn. Rankings, holdings och samtliga portföljmått blev därför identiska med H0. Ingen närliggande tröskel testades.

## Fortsatt blockerad data

Report/attention/PEAD, dividend-gap och insider-gap är otestade på grund av saknad QA-godkänd PIT-eventdata. ATR/high-low är fortsatt blockerad. Detta är inte negativa resultat.

## Avslut

Varje av de 46 relevanta `REPLIKERA NU`-posterna är nu testad, täckt av ett annat V2-test, blockerad av data/definition eller bedömd som ekonomisk dubblett. Ingen Batch 4 skapas. Framtida idéer ska separeras som **NY FORSKNING**. H0/H1/H2 fortsätter oförändrade.
