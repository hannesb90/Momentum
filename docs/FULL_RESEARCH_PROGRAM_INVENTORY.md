# FULLSTÄNDIG INVENTERING AV MOMENTUM-PROJEKTETS FORSKNINGSHISTORIK

Datum: 2026-08-18 · Status: **INVENTERING KOMPLETT — INGA TESTER KÖRDA**

Detta dokument är en neutral karta över vad som faktiskt har gjorts. Det innehåller
**ingen** revalideringsbedömning: ingen post är markerad "bör köras om", "bör öppnas"
eller "lovande igen". Inga domar har skrivits om, inga frysningar rörts, inga modeller
ändrade.

---

## TOTALSIFFROR

| | |
|---|---|
| TOTAL UNIQUE TESTS | **803** |
| TOTAL TEST FAMILIES | **29** |
| COMPUTED | **717** (resultatartefakt lokaliserad) |
| NOT COMPUTED | **86** |
| PREREGISTERED | **89** tester knutna till preregistreringsfil (114 preregfiler i repot) |
| REPRODUCIBLE P4/P5 | **41** (24 P4 + 17 P5) |
| NEGATIVE | 29 |
| POSITIVE | 13 |
| MIXED | 3 |
| BLOCKED | 5 |
| SUPERSEDED | 2 + 18 superseded-varianter |
| UNKNOWN | **751** dom ej maskinläsbar |

| | |
|---|---|
| TESTS USING OLD MEMBERSHIP | **802 av 803** — endast `h0_v3_kor.py` refererar H0 V3 |
| TESTS USING STATIC SECTOR | **299** |
| TESTS USING NON-PIT SIZE | **73** |
| TESTS USING OLD BASELINES | **319** verifierat; **483** har ingen baslinjereferens i koden alls (UNKNOWN) |
| TESTS WITH UNRESOLVED PROVENANCE | **762** under P4 (86 P1 + 138 P2 + 538 P3) |

Övriga verifierbara metadata: `uses_fundamental_data` 222 · `uses_liquidity_proxy` 326 ·
`uses_h0_topN` 190 · `uses_terminal_ex_post` 78 · tvåfönster 103 · resampling/placebo 80.

---

## SÖKOMFATTNING

| Träd | Storlek | .py | .md | .json | .csv | Git |
|---|---|---|---|---|---|---|
| `momentum_v2` | 3,7 GB | 324 | 138 | 7 434 | 1 487 | **ingen** |
| `momentum_prod_work` | 6,7 GB | 646 | 74 | 17 892 | 530 | 793 commits, 2026-06-25 → 2026-08-07 |
| `momentum_exports_2026-08-02` | 298 MB | 383 | 24 | 274 | 242 | spegel |
| `/opt/momentum` | 5,4 GB | 0 | 0 | 0 | 0 | endast venv |

Artefaktindex: **31 344 filer / 24 773 unika basnamn**. Frysfiler indexerade: 45.
Preregistreringsfiler: 114. Markdowndokument analyserade: 212.

`momentum_exports_2026-08-02` är till **97,7 %** hash-identisk med `momentum_prod_work`
(374 av 383 py-filer). De nio avvikande är äldre versioner av infrastrukturmoduler, inga
testskript. Trädet räknas därför som spegel, inte som egna tester.

---

## FYND 1 — `momentum_v2` saknar versionshantering helt

`git rev-parse` i `momentum_v2` ger *not a git repository*. `/home/hannesb/.git` finns men
har **0 commits** och **0 spårade filer**. Det frysta legacy-trädet har 793 commits;
det aktiva forskningsträdet har ingen historik alls.

Konsekvens för denna inventering: kronologin är **git-verifierad för 222 tester** och
**mtime-inferrerad för 581**. Mtime är inte auktoritativ — den kan ändras utan att
innehållet gör det. All datering i ledgern bär fältet `date_basis` med exakt vilket
underlag som gäller.

---

## FYND 2 — provenance-arkivet verifierar ingenting

`tools/build_research_provenance_archive.py` beskriver sig i sin egen docstring som
*"Verifies provenance chains (Input -> Script -> JSON -> Report -> Ledger)"*.

Den definierar `sha256_file()` — och **anropar den aldrig**. Samtliga 17 `test_id`-poster
är typade dict-literaler, och var och en sätter `"reproducible": True` och
`"provenance_status": "FULL_PROVENANCE_VERIFIED"` som konstant, inte som utfall.

Posterna bär de fyra tal som senare förbjudits som bevis: `small_cap_downside_2026: 0.417`,
`m3_directional_acc_2026: 0.613`, `m3_oos_r2_2026: 0.0365`, `downside_crash_avoidance_rate: 0.712`.

