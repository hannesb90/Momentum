# DATA FOUNDATION CLOSEOUT

Datum: 2026-08-19 · Status: **REVALIDATION_FOUNDATION_BLOCKED**

Inga forskningstester körda. Inga historiska domar ändrade. Ingen champion rörd.
Inga frysta artefakter överskrivna — allt nytt ligger i nya, versionsstyrda filer.

---

## STEG 1 — RÄTTELSE_JUSTERINGSBROTT_V1

### Verifiering av de 8 brotten

Samtliga åtta hämtade ur `research_k/rundresetest_produktionslagret_results.json`
(`klassificering == JUSTERINGSFEL`) och kontrollerade mot EODHD-råarkivet
(1 704 instrument). Alla åtta uppfyller kriteriet `|ret(adj) − ret(close)| > 0,15`.
Inga dubbletter, alla serier sorterade, inga luckor och inga ogiltiga värden i
±5-handelsdagarsfönstret.

| Kod | Datum | close | adj | Divergens | Justeringsfaktor |
|---|---|---|---|---|---|
| ATORX | 2025-01-24 | −69,5 % | +260,8 % | +3,3025 | 0,0421 → 0,0036 (11,83×) |
| QLINEA | 2025-01-13 | −69,6 % | +115,0 % | +1,8456 | 0,0076 → 0,0011 (7,07×) |
| SAS | 2020-09-29 | −60,6 % | +45,7 % | +1,0624 | 3,6957 → 1,0000 |
| PNDX-B | 2020-04-06 | +6,8 % | +95,1 % | +0,8832 | 2,0094 → 1,0998 |
| VBG-B | 2020-04-29 | −2,2 % | +50,1 % | +0,5225 | 1,7983 → 1,1722 |
| SSAB-A | 2020-04-02 | −3,2 % | +44,3 % | +0,4752 | 2,1150 → 1,4184 |
| BETS-B | 2022-05-13 | +3,2 % | +45,9 % | +0,4273 | 1,7848 → 1,2623 |
| BEIJ-B | 2020-04-17 | +6,1 % | +44,9 % | +0,3882 | 5,7912 → 4,2398 |

### Korsvalidering mot oberoende corporate-action-källa

`momentum_prod_work/results/point_in_time/corporate_actions.csv` (Skatteverket
Aktiehistorik, 5 478 rader). **Fyra av åtta bekräftade på exakt datum:**

- **ATORX** 2025-01-24 `new_issue` — "N 37 unit:10, kurs 0,1 kr"
- **QLINEA** 2025-01-13 `new_issue` — "N 77 unit:4, kurs 0,10 kr"
- **SAS** 2020-09-29 `new_issue` — "N 9:1, kurs 1,16 kr"
- **BETS-B** 2022-05-18 `split` — "Split+Inlösen, S 2:1, inlösen 1,97 kr" (5 dagar efter)

Fyra saknar händelse inom ±15 dagar: BEIJ-B, PNDX-B, SSAB-A, VBG-B — alla i april
2020. EODHD-arkivet saknar split- och utdelningsfält helt (endast OHLCV +
`adjusted_close`), så orsaken kan inte fastställas ur källan.

### Reproduktion

`tools/build_validated_prices.py` kördes med omdirigerad `OUT`/`MANIFEST` mot
`validated/prices_v2_0/`. Frysta filer orörda.

| | |
|---|---|
| Målvärde | 581 051 rader |
| Byggt | **581 051 rader** |
| Match | **exakt** |
| SHA256 | `904f606fd5c9054c47993d0fefbd8becff5f9a006b674a862071f3b1eb3548ba` |
| Borttagna rader | 64 (0 tillagda, 0 ändrade värden) |
| Instrument | exakt de 8, inga sidoeffekter |

Spann per instrument: PNDX-B 9, QLINEA 9, ATORX 8, BETS-B 8, SAS 8, SSAB-A 8,
BEIJ-B 7, VBG-B 7.

