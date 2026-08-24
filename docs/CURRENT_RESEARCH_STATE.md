# MOMENTUM_V2 CURRENT RESEARCH STATE (GOVERNANCE RECONCILED 2026-08-18)

**Kör alltid `tools/repo_integrity_gate.py` först. FAIL CLOSED.**
Kedjedefinition: [`research_k/freeze_chains.json`](../research_k/freeze_chains.json)

---

## 1. VAD ÄR EMPIRISKT VALIDERAT OCH FRYST?

Endast två komponenter har verifierbar frysningskedja
(`PREREGISTRATION → INPUT MANIFEST → IMPLEMENTATION → RESULT → DECISION → FREEZE`).

### H0 Core Momentum Engine — `FROZEN`
12m/18m relativ trendrankning på universumsnivå.
**Kanonisk version V2** (`h1419_exakt_h0_preregistration_v2.json`, sha `23cd3cde…`).
Implementation `tools/h1419_kor_exakt_h0_v2.py`. Reproducerad bitidentiskt 2026-08-18.

| Fönster 2014-2019, 79 paneler, medelinnehav 27,5 | |
|---|---:|
| H0 CAGR | **29,99 %** |
| H0 vol / MaxDD / Sharpe | 15,00 % / **−14,63 %** / 1,850 |
| Likaviktat universum CAGR | 17,84 % |
| Primärt utfall | **Δ +12,15 pp**, KI [+4,25, +23,74], t +3,27, DOM STÖD |

**Hederlighetsklausul:** den ersatta V1-körningen får aldrig utelämnas — CAGR
27,39 %, MaxDD −12,09 %, Δ +8,62 pp, status `SUPERSEDED_BY_V2` (survivorship-defekt:
44 bolag saknades, varav 38 med terminal-event).

### K1 Sector Classification — `VERIFIED_TAXONOMY`
Manifest SHA256 `816cb6b38a2130728bd282e8352c74ccf119f374b8747717c0b0603fa5523041`,
hash verifierad. Scope: *classification/provenance only*. Endast populationsstratifiering.

---

## 2. KOMPONENTER SOM INTE ÄR FRYSTA

Får inte citeras som frysta eller verifierade, inte användas som beroende, inte
som evidens för en öppen kandidat. Ingen av dem är `CLOSED_NEGATIVE` eller
`INVALID`, och ingen är en licens att köras om.

* **Hysteres rank ≤ 35** — `UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION`.
  Artefakten är självdeklarerat diagnostisk, koden är ett rutnät, bästa cell är
  `N10_kop15-25_H30`, och `rank ≤ 35` är STACK_H:s parameter.
* **G97-P svansexkludering** — `COMPUTED_BUT_NOT_VALIDATED_CANDIDATE`.
  Verifierad regel: **K = 6, de sex högsta `vol_52w` inom Top-30 ersätts med rank
  31–36** (6/30 = 20 %, **inte** en 97,5-percentil). Bootstrap-KI korsar noll i
  båda fönstren och MaxDD blev sämre i båda.

---

## 3. VAD ÄR STÄNGT / NEGATIVT (VALIDATED NULLS)?

- **`tis` (G-PATH-1)**: redundant med H0-rank. Stängt.
- **`run_return` (G-PATH-2)**: redundant med H0-rank i poolad analys. Stängt.
- **`is_recovery` (H-ORIGIN-1)**: ingen oberoende alpha utöver H0. Stängt.
- **`propensity_eb` (G-PROP-1)**: kollineärt med TIS, Q5 negativ return. Stängt.

Återöppnas inte utan ny evidens.

---

## 4. OGILTIGFÖRKLARAT / NON-COMPUTED / NOT IDENTIFIED

- **G-HET-1 & G-SIZE-HET-1**: `NOT_IDENTIFIED` (odaterad 2026 `market_list`-snapshot
  och ex-post delistingstatus).
- **G-HIER-1 & G-HIER-2**: `NON_COMPUTED_CLAIM` (hårdkodade resultatdictar).
  **Passport är inte fryst.**
- **Reclassification Audit**: `INVALID`.

---

## 5. DATABLOCKERAT / FÖRBJUDET

- **`list_segment` / `market_list`**: `FORBIDDEN_IN_MODEL_TEST` — ingen PIT-historik.
- **Terminalstatus**: får aldrig användas ex ante.
- **Fundamenta KPI**: `FORBIDDEN_IN_MODEL_TEST`.
- **Market cap / EV**: `DATA_BLOCKED_GOVERNANCE`.

PIT-size-datauppdraget är separat och **ännu ej genomfört**. Gaten för det står i
`REPOSITORY_INTEGRITY_AND_FREEZE_RECONCILIATION_2026-08-18.md` avsnitt 6.

---

## 6. AKTUELLA ÖPPNA KANDIDATER

**0.** Ingen size- eller hierarkiforskning återöppnas. Projektet kräver först en
genuint PIT-korrekt historisk storleksklassificering och reproducerbara dynamiska
beräkningar.

---

## AUDIT HISTORY

| | |
|---|---|
| **Previous claim** | §1 angav *"H0 Core Momentum Engine … (CAGR 13,56 %, MaxDD −24,32 %). Fil `tools/h1419_kor_exakt_h0.py`"*. |
| **Contradicting evidence** | 13,56 % / −24,32 % står ordagrant i `tools/stack_h_motor.py` rad 17 som **SHADOW_INTEGRATED_STACK_H på 2020-2026** (ERC invvol^1,5 + FR-overlay + hysteres rank 35 + NTZ 0,005 + SMA200). Den angivna filen kör **2014-2019** och dess egen artefakt ger 27,39 % / −12,09 % (V1) respektive 29,99 % / −14,63 % (V2). Fel modell och fel fönster. |
| **Correction date** | 2026-08-18 |
| **Resulting status** | H0 redovisas nu med V2:s verifierade tal, bundna till artefakt och fönster. |

| | |
|---|---|
| **Previous claim** | §1 listade hysteres (*"minskar omsättning med 38,5 %"*) och G97-P (*"sänker MaxDD med +4,8 pp"*) som empiriskt validerade och frysta. |
| **Contradicting evidence** | Se `FREEZE_REGISTRY.md` rättelse 2 och 3. |
| **Correction date** | 2026-08-18 |
| **Resulting status** | `UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION` respektive `COMPUTED_BUT_NOT_VALIDATED_CANDIDATE`. |
