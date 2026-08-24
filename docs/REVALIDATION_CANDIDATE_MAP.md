# REVALIDATION CANDIDATE MAP

Datum: 2026-08-18 · Status: **KARTLÄGGNING KLAR — INGA TESTER KÖRDA**

Underlag: `research_inventory/master_test_ledger.json` (803 tester).
Datakonsumtionen är **läst ur koden** med transitiv importupplösning (53 skript importerar
`stack_h_motor`, 46 importerar `h1419_motor` — deras laddningar räknas som konsumtion),
inte gissad ur filnamn. Inga domar ändrade, ingen champion rörd, inga tester körda.

---

## SLUTSIFFROR

| | |
|---|---|
| TOTALT | **803** |
| UNAFFECTED | **70** |
| DIRECTLY_AFFECTED | **198** |
| STRUCTURALLY_AFFECTED | **86** |
| POSSIBLY_AFFECTED | **401** |
| UNKNOWN | **48** |

| Prioritet | Antal |
|---|---|
| P0 | **60** |
| P1 | 118 |
| P2 | 230 |
| P3 | 325 |

**Antal som säkert kan exkluderas från revalidering: 70** (8,7 %). Alla 70 bär explicit
positiv evidens: 57 producerar ingen forskningsslutsats alls (inga prestanda- eller
IC-mått i koden — de hämtar, parsar, fryser eller verifierar), och 13 är byggda **på** den
nya datan, där förändringen är deras indata och inte ett hot mot slutsatsen.

Nio kandidater som först föll ut som UNAFFECTED **återfördes** till STRUCTURALLY_AFFECTED:
deras slutsats *handlar om* en komponent som sedan ersatts — `spark_avanza_sector_recovery_qa`
bedömer den statiska sektorkällan, `build_delisted_pit_features_niva3` bedömer prisserier
som byggts om, `instrument_master_v2` / `verify_universe_mapping` / `skatteverket_universe` /
`build_omx30_pit` / `point_in_time_registry` definierar universum, och två filer transkriberar
metrikvärden från beräkningar som vilar på den gamla baslinjen.

---

## DATAFÖRÄNDRINGSREGISTER (verifierat, inte antaget)

| id | Förändring | Datum | Materialitet | Verifierat underlag | Tester |
|---|---|---|---|---|---|
| DC7 | H0 V3 PIT-medlemskap | 2026-08-18 | **MATERIAL_BASELINE** | 2014-2019: 3 071/21 896 rankade rader (14,0 %) och 530/2 370 Top-30-rader (22,4 %) kontaminerade; **alla 79 paneler ändrade**, i snitt 13,29 av 30 namn. 2020-2026: 1 147/23 293 (4,9 %), 112/1 980 Top-30 (5,7 %), 51 paneler, 3,42 namn | 120 |
| DC4 | Justeringsbrott **ej åtgärdade** | 2026-08-15 | PENDING_DEFECT | 8 brott / 64 rader diagnostiserade (R4, ±5 dagar). Kanonfilen har fortfarande 581 115 rader; **ingen fil i repot har 581 051**. ATORX, BEIJ-B, BETS-B, PNDX-B, QLINEA, SAS, SSAB-A, VBG-B | 164 |
| DC3 | H1419-prisryggrad | 2026-08-15 | ENABLING_NEW_WINDOW | Nytt 2014-2019-lager; fanns inte tidigare | 102 |
| DC9 | repair_df exekvering/lookahead | 2026-08-09 | MATERIAL_EXECUTION | fryst manifest | 90 |
| DC8 | N3S-priskontaminering ombyggd | 2026-08-03 | MATERIAL_HISTORICAL (legacy) | sentinel 999999,9999; endagsspikar +1 175 % / +794 %; bruten bakåtjustering i 7 namn | 83 |
| DC5 | Nasdaq PIT ICB | 2026-08-18 | MATERIAL_HISTORICAL | statisk etikett (0/420 med >1 intervall) → 176/756 byter industry, 398/756 supersector | 26 |
| DC6 | Nasdaq PIT-segment | 2026-08-18 | MATERIAL_HISTORICAL | Avanza-ögonblicksbild → 201 månaders PIT-segment | 21 |
| DC1 | Fundamenta, valutabugg | 2026-08-08 | MATERIAL_HISTORICAL | **9,4–10,1 % av posterna ändrade, magnitud ~9×** (442/4 691 år, 336/3 334 kvartal, 338/3 340 r12) | 15 |
| DC10 | KPI-arrayer tillagda | 2026-08-13 | ENABLING_NEW_DATA | ny värderings-/kvalitetsdata | 8 |
| DC2 | Priser v1.1 | 2026-08-13 | **NON_MATERIAL** | 420/420 tickers **ren framåtförlängning** 2026-07-24 → 2026-08-12; **0 historiska punkter ändrade** | 2 |