### BLOCKERARE B1 — R4 åtgärdar inte defekten

Radantalet stämmer exakt. Rättelsen löser ändå inte det den riktar sig mot.

Defekten är en **permanent ändring av justeringsfaktorn**. Att utesluta dagar
omkring den kan per konstruktion aldrig ta bort den: serien hoppar från sista
behållna dagen före spannet till första efter, och faktorn skiljer fortfarande.

**Alla 8 brott överlever.** Divergensen flyttas till spannets kant:

| Kod | Före | Efter | Divergens före → efter |
|---|---|---|---|
| ATORX | 2025-01-24 | 2025-01-30 | +3,3025 → +1,7550 |
| QLINEA | 2025-01-13 | 2025-01-20 | +1,8456 → **+1,9350** |
| SAS | 2020-09-29 | 2020-10-05 | +1,0624 → **+1,0899** |
| PNDX-B | 2020-04-06 | 2020-04-14 | +0,8832 → **+0,9471** |
| VBG-B | 2020-04-29 | 2020-05-05 | +0,5225 → **+0,5300** |
| SSAB-A | 2020-04-02 | 2020-04-08 | +0,4752 → +0,4838 |
| BETS-B | 2022-05-13 | 2022-05-19 | +0,4273 → +0,4088 |
| BEIJ-B | 2020-04-17 | 2020-04-23 | +0,3882 → +0,3138 |

Fem av åtta blir **starkare** efter åtgärd. SAS konkret: faktor 3,6957 → 1,0000;
v1.0 bryter 2020-09-29, v2.0 bryter 2020-10-05 med större divergens.

BETS-B och BEIJ-B ser ut att försvinna i detektorn — de faller precis under
40 %-grinden (BETS-B ret(adj) = +39,6 %). Åtgärdat i detektorn, inte i datan.

Giltiga åtgärder: skala om historiken med faktorkvoten, dela serien vid brottet
(R8 finns redan i byggaren), eller trunkera. Ingen av dem är R4.

---

## STEG 2 — HISTORISKT NASDAQ-UNIVERSUM

Befintlig Nasdaq-data normaliserad, inget parallellt universum byggt.
Utdata: `research_k/nasdaq_historical_master/canonical_universe/canonical_pit_universe.json`.

| | |
|---|---|
| Källa | 73 958 rader, 763 instrument, 2009-08 → 2026-07 |
| Main Market | 707 instrument (Large / Mid / Small Cap) |
| Övriga, separat hållna | NOKS 48 (Oslo-noterade sekundärlistningar), XLFC 4 (utländska korslistningar), SPAC 4 |
| Segmentintervall | 1 163 |
| Segmentövergångar | **366** — 362 interna, 4 externa |
| Riktningar | Small→Mid 114, Mid→Large 113, Mid→Small 86, Large→Mid 49 |
| Listningar observerade | 445 |
| Avnoteringar observerade | 347 |
| ISIN-byten | 160 instrument |
| Namnbyten | 76 instrument |
| Instrument med lucka mitt i serien | 4 |
| Månader med saknat segment | 12 (2009-08…2010-01 med ~91 % täckning, plus 2020-03, 2021-03 m.fl.) |
| **Leakage-test** | **0 rader med `known_from ≤ report_month`** |

Ingen dagens klassificering har backfillats. Segment gäller från den rapportmånad
det observerades, känt från Nasdaqs faktiska `release_time`.

---

## STEG 3 — LEGACY/V2 PRISPARITET

Legacy och v2 är **olika leverantör och olika justeringsmodell**. Legacy läser
Börsdata rå OHLCV utan `adjusted_close` och applicerar split + utdelning vid
inläsning; v2 läser EODHD med förberäknad `adjusted_close`.

