# MOMENTUM_V2 FREEZE REGISTRY (GOVERNANCE RECONCILED 2026-08-18)

Auktoritativt register över frysta systemkomponenter.
Maskinläsbar kedjedefinition: [`research_k/freeze_chains.json`](../research_k/freeze_chains.json)
Verifieras av [`tools/repo_integrity_gate.py`](../tools/repo_integrity_gate.py)

---

## FRYSNINGSSEMANTIK

En komponent får kallas **FROZEN** endast om hela kedjan verifierar:

```
PREREGISTRATION → INPUT MANIFEST → EXECUTABLE IMPLEMENTATION
  → RESULT ARTIFACT → DECISION → FREEZE/MANIFEST
```

**En hash av ett löst script är inte i sig en freeze.** Registret beskriver därför
vad som är fryst och vilken kedja som bevisar det — inte en filhash.

---

## AKTIV TABELL — verifierade frysta komponenter

### H0 CORE MOMENTUM ENGINE — `FROZEN`

| Kedjeled | Artefakt | Verifiering |
|---|---|---|
| **Preregistrering** | `research_k/h1419_exakt_h0_preregistration_v2.json` | sha `23cd3cde…7ee2b3` |
| **Frysning** | `research_k/H1419_PREREG_FREEZE_V2.json` | `LOCKED_BEFORE_ANY_RESULT`, `2026-08-15T20:03:55Z` — **hash MATCH** |
| **Input manifest** | 7 låsta indatafiler i `indata_last` | **samtliga 7 verifierade** |
| **Implementation** | `tools/h1419_kor_exakt_h0_v2.py` | självverifierar låset före körning |
| **Result artifact** | `research_k/h1419_exakt_h0_RESULTAT_V2.json` | refererar prereg-hash, `las_verifierat: true` |
| **Decision** | `dom: STÖD` | — |
| **Reproducerbarhet** | omkörd 2026-08-18 | **bitidentisk utom `run_utc`** |

**Kanonisk version: V2.** Avgjord ur artefakter, **inte** ur prestanda:

* V2:s `ersatter`-fält namnger V1 med dess sha256 och dokumenterar en **datadefekt**:
  V1:s universumfilter krävde Main Market-ISIN i *dagens* lista och uteslöt därmed
  **44 bolag** som låg på Main Market 2014-2019 men avnoterades 2020-2026, varav
  **38 med terminal-event**.
* `tools/h1419_motor.py` rad 19 läser `prices_h1419_universum_v2.json` och rad 5
  refererar `H1419_PREREG_FREEZE_V2` — motorn som **samtliga verifierade
  2014-2019-spår** använder beror på V2.
* Tidsordning: V2 låst 20:03:55Z efter V1 19:04:01Z.

**Verifierat resultat (2014-2019, 79 paneler, medelinnehav 27,5):**

```
H0:                CAGR 29,99 %   vol 15,00 %   MaxDD −14,63 %   Sharpe 1,850
likaviktat univ.:  CAGR 17,84 %
primärt utfall:    Δ +12,15 pp   KI [+4,25, +23,74]   t +3,27   DOM STÖD
```

**Hederlighetsklausul (från V2:s preregistrering):** V1:s resultat får aldrig
utelämnas när V2 rapporteras. V1 gav CAGR 27,39 %, MaxDD −12,09 %, Δ +8,62 pp.
Status `SUPERSEDED_BY_V2`.

**Känd begränsning, explicit deklarerad i artefakten:** V2:s
`created_before_any_return_computed` är `False` — preregistreringen skrevs efter
att V1:s avkastningar observerats. Detta är öppet redovisat, inte dolt, och
hanteras av hederlighetsklausulen.

### K1 SECTOR CLASSIFICATION — `VERIFIED_TAXONOMY`

| Kedjeled | Artefakt | Verifiering |
|---|---|---|
| **Manifest** | `research_k/sector_classification_v1/manifest.json` | `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041` — **MATCH** |
| **Output** | `sector_classification_v1/validated/sector_classification_intervals.json` | `valid_from`/`valid_to` per instrument |
| **Scope** | *"classification/provenance only; no target, IC, alpha or backtest"* | — |

**Tillåten användning:** endast populationsstratifiering, ingen poängtilt.
**Ej verifierat i denna audit:** att intervallrekonstruktionen är materiellt
riktig. Endast hash och scope är verifierade.

---

## KOMPONENTER SOM INTE ÄR FRYSTA