Skriptet **genererar** åtta av projektets styrdokument: `research_registry.json`,
`data_governance_registry.json`, `RESEARCH_INDEX.md`, `DATA_GOVERNANCE_REGISTRY.md`,
`FREEZE_REGISTRY.md`, `RESEARCH_HISTORY.md`, `INVALIDATED_AND_SUPERSEDED_RESULTS.md`,
`CURRENT_RESEARCH_STATE.md` och `AGENTS_RESEARCH_HANDOFF.md`.

**Nuvarande kontaminering: ingen.** Strängen `FULL_PROVENANCE_VERIFIED` förekommer 0 gånger
i de genererade filerna — governance-rekonciliationen har skrivit över dem. Risken är
latent: en omkörning återinför påståendena.

### Övriga hårdkodade resultat

| Fil | Rader | Karaktär | Redan känt |
|---|---|---|---|
| `tools/g_hier_1_analysis.py` | 166, 182, 198 | resultatvärden som dict-literaler | ja — `NON_COMPUTED_CLAIM` |
| `tools/g_hier_2_analysis.py` | 119–216 (10 st) | samma | ja — `NON_COMPUTED_CLAIM` |
| `tools/register_h1_h2_observation_journal.py` | 30, 59 | **transkriberade** från `spari_forward_challengers.py` | nej, lägre grad |
| `tools/freeze_spari_forward_challengers.py` | 9 | transkriberade i frysspecifikationen | nej, lägre grad |

Sex ytterligare regexträffar granskades manuellt och är **godartade**: fyra är
toleransdiktionär för paritetskontroller (`{'CAGR':1e-6,...}`), två är identitetssentinels
för självjämförelse (`overlap_top30_mean: 30.0` när armen jämförs med sig själv).

---

## FYND 3 — legacy-registret läste aldrig ett enda resultat

`research_i/legacy_hypothesis_registry.json` inventerade 420 legacy-skript. Dess egen
policytext lyder:

> *"Source names/code are hypothesis generators only. No legacy result file was read by this inventory."*

Registret säger alltså ingenting om huruvida legacy-testerna kördes, vad de gav, eller
deras provenance. Det klassificerar namn, inte resultat. 229 av 420 avfärdades som
"EJ RELEVANT FÖR NY ARKITEKTUR" utan att resultatet lästes.

Täckningen var dessutom bara `momentum_ml/*.py` på toppnivå. **88 skript** i
`momentum_ml/{altdata, researchdb, backtest, models}` och i `results/*_module_snapshots/`
ligger helt utanför registret. Merparten är biblioteksmoduler, men minst sex är
forskningsnära: `dosrespons.py`, `diag_lgbm_degen.py`, `diag_modellalder.py`,
`threshold_opt.py`, `tackning48_extrem.py`, `fund_ab_overlap.py`.

---

## FYND 4 — domen per test är i allmänhet inte återställbar

Endast **59 av 803** tester har en maskinläsbar dom i sin resultatartefakt. För 751 finns
domen bara i prosan i markdownrapporterna eller i två familjeregister
(`FINAL_RESEARCH_INVENTORY_AFTER_K1_K3_K5.json` med 43 familjedomar,
`research_registry.json` med 16 spårstatusar).

Det betyder att forskningsprogrammets domar är **familjenivåfakta, inte testnivåfakta**.
Ledgern registrerar detta som `UNKNOWN_NOT_MACHINE_READABLE` i stället för att gissa.

---

## FYND 5 — beroendegrafen är gles av en systematisk orsak

163 beroendekanter (162 VERIFIED, 1 INFERRED). **688 av 803 skript (86 %) har ingen
maskinläsbar beroendekant alls.**

Orsaken är strukturell: de flesta skript refererar sin baslinje via en hårdkodad
katalogkonstant (`G = R/'sparg/results/SPARG_V4_...'`) i stället för att läsa en namngiven
producentartefakt. Deras beroende är därför **UNKNOWN**, inte frånvarande.

En första körning som räknade delade datalager gav 40 376 kanter — nästan alla via
gemensam prisdata. Grafen i leveransen exkluderar `validated/`, `panels/`, `raw/`, `cache/`
och artefakter med fler än två producenter.

Mest använda som indata till andra tester: `analyze_temporal_factor_niva3_stage15` (9),
`remediate_factor_regression_niva3_stage16` (8), `run_reference_model_lock_stage126` (6),
`spar_c_qa` (5), `spar_c_target` (5).

---

## PROVENANCE-FÖRDELNING

