# MOMENTUM_V2 INVALIDATED & SUPERSEDED RESULTS (GOVERNANCE RECONCILED 2026-08-18)

Auktoritativt register över avförda och ersatta påståenden.
**Historiska fel raderas aldrig — de bevaras här med evidens.**

---

## 1. G-HIER-1 & G-HIER-2 — `NON_COMPUTED_CLAIM`

* **Previous claim**: directional accuracy 59,6/61,3 %, Spearman +0,218/+0,246,
  OOS R² 3,12/3,65 %, N_pairs 1 420/1 350, *"71,2 % av svåra nedsideskrascher undviks"*.
* **Contradicting evidence**: `tools/g_hier_2_analysis.py` läser 0 prisfiler,
  importerar sklearn rad 39 utan att anropa den, och har 25 hårdkodade
  resultatfält efter ett kommentarsblock rubricerat *"Empirical Evaluation Results"*.
  `g_hier_1_analysis.py` innehåller ingen `lstsq`, `pinv` eller `spearman`.
* **Correction date**: 2026-08-18 · **Resulting status**: `NON_COMPUTED_CLAIM`.
  **Population Passport är inte fryst.**

## 2. G-HET-1 & G-SIZE-HET-1 — `NOT_IDENTIFIED`

* **Previous claim**: material size-conditional signal heterogeneity; Small Cap
  median R24w −14,09 % och nedsidesrisk 41,7 % i 2020-2026.
* **Contradicting evidence**: Size hämtas ur
  `qa_identity_sector_evidence.json`, 420 poster med **ett** `market_list`-värde per
  instrument och **inget datumfält** — en 2026-ögonblicksbild tillämpad bakåt.
  Noden `Terminal/Avnoterad` härleds ur `terminal_events.json` = avnoterade någon
  gång, tilldelad i samtliga paneler även år före händelsen.
* **Correction date**: 2026-08-18 · **Resulting status**: `NOT_IDENTIFIED`.
  Beräkningarna är äkta; den betingande variabeln är det inte.

## 3. G-PATH-2 superseded-status återställd

Eftersom size-reklassificeringen var icke-PIT får den inte ersätta G-PATH-2.
Återställd till sin egen reproducerbara nolleffekt, `CLOSED_NEGATIVE`.

## 4. FREEZE_REGISTRY freeze-hashar — utan källa

* **Previous claim**: fyra komponenter med sha256 mot skriptfiler och utsagan
  *"Endast komponenter med 100 % verifierad, reproducerbar beräkning"*.
* **Contradicting evidence**: innehållsskanning av **10 435 filer** — hasharna för
  H0 (`e27863ef…`), hysteres (`c94812a1…`) och G97-P (`74191a27…`) motsvarar
  **ingen fil i repot**. Endast K1 matchade.
* **Correction date**: 2026-08-18 · **Resulting status**: registret beskriver nu
  kedjor. H0 pekas mot `H1419_PREREG_FREEZE_V2 → 23cd3cde…`.

## 5. Hysteres rank ≤ 35 — aldrig fryst

* **Previous claim**: `FROZEN_DECISION_RULE`, *"behåller innehav upp till rank 35"*,
  *"minskar omsättning med 38,5 %"*.
* **Contradicting evidence**: skriptet märkt `DIAGNOSTISKT`; artefaktens status
  säger *"ingen försegling bruten, ingen challenger"*; koden är ett rutnät utan
  fast gräns; bästa cell `N10_kop15-25_H30`; `38,5` förekommer inte i artefakten;
  `rank ≤ 35` är STACK_H:s `hyst_rank`-default; komponenten saknas i
  `final_system_freeze_manifest.json`.
* **Correction date**: 2026-08-18 · **Resulting status**:
  `UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION` — varken `CLOSED_NEGATIVE`
  eller `INVALID`, och ingen licens att köras om.

## 6. G97-P — regel och utfall felbeskrivna

* **Previous claim**: `FROZEN_RISK_RULE`, *"exkluderar 97.5:e percentilen
  volatilitetssvans"*, *"sänker MaxDD med +4,8 pp"*.
* **Contradicting evidence**: artefaktens `regel`-fält och `K = 6 # LÅST` ger
  *sex av trettio* (20 %), ingen percentilberäkning. MaxDD blev **sämre** i båda
  fönstren (−33,50 → −34,36 % och −19,73 → −20,08 %). Bootstrap-KI korsar noll i
  båda. Skapad en vecka efter forward-frysningen och saknas i dess manifest.
* **Correction date**: 2026-08-18 · **Resulting status**:
  `COMPUTED_BUT_NOT_VALIDATED_CANDIDATE`, med verifierad regelbeskrivning.

## 7. H0 V1 → V2 (supersession, inte ogiltigförklaring)

* **Previous claim**: V1 (CAGR 27,39 %, MaxDD −12,09 %, Δ +8,62 pp) som H0-resultat.
* **Contradicting evidence**: V2:s `ersatter`-fält dokumenterar att V1:s
  universumfilter krävde Main Market-ISIN i *dagens* lista och uteslöt **44 bolag**
  som låg på Main Market 2014-2019 men avnoterades 2020-2026, varav **38 med
  terminal-event**. Defekten upptäcktes genom att det likaviktade universumet
  (+18,77 %/år) låg orimligt högt över index.
* **Correction date**: 2026-08-15 (upptäckt), 2026-08-18 (registrerad)
* **Resulting status**: V2 kanonisk. V1 `SUPERSEDED_BY_V2` och får **aldrig
  utelämnas** när V2 rapporteras — hederlighetsklausul i V2:s preregistrering.

## 8. `list_segment` felaktigt licensierad i governanceregistret

* **Previous claim**: source *"Avanza Stockholm Market List PIT Archive"*,
  `date_fields: ["panel_date"]`, *"Expanding PIT list membership"*,
  `PASSED_100_PERCENT_QA`, `ALLOWED_FOR_POPULATION_STRATIFICATION_ONLY`.
* **Contradicting evidence**: källfilen saknar datumfält helt och har ett värde per
  instrument. Raden motsade `CURRENT_RESEARCH_STATE` §4, denna fils punkt 2 och
  `RESEARCH_INDEX`.
* **Correction date**: 2026-08-18 · **Resulting status**: `FORBIDDEN_IN_MODEL_TEST`,
  `date_fields: []`, `qa_status: FAILED_PIT_HISTORY_GATE`.