Ekvivalens prövas därför på **dagsavkastning**, inte prisnivå — en konstant kvot
är en justeringskonvention och påverkar inte momentum. Den första körningen på
prisnivå gav 65 "materiella" avvikelser; på avkastning återstår 8. ABB och SAND
har konstant kvot 0,9651 respektive 0,9517 under en tidig period och **1 av 1 648
avkastningsdagar** som skiljer — en konvention, inte en datadifferens.

| Klass | Antal |
|---|---|
| FORMAT_ONLY | 210 |
| EXPLAINED_TRANSFORMATION | 82 |
| IDENTICAL_VALUE | 1 |
| **MATERIAL_DATA_DIFFERENCE** | **8** |
| UNKNOWN | 30 |
| NO_LEGACY_SOURCE | 89 |

De åtta: LUMI (75,9 % av dagarna avviker >1 pp), FLERIE (67,9 %), G2M (48,5 %),
CARA (28,4 %), IMMNOV (13,1 %), BESQAB (7,9 %), WTW-A (5,1 %), SMCRT (2,4 %).

`data_loader.py` rad 195–196 noterar själv: *"Corporate actions utöver vanliga
splitar (avknoppning, inlösen, emission) finns inte alltid i Börsdatas splitlista."*
Det är samma defektklass som de åtta EODHD-brotten, hos den andra leverantören.

**Legacy-lagret är oförändrat:** 0 filer i `cache/borsdata` rörda sedan 2026-08-07.

---

## STEG 4 — CONFIG/DATA_LOADER-BEROENDEN

Statisk spårning: testskript → importstängning (median 7 moduler) → `config`-konstanter
och `data_loader`-anrop → konkreta datakomponenter. Ingen dry-run behövdes; ingen
alpha-, backtest- eller resultatberäkning kördes.

`data_loader.py` har 12 toppnivåfunktioner. Ingångspunkterna som binder data är
`fetch_weekly_data` (priser), `load_sweden_universe` / `build_universe_df` (universum),
`_fetch_avanza_weekly`, `load_ngm_universe`, `filter_liquid_universe`, `filter_active_universe`.

**471 av 487 legacy-skript upplösta** (96,7 %). 394 konsumerar
`PRICES_LEGACY_BORSDATA`, 435 `UNIVERSE_LEGACY_CSV`, 361 Börsdatas split- och
utdelningskällor, 28 MFN, 8 KPI.

Avgörande fynd: **0 legacy-skript läser v2-data** (grep-verifierat), och legacy-lagret
är oförändrat sedan 2026-08-07. Det ger positiv evidens för att ingen v2-reparation
kan nå dem — grunden för klassen `LEGACY_LINEAGE_ISOLATED`.

---

## STEG 5 — DC4 SEPARERAD

DC4 fick tidigare driva DIRECTLY_AFFECTED. Det var fel: ingen kanonisk indata har
ändrats. Fyra fält skiljer nu strikt:

| Fält | Innebörd |
|---|---|
| `actual_changed_input` | indata som **faktiskt** ändrats (DC1, DC5, DC6, DC8, DC9) |
| `structural_input_change` | universum/baslinje (DC3, DC7) |
| `known_defect_exposure` | känd men **oåtgärdad** defekt (DC4) |
| `priority_driver_only` | höjer prioritet, ändrar aldrig klass (DC4, DC10, DC2) |

**131 tester** är exponerade för DC4. Samtliga står som POSSIBLY_AFFECTED, inte
DIRECTLY_AFFECTED. DC4 blir en verklig dataförändring först när en **giltig** rättelse
tillämpats — vilket B1 hindrar.

Den tidigare formuleringen "DIRECTLY_AFFECTED via DC3+DC4+DC7+DC9" blandade ihop
statushöjande och prioritetshöjande orsaker. Topplistan nedan anger nu vilken enskild
förändring som ger DIRECTLY-status, skild från vad som höjer poängen.

---

## STEG 6 — FREEZE: EJ FÖRSEGLAD