Dessa har flyttats ut ur den aktiva tabellen. De får **inte** citeras som frysta
eller verifierade resultat, inte användas som beroende för en fryst komponent,
och inte som evidens för en öppen forskningskandidat.

| Komponent | Status |
|---|---|
| Hysteres rank ≤ 35 | **`UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION`** |
| G97-P svansexkludering | **`COMPUTED_BUT_NOT_VALIDATED_CANDIDATE`** |

Ingen av statusarna är `CLOSED_NEGATIVE` eller `INVALID`, och ingen av dem är en
licens att köra om testet. Full motivering i `freeze_chains.json` och i
[`REPOSITORY_INTEGRITY_AND_FREEZE_RECONCILIATION_2026-08-18.md`](REPOSITORY_INTEGRITY_AND_FREEZE_RECONCILIATION_2026-08-18.md).

---

## AUDIT HISTORY

Historiska fel raderas aldrig. De bevaras här.

### Rättelse 1 — freeze-hashar utan källa

| | |
|---|---|
| **Previous claim** | Registret angav *"Endast komponenter med 100 % verifierad, reproducerbar beräkning"* och listade fyra komponenter med sha256 mot **skriptfiler**: H0 `e27863ef…4e7687`, hysteres `c94812a1…726581`, G97-P `74191a27…192039`, K1 `816cb6b3…523041`. |
| **Contradicting evidence** | Innehållsskanning av samtliga **10 435 filer** i repot: de tre förstnämnda hasharna motsvarar **ingen fil**. De är inte gamla hashar av redigerade filer. Faktiska skripthashar: `c94fd568…`, `fef90f15…`, `a8a96ab3…`. Endast K1 matchade. |
| **Correction date** | 2026-08-18 |
| **Resulting status** | Registret beskriver nu **kedjor**, inte skripthashar. H0 pekas mot preregistreringskedjan `H1419_PREREG_FREEZE_V2 → 23cd3cde…`, som verifierar. |

### Rättelse 2 — hysteres var aldrig fryst

| | |
|---|---|
| **Previous claim** | *"Hysteres Behållningsregel (rank ≤ 35)"*, `FROZEN_DECISION_RULE`, *"Behåller befintliga portföljinnehav upp till rank 35"*, *"Minskar omsättning med 38,5 %"*. |
| **Contradicting evidence** | `tools/hysteres_kop_och_agande.py` rad 25 är märkt `DIAGNOSTISKT`; artefaktens `status`-fält lyder *"DIAGNOSTISKT — ingen fryst fil ändrad, ingen försegling bruten, ingen challenger"*. Koden implementerar ingen fast gräns utan ett **rutnät** (`köpband [lo, hi]`, `ägandegräns H`, `portföljtak N`) med placebo på bästa cellen. Artefaktens bästa cell är **`N10_kop15-25_H30`** — inte rank ≤ 35 och inte N=30. Strängarna `38,5`, `38.5` och `0.385` förekommer inte i artefakten. `rank ≤ 35` är `hyst_rank=35`, standardvärdet i `stack_h_motor.py`, alltså **STACK_H:s** parameter. Komponenten saknas i `final_system_freeze_manifest.json`. Bästa cellens KI `[−9,52, +10,09]`, t 0,35, bästa av 23 celler. |
| **Correction date** | 2026-08-18 |
| **Resulting status** | `UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION` |

### Rättelse 3 — G97-P:s regel och utfall

| | |
|---|---|
| **Previous claim** | `FROZEN_RISK_RULE`, *"Exkluderar 97.5:e percentilen volatilitetssvans"*, *"Sänker MaxDD med +4,8 pp"*. |
| **Contradicting evidence** | `g97p_results.json` `regel`-fält: *"exkludera de sex hogsta vol_52w i topp-30, ersatt med rank 31-36"*; skriptet rad 47 `K = 6 # LÅST`, rad 3 *"6/30 = 20 %"*. Ingen 97,5-percentil förekommer i implementationen. MaxDD blev **sämre** i båda fönstren: −33,50 → −34,36 % och −19,73 → −20,08 %. Bootstrap-KI korsar noll i båda (`ki_lo −0,0236`; `[−0,0473, +0,0535]`, t 0,842). Skapad 2026-08-17, en vecka **efter** den förseglade forward-frysningen 2026-08-10, och saknas i dess manifest. |
| **Correction date** | 2026-08-18 |
| **Resulting status** | `COMPUTED_BUT_NOT_VALIDATED_CANDIDATE`. Verifierad regel: **K = 6, de sex högsta `vol_52w` inom Top-30 ersätts med rank 31–36.** |
