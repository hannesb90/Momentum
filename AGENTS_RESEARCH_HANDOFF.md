# AGENTS RESEARCH HANDOFF & OBLIGATORY PRE-FLIGHT PROTOCOL

Datum 2026-08-18 · **Obligatoriska instruktioner för alla AI-agenter**
Governance reconciled — se `docs/REPOSITORY_INTEGRITY_AND_FREEZE_RECONCILIATION_2026-08-18.md`

---

## STEG 0 — KÖR INTEGRITY GATE FÖRST (FAIL CLOSED)

```
/opt/momentum/venv/bin/python tools/repo_integrity_gate.py
```

Returkod 0 = PASS, 1 = FAIL eller internt fel. **En agent som får returkod ≠ 0,
eller som inte kan köra gaten, får inte påbörja forskning.** Maskinläsbart utfall:
`research_k/repo_integrity_gate_result.json`.

## STEG 1 — LÄS

1. `docs/CURRENT_RESEARCH_STATE.md`
2. `docs/RESEARCH_INDEX.md`
3. `docs/FREEZE_REGISTRY.md`
4. `docs/DATA_GOVERNANCE_REGISTRY.md`
5. `docs/INVALIDATED_AND_SUPERSEDED_RESULTS.md`

## STEG 2 — VERIFIERA PROVENANCE

Ett skript som returnerar hårdkodade värden får status `NON_COMPUTED_CLAIM`.
Ett skript som läser en odaterad snapshot som historisk variabel får
`NOT_IDENTIFIED`. Kontrollen kostar tre grep: **läser den data · anropar den en
skattare · finns hårdkodade resultatfält.**

---

## FRYSNINGSSEMANTIK

En komponent får kallas **FROZEN** endast om hela kedjan verifierar:

```
PREREGISTRATION → INPUT MANIFEST → EXECUTABLE IMPLEMENTATION
  → RESULT ARTIFACT → DECISION → FREEZE/MANIFEST
```

**En hash av ett löst script är inte i sig en freeze.** Maskinläsbar
kedjedefinition: `research_k/freeze_chains.json`.

### Frysta komponenter — endast två

| Komponent | Status | Bevis |
|---|---|---|
| **H0 Core Momentum Engine** (kanonisk **V2**) | `FROZEN` | prereg `23cd3cde…` + 7 verifierade indata + reproducerad bitidentiskt |
| **K1 Sector Classification** | `VERIFIED_TAXONOMY` | manifesthash `816cb6b3…` |

H0:s verifierade tal, 2014-2019: **CAGR 29,99 %, MaxDD −14,63 %, Δ +12,15 pp**.
Den ersatta V1-körningen (27,39 %, −12,09 %, Δ +8,62 pp) får aldrig utelämnas.

**13,56 % / −24,32 % tillhör STACK_H 2020-2026 och är inte H0-prestanda.**

### Ej frysta komponenter

| Komponent | Status |
|---|---|
| Hysteres rank ≤ 35 | `UNVERIFIED_DECISION_RULE_REQUIRES_REVALIDATION` |
| G97-P svansexkludering (K = 6) | `COMPUTED_BUT_NOT_VALIDATED_CANDIDATE` |

Får inte citeras som frysta eller verifierade, inte användas som beroende, inte
som evidens för en öppen kandidat. Ingen av dem är `CLOSED_NEGATIVE` eller
`INVALID`, och **ingen är en licens att köras om.**

G97-P:s verifierade regel: **K = 6, de sex högsta `vol_52w` inom Top-30 ersätts
med rank 31–36.** Beskrivningen *"97,5:e percentilen"* är felaktig och får inte
användas.

---

## PERMANENTA FÖRBUD

* `list_segment` / `market_list` — `FORBIDDEN_IN_MODEL_TEST`, ingen PIT-historik.
* Terminalstatus (`terminal_events`) får **aldrig** användas ex ante, endast i
  avkastningsberäkningens utfallshantering.
* Fundamenta-KPI — `FORBIDDEN_IN_MODEL_TEST`.
* Market cap / EV — `DATA_BLOCKED_GOVERNANCE`.
* Ingen size- eller hierarkiforskning återöppnas. PIT-size-datauppdraget är
  separat och ännu ej genomfört.
* Giltiga `CLOSED_NEGATIVE`-spår återöppnas inte utan ny evidens.

---

## AKTUELLT UTFALL

```
REPOSITORY INTEGRITY:      se gate-körning
OPEN RESEARCH CANDIDATES:  0
```