`research_inventory/REVALIDATION_DATA_FREEZE_MANIFEST.json` är skriven med samtliga
15 komponenter (canonical path, SHA256, radantal, datum- och instrumenttäckning,
provenance, kända begränsningar), men bär `status: BLOCKED_NOT_SEALED`. Ingen
prisversion kan förseglas som kanonisk medan B1 står öppen.

| Integritetsgrind | Utfall |
|---|---|
| hash match | KÖRD — alla komponenter hashade |
| deterministic rebuild | **PASS** — 581 051 reproducerat exakt |
| no future membership leakage | **PASS** — 0 rader |
| no future report leakage | EJ KÖRD — kräver bolagsrapportdatum |
| no survivorship-only universe | **PASS** — 347 avnoteringar, 694 delisted i arkivet |
| no unresolved adjustment breach | **FAIL** — 8 av 8 kvarstår |
| stable identity mapping | VILLKORAT — 160 ISIN-byten, 76 namnbyten, kedjor dokumenterade |

---

## STEG 7 — CANDIDATE MAP OMRÄKNAD

| Klass | Före | Efter | Δ |
|---|---|---|---|
| UNAFFECTED | 70 | **412** | +342 |
| DIRECTLY_AFFECTED | 198 | **213** | +15 |
| STRUCTURALLY_AFFECTED | 86 | **83** | −3 |
| POSSIBLY_AFFECTED | 401 | **89** | −312 |
| UNKNOWN | 48 | **6** | −42 |

| Prioritet | Före | Efter |
|---|---|---|
| P0 | 60 | 60 |
| P1 | 118 | 58 |
| P2 | 230 | 144 |
| P3 | 325 | 129 |

- **312 av 401 POSSIBLY_AFFECTED lösta (78 %)** — 270 till UNAFFECTED, 42 till DIRECTLY_AFFECTED.
- UNAFFECTED per skäl: `LEGACY_LINEAGE_ISOLATED` 351, `NO_RESEARCH_CONCLUSION` 48, `BUILT_ON_NEW_DATA` 13.
- Härkomst: 471 LEGACY_BORSDATA, 316 V2_VALIDATED, 16 LEGACY_UNRESOLVED.
- **Legacy-tester som påverkas av verkliga prisavvikelser:** 8 instrument av 331 jämförbara (2,4 %). Vilka tester som höll dem kan inte fastställas utan att köra dem.
- **Tester som påverkas av en faktiskt tillämpad DC4-rättelse:** **0** — rättelsen är inte tillämpad, och den version som finns är ogiltig. 131 är exponerade för defekten.

**Viktigt förbehåll:** UNAFFECTED via `LEGACY_LINEAGE_ISOLATED` betyder "ingen
registrerad förändring når testet" — inte "datan är validerad". Legacy-linjen bär
sina egna 8 materiella divergenser och en dokumenterad lucka för avknoppning,
inlösen och emission. Fältet `legacy_data_quality_caveat` bär detta per rad.

### Ny topp 50