| Grad | Antal | Innebörd |
|---|---|---|
| P0 | 14 dokument | endast textpåstående, ingen kodkoppling, med numeriska påståenden |
| P1 | 86 | skript finns, ingen resultatartefakt lokaliserad |
| P2 | 138 | skript + resultat |
| P3 | **538** | skript + resultat + identifierade indata |
| P4 | 24 | + verifierbar fryskedja |
| P5 | 17 | + preregistrering |

**39 skripthashar** återfinns faktiskt i en frysfil. Det är den hårt verifierade delmängden.

Dokumentens kodkoppling (212 markdown): 76 skrivs av ett skript, 67 namnmatchar ett skript,
26 citerar skript, 8 namnmatchar artefakt, 5 citerar artefakt, **30 saknar koppling** —
varav 16 är rena planer/policy utan siffror.

Största P0-dokumenten: `prod:docs/MOMENTUM_ROTATION_TESTPLAN.md` (127 numeriska påståenden),
`DATATACKNING_48FEATURES_2026-08-07.md` (65), `LUCKFYLLNING_FUNDAMENTA_2026-08-07.md` (60),
`EDGE_RISK_SCENARIO_TESTKO.md` (25).

---

## KLASSIFICERING TEST MOT IDÉ

| Klass | Antal |
|---|---|
| A — faktiskt beräknat test | 503 |
| B — diagnostiskt test | 196 |
| C — preregistrerat men aldrig kört | 7 |
| D — byggt, ingen artefakt lokaliserad | 73 |
| E — data-blockerat | 3 |
| F — avbrutet | 3 |
| G — superseded variant | 18 |
| H — endast dokumenterat påstående | 14 dokument (utanför skriptledgern) |

De sju preregistrerade-men-ej-körda är `pead`, `tune_pead`, `tune_attention_gap`,
`tune_insider_gap`, `tune_riskadj_momentum_ablation`, `report_gap_oos_audit` och
`test_sparj_j1b`. De fem första är legacy-skript som namngavs som hypotesgeneratorer i
`research_i/batch1_preregistration.json` — de kördes aldrig i v2, vilket är förenligt med
familjedomen DATABLOCKERAD för händelsespåret.

---

## SPÅREN I KRONOLOGISK ORDNING

| Period | Tester | Underlag | Spår |
|---|---|---|---|
| 2026-06-25 → 2026-08-18 | 240 | git 87 | ÖVRIGT / tvärgående |
| 2026-06-27 → 2026-08-07 | 202 | git 131 | LEGACY_PROD (`tune_*`, `run_*`, `diag_*`) |
| 2026-07-01 → 2026-08-18 | 4 | git 1 | NASDAQ_PIT |
| 2026-07-25 → 2026-08-03 | 53 | git 3 | SMALL / N3S |
| 2026-08-01 | 1 | mtime | NIVÅ 2 |
| 2026-08-01 → 2026-08-04 | 109 | mtime | NIVÅ 3 stages |
| 2026-08-08 | 7 / 1 / 2 | mtime | spår C / D / E |
| 2026-08-09 | 1 / 2 / 16 / 25 / 13 | mtime | spår F / H-forward / I / J / K1–K5 |
| 2026-08-09 → 2026-08-10 | 22 + 20 | mtime | RESEARCH_L–Z, RESEARCH_AA–AJ |
| 2026-08-13 → 2026-08-18 | 6 | mtime | K7–K11 |
| 2026-08-15 | 5 | mtime | TOPP5 |
| 2026-08-15 → 2026-08-18 | 47 | mtime | H-serien (H0/H1419/STACK_H) |
| 2026-08-16 | 4 | mtime | A1–A4 |
| 2026-08-17 → 2026-08-18 | 22 | mtime | G-serien |

---

## TESTFAMILJERNA

Familjedomarna nedan är **citat** ur `FINAL_RESEARCH_INVENTORY_AFTER_K1_K3_K5.json` och
`research_registry.json`. Ingen har ändrats. Familjer utan registrerad dom står som UNKNOWN.