**Störst spridning:** DC4 (164 tester), DC7 (120), DC3 (102), DC9 (90), DC8 (83).
**Störst genomslag per test:** DC7 — i 2014-2019 ändras varenda panels Top-30 med i snitt
13,29 av 30 namn. Inget annat i registret är i närheten.

### Två fynd som ändrar bilden

**Priserna har inte reparerats.** Jag utgick från att prislagret ändrats 2026-08-16 (mtime),
men filen är **byte-identisk** med säkerhetskopian från 2026-08-15, och v1.1 är en ren
framåtförlängning utan en enda ändrad historisk punkt. Prisdriven historik är alltså
**inte** påverkad av någon prisreparation — den är påverkad av universumbytet (DC7).

**Justeringsrättelsen är inte tillämpad.** Rapporten `RATTELSE_JUSTERINGSBROTT_V1` anger
581 051 rader efter rättelse. Kanonfilen har 581 115, alla åtta brottens ±5-dagarsspann
ligger kvar, och ingen fil i repot har 581 051 rader. Tidsordningen är: säkerhetskopia
23:28:44 → rapport 23:29:11 (2026-08-15) → kanonfilen skriven 2026-08-16 17:49 med
förkontrollerat innehåll. Detta är en **oåtgärdad känd defekt**, inte en genomförd
förändring, och driver därför inte DIRECTLY_AFFECTED — men den höjer prioritet och är en
öppen epistemisk lucka.

---

## PRIORITERINGSMODELL

`priority_score` = p_change + change_magnitude + window_1419 + champion_proximity
+ research_value + verdict_uncertainty + reproducibility + cost_bonus

| Komponent | Skala | Motivering |
|---|---|---|
| p_change | DIRECTLY 35 · STRUCTURALLY 25 · POSSIBLY 12 · UNKNOWN 8 | sannolikhet att slutsatsen ändras |
| change_magnitude | 0–20 efter materialitet | storlek på dataförändringen |
| window_1419 | +8 | 2014-2019 är fönstret där *alla* paneler ändrades |
| champion_proximity | 15 om baslinjekomponent konsumeras, annars 10/3 | närhet till champion |
| research_value | 2–18 efter exekveringsstatus + nära-tröskel-familj | historiskt forskningsvärde |
| verdict_uncertainty | UNKNOWN 10 · MIXED 8 · POSITIVE 6 · NEGATIVE 4 · BLOCKED 2 | osäkerhet i historisk dom |
| reproducibility | P5 10 · P4 8 · P3 6 · P2 3 · P1 0 | reproducerbarhet |
| cost_bonus | LOW 8 · MEDIUM 4 · HIGH 0 | kostnad att köra om |

Trösklar: **P0 ≥ 104, P1 ≥ 84, P2 ≥ 53, P3 < 53.** Kostnadsfördelning: 227 LOW, 386 MEDIUM,
120 HIGH.

P0 per familj: DRAWDOWN_EXIT 8 · FUNDAMENTAL 6 · PATH_STATE_MEMORY 5 · PORTFOLIO_WEIGHT 4 ·
ROBUSTNESS_ABLATION 4 · COMBINATION_STACK 3 · EVENT_PEAD 3 · H0_BASELINE 3 ·
INDEX_MEMBERSHIP 3 · VOLATILITY_RISK 3 · MOMENTUM_LOOKBACK 2 · RANKING 2 ·
REBALANCE_TIMING 2 · SECTOR 2 · SIZE_SEGMENT 2 · nio familjer med 1 vardera.

---

## TOPP 50 FÖR FRAMTIDA REVALIDERING