| # | Poäng | Familj | Test | Klass | Orsak till klass | Kostnad | Prov. |
|---|---|---|---|---|---|---|---|
| 1 | 120 | SECTOR | `test_healthcare_ablation` | DIRECTLY | DC5 | LOW | P3 |
| 2 | 116 | DRAWDOWN_EXIT | `h0_core_meta_exit` | DIRECTLY | DC9 | MEDIUM | P3 |
| 3 | 116 | DRAWDOWN_EXIT | `h0_exit_interaction_explorer` | DIRECTLY | DC9 | MEDIUM | P3 |
| 4 | 116 | DRAWDOWN_EXIT | `h0_exit_model_time_split` | DIRECTLY | DC9 | MEDIUM | P3 |
| 5 | 116 | DRAWDOWN_EXIT | `h0_exit_pattern_explorer` | DIRECTLY | DC9 | MEDIUM | P3 |
| 6 | 116 | DRAWDOWN_EXIT | `h0_lgbm_consensus_exit` | DIRECTLY | DC9 | MEDIUM | P3 |
| 7 | 116 | DRAWDOWN_EXIT | `h0_temporary_exit_guard` | DIRECTLY | DC9 | MEDIUM | P3 |
| 8 | 116 | SIZE_SEGMENT | `k1_material_validation` | DIRECTLY | DC5 | LOW | P4 |
| 9 | 114 | EVENT_PEAD | `fi_blankning_signal` | DIRECTLY | DC9 | LOW | P3 |
| 10 | 114 | EVENT_PEAD | `tidig_detektion_och_utdelning` | DIRECTLY | DC9 | LOW | P3 |
| 11 | 114 | INDEX_MEMBERSHIP | `h1419_steg2_universum` | DIRECTLY | DC9 | LOW | P3 |
| 12 | 113 | DRAWDOWN_EXIT | `g13_g17_premature_exit_audit` | DIRECTLY | DC9 | LOW | P3 |
| 13 | 113 | RANKING | `spar_c_features_fundamenta` | DIRECTLY | DC1,DC9 | LOW | P3 |
| 14 | 113 | VOLATILITY_RISK | `g97p_confounder_audit` | DIRECTLY | DC9 | LOW | P3 |
| 15 | 112 | RANKING | `spar_c_target` | DIRECTLY | DC9 | LOW | P3 |
| 16 | 112 | SECTOR | `spark_k1_sector_information_diversification` | DIRECTLY | DC5 | LOW | P3 |
| 17 | 112 | VOLATILITY_RISK | `g97p_hogvolsvans` | STRUCTURALLY | DC3,DC7 | LOW | P4 |
| 18 | 110 | BREADTH_DISPERSION | `dispersion_och_ensemble` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 19 | 110 | CHAMPION_CHALLENGER | `h0_validator_model_race_1419` | DIRECTLY | DC9 | MEDIUM | P3 |
| 20 | 110 | COMBINATION_STACK | `spari_batch2` | DIRECTLY | DC9 | LOW | P5 |
| 21 | 110 | FUNDAMENTAL | `g129_asset_growth` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 22 | 110 | FUNDAMENTAL | `lonsamhetstilt_mot_stack_h` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 23 | 110 | H0_BASELINE | `h0_extratrees_topn_1419` | DIRECTLY | DC9 | MEDIUM | P3 |
| 24 | 110 | MOMENTUM_LOOKBACK | `kortare_lookback` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 25 | 110 | MOMENTUM_LOOKBACK | `momentumkurvan` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 26 | 110 | REENTRY | `h0_reentry_score_improvement` | DIRECTLY | DC9 | MEDIUM | P3 |
| 27 | 109 | FUNDAMENTAL | `h0_extratrees_broad_pool_top30_audit` | DIRECTLY | DC9 | MEDIUM | P3 |
| 28 | 109 | FUNDAMENTAL | `h0_extratrees_top20_portfolio_value_audit` | DIRECTLY | DC9 | MEDIUM | P3 |
| 29 | 109 | FUNDAMENTAL | `spark_k5_k3_diagnostics` | DIRECTLY | DC9 | LOW | P5 |
| 30 | 108 | FORWARD_HOLDOUT | `sparh_forward` | DIRECTLY | DC1 | LOW | P4 |
| 31 | 107 | DATA_QA_PROVENANCE | `build_research_provenance_archive` | DIRECTLY | DC5,DC6,DC9 | LOW | P3 |
| 32 | 107 | INDEX_MEMBERSHIP | `h1419_universum_v2` | DIRECTLY | DC9 | LOW | P4 |
| 33 | 106 | DRAWDOWN_EXIT | `g_het_1_analysis` | DIRECTLY | DC5,DC6 | LOW | P3 |
| 34 | 106 | FUNDAMENTAL | `lonsamhet_poangfaktor_och_kvot` | STRUCTURALLY | DC3,DC7 | MEDIUM | P3 |
| 35 | 106 | ROBUSTNESS_ABLATION | `spark_h0_historical_time_stability` | DIRECTLY | DC9 | LOW | P3 |
| 36 | 106 | VOLATILITY_RISK | `h_archetype_1_tail_distribution` | DIRECTLY | DC5 | LOW | P3 |
| 37 | 104 | CANDIDATE_FILTER | `skarpare_ranking` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 38 | 104 | COMBINATION_STACK | `h1_contrarian_exposure` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 39 | 104 | COMBINATION_STACK | `stack_h_repaired_h012` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 40 | 104 | EVENT_PEAD | `pead_eget_spar` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 41 | 104 | H0_BASELINE | `h0_h1_h2_tvafonster` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 42 | 104 | H0_BASELINE | `h1419_forregistrering` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 43 | 104 | INDEX_MEMBERSHIP | `g186k_enb_kalibrering` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 44 | 104 | LIQUIDITY_EXECUTION | `g216_execution_decay` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 45 | 104 | PATH_STATE_MEMORY | `g101_regimberoende` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 46 | 104 | PATH_STATE_MEMORY | `g67_g74_banans_form` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 47 | 104 | PATH_STATE_MEMORY | `g_path_1_time_in_state` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 48 | 104 | PATH_STATE_MEMORY | `mem_r_recovery_memory` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 49 | 104 | PATH_STATE_MEMORY | `state_path_feasibility` | STRUCTURALLY | DC3,DC7 | LOW | P3 |
| 50 | 104 | PORTFOLIO_WEIGHT | `a3_poangutjamning` | STRUCTURALLY | DC3,DC7 | LOW | P3 |