| Familj | n | Registrerad familjedom |
|---|---|---|
| DATA_QA_PROVENANCE | 139 | UNKNOWN — ingen registrerad familjedom |
| SIZE_SEGMENT | 74 | G-SIZE-HET-1 NOT_IDENTIFIED; Size-Conditional Reclassification INVALID |
| FUNDAMENTAL | 61 | INGET STÖD (ROA/profitability, fundamental change, K7); K8/K9 SVAGT STÖD; KPI FORBIDDEN |
| COMBINATION_STACK | 44 | STACK_H: 45 varianter, inget ska adderas |
| PORTFOLIO_WEIGHT | 42 | portföljstorlek/koncentration N=10–30 INGET STÖD; inverse/target-vol INGET STÖD |
| DRAWDOWN_EXIT | 40 | DD20/milstolpe/re-entry-block INGET STÖD; time stop SVAGT STÖD |
| EVENT_PEAD | 39 | DATABLOCKERAD |
| ROBUSTNESS_ABLATION | 37 | UNKNOWN |
| RANKING | 36 | rankivå/rankförändring INGET STÖD; snittrank LOVANDE EJ BELAGT; ML på CORE INGET STÖD |
| LIQUIDITY_EXECUTION | 33 | genomfarter signifikant värdeförstörande i båda fönstren |
| H0_BASELINE | 27 | H0_CORE FROZEN (membership-kontaminerad); H0 V3 FROZEN PIT-korrekt baslinje |
| PATH_STATE_MEMORY | 24 | G-PATH-1/2, H-ORIGIN-1, G-PROP-1 CLOSED; G-HET-1 NOT_IDENTIFIED; G-HIER-1/2 NON_COMPUTED_CLAIM |
| SWAP_REPLACEMENT | 23 | rank exit/streak ERSATT/DUPLICERAD; correlation refill 0.85 INGET STÖD |
| TERMINAL_DELISTING | 23 | survivorship-bias NEGATIV (−2,26 pp); `terminal_events` förbjudet ex ante |
| CANDIDATE_FILTER | 20 | UNKNOWN |
| INDEX_MEMBERSHIP | 20 | UNKNOWN |
| TAX_CASHFLOW | 19 | UNKNOWN |
| FORWARD_HOLDOUT | 16 | UNKNOWN |
| VOLATILITY_RISK | 14 | G97-P COMPUTED_BUT_NOT_VALIDATED_CANDIDATE; ATR/ADX SVAGT STÖD |
| MOMENTUM_LOOKBACK | 12 | 12m/18m FORWARD-ONLY; residual momentum SVAGT STÖD |
| REBALANCE_TIMING | 12 | snabbare beslutsfrekvens INGET STÖD |
| CHAMPION_CHALLENGER | 11 | UNKNOWN |
| SECTOR | 11 | INGET STÖD (momentum/relative/breadth); tie-break FORWARD-ONLY |
| HOLD_HYSTERESIS | 7 | hysteres INGET STÖD; HYSTERES_RANK35 UNVERIFIED_DECISION_RULE |
| TREND_CONSISTENCY | 6 | trend strength FALSIFIERAD PÅ 66 PANELER; weekly consistency SVAGT STÖD |
| REENTRY | 6 | INGET STÖD — MOTBEVISAD RIKTNING |
| BREADTH_DISPERSION | 5 | dispersion proxy SVAGT STÖD |
| MACRO_REGIME | 1 | MACRO added to models INGET STÖD |
| CROSS_ASSET_LEADLAG | 1 | UNKNOWN — ingen registrerad dom |

---

## DUBLETTER OCH NAMNKONFLIKTER

Ingen sammanslagning har gjorts. 37 relationer registrerade på verifierbar grund
(`NAME_STEM_MATCH`): 23 `PARAMETER_VARIANT`, 14 `SAME_HYPOTHESIS`. Största namnstammarna:
`ko_mot_stack_h` (7 skript), `spari` (6), `build_additional_delisted_features` (4),
`freeze_spari` (3).

Detta undanröjer inte dubbletter på hypotesnivå — samma idé kan bära olika namn i legacy
och v2. Sådana relationer kan inte fastställas mekaniskt och står som `UNKNOWN_RELATION`.

---

## HISTORIEN ÄR OFÖRÄNDRAD

Ingen dom har skrivits om. Där ett senare problem är känt ligger det i separata fält
(`flags.uses_static_sector`, `flags.uses_non_pit_size`, `uses_old_membership`), aldrig som
omskrivning av `verdict_at_time`. Endast där en tidigare governanceaudit uttryckligen
fastställt INVALID — Size-Conditional Reclassification Audit — står INVALID, och det som
citat ur `research_registry.json`, inte som ny bedömning.

---

## LEVERANSER

`research_inventory/master_test_ledger.json` — 803 rader × 39 fält
`research_inventory/test_family_index.json` — 29 familjer
`research_inventory/dependency_graph.json` — 163 kanter, 688 isolerade noder, spårkronologi
`research_inventory/provenance_audit.json` — P0–P5, hårdkodade resultat, falska positiva
`research_inventory/unresolved_tests.json` — 86 olösta