| # | Poäng | Familj | Test | Klass | Dataförändringar | Kostnad | Reproducerbarhet |
|---|---|---|---|---|---|---|---|
| 1 | 120 | SECTOR | `test_healthcare_ablation` | DIRECTLY | DC3,DC5,DC7 | LOW | INPUTS_IDENTIFIED |
| 2 | 116 | DRAWDOWN_EXIT | `h0_core_meta_exit` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 3 | 116 | DRAWDOWN_EXIT | `h0_exit_interaction_explorer` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 4 | 116 | DRAWDOWN_EXIT | `h0_exit_model_time_split` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 5 | 116 | DRAWDOWN_EXIT | `h0_exit_pattern_explorer` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 6 | 116 | DRAWDOWN_EXIT | `h0_lgbm_consensus_exit` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 7 | 116 | DRAWDOWN_EXIT | `h0_temporary_exit_guard` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 8 | 116 | SIZE_SEGMENT | `k1_material_validation` | DIRECTLY | DC3,DC5,DC7 | LOW | FULLY_REPRODUCIBLE |
| 9 | 114 | EVENT_PEAD | `fi_blankning_signal` | DIRECTLY | DC3,DC4,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 10 | 114 | EVENT_PEAD | `tidig_detektion_och_utdelning` | DIRECTLY | DC3,DC4,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 11 | 114 | INDEX_MEMBERSHIP | `h1419_steg2_universum` | DIRECTLY | DC3,DC4,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 12 | 113 | DRAWDOWN_EXIT | `g13_g17_premature_exit_audit` | DIRECTLY | DC3,DC4,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 13 | 113 | RANKING | `spar_c_features_fundamenta` | DIRECTLY | DC1,DC4,DC9 | LOW | INPUTS_IDENTIFIED |
| 14 | 113 | VOLATILITY_RISK | `g97p_confounder_audit` | DIRECTLY | DC3,DC4,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 15 | 112 | RANKING | `spar_c_target` | DIRECTLY | DC4,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 16 | 112 | SECTOR | `spark_k1_sector_information_diversification` | DIRECTLY | DC4,DC5,DC7 | LOW | INPUTS_IDENTIFIED |
| 17 | 112 | VOLATILITY_RISK | `g97p_hogvolsvans` | STRUCTURALLY | DC3,DC7 | LOW | FULLY_REPRODUCIBLE |
| 18 | 110 | BREADTH_DISPERSION | `dispersion_och_ensemble` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 19 | 110 | CHAMPION_CHALLENGER | `h0_validator_model_race_1419` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 20 | 110 | COMBINATION_STACK | `spari_batch2` | DIRECTLY | DC4,DC7,DC9 | LOW | FULLY_REPRODUCIBLE_PRE |
| 21 | 110 | FUNDAMENTAL | `g129_asset_growth` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 22 | 110 | FUNDAMENTAL | `lonsamhetstilt_mot_stack_h` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 23 | 110 | H0_BASELINE | `h0_extratrees_topn_1419` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 24 | 110 | MOMENTUM_LOOKBACK | `kortare_lookback` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 25 | 110 | MOMENTUM_LOOKBACK | `momentumkurvan` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 26 | 110 | REENTRY | `h0_reentry_score_improvement` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 27 | 109 | FUNDAMENTAL | `h0_extratrees_broad_pool_top30_audit` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 28 | 109 | FUNDAMENTAL | `h0_extratrees_top20_portfolio_value_audit` | DIRECTLY | DC3,DC4,DC7,DC9 | MEDIUM | INPUTS_IDENTIFIED |
| 29 | 109 | FUNDAMENTAL | `spark_k5_k3_diagnostics` | DIRECTLY | DC4,DC7,DC9 | LOW | FULLY_REPRODUCIBLE_PRE |
| 30 | 108 | FORWARD_HOLDOUT | `sparh_forward` | DIRECTLY | DC1,DC4,DC7 | LOW | FULLY_REPRODUCIBLE |
| 31 | 107 | DATA_QA_PROVENANCE | `build_research_provenance_archive` | DIRECTLY | DC3,DC4,DC5,DC6,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 32 | 107 | INDEX_MEMBERSHIP | `h1419_universum_v2` | DIRECTLY | DC3,DC4,DC7,DC9 | LOW | FULLY_REPRODUCIBLE |
| 33 | 106 | DRAWDOWN_EXIT | `g_het_1_analysis` | DIRECTLY | DC3,DC4,DC5,DC6 | LOW | INPUTS_IDENTIFIED |
| 34 | 106 | FUNDAMENTAL | `lonsamhet_poangfaktor_och_kvot` | STRUCTURALLY | DC3,DC7 | MEDIUM | INPUTS_IDENTIFIED |
| 35 | 106 | ROBUSTNESS_ABLATION | `spark_h0_historical_time_stability` | DIRECTLY | DC4,DC7,DC9 | LOW | INPUTS_IDENTIFIED |
| 36 | 106 | VOLATILITY_RISK | `h_archetype_1_tail_distribution` | DIRECTLY | DC3,DC4,DC5 | LOW | INPUTS_IDENTIFIED |
| 37 | 104 | CANDIDATE_FILTER | `skarpare_ranking` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 38 | 104 | COMBINATION_STACK | `h1_contrarian_exposure` | STRUCTURALLY | DC3,DC4,DC7 | LOW | INPUTS_IDENTIFIED |
| 39 | 104 | COMBINATION_STACK | `stack_h_repaired_h012` | STRUCTURALLY | DC3,DC4,DC7 | LOW | INPUTS_IDENTIFIED |
| 40 | 104 | EVENT_PEAD | `pead_eget_spar` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 41 | 104 | H0_BASELINE | `h0_h1_h2_tvafonster` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 42 | 104 | H0_BASELINE | `h1419_forregistrering` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 43 | 104 | INDEX_MEMBERSHIP | `g186k_enb_kalibrering` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 44 | 104 | LIQUIDITY_EXECUTION | `g216_execution_decay` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 45 | 104 | PATH_STATE_MEMORY | `g101_regimberoende` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 46 | 104 | PATH_STATE_MEMORY | `g67_g74_banans_form` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 47 | 104 | PATH_STATE_MEMORY | `g_path_1_time_in_state` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 48 | 104 | PATH_STATE_MEMORY | `mem_r_recovery_memory` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 49 | 104 | PATH_STATE_MEMORY | `state_path_feasibility` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |
| 50 | 104 | PORTFOLIO_WEIGHT | `a3_poangutjamning` | STRUCTURALLY | DC3,DC7 | LOW | INPUTS_IDENTIFIED |