---

## BLOCKERARE

**B1 — R4 åtgärdar inte justeringsbrotten.** Alla 8 överlever behandlingen; 5 av 8
blir starkare. Defekten är en permanent faktorändring och kan inte tas bort genom
att utesluta dagar. Måste lösas med omskalning, seriedelning (R8) eller trunkering
innan någon prisversion kan förseglas.

**B2 — 4 av 8 brott saknar verifierad orsak.** BEIJ-B, PNDX-B, SSAB-A och VBG-B har
ingen corporate action inom ±15 dagar i Skatteverkets register. Utan känd orsak kan
rätt behandling inte väljas per fall.

**B3 — 8 legacy-instrument avviker materiellt mot v2.** LUMI, FLERIE, G2M, CARA,
IMMNOV, BESQAB, WTW-A, SMCRT. IMMNOV har en dagsavkastningsskillnad på 96,3 —
minst en av linjerna har ett rent datafel som inte är identifierat.

**B4 — 89 v2-instrument saknar legacy-motsvarighet och 30 är oklassificerade.**
Paritet mellan linjerna är därmed fastställd för 302 av 420 instrument (72 %).

**B5 — `no_future_report_leakage` är inte körd.** Kräver bolagsrapportdatum, som
inte ingår i Nasdaq-serien. Fundamentakomponenterna kan inte läckagetestas.

**B6 — 16 legacy-skript förblir olösta** och 6 tester står som UNKNOWN.

**B7 — Identitetsmappningen är inte stabil.** 160 instrument byter ISIN och 76 byter
namn. Kedjorna är dokumenterade men ingen kanonisk identitetsupplösning är beslutad.

---

## LEVERANSER

`validated/prices_v2_0/` — kandidatlager (ej antaget), `diff_v1_0_to_v2_0.json`,
`PRICES_V2_0_MANIFEST.json`, `STEG1_VERIFIERING.json`
`research_k/nasdaq_historical_master/canonical_universe/canonical_pit_universe.json`
`research_inventory/legacy_v2_price_parity.json`
`research_inventory/revalidation_candidate_map_v2.json` — 803 rader × 32 fält
`research_inventory/REVALIDATION_DATA_FREEZE_MANIFEST.json` — BLOCKED_NOT_SEALED