---

## KVARVARANDE EPISTEMISKA LUCKOR

**1. Domen är inte återställbar per test.** 59 av 803 har en maskinläsbar dom i sin
artefakt. 501 får sin dom från familjeregister — det är en familjedom, inte en testdom —
och för 243 finns ingen återställbar dom alls. En revalidering kan därför i de flesta fall
inte jämföras mot vad testet faktiskt kom fram till, bara mot vad familjen kom fram till.

**2. 401 tester (50 %) är POSSIBLY_AFFECTED, inte skarpare.** 327 har `dependency_confidence`
LOW eftersom de laddar data via `config`/`data_loader` i legacy-trädet i stället för via
namngivna sökvägar. Deras faktiska datakonsumtion kan bara fastställas genom att köra dem —
vilket detta uppdrag inte gör.

**3. Två prislinjer, inte en.** 253 legacy-skript importerar `config` med
`PRICE_DATA_SOURCE = "borsdata_total_return"` mot `momentum_prod_work/cache/` (3 550
börsdata-filer, 1 062 MFN-filer). v2 använder `validated/prices`. Inget legacy-skript läser
v2-data. v2:s reparationer rör alltså inte legacy, och DC8 rör inte v2. Om de två linjerna
ska jämföras måste ekvivalensen först fastställas — den är inte fastställd.

**4. Justeringsdefekten är kvantifierad men inte lokaliserad.** Vi vet att åtta namn har
brott vid givna datum. Vi vet **inte** om dessa namn låg i topp-30 vid brottsdatumen. Tills
det är avgjort kan påverkan på portföljresultat varken bekräftas eller uteslutas — därför
POSSIBLY_AFFECTED och inte något skarpare för de 164.

**5. 48 UNKNOWN.** Varken identifierad datakonsumtion eller lokaliserad artefakt. De kan
inte klassas — och får enligt uppdragets regel inte klassas som UNAFFECTED.

**6. `momentum_v2` saknar versionshantering.** Dateringen för 581 av 803 tester vilar på
mtime. Om en fil rörts utan innehållsändring — vilket bevisligen skett med prislagret
2026-08-16 — är ordningen mellan test och dataförändring osäker. Fältet `date_basis` bär
detta per rad.

**7. Materialiteten är uppmätt på datan, inte på utfallet.** Att 10 % av fundamentaposterna
ändrades med faktor 9 säger att indata ändrats materiellt. Det säger ingenting om hur mycket
slutsatsen rör sig. Att avgöra det kräver omkörning, vilket ligger utanför detta uppdrag.

---

## LEVERANS

`research_inventory/revalidation_candidate_map.json` — 803 rader med samtliga begärda fält,
inbäddat dataförändringsregister och poängkomponenter per test.
